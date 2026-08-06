import os
import json
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from flask import Flask, send_from_directory, jsonify, request
import psycopg
import openai
from databricks.sdk import WorkspaceClient

app = Flask(__name__, static_folder="dist", static_url_path="")

# ─── Lakebase connection ──────────────────────────────────────────────────────
ENDPOINT  = os.environ["LAKEBASE_ENDPOINT"]
DATABASE  = os.environ.get("LAKEBASE_DATABASE", "matchview")
PG_SCHEMA = os.environ.get("LAKEBASE_SCHEMA", "app")

def get_conn():
    """Fresh connection with auto-refreshed Databricks OAuth token."""
    w = WorkspaceClient()
    cred = w.postgres.generate_database_credential(endpoint=ENDPOINT)
    user = w.current_user.me().user_name
    ep = w.postgres.get_endpoint(name=ENDPOINT)
    host = ep.status.hosts.host
    return psycopg.connect(
        host=host, port=5432, dbname=DATABASE,
        user=user, password=cred.token, sslmode="require", autocommit=True,
    )

# ─── SMTP config (set these as Databricks App env vars / secrets) ────────────
SMTP_HOST = os.environ.get("SMTP_HOST")
SMTP_PORT = int(os.environ.get("SMTP_PORT", "587"))
SMTP_USER = os.environ.get("SMTP_USER")
SMTP_PASSWORD = os.environ.get("SMTP_PASSWORD")
SMTP_FROM_EMAIL = os.environ.get("SMTP_FROM_EMAIL", SMTP_USER)
SMTP_USE_TLS = os.environ.get("SMTP_USE_TLS", "true").lower() != "false"

# ─── Databricks Foundation Model API (FMAPI) — real LLM chat completion ──────
# Endpoint names must match what's registered in your workspace's serving
# endpoints / model catalog.
FMAPI_ENDPOINTS = [
    "databricks-claude-sonnet-4-6",
    "databricks-claude-haiku-4-5",
    "databricks-claude-opus-4-6",
]
FMAPI_DEFAULT_ENDPOINT = os.environ.get("FMAPI_DEFAULT_ENDPOINT", FMAPI_ENDPOINTS[0])

@app.route("/api/fmapi/endpoints")
def fmapi_endpoints():
    return jsonify({"endpoints": FMAPI_ENDPOINTS, "default": FMAPI_DEFAULT_ENDPOINT})

@app.route("/api/fmapi/chat", methods=["POST"])
def fmapi_chat():
    """Real LLM chat completion via Databricks Foundation Model API.
    Uses the same WorkspaceClient() auto-OAuth pattern already used for
    Lakebase above — no separate API key needed when running as a Databricks
    App with a service principal that has CAN QUERY on the serving endpoint.
    """
    data = request.get_json() or {}
    messages = data.get("messages")
    model = data.get("model") or FMAPI_DEFAULT_ENDPOINT
    system_prompt = data.get("systemPrompt")
    max_tokens = data.get("maxTokens", 800)
    tools = data.get("tools")  # OpenAI-compatible tool definitions
    tool_choice = data.get("tool_choice")  # 'auto', 'none', or specific

    if not messages or not isinstance(messages, list):
        return jsonify({"error": "messages (list of {role, content}) is required"}), 400
    if model not in FMAPI_ENDPOINTS:
        return jsonify({"error": f"Unknown endpoint '{model}'. Valid: {FMAPI_ENDPOINTS}"}), 400

    chat_messages = []
    if system_prompt:
        chat_messages.append({"role": "system", "content": system_prompt})
    chat_messages.extend(messages)

    try:
        w = WorkspaceClient()
        # Use the OpenAI-compatible Chat Completions API exposed by Databricks
        # serving endpoints -- supports tools, tool_choice, and structured output.
        # Extract bearer token via authenticate() -- works reliably for ALL auth
        # types (PAT, OAuth M2M, managed identity). w.config.token returns None
        # for OAuth-based auth (Databricks Apps), causing "Missing credentials".
        _auth_headers: dict = {}
        w.config.authenticate()(_auth_headers)
        _bearer_token = _auth_headers.get("Authorization", "").removeprefix("Bearer ")
        if not _bearer_token:
            raise ValueError(
                "Could not obtain auth token from WorkspaceClient. "
                "Ensure the app service principal credentials are configured."
            )
        client = openai.OpenAI(
            api_key=_bearer_token,
            base_url=f"{w.config.host}/serving-endpoints",
        )

        # Build kwargs, only including tools/tool_choice when provided
        create_kwargs = dict(
            model=model,
            messages=chat_messages,
            max_tokens=max_tokens,
        )
        if tools:
            create_kwargs["tools"] = tools
        if tool_choice:
            create_kwargs["tool_choice"] = tool_choice

        response = client.chat.completions.create(**create_kwargs)
        choice = response.choices[0] if response.choices else None

        if not choice or not choice.message:
            return jsonify({"error": "Empty response from model endpoint", "raw": str(response)}), 502

        msg = choice.message

        # Handle tool_calls response (agent wants to invoke a tool)
        if msg.tool_calls:
            tool_calls_out = []
            for tc in msg.tool_calls:
                tool_calls_out.append({
                    "id": tc.id,
                    "type": "function",
                    "function": {
                        "name": tc.function.name,
                        "arguments": tc.function.arguments,
                    },
                })
            return jsonify({
                "reply": msg.content,
                "tool_calls": tool_calls_out,
                "model": model,
            })

        # Handle plain text response
        reply_text = msg.content
        if not reply_text:
            return jsonify({"error": "Empty response from model endpoint", "raw": str(response)}), 502
        return jsonify({"reply": reply_text, "tool_calls": None, "model": model})
    except Exception as e:
        return jsonify({
            "error": str(e),
            "hint": (
                "Confirm this Databricks App's service principal has CAN QUERY on the "
                f"'{model}' serving endpoint, and that the endpoint name matches your "
                "workspace's endpoints_catalog exactly."
            ),
        }), 502

# ─── API routes ───────────────────────────────────────────────────────────────
@app.route("/api/health")
def health():
    return jsonify({"status": "ok", "database": DATABASE, "schema": PG_SCHEMA})

@app.route("/api/send-deploy-notification", methods=["POST"])
def send_deploy_notification():
    """Sends the pre-flight sign-off email when an experiment is deployed.
    Requires SMTP_HOST / SMTP_USER / SMTP_PASSWORD to be set as Databricks App
    environment variables or secrets — without them this returns a clear
    'not configured' error rather than silently pretending to send.
    """
    if not SMTP_HOST or not SMTP_USER or not SMTP_PASSWORD:
        return jsonify({
            "sent": False,
            "error": "SMTP not configured. Set SMTP_HOST, SMTP_USER, SMTP_PASSWORD "
                     "(and optionally SMTP_PORT, SMTP_FROM_EMAIL, SMTP_USE_TLS) as "
                     "environment variables/secrets on this Databricks App.",
        }), 503

    data = request.get_json() or {}
    to_email = data.get("toEmail")
    experiment_name = data.get("experimentName", "Untitled Experiment")
    summary_html = data.get("summaryHtml", "")
    notes = data.get("notes", "")

    if not to_email:
        return jsonify({"sent": False, "error": "toEmail is required"}), 400

    subject = f"MatchView Store — Experiment Deployed: {experiment_name}"
    body_html = f"""
    <h2>Experiment Deployed to Store Fleet</h2>
    <p><strong>{experiment_name}</strong> has been signed off and deployed.</p>
    {summary_html}
    {f'<p><strong>Launch notes:</strong> {notes}</p>' if notes else ''}
    <p style="color:#64748b;font-size:12px;">Sent automatically by MatchView Store.</p>
    """

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = SMTP_FROM_EMAIL
    msg["To"] = to_email
    msg.attach(MIMEText(body_html, "html"))

    try:
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=15) as server:
            if SMTP_USE_TLS:
                server.starttls()
            server.login(SMTP_USER, SMTP_PASSWORD)
            server.sendmail(SMTP_FROM_EMAIL, [to_email], msg.as_string())
        return jsonify({"sent": True})
    except Exception as e:
        return jsonify({"sent": False, "error": str(e)}), 502

@app.route("/api/projects", methods=["GET"])
def list_projects():
    conn = get_conn()
    with conn.cursor() as cur:
        cur.execute(f'SELECT * FROM "{PG_SCHEMA}".projects ORDER BY created_at DESC')
        cols = [d[0] for d in cur.description]
        rows = [dict(zip(cols, r)) for r in cur.fetchall()]
    conn.close()
    return jsonify(rows)

@app.route("/api/projects", methods=["POST"])
def create_project():
    data = request.get_json()
    conn = get_conn()
    with conn.cursor() as cur:
        cur.execute(f'''
            INSERT INTO "{PG_SCHEMA}".projects (name, hypothesis, goal, channel, experiment_type, created_by)
            VALUES (%s, %s, %s, %s, %s, %s) RETURNING project_id
        ''', (data.get("name"), data.get("hypothesis"), data.get("goal"),
              data.get("channel", "digital"), data.get("experimentType"), data.get("createdBy")))
        project_id = cur.fetchone()[0]
    conn.close()
    return jsonify({"project_id": str(project_id)}), 201

@app.route("/api/projects/<project_id>/modules", methods=["GET"])
def list_module_runs(project_id):
    conn = get_conn()
    with conn.cursor() as cur:
        cur.execute(f'SELECT * FROM "{PG_SCHEMA}".module_runs WHERE project_id = %s ORDER BY created_at', (project_id,))
        cols = [d[0] for d in cur.description]
        rows = [dict(zip(cols, r)) for r in cur.fetchall()]
    conn.close()
    return jsonify(rows)

@app.route("/api/projects/<project_id>/chat", methods=["GET"])
def list_chat(project_id):
    conn = get_conn()
    with conn.cursor() as cur:
        cur.execute(f'SELECT * FROM "{PG_SCHEMA}".chat_messages WHERE project_id = %s ORDER BY created_at', (project_id,))
        cols = [d[0] for d in cur.description]
        rows = [dict(zip(cols, r)) for r in cur.fetchall()]
    conn.close()
    return jsonify(rows)

@app.route("/api/projects/<project_id>/chat", methods=["POST"])
def post_chat(project_id):
    data = request.get_json()
    conn = get_conn()
    with conn.cursor() as cur:
        cur.execute(f'''
            INSERT INTO "{PG_SCHEMA}".chat_messages (project_id, role, content, intent, metadata)
            VALUES (%s, %s, %s, %s, %s) RETURNING message_id
        ''', (project_id, data.get("role"), data.get("content"),
              data.get("intent"), json.dumps(data.get("metadata", {}))))
        msg_id = cur.fetchone()[0]
    conn.close()
    return jsonify({"message_id": msg_id}), 201

# ─── SPA catch-all (serve React app for any non-API route) ────────────────────
@app.route("/", defaults={"path": ""})
@app.route("/<path:path>")
def serve_spa(path):
    if path and os.path.exists(os.path.join(app.static_folder, path)):
        return send_from_directory(app.static_folder, path)
    return send_from_directory(app.static_folder, "index.html")

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000)