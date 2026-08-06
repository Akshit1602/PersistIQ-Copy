# Databricks notebook source
# DBTITLE 1,MatchView v2.0 — Databricks App + Lakebase Setup
# MAGIC %md
# MAGIC # MatchView v2.0 — Deploy on Databricks Apps + Lakebase
# MAGIC
# MAGIC This notebook provisions **everything** needed to deploy the MatchView experimentation workspace as a **Databricks App** backed by **Lakebase Postgres**:
# MAGIC
# MAGIC 1. Configures widgets (app name, project ID)
# MAGIC 2. Locates the `MatchView App/` source folder (pre-built `dist/`)
# MAGIC 3. Provisions a Lakebase project (auto-creates production branch + primary endpoint)
# MAGIC 4. Creates the app state schema + tables in Lakebase
# MAGIC 5. Generates a lightweight Flask backend (`server.py`) that serves the SPA + exposes API endpoints
# MAGIC 6. Writes `app.yaml`, `requirements.txt`, `.databricksignore`
# MAGIC 7. Deploys the Databricks App
# MAGIC
# MAGIC ## Prerequisites
# MAGIC - The `MatchView App/` folder (with `dist/`) must be alongside this notebook
# MAGIC - Workspace must have Lakebase enabled

# COMMAND ----------

# DBTITLE 1,1. Configure
# ─── Widgets ───────────────────────────────────────────────────────────────────
dbutils.widgets.text("app_name",        "matchviewv1",   "1. Databricks App name (lowercase, hyphens ok)")
dbutils.widgets.text("lakebase_project", "matchview",  "2. Lakebase project ID (lowercase, hyphens ok)")
dbutils.widgets.text("pg_database",      "matchview",  "3. Postgres database name")
dbutils.widgets.text("pg_schema",        "app_v1",        "4. Postgres schema for app tables")

APP_NAME     = dbutils.widgets.get("app_name").strip()
LB_PROJECT   = dbutils.widgets.get("lakebase_project").strip()
LB_DATABASE  = dbutils.widgets.get("pg_database").strip()
PG_SCHEMA    = dbutils.widgets.get("pg_schema").strip()

# Derived Lakebase resource paths
PROJECT  = f"projects/{LB_PROJECT}"
BRANCH   = f"{PROJECT}/branches/production"
ENDPOINT = f"{BRANCH}/endpoints/primary"

print(f"App name        : {APP_NAME}")
print(f"Lakebase project: {LB_PROJECT}")
print(f"Database/schema : {LB_DATABASE}.{PG_SCHEMA}")

# COMMAND ----------

# DBTITLE 1,2. Locate repo root & verify dist/
import os

# This notebook lives at <root>/setup_deploy — the app folder is <root>/MatchView App/
try:
    nb_path = dbutils.notebook.entry_point.getDbutils().notebook().getContext().notebookPath().get()
    nb_path = nb_path.replace("\\", "/")
    REPO_ROOT = "/Workspace" + "/".join(nb_path.split("/")[:-1])
except Exception:
    REPO_ROOT = os.getcwd()

APP_DIR = os.path.join(REPO_ROOT, "MatchView App")
DIST_DIR = os.path.join(APP_DIR, "dist")

assert os.path.isdir(APP_DIR), f"MatchView App/ not found at {APP_DIR}"
assert os.path.isdir(DIST_DIR), f"dist/ not found at {DIST_DIR} — run 'npm run build' first"
assert os.path.isfile(os.path.join(DIST_DIR, "index.html")), "dist/index.html missing"

print(f"Repo root : {REPO_ROOT}")
print(f"App dir   : {APP_DIR}")
print(f"Dist dir  : {DIST_DIR} ✓")

# COMMAND ----------

# DBTITLE 1,3. Install SDK & client libs
# MAGIC %pip install -q "databricks-sdk>=0.118.0" "psycopg[binary]>=3.1.0" pyyaml
# MAGIC dbutils.library.restartPython()

# COMMAND ----------

# DBTITLE 1,4. Re-read widgets + SDK init (after restartPython)
import os, time
from databricks.sdk import WorkspaceClient
from databricks.sdk.errors import NotFound

APP_NAME     = dbutils.widgets.get("app_name").strip()
LB_PROJECT   = dbutils.widgets.get("lakebase_project").strip()
LB_DATABASE  = dbutils.widgets.get("pg_database").strip()
PG_SCHEMA    = dbutils.widgets.get("pg_schema").strip()

PROJECT  = f"projects/{LB_PROJECT}"
BRANCH   = f"{PROJECT}/branches/production"
ENDPOINT = f"{BRANCH}/endpoints/primary"

try:
    nb_path = dbutils.notebook.entry_point.getDbutils().notebook().getContext().notebookPath().get()
    nb_path = nb_path.replace("\\", "/")
    REPO_ROOT = "/Workspace" + "/".join(nb_path.split("/")[:-1])
except Exception:
    REPO_ROOT = os.getcwd()

APP_DIR  = os.path.join(REPO_ROOT, "MatchView App")
DIST_DIR = os.path.join(APP_DIR, "dist")

ws = WorkspaceClient()
USER_EMAIL = ws.current_user.me().user_name
print(f"Workspace : {ws.config.host}")
print(f"User      : {USER_EMAIL}")
print(f"App dir   : {APP_DIR}")

# COMMAND ----------

# DBTITLE 1,5. Provision Lakebase project + database
import psycopg
from psycopg import sql as pgsql
from databricks.sdk.service.postgres import Project, ProjectSpec

# Create or verify Lakebase project
try:
    ep = ws.postgres.get_endpoint(name=ENDPOINT)
    print(f"✓ Lakebase project '{LB_PROJECT}' exists")
except NotFound:
    print(f"  Creating Lakebase project '{LB_PROJECT}'…")
    ws.postgres.create_project(
        project=Project(spec=ProjectSpec(display_name=f"MatchView ({LB_PROJECT})", pg_version=17)),
        project_id=LB_PROJECT,
    ).wait()
    ep = ws.postgres.get_endpoint(name=ENDPOINT)
    print(f"✓ Lakebase project '{LB_PROJECT}' created")

LB_HOST = ep.status.hosts.host
print(f"✓ Endpoint host: {LB_HOST}")

# Create the app database (retry credential generation for eventual consistency)
for _attempt in range(5):
    try:
        cred = ws.postgres.generate_database_credential(endpoint=ENDPOINT)
        break
    except NotFound:
        time.sleep(3)
else:
    raise RuntimeError(f"Endpoint {ENDPOINT} not ready for credential generation after retries")
admin_conn = psycopg.connect(
    host=LB_HOST, port=5432, dbname="postgres",
    user=USER_EMAIL, password=cred.token, sslmode="require", autocommit=True,
)
with admin_conn.cursor() as cur:
    cur.execute("SELECT 1 FROM pg_database WHERE datname = %s", (LB_DATABASE,))
    if cur.fetchone():
        print(f"✓ Database '{LB_DATABASE}' already exists")
    else:
        cur.execute(pgsql.SQL("CREATE DATABASE {}").format(pgsql.Identifier(LB_DATABASE)))
        print(f"✓ Database '{LB_DATABASE}' created")
admin_conn.close()

# COMMAND ----------

# DBTITLE 1,6. Create app schema + tables
# Connect to the matchview database and create state tables
cred = ws.postgres.generate_database_credential(endpoint=ENDPOINT)
conn = psycopg.connect(
    host=LB_HOST, port=5432, dbname=LB_DATABASE,
    user=USER_EMAIL, password=cred.token, sslmode="require", autocommit=True,
)
with conn.cursor() as cur:
    cur.execute(f'CREATE SCHEMA IF NOT EXISTS "{PG_SCHEMA}"')
    cur.execute("CREATE EXTENSION IF NOT EXISTS pgcrypto")
print(f"✓ Schema '{PG_SCHEMA}' ready")

TABLES = {
    "projects": f"""
        CREATE TABLE IF NOT EXISTS "{PG_SCHEMA}".projects (
            project_id    UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            name          TEXT NOT NULL,
            hypothesis    TEXT,
            goal          TEXT,
            channel       TEXT DEFAULT 'digital',
            experiment_type TEXT,
            status        TEXT DEFAULT 'active',
            created_by    TEXT,
            created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
        );
    """,
    "module_runs": f"""
        CREATE TABLE IF NOT EXISTS "{PG_SCHEMA}".module_runs (
            run_id        UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            project_id    UUID REFERENCES "{PG_SCHEMA}".projects(project_id),
            module_key    TEXT NOT NULL,
            phase         TEXT,
            status        TEXT DEFAULT 'pending',
            params        JSONB,
            result        JSONB,
            started_at    TIMESTAMPTZ,
            finished_at   TIMESTAMPTZ,
            created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
        );
        CREATE INDEX IF NOT EXISTS idx_runs_project ON "{PG_SCHEMA}".module_runs (project_id, module_key);
    """,
    "chat_messages": f"""
        CREATE TABLE IF NOT EXISTS "{PG_SCHEMA}".chat_messages (
            message_id   BIGSERIAL PRIMARY KEY,
            project_id   UUID REFERENCES "{PG_SCHEMA}".projects(project_id),
            role         TEXT NOT NULL,
            content      TEXT,
            intent       TEXT,
            metadata     JSONB,
            created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW()
        );
        CREATE INDEX IF NOT EXISTS idx_chat_project ON "{PG_SCHEMA}".chat_messages (project_id, created_at);
    """,
    "insights": f"""
        CREATE TABLE IF NOT EXISTS "{PG_SCHEMA}".insights (
            insight_id   UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            project_id   UUID REFERENCES "{PG_SCHEMA}".projects(project_id),
            title        TEXT,
            category     TEXT,
            content      JSONB,
            created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW()
        );
    """,
    "reports": f"""
        CREATE TABLE IF NOT EXISTS "{PG_SCHEMA}".reports (
            report_id    UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            project_id   UUID REFERENCES "{PG_SCHEMA}".projects(project_id),
            title        TEXT NOT NULL,
            report_type  TEXT,
            content_md   TEXT,
            artifacts    JSONB,
            created_by   TEXT,
            created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW()
        );
    """,
    "app_settings": f"""
        CREATE TABLE IF NOT EXISTS "{PG_SCHEMA}".app_settings (
            setting_key   TEXT PRIMARY KEY,
            setting_value JSONB NOT NULL,
            updated_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
        );
    """,
}

for name, ddl in TABLES.items():
    with conn.cursor() as cur:
        cur.execute(ddl)
    print(f"  ✓ {name}")

with conn.cursor() as cur:
    cur.execute("SELECT count(*) FROM information_schema.tables WHERE table_schema=%s", (PG_SCHEMA,))
    n = cur.fetchone()[0]
print(f"\n✓ {n} tables in {LB_DATABASE}.{PG_SCHEMA}")
conn.close()

# COMMAND ----------

# DBTITLE 1,7. Generate server.py (Flask backend + SPA static serving)
SERVER_PY = '''
import os
import json
from flask import Flask, send_from_directory, jsonify, request
import psycopg
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

# ─── API routes ───────────────────────────────────────────────────────────────
@app.route("/api/health")
def health():
    return jsonify({"status": "ok", "database": DATABASE, "schema": PG_SCHEMA})

@app.route("/api/projects", methods=["GET"])
def list_projects():
    conn = get_conn()
    with conn.cursor() as cur:
        cur.execute(f\'SELECT * FROM "{PG_SCHEMA}".projects ORDER BY created_at DESC\')
        cols = [d[0] for d in cur.description]
        rows = [dict(zip(cols, r)) for r in cur.fetchall()]
    conn.close()
    return jsonify(rows)

@app.route("/api/projects", methods=["POST"])
def create_project():
    data = request.get_json()
    conn = get_conn()
    with conn.cursor() as cur:
        cur.execute(f\'\'\'
            INSERT INTO "{PG_SCHEMA}".projects (name, hypothesis, goal, channel, experiment_type, created_by)
            VALUES (%s, %s, %s, %s, %s, %s) RETURNING project_id
        \'\'\', (data.get("name"), data.get("hypothesis"), data.get("goal"),
              data.get("channel", "digital"), data.get("experimentType"), data.get("createdBy")))
        project_id = cur.fetchone()[0]
    conn.close()
    return jsonify({"project_id": str(project_id)}), 201

@app.route("/api/projects/<project_id>/modules", methods=["GET"])
def list_module_runs(project_id):
    conn = get_conn()
    with conn.cursor() as cur:
        cur.execute(f\'SELECT * FROM "{PG_SCHEMA}".module_runs WHERE project_id = %s ORDER BY created_at\', (project_id,))
        cols = [d[0] for d in cur.description]
        rows = [dict(zip(cols, r)) for r in cur.fetchall()]
    conn.close()
    return jsonify(rows)

@app.route("/api/projects/<project_id>/chat", methods=["GET"])
def list_chat(project_id):
    conn = get_conn()
    with conn.cursor() as cur:
        cur.execute(f\'SELECT * FROM "{PG_SCHEMA}".chat_messages WHERE project_id = %s ORDER BY created_at\', (project_id,))
        cols = [d[0] for d in cur.description]
        rows = [dict(zip(cols, r)) for r in cur.fetchall()]
    conn.close()
    return jsonify(rows)

@app.route("/api/projects/<project_id>/chat", methods=["POST"])
def post_chat(project_id):
    data = request.get_json()
    conn = get_conn()
    with conn.cursor() as cur:
        cur.execute(f\'\'\'
            INSERT INTO "{PG_SCHEMA}".chat_messages (project_id, role, content, intent, metadata)
            VALUES (%s, %s, %s, %s, %s) RETURNING message_id
        \'\'\', (project_id, data.get("role"), data.get("content"),
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
'''.strip()

server_path = os.path.join(APP_DIR, "server.py")
with open(server_path, "w") as f:
    f.write(SERVER_PY)
print(f"✓ server.py written to {server_path}")

# COMMAND ----------

# DBTITLE 1,8. Generate requirements.txt, app.yaml, .databricksignore
import yaml, uuid

# ─── requirements.txt ─────────────────────────────────────────────────────────
REQUIREMENTS = """flask>=3.0
psycopg[binary]>=3.1.0
databricks-sdk>=0.118.0
gunicorn>=22.0
"""
with open(os.path.join(APP_DIR, "requirements.txt"), "w") as f:
    f.write(REQUIREMENTS)
print("✓ requirements.txt")

# ─── .databricksignore ────────────────────────────────────────────────────────
IGNORE = """src/
node_modules/
public/
*.ts
*.tsx
package-lock.json
tsconfig*.json
vite.config.ts
eslint.config.js
postcss.config.js
design.md
README.md
.gitignore
"""
with open(os.path.join(APP_DIR, ".databricksignore"), "w") as f:
    f.write(IGNORE)
print("✓ .databricksignore")

# ─── Resolve Lakebase Database entity for app resource ────────────────────────
candidates = [
    d for d in ws.postgres.list_databases(parent=BRANCH)
    if d.status and d.status.postgres_database == LB_DATABASE
]
LAKEBASE_DB_PATH = candidates[0].name if candidates else None
print(f"  Lakebase DB entity: {LAKEBASE_DB_PATH}")

# ─── app.yaml ─────────────────────────────────────────────────────────────────
env = [
    {"name": "LAKEBASE_ENDPOINT",  "value": ENDPOINT},
    {"name": "LAKEBASE_DATABASE",  "value": LB_DATABASE},
    {"name": "LAKEBASE_SCHEMA",    "value": PG_SCHEMA},
    {"name": "FLASK_SECRET_KEY",   "value": uuid.uuid4().hex},
]

app_yaml = {
    "command": ["gunicorn", "server:app", "--bind", "0.0.0.0:8000", "--workers", "2"],
    "env": env,
}
with open(os.path.join(APP_DIR, "app.yaml"), "w") as f:
    yaml.safe_dump(app_yaml, f, sort_keys=False)
print("✓ app.yaml")
print("\nGenerated app.yaml:")
print(yaml.safe_dump(app_yaml, sort_keys=False))

# COMMAND ----------

# DBTITLE 1,Store Channel — Unity Catalog Tables & CSV Volume
# MAGIC %md
# MAGIC ## 8b. Store Channel — Unity Catalog Tables & CSV Volume
# MAGIC
# MAGIC This section provisions the **Store channel** data layer for MatchView:
# MAGIC
# MAGIC 1. Creates a UC schema (`dev.matchview_store`) and a Volume for CSV uploads
# MAGIC 2. Creates 5 Delta tables matching the Dollar Tree MVP data model
# MAGIC 3. Generates realistic sample data (~9,500 stores, 52 weeks, 25 initiatives)
# MAGIC 4. Uploads CSVs to the Volume so the MatchView app can load them as an internal data source
# MAGIC
# MAGIC | Table | Purpose |
# MAGIC |-------|--------|
# MAGIC | `store_master` | Fixed/slowly-changing store attributes (9,500 locations) |
# MAGIC | `store_performance_weekly` | Time-series KPIs (sales, traffic, conversion, UPT, AUR) |
# MAGIC | `initiative_catalog` | Experiment/initiative metadata with expected lag |
# MAGIC | `store_initiative_mapping` | Which store got which initiative and when (concurrency matrix) |
# MAGIC | `macro_external_data` | External noise factors (weather, local economy) |

# COMMAND ----------

# DBTITLE 1,8b-1. Create UC schema, volume, and Delta tables
# ─── Store Channel: UC Schema + Volume + Tables ──────────────────────────────────
from databricks.sdk import WorkspaceClient
from databricks.sdk.errors import NotFound
from databricks.sdk.service.catalog import VolumeType

ws = WorkspaceClient()

UC_CATALOG = "dev"
UC_STORE_SCHEMA = "matchview_store"
UC_STORE_VOLUME = "store_csv_uploads"

# Schema
try:
    ws.schemas.get(full_name=f"{UC_CATALOG}.{UC_STORE_SCHEMA}")
    print(f"✓ Schema {UC_CATALOG}.{UC_STORE_SCHEMA} exists")
except NotFound:
    ws.schemas.create(name=UC_STORE_SCHEMA, catalog_name=UC_CATALOG,
                      comment="MatchView Store Channel — Dollar Tree MVP data model")
    print(f"✓ Schema {UC_CATALOG}.{UC_STORE_SCHEMA} created")

# Volume for CSV uploads
try:
    ws.volumes.read(f"{UC_CATALOG}.{UC_STORE_SCHEMA}.{UC_STORE_VOLUME}")
    print(f"✓ Volume {UC_STORE_VOLUME} exists")
except NotFound:
    ws.volumes.create(catalog_name=UC_CATALOG, schema_name=UC_STORE_SCHEMA,
                      name=UC_STORE_VOLUME, volume_type=VolumeType.MANAGED,
                      comment="CSV upload landing zone for Store channel data")
    print(f"✓ Volume {UC_STORE_VOLUME} created")

VOLUME_PATH = f"/Volumes/{UC_CATALOG}/{UC_STORE_SCHEMA}/{UC_STORE_VOLUME}"
FQ = lambda t: f"{UC_CATALOG}.{UC_STORE_SCHEMA}.{t}"
print(f"  Volume path: {VOLUME_PATH}")

# COMMAND ----------

# DBTITLE 1,8b-2. DDL — 5 Delta tables for Store channel
# MAGIC %sql
# MAGIC -- ═══════════════════════════════════════════════════════════════════════════════
# MAGIC -- 1. store_master — Fixed/slowly-changing store attributes
# MAGIC -- ═══════════════════════════════════════════════════════════════════════════════
# MAGIC CREATE TABLE IF NOT EXISTS dev.matchview_store.store_master (
# MAGIC   store_id            STRING    NOT NULL  COMMENT 'Unique identifier for all 9,500 locations',
# MAGIC   store_name          STRING              COMMENT 'Human-readable store name',
# MAGIC   open_date           DATE                COMMENT 'Used to calculate new-store cannibalization effect',
# MAGIC   store_size_sqft     INT                 COMMENT 'Store square footage — key attribute variable',
# MAGIC   population_density  DOUBLE              COMMENT 'Population density of surrounding area',
# MAGIC   location_zip        STRING              COMMENT 'ZIP code for geographic spillover & weather mapping',
# MAGIC   risk_tier           STRING              COMMENT 'Baseline risk classification (Low/Medium/High)',
# MAGIC   region              STRING              COMMENT 'Geographic region',
# MAGIC   state               STRING              COMMENT 'US state code',
# MAGIC   format_type         STRING              COMMENT 'Store format (Standard/Plus/Combo)'
# MAGIC )
# MAGIC USING DELTA
# MAGIC COMMENT 'MatchView Store Channel — Non-variable baseline for all Dollar Tree locations'
# MAGIC TBLPROPERTIES ('delta.enableChangeDataFeed' = 'true');
# MAGIC
# MAGIC -- ═══════════════════════════════════════════════════════════════════════════════
# MAGIC -- 2. store_performance_weekly — Time-series KPIs (monthly refresh cadence)
# MAGIC -- ═══════════════════════════════════════════════════════════════════════════════
# MAGIC CREATE TABLE IF NOT EXISTS dev.matchview_store.store_performance_weekly (
# MAGIC   store_id            STRING    NOT NULL  COMMENT 'FK → store_master',
# MAGIC   week_start_date     DATE      NOT NULL  COMMENT 'Time-series anchor (Monday of each week)',
# MAGIC   gold_score          DOUBLE              COMMENT '90-day store operating quality metric (0-100)',
# MAGIC   total_sales         DOUBLE              COMMENT 'Total weekly sales ($) — primary target variable',
# MAGIC   traffic             INT                 COMMENT 'Weekly customer foot traffic count',
# MAGIC   conversion_rate     DOUBLE              COMMENT 'Traffic-to-transaction conversion (%)',
# MAGIC   upt                 DOUBLE              COMMENT 'Units Per Transaction',
# MAGIC   aur                 DOUBLE              COMMENT 'Average Unit Retail ($)'
# MAGIC )
# MAGIC USING DELTA
# MAGIC COMMENT 'MatchView Store Channel — Weekly performance time-series with delayed-lag awareness'
# MAGIC TBLPROPERTIES ('delta.enableChangeDataFeed' = 'true');
# MAGIC
# MAGIC -- ═══════════════════════════════════════════════════════════════════════════════
# MAGIC -- 3. initiative_catalog — Experiment/initiative metadata
# MAGIC -- ═══════════════════════════════════════════════════════════════════════════════
# MAGIC CREATE TABLE IF NOT EXISTS dev.matchview_store.initiative_catalog (
# MAGIC   initiative_id       STRING    NOT NULL  COMMENT 'Unique initiative identifier',
# MAGIC   initiative_name     STRING    NOT NULL  COMMENT 'Display name (e.g. Multi-Price Roll-out)',
# MAGIC   initiative_category STRING              COMMENT 'Category: Assortment, Staffing, Remodel, Pricing, Marketing',
# MAGIC   expected_lag_weeks  INT                 COMMENT 'Expected weeks for customer behavior to respond',
# MAGIC   description         STRING              COMMENT 'Detailed description of the initiative',
# MAGIC   start_date          DATE                COMMENT 'Earliest rollout date across all stores',
# MAGIC   owner               STRING              COMMENT 'Initiative owner/team'
# MAGIC )
# MAGIC USING DELTA
# MAGIC COMMENT 'MatchView Store Channel — Catalog of all interventions being measured';
# MAGIC
# MAGIC -- ═══════════════════════════════════════════════════════════════════════════════
# MAGIC -- 4. store_initiative_mapping — Concurrency matrix (which store got what, when)
# MAGIC -- ═══════════════════════════════════════════════════════════════════════════════
# MAGIC CREATE TABLE IF NOT EXISTS dev.matchview_store.store_initiative_mapping (
# MAGIC   store_id            STRING    NOT NULL  COMMENT 'FK → store_master (specific store receiving treatment)',
# MAGIC   initiative_id       STRING    NOT NULL  COMMENT 'FK → initiative_catalog (specific initiative deployed)',
# MAGIC   rollout_date        DATE      NOT NULL  COMMENT 'When the initiative went live at this store',
# MAGIC   status              STRING    NOT NULL  COMMENT 'Active | Paused | Control',
# MAGIC   cohort_label        STRING              COMMENT 'Rollout wave label (Wave 1, Wave 2, etc.)'
# MAGIC )
# MAGIC USING DELTA
# MAGIC COMMENT 'MatchView Store Channel — Tracks overlapping 10-30 initiatives per store for causal untangling';
# MAGIC
# MAGIC -- ═══════════════════════════════════════════════════════════════════════════════
# MAGIC -- 5. macro_external_data — Environmental noise factors
# MAGIC -- ═══════════════════════════════════════════════════════════════════════════════
# MAGIC CREATE TABLE IF NOT EXISTS dev.matchview_store.macro_external_data (
# MAGIC   location_zip        STRING    NOT NULL  COMMENT 'FK → store_master.location_zip',
# MAGIC   week_start_date     DATE      NOT NULL  COMMENT 'Ties to store_performance_weekly',
# MAGIC   weather_index       DOUBLE              COMMENT 'Composite weather severity index (0-100, higher = worse)',
# MAGIC   local_economic_index DOUBLE             COMMENT 'Local economic health (median income shifts, unemployment)',
# MAGIC   holiday_flag        BOOLEAN             COMMENT 'Whether this week contains a major retail holiday',
# MAGIC   competitor_event    STRING              COMMENT 'Nearby competitor promotional event (if any)'
# MAGIC )
# MAGIC USING DELTA
# MAGIC COMMENT 'MatchView Store Channel — External uncontrollable factors for accurate baseline modeling';

# COMMAND ----------

# DBTITLE 1,8b-3. Generate sample data & load into tables + CSV volume
import random
import datetime
from pyspark.sql import Row
from pyspark.sql.types import *

random.seed(42)
print("Generating Dollar Tree MVP sample data…\n")

# ═══ 1. store_master (9,500 stores) ═══════════════════════════════════════════
REGIONS = ["Northeast", "Southeast", "Midwest", "Southwest", "West", "Mid-Atlantic"]
STATES = ["TX","CA","FL","NY","PA","OH","IL","GA","NC","MI","VA","NJ","AZ","TN","IN",
          "MO","WI","SC","AL","CO","KY","OK","OR","CT","IA","MS","AR","KS","NV","NM"]
FORMATS = ["Standard", "Standard", "Standard", "Plus", "Plus", "Combo"]
RISK_TIERS = ["Low", "Low", "Medium", "Medium", "Medium", "High"]

stores = []
for i in range(9500):
    sid = f"ST-{i+1:05d}"
    stores.append(Row(
        store_id=sid,
        store_name=f"Dollar Tree #{i+1}",
        open_date=datetime.date(2000 + random.randint(0, 24), random.randint(1, 12), random.randint(1, 28)),
        store_size_sqft=random.randint(6000, 14000),
        population_density=round(random.uniform(200, 12000), 1),
        location_zip=f"{random.randint(10000, 99999)}",
        risk_tier=random.choice(RISK_TIERS),
        region=random.choice(REGIONS),
        state=random.choice(STATES),
        format_type=random.choice(FORMATS),
    ))

schema_store_master = StructType([StructField('store_id', StringType(), True), StructField('store_name', StringType(), True), StructField('open_date', DateType(), True), StructField('store_size_sqft', IntegerType(), True), StructField('population_density', DoubleType(), True), StructField('location_zip', StringType(), True), StructField('risk_tier', StringType(), True), StructField('region', StringType(), True), StructField('state', StringType(), True), StructField('format_type', StringType(), True)]); df_stores = spark.createDataFrame(stores, schema=schema_store_master)

df_stores.write.mode("overwrite").option("overwriteSchema", "true").saveAsTable(FQ("store_master"))
print(f"  ✓ store_master: {df_stores.count():,} rows")

# ═══ 2. initiative_catalog (25 initiatives) ═══════════════════════════════════
INITIATIVES = [
    ("Multi-Price Roll-out", "Pricing", 4),
    ("Dedicated Cashiers", "Staffing", 3),
    ("Paint-and-Powder Remodel", "Remodel", 8),
    ("Fresh/Frozen Expansion", "Assortment", 6),
    ("Self-Checkout Install", "Staffing", 5),
    ("Endcap Optimization", "Marketing", 2),
    ("Loyalty Program Launch", "Marketing", 4),
    ("Seasonal Aisle Refresh", "Assortment", 3),
    ("LED Lighting Upgrade", "Remodel", 6),
    ("Express Lane Addition", "Staffing", 3),
    ("Private Label Push", "Assortment", 5),
    ("Digital Signage", "Marketing", 2),
    ("Extended Hours Pilot", "Staffing", 4),
    ("Curbside Pickup", "Marketing", 6),
    ("Dollar Tree Plus Conversion", "Remodel", 10),
    ("Back-to-School Feature", "Assortment", 2),
    ("Inventory RFID Tagging", "Staffing", 5),
    ("Planogram Reset Q3", "Assortment", 3),
    ("Community Board Program", "Marketing", 4),
    ("Stockroom Expansion", "Remodel", 7),
    ("Workforce Scheduling AI", "Staffing", 4),
    ("Combo Store Merger", "Remodel", 12),
    ("Price Perception Signage", "Pricing", 3),
    ("High-Shrink Mitigation", "Staffing", 5),
    ("Adjacency Optimization", "Assortment", 3),
]

initiatives = []
for idx, (name, cat, lag) in enumerate(INITIATIVES):
    initiatives.append(Row(
        initiative_id=f"INIT-{idx+1:03d}",
        initiative_name=name,
        initiative_category=cat,
        expected_lag_weeks=lag,
        description=f"{name} initiative targeting store-level {cat.lower()} improvements",
        start_date=datetime.date(2025, random.randint(1, 12), random.randint(1, 28)),
        owner=random.choice(["Ops Team", "Merch Team", "Store Dev", "Marketing", "Finance"]),
    ))

df_init = spark.createDataFrame(initiatives)
df_init.write.mode("overwrite").option("overwriteSchema", "true").saveAsTable(FQ("initiative_catalog"))
print(f"  ✓ initiative_catalog: {df_init.count()} rows")

# ═══ 3. store_initiative_mapping (concurrency matrix) ═════════════════════════
# Each store gets 10-30 random initiatives
mappings = []
for store in stores:
    n_initiatives = random.randint(10, 30)
    chosen = random.sample(range(len(INITIATIVES)), min(n_initiatives, len(INITIATIVES)))
    for init_idx in chosen:
        mappings.append(Row(
            store_id=store.store_id,
            initiative_id=f"INIT-{init_idx+1:03d}",
            rollout_date=datetime.date(2025, random.randint(1, 12), random.randint(1, 28)),
            status=random.choice(["Active", "Active", "Active", "Paused", "Control"]),
            cohort_label=f"Wave {random.randint(1, 5)}",
        ))

df_map = spark.createDataFrame(mappings)
df_map.write.mode("overwrite").option("overwriteSchema", "true").saveAsTable(FQ("store_initiative_mapping"))
print(f"  ✓ store_initiative_mapping: {df_map.count():,} rows")

# ═══ 4. store_performance_weekly (52 weeks × 9,500 stores) ════════════════════
# Generate in batches to manage memory
print("  Generating store_performance_weekly (52 weeks × 9,500 stores)…")
base_date = datetime.date(2025, 1, 6)  # First Monday of 2025

perf_rows = []
for week_num in range(52):
    week_date = base_date + datetime.timedelta(weeks=week_num)
    for store in stores:
        base_sales = random.uniform(15000, 85000)
        traffic = random.randint(800, 5000)
        conv = round(random.uniform(0.15, 0.55), 4)
        upt = round(random.uniform(2.0, 5.5), 2)
        aur = round(random.uniform(1.25, 4.50), 2)
        perf_rows.append(Row(
            store_id=store.store_id,
            week_start_date=week_date,
            gold_score=round(random.uniform(40, 98), 1),
            total_sales=round(base_sales * random.uniform(0.85, 1.15), 2),
            traffic=traffic,
            conversion_rate=conv,
            upt=upt,
            aur=aur,
        ))
    # Write in batches of 4 weeks to avoid OOM
    if (week_num + 1) % 4 == 0:
        df_batch = spark.createDataFrame(perf_rows)
        mode = "overwrite" if week_num < 4 else "append"
        df_batch.write.mode(mode).option("overwriteSchema", "true").saveAsTable(FQ("store_performance_weekly"))
        perf_rows = []
        print(f"    … week {week_num + 1}/52 written")

count = spark.table(FQ("store_performance_weekly")).count()
print(f"  ✓ store_performance_weekly: {count:,} rows")

# ═══ 5. macro_external_data (52 weeks × unique ZIPs) ══════════════════════════
zips = list(set(s.location_zip for s in stores))
macro_rows = []
for week_num in range(52):
    week_date = base_date + datetime.timedelta(weeks=week_num)
    for z in zips:
        macro_rows.append(Row(
            location_zip=z,
            week_start_date=week_date,
            weather_index=round(random.uniform(5, 85), 1),
            local_economic_index=round(random.uniform(40, 110), 1),
            holiday_flag=(week_num in [0, 5, 12, 21, 26, 35, 44, 47, 48, 51]),
            competitor_event=random.choice([None, None, None, "Walmart Rollback", "Target Circle Week", "Amazon Prime Day"]),
        ))

df_macro = spark.createDataFrame(macro_rows)
df_macro.write.mode("overwrite").option("overwriteSchema", "true").saveAsTable(FQ("macro_external_data"))
print(f"  ✓ macro_external_data: {df_macro.count():,} rows")

print("\n═══ All 5 tables loaded ═══")

# COMMAND ----------

# DBTITLE 1,8b-4. Export CSVs to Volume & register store data source
# ─── Ensure psycopg is available (may be missing after kernel restart) ────────
import subprocess, sys
subprocess.check_call([sys.executable, '-m', 'pip', 'install', '-q', 'psycopg[binary]>=3.1.0'])

# ─── Re-establish all session variables ─────────────────────────────────────
from databricks.sdk import WorkspaceClient
ws = WorkspaceClient()
UC_CATALOG = "dev"
UC_STORE_SCHEMA = "matchview_store"
VOLUME_PATH = f"/Volumes/{UC_CATALOG}/{UC_STORE_SCHEMA}/store_csv_uploads"
PG_SCHEMA = dbutils.widgets.get("pg_schema")
LB_DATABASE = dbutils.widgets.get("pg_database")
LB_PROJECT = dbutils.widgets.get("lakebase_project")
ENDPOINT = f"projects/{LB_PROJECT}/branches/production/endpoints/primary"
ep = ws.postgres.get_endpoint(name=ENDPOINT)
LB_HOST = ep.status.hosts.host
USER_EMAIL = ws.current_user.me().user_name
FQ = lambda t: f"{UC_CATALOG}.{UC_STORE_SCHEMA}.{t}"

# ─── Export each table as CSV to the UC Volume (for CSV upload workflow) ───────
TABLES_TO_EXPORT = [
    "store_master",
    "store_performance_weekly",
    "initiative_catalog",
    "store_initiative_mapping",
    "macro_external_data",
]

for tbl in TABLES_TO_EXPORT:
    df = spark.table(FQ(tbl))
    csv_path = f"{VOLUME_PATH}/{tbl}.csv"
    df.toPandas().to_csv(csv_path, index=False)
    print(f"  ✓ {tbl}.csv → {csv_path}")

print(f"\n✓ All CSVs exported to {VOLUME_PATH}")

# ─── Register the Store channel data source in Lakebase app_settings ──────────
import json
import psycopg
from psycopg.types.json import Json

cred = ws.postgres.generate_database_credential(endpoint=ENDPOINT)
conn = psycopg.connect(
    host=LB_HOST, port=5432, dbname=LB_DATABASE,
    user=USER_EMAIL, password=cred.token, sslmode="require", autocommit=True,
)

store_datasource_config = {
    "channel": "store",
    "type": "internal",
    "uc_catalog": UC_CATALOG,
    "uc_schema": UC_STORE_SCHEMA,
    "volume_path": VOLUME_PATH,
    "tables": {
        "store_master": FQ("store_master"),
        "store_performance_weekly": FQ("store_performance_weekly"),
        "initiative_catalog": FQ("initiative_catalog"),
        "store_initiative_mapping": FQ("store_initiative_mapping"),
        "macro_external_data": FQ("macro_external_data"),
    },
    "description": "Dollar Tree Store Channel — 9,500 locations, 25 initiatives, weekly KPIs",
}

with conn.cursor() as cur:
    cur.execute(f"""
        INSERT INTO "{PG_SCHEMA}".app_settings (setting_key, setting_value)
        VALUES ('store_channel_datasource', %s)
        ON CONFLICT (setting_key) DO UPDATE
        SET setting_value = EXCLUDED.setting_value, updated_at = NOW()
    """, (Json(store_datasource_config),))
conn.close()

print("\n✓ Store channel data source registered in Lakebase (app_settings.store_channel_datasource)")
print("\n📋 Store channel summary:")
print(f"   UC location   : {UC_CATALOG}.{UC_STORE_SCHEMA}")
print(f"   CSV volume    : {VOLUME_PATH}")
print(f"   Tables        : {', '.join(TABLES_TO_EXPORT)}")
print(f"   Stores        : 9,500")
print(f"   Initiatives   : 25")
print(f"   Time range    : 52 weeks (2025)")

# COMMAND ----------

# DBTITLE 0,9. Deploy Databricks App
import time
import os
from databricks.sdk import WorkspaceClient
from databricks.sdk.errors import NotFound
from databricks.sdk.service.apps import App, AppDeployment

# Re-establish session variables after kernel restart
ws = WorkspaceClient()
APP_NAME = dbutils.widgets.get("app_name")
APP_DIR = "/Workspace/Users/thannarasu.t@latentviewo365.onmicrosoft.com/MatchView v2.0/MatchView App"

APP_DESC = "MatchView v2.0 — B2B experimentation workspace (React + Lakebase)"

# Create or update the app (resources already configured from prior deployment)
try:
    ws.apps.get(name=APP_NAME)
    print(f"App '{APP_NAME}' exists — updating…")
    ws.apps.update(
        name=APP_NAME,
        app=App(name=APP_NAME, description=APP_DESC,
                default_source_code_path=APP_DIR),
    )
    print("✓ App updated")
except NotFound:
    print(f"Creating app '{APP_NAME}'… (~30s)")
    created = ws.apps.create_and_wait(
        app=App(name=APP_NAME, description=APP_DESC,
                default_source_code_path=APP_DIR),
    )
    print(f"✓ App created at {created.url}")

# Ensure app is in RUNNING state (required for deploy)
print("\nEnsuring app is running…")
try:
    ws.apps.start(name=APP_NAME)
    time.sleep(10)
    print("✓ App start requested")
except Exception as _start_err:
    if "already" in str(_start_err).lower() or "running" in str(_start_err).lower():
        print("✓ App already running")
    else:
        print(f"  Start note: {_start_err} (continuing with deploy)")

# Deploy
print(f"\nDeploying from {APP_DIR}… (~1-3 min)")
for _attempt in range(12):
    try:
        deployment = ws.apps.deploy_and_wait(
            app_name=APP_NAME,
            app_deployment=AppDeployment(source_code_path=APP_DIR),
        )
        break
    except Exception as _e:
        if "active deployment in progress" in str(_e).lower() and _attempt < 11:
            print(f"  Previous deployment in progress — retrying in 15s ({_attempt + 1}/12)…")
            time.sleep(15)
        else:
            raise

print(f"✓ Deployment complete (status={deployment.status.state if deployment.status else 'unknown'})")
app = ws.apps.get(name=APP_NAME)
print(f"\n🌐 App URL: {app.url}")

# COMMAND ----------

