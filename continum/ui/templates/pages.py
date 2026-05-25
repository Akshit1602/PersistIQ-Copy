DASHBOARD_HTML = """
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>PersistIQ — Experimentation Intelligence</title>
<link href="https://cdnjs.cloudflare.com/ajax/libs/bootstrap/5.3.2/css/bootstrap.min.css" rel="stylesheet">
<link href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.5.1/css/all.min.css" rel="stylesheet">
<style>
  :root {
    --bg:        #0d1117;
    --surface:   #161b22;
    --surface2:  #21262d;
    --border:    #30363d;
    --text:      #e6edf3;
    --muted:     #8b949e;
    --accent:    #58a6ff;
    --green:     #3fb950;
    --yellow:    #d29922;
    --red:       #f85149;
    --purple:    #bc8cff;
    --orange:    #ffa657;
  }
  * { box-sizing: border-box; }
  body { background: var(--bg); color: var(--text); font-family: 'Segoe UI', system-ui, sans-serif; margin: 0; min-height: 100vh; }
  /* ── Layout ── */
  .layout { display: grid; grid-template-columns: 240px 1fr 320px; min-height: 100vh; }
  /* ── Sidebar ── */
  .sidebar { background: var(--surface); border-right: 1px solid var(--border); padding: 0; display: flex; flex-direction: column; }
  .sidebar-brand { padding: 18px 20px; border-bottom: 1px solid var(--border); }
  .sidebar-brand .os-name { font-size: 13px; font-weight: 700; letter-spacing: 2px; color: var(--accent); text-transform: uppercase; }
  .sidebar-brand .tagline { font-size: 11px; color: var(--muted); margin-top: 2px; }
  .session-pill { margin: 12px 16px; background: var(--surface2); border: 1px solid var(--border); border-radius: 8px; padding: 10px 14px; }
  .session-pill .label { font-size: 10px; color: var(--muted); text-transform: uppercase; letter-spacing: 1px; }
  .session-pill .value { font-size: 13px; color: var(--text); margin-top: 2px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
  .nav-section { padding: 8px 0; }
  .nav-section-label { font-size: 10px; color: var(--muted); text-transform: uppercase; letter-spacing: 1px; padding: 6px 20px 4px; }
  .nav-item { display: flex; align-items: center; gap: 10px; padding: 8px 20px; cursor: pointer; font-size: 13px; color: var(--muted); border-left: 2px solid transparent; transition: all 0.15s; text-decoration: none; }
  .nav-item:hover { background: var(--surface2); color: var(--text); }
  .nav-item.active { color: var(--accent); border-left-color: var(--accent); background: rgba(88,166,255,0.07); }
  .nav-item .icon { width: 16px; text-align: center; font-size: 12px; }
  .nav-item .badge-dot { width: 6px; height: 6px; border-radius: 50%; background: var(--green); margin-left: auto; }
  .nav-item .badge-warn { width: 6px; height: 6px; border-radius: 50%; background: var(--yellow); margin-left: auto; }
  /* ── Main ── */
  .main { display: flex; flex-direction: column; overflow: hidden; }
  .topbar { background: var(--surface); border-bottom: 1px solid var(--border); padding: 12px 24px; display: flex; align-items: center; gap: 16px; }
  .topbar .exp-selector { flex: 1; }
  .topbar select { background: var(--surface2); border: 1px solid var(--border); color: var(--text); border-radius: 6px; padding: 6px 12px; font-size: 13px; width: 100%; max-width: 400px; }
  .topbar select:focus { outline: none; border-color: var(--accent); }
  .run-btn { background: var(--accent); color: #0d1117; border: none; border-radius: 6px; padding: 7px 20px; font-size: 13px; font-weight: 600; cursor: pointer; transition: opacity 0.15s; }
  .run-btn:hover { opacity: 0.85; }
  .run-btn:disabled { opacity: 0.4; cursor: not-allowed; }
  /* ── Workflow grid ── */
  .content { padding: 20px 24px; overflow-y: auto; flex: 1; }
  .section-title { font-size: 11px; text-transform: uppercase; letter-spacing: 1px; color: var(--muted); margin-bottom: 12px; }
  .workflow-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(160px, 1fr)); gap: 10px; margin-bottom: 24px; }
  .wf-card { background: var(--surface); border: 1px solid var(--border); border-radius: 8px; padding: 14px; cursor: pointer; transition: all 0.15s; position: relative; }
  .wf-card:hover { border-color: var(--accent); background: var(--surface2); }
  .wf-card.done { border-color: var(--green); }
  .wf-card .wf-icon { font-size: 20px; margin-bottom: 8px; }
  .wf-card .wf-name { font-size: 12px; font-weight: 600; color: var(--text); line-height: 1.3; }
  .wf-card .wf-phase { font-size: 10px; color: var(--muted); margin-top: 3px; }
  .wf-card .done-badge { position: absolute; top: 8px; right: 8px; font-size: 9px; }
  /* ── Execution console ── */
  .console-panel { background: var(--surface); border: 1px solid var(--border); border-radius: 8px; margin-bottom: 20px; }
  .console-header { padding: 10px 16px; border-bottom: 1px solid var(--border); display: flex; align-items: center; gap: 10px; font-size: 12px; font-weight: 600; color: var(--muted); }
  .console-header .dot { width: 8px; height: 8px; border-radius: 50%; background: var(--border); }
  .console-header .dot.running { background: var(--green); animation: pulse 1s infinite; }
  .console-body { font-family: 'Consolas', 'Courier New', monospace; font-size: 12px; padding: 12px 16px; height: 220px; overflow-y: auto; background: #0d1117; border-radius: 0 0 8px 8px; }
  .log-line { margin: 1px 0; line-height: 1.5; }
  .log-INFO  { color: var(--muted); }
  .log-INFO::before  { content: "[INFO] "; color: var(--accent); }
  .log-WARN::before  { content: "[WARN] "; color: var(--yellow); }
  .log-ERR::before   { content: "[ERR ] "; color: var(--red); }
  .log-OK::before    { content: "[OK  ] "; color: var(--green); }
  .log-DONE { color: var(--green); }
  .log-PING  { color: transparent; height: 0; }
  /* ── Run history ── */
  .history-table { width: 100%; border-collapse: collapse; font-size: 12px; }
  .history-table th { padding: 6px 12px; text-align: left; font-size: 10px; text-transform: uppercase; letter-spacing: 1px; color: var(--muted); border-bottom: 1px solid var(--border); }
  .history-table td { padding: 7px 12px; border-bottom: 1px solid var(--border); color: var(--text); }
  .history-table tr:last-child td { border-bottom: none; }
  .badge-ok   { background: rgba(63,185,80,.15); color: var(--green); padding: 2px 8px; border-radius: 10px; font-size: 10px; }
  .badge-fail { background: rgba(248,81,73,.15); color: var(--red);   padding: 2px 8px; border-radius: 10px; font-size: 10px; }
  /* ── Right panel ── */
  .intel-panel { background: var(--surface); border-left: 1px solid var(--border); display: flex; flex-direction: column; overflow: hidden; }
  .intel-tabs  { display: flex; border-bottom: 1px solid var(--border); }
  .intel-tab   { padding: 10px 16px; font-size: 12px; cursor: pointer; color: var(--muted); border-bottom: 2px solid transparent; transition: all 0.15s; }
  .intel-tab.active { color: var(--accent); border-bottom-color: var(--accent); }
  .intel-body  { flex: 1; overflow-y: auto; padding: 12px; }
  .insight-item { background: var(--surface2); border: 1px solid var(--border); border-radius: 6px; padding: 10px 12px; margin-bottom: 8px; font-size: 12px; }
  .insight-item .ins-source { font-size: 10px; color: var(--muted); margin-bottom: 3px; }
  .insight-item .ins-msg { color: var(--text); line-height: 1.4; }
  .insight-item .ins-detail { color: var(--muted); font-size: 11px; margin-top: 4px; }
  .sev-warning  { border-left: 3px solid var(--yellow); }
  .sev-critical { border-left: 3px solid var(--red); }
  .sev-info     { border-left: 3px solid var(--border); }
  .sev-success  { border-left: 3px solid var(--green); }
  /* ── Ask Continum ── */
  .ask-panel { padding: 12px; border-top: 1px solid var(--border); }
  .ask-input-row { display: flex; gap: 8px; }
  .ask-input { flex: 1; background: var(--surface2); border: 1px solid var(--border); color: var(--text); border-radius: 6px; padding: 8px 12px; font-size: 13px; }
  .ask-input:focus { outline: none; border-color: var(--accent); }
  .ask-btn { background: var(--purple); color: #0d1117; border: none; border-radius: 6px; padding: 8px 14px; font-size: 13px; font-weight: 600; cursor: pointer; }
  .ask-response { background: var(--surface2); border-radius: 6px; padding: 12px; margin-top: 10px; font-size: 12px; line-height: 1.6; white-space: pre-wrap; max-height: 280px; overflow-y: auto; }
  /* ── Animations ── */
  @keyframes pulse { 0%, 100% { opacity: 1; } 50% { opacity: 0.4; } }
  /* ── Phase labels ── */
  .phase-0 { color: #58a6ff; }
  .phase-1 { color: #3fb950; }
  .phase-2 { color: #d29922; }
  .phase-3 { color: #f85149; }
  .phase-4 { color: #bc8cff; }
</style>
</head>
<body>
<div class="layout">

  <!-- ══ SIDEBAR ══════════════════════════════════════════════════════════ -->
  <aside class="sidebar">
    <div class="sidebar-brand">
      <div class="os-name">PersistIQ</div>
      <div class="tagline">Experimentation Intelligence</div>
    </div>

    <div class="session-pill">
      <div class="label">Session</div>
      <div class="value">{{ session_id }}</div>
      <div class="label" style="margin-top:6px">Experiment</div>
      <div class="value" id="active-exp-display">{{ active_exp }}</div>
    </div>

    <nav class="nav-section">
      <div class="nav-section-label">Workflow</div>
      <a class="nav-item active" href="#" onclick="showSection('dashboard')">
        <i class="icon fas fa-th-large"></i> Dashboard
      </a>
      <a class="nav-item" href="#" onclick="showSection('discovery')">
        <i class="icon fas fa-search"></i> Discovery
        {% if 'schema_discovery' in [h.module for h in history] %}<span class="badge-dot"></span>{% endif %}
      </a>
      <a class="nav-item" href="#" onclick="showSection('planning')">
        <i class="icon fas fa-clipboard-list"></i> Planning
      </a>
      <a class="nav-item" href="#" onclick="showSection('monitoring')">
        <i class="icon fas fa-heartbeat"></i> Monitoring
        {% if warnings %}<span class="badge-warn"></span>{% endif %}
      </a>
      <a class="nav-item" href="#" onclick="showSection('causal')">
        <i class="icon fas fa-flask"></i> Analysis
        {% if 'experiment_analysis' in [h.module for h in history] %}<span class="badge-dot"></span>{% endif %}
      </a>
    </nav>

    <nav class="nav-section">
      <div class="nav-section-label">Tools</div>
      <a class="nav-item" href="#" onclick="showSection('compare')">
        <i class="icon fas fa-columns"></i> Compare
      </a>
      <a class="nav-item" href="#" onclick="showSection('memory')">
        <i class="icon fas fa-database"></i> Memory
        <small style="margin-left:auto;color:var(--muted)">{{ n_memory }}</small>
      </a>
      <a class="nav-item" href="#" onclick="showSection('session')">
        <i class="icon fas fa-history"></i> Lineage
      </a>
    </nav>

    <div style="margin-top:auto; padding:16px; font-size:11px; color:var(--muted)">
      {{ n_runs }} run{{ 's' if n_runs != 1 else '' }}
      &nbsp;·&nbsp; {{ active_metrics }}
    </div>
  </aside>

  <!-- ══ MAIN ═════════════════════════════════════════════════════════════ -->
  <main class="main">
    <!-- Top bar -->
    <div class="topbar">
      <div class="exp-selector">
        <select id="exp-select" onchange="selectExperiment(this.value)">
          <option value="">— Select experiment —</option>
        </select>
      </div>
      <button class="run-btn" id="run-btn" onclick="runSelected()">
        <i class="fas fa-play"></i>&nbsp; Run
      </button>
    </div>

    <!-- Content -->
    <div class="content" id="content-area">

      <!-- ── Workflow cards ── -->
      <div id="section-dashboard">
        <div class="section-title">Workflow Modules</div>
        <div class="workflow-grid" id="module-grid">
          <!-- populated by JS -->
        </div>

        <!-- Execution console -->
        <div class="console-panel">
          <div class="console-header">
            <div class="dot" id="console-dot"></div>
            <span>Execution Console</span>
            <span style="margin-left:auto;font-size:11px" id="console-status">Idle</span>
          </div>
          <div class="console-body" id="console-body">
            <div class="log-line log-INFO">PersistIQ ready.</div>
          </div>
        </div>

        <!-- Run history -->
        <div class="section-title">Run History</div>
        <div class="surface" style="background:var(--surface);border:1px solid var(--border);border-radius:8px;overflow:hidden">
          <table class="history-table">
            <thead>
              <tr><th>Module</th><th>Status</th><th>Duration</th><th>Summary</th></tr>
            </thead>
            <tbody id="history-body">
              {% for h in history %}
              <tr>
                <td style="font-family:monospace;color:var(--accent)">{{ h.module }}</td>
                <td><span class="{{ 'badge-ok' if h.ok else 'badge-fail' }}">{{ 'OK' if h.ok else 'FAIL' }}</span></td>
                <td style="color:var(--muted)">{{ h.elapsed }}s</td>
                <td style="color:var(--muted)">{{ h.summary }}</td>
              </tr>
              {% else %}
              <tr><td colspan="4" style="color:var(--muted);text-align:center;padding:20px">No runs yet — select a module above</td></tr>
              {% endfor %}
            </tbody>
          </table>
        </div>
      </div>

      <!-- ── Compare section ── -->
      <div id="section-compare" style="display:none">
        <div class="section-title">Comparative Analysis</div>
        <div style="background:var(--surface);border:1px solid var(--border);border-radius:8px;padding:20px">
          <div class="row g-3 mb-3">
            <div class="col">
              <label style="font-size:12px;color:var(--muted)">Experiment A</label>
              <select id="cmp-a" class="form-select" style="background:var(--surface2);border:1px solid var(--border);color:var(--text);font-size:13px">
                <option value="">Select…</option>
              </select>
            </div>
            <div class="col">
              <label style="font-size:12px;color:var(--muted)">Experiment B</label>
              <select id="cmp-b" class="form-select" style="background:var(--surface2);border:1px solid var(--border);color:var(--text);font-size:13px">
                <option value="">Select…</option>
              </select>
            </div>
          </div>
          <button class="run-btn" onclick="runCompare()"><i class="fas fa-columns"></i>&nbsp; Compare</button>
          <div id="compare-result" style="margin-top:20px"></div>
        </div>
      </div>

      <!-- ── Memory section ── -->
      <div id="section-memory" style="display:none">
        <div class="section-title">Cross-Experiment Memory</div>
        <div style="background:var(--surface);border:1px solid var(--border);border-radius:8px;padding:20px;font-size:13px">
          <p style="color:var(--muted)">{{ n_memory }} experiment(s) in persistent memory.</p>
          {% if n_memory == 0 %}
          <p style="color:var(--muted)">Run modules to populate memory. Results are stored automatically.</p>
          {% endif %}
          {% for r in session_recs %}
          <div class="insight-item sev-info">
            <div class="ins-source">Workflow recommendation</div>
            <div class="ins-msg">{{ r.action }}</div>
            <div class="ins-detail">{{ r.reason }}</div>
          </div>
          {% endfor %}
        </div>
      </div>

      <!-- ── Session lineage section ── -->
      <div id="section-session" style="display:none">
        <div class="section-title">Session Lineage</div>
        <div style="background:var(--surface);border:1px solid var(--border);border-radius:8px;overflow:hidden">
          <table class="history-table">
            <thead><tr><th>Run ID</th><th>Module</th><th>Phase</th><th>Status</th><th>Duration</th></tr></thead>
            <tbody>
              {% for h in history %}
              <tr>
                <td style="font-family:monospace;color:var(--muted);font-size:11px">{{ loop.index }}</td>
                <td style="color:var(--accent);font-family:monospace">{{ h.module }}</td>
                <td style="color:var(--muted)">{{ h.module }}</td>
                <td><span class="{{ 'badge-ok' if h.ok else 'badge-fail' }}">{{ 'OK' if h.ok else 'FAIL' }}</span></td>
                <td style="color:var(--muted)">{{ h.elapsed }}s</td>
              </tr>
              {% endfor %}
            </tbody>
          </table>
        </div>
      </div>

      <!-- Dynamic phase sections -->
      {% for phase in ['discovery','planning','monitoring','causal'] %}
      <div id="section-{{ phase }}" style="display:none">
        <div class="section-title">{{ phase | title }} Modules</div>
        <div class="workflow-grid" id="grid-{{ phase }}"></div>
      </div>
      {% endfor %}

    </div>
  </main>

  <!-- ══ INTELLIGENCE PANEL ════════════════════════════════════════════════ -->
  <aside class="intel-panel">
    <div class="intel-tabs">
      <div class="intel-tab active" onclick="switchTab('insights')">Insights</div>
      <div class="intel-tab" onclick="switchTab('warnings')">Warnings{% if warnings %} <span style="color:var(--yellow)">({{ warnings|length }})</span>{% endif %}</div>
      <div class="intel-tab" onclick="switchTab('recs')">Next Steps</div>
    </div>
    <div class="intel-body" id="intel-insights">
      {% if insights %}
        {% for i in insights %}
        <div class="insight-item sev-{{ i.severity }}">
          <div class="ins-source">{{ i.source }}</div>
          <div class="ins-msg">{{ i.message }}</div>
          {% if i.detail %}<div class="ins-detail">{{ i.detail }}</div>{% endif %}
        </div>
        {% endfor %}
      {% else %}
        <div style="color:var(--muted);font-size:12px;padding:20px;text-align:center">
          Run modules to generate insights
        </div>
      {% endif %}
    </div>
    <div class="intel-body" id="intel-warnings" style="display:none">
      {% if warnings %}
        {% for i in warnings %}
        <div class="insight-item sev-{{ i.severity }}">
          <div class="ins-source">{{ i.source }}</div>
          <div class="ins-msg">{{ i.message }}</div>
          {% if i.detail %}<div class="ins-detail">{{ i.detail }}</div>{% endif %}
        </div>
        {% endfor %}
      {% else %}
        <div style="color:var(--green);font-size:12px;padding:20px;text-align:center">✅ No warnings</div>
      {% endif %}
    </div>
    <div class="intel-body" id="intel-recs" style="display:none">
      {% if recs %}
        {% for r in recs %}
        <div class="insight-item sev-info">
          <div class="ins-source">{{ r.source }}</div>
          <div class="ins-msg">{{ r.message }}</div>
          {% if r.detail %}<div class="ins-detail">{{ r.detail }}</div>{% endif %}
        </div>
        {% endfor %}
      {% else %}
        <div style="color:var(--muted);font-size:12px;padding:20px;text-align:center">No recommendations yet</div>
      {% endif %}
    </div>

    <!-- ── Ask Continum ── -->
    <div class="ask-panel">
      <div style="font-size:11px;color:var(--muted);text-transform:uppercase;letter-spacing:1px;margin-bottom:8px">
        <i class="fas fa-comment-dots"></i> Ask Continum
      </div>
      <div class="ask-input-row">
        <input class="ask-input" id="ask-input" placeholder="Why did conversion drop?" onkeydown="if(event.key==='Enter')sendAsk()">
        <button class="ask-btn" onclick="sendAsk()"><i class="fas fa-paper-plane"></i></button>
      </div>
      <div class="ask-response" id="ask-response" style="display:none"></div>
    </div>
  </aside>

</div>

<script>
// ── Module definitions for the UI ─────────────────────────────────────────
const PHASE_MODULES = {
  dashboard: [
    {icon:"🔍",name:"Schema Discovery",  key:"schema_discovery",  phase:"phase_0"},
    {icon:"✅",name:"Data Validation",    key:"data_validation",    phase:"phase_0"},
    {icon:"📋",name:"Opportunity Sizing", key:"opportunity_sizing", phase:"phase_1"},
    {icon:"⚡",name:"Power Calculator",   key:"power_calculator",   phase:"phase_1"},
    {icon:"📄",name:"Brief Generator",    key:"brief_generator",    phase:"phase_1"},
    {icon:"🩺",name:"Health Monitor",     key:"health_monitor",     phase:"phase_2"},
    {icon:"🔬",name:"A/B Readout",        key:"experiment_analysis",phase:"phase_2"},
    {icon:"🔗",name:"Causal Analysis",    key:"causal_analysis",    phase:"phase_3"},
    {icon:"🔀",name:"Segment Analysis",   key:"simpsons_paradox",   phase:"phase_3"},
    {icon:"💰",name:"ROI Tracker",        key:"roi_tracker",        phase:"phase_3"},
    {icon:"🧠",name:"Learnings Repo",     key:"learnings_repository",phase:"phase_3"},
    {icon:"🚀",name:"Uplift Modeller",    key:"uplift_modeller",    phase:"phase_4"},
  ],
  discovery: [
    {icon:"🔍",name:"Schema Discovery",key:"schema_discovery",phase:"phase_0"},
    {icon:"✅",name:"Data Validation", key:"data_validation", phase:"phase_0"},
    {icon:"📐",name:"Dimension Setup", key:"dimension_setup", phase:"phase_0"},
    {icon:"❤️",name:"Pipeline Health",key:"pipeline_health", phase:"phase_0"},
    {icon:"👁️",name:"Watchtower",      key:"watchtower",      phase:"phase_0"},
  ],
  planning: [
    {icon:"📄",name:"Brief Generator",   key:"brief_generator",    phase:"phase_1"},
    {icon:"📋",name:"Opportunity Sizing",key:"opportunity_sizing",  phase:"phase_1"},
    {icon:"⚡",name:"Power Calculator",  key:"power_calculator",    phase:"phase_1"},
    {icon:"📊",name:"KPI & Tracking",   key:"metrics_and_tracking",phase:"phase_1"},
    {icon:"👥",name:"Audience Selection",key:"audience_selection",  phase:"phase_1"},
  ],
  monitoring: [
    {icon:"🩺",name:"Health Monitor",      key:"health_monitor",    phase:"phase_2"},
    {icon:"📈",name:"Sequential Testing",  key:"sequential_testing",phase:"phase_2"},
    {icon:"❤️",name:"Pipeline Health",    key:"pipeline_health",   phase:"phase_0"},
  ],
  causal: [
    {icon:"🔬",name:"A/B Readout",        key:"experiment_analysis",phase:"phase_2"},
    {icon:"🔗",name:"Causal Analysis",    key:"causal_analysis",    phase:"phase_3"},
    {icon:"📈",name:"Pre-Post",           key:"pre_post_analysis",  phase:"phase_3"},
    {icon:"🔀",name:"Simpson's Paradox",  key:"simpsons_paradox",   phase:"phase_3"},
    {icon:"💰",name:"ROI Tracker",        key:"roi_tracker",        phase:"phase_3"},
    {icon:"🧠",name:"Learnings",          key:"learnings_repository",phase:"phase_3"},
    {icon:"🚀",name:"Uplift Modeller",    key:"uplift_modeller",    phase:"phase_4"},
    {icon:"🎯",name:"Decision Engine",    key:"decision_engine",    phase:"phase_4"},
  ],
};

let selectedModule = null;
let currentSection = 'dashboard';

// ── Populate grids ─────────────────────────────────────────────────────────
function populateGrid(section, gridId) {
  const modules = PHASE_MODULES[section] || [];
  const grid    = document.getElementById(gridId);
  if (!grid) return;
  grid.innerHTML = modules.map(m => `
    <div class="wf-card" id="card-${m.key}" onclick="selectModule('${m.key}','${m.name}')">
      <div class="wf-icon">${m.icon}</div>
      <div class="wf-name">${m.name}</div>
      <div class="wf-phase ${m.phase}">${m.phase.replace('_',' ')}</div>
    </div>
  `).join('');
}

// ── Section switching ──────────────────────────────────────────────────────
function showSection(name) {
  currentSection = name;
  document.querySelectorAll('[id^="section-"]').forEach(el => el.style.display = 'none');
  const el = document.getElementById('section-' + name);
  if (el) el.style.display = 'block';
  document.querySelectorAll('.nav-item').forEach(n => n.classList.remove('active'));
  populateGrid(name, 'module-grid');
  ['discovery','planning','monitoring','causal'].forEach(p => populateGrid(p, 'grid-' + p));
  return false;
}

function selectModule(key, name) {
  selectedModule = key;
  document.querySelectorAll('.wf-card').forEach(c => c.style.borderColor = '');
  const card = document.getElementById('card-' + key);
  if (card) card.style.borderColor = 'var(--accent)';
  document.getElementById('run-btn').textContent = '▶ Run: ' + name;
}

// ── Execute a module ───────────────────────────────────────────────────────
function runSelected() {
  if (!selectedModule) { alert('Select a module first.'); return; }
  runModule(selectedModule);
}

function runModule(moduleKey) {
  const body     = document.getElementById('console-body');
  const dot      = document.getElementById('console-dot');
  const status   = document.getElementById('console-status');
  const btn      = document.getElementById('run-btn');
  const exp      = document.getElementById('exp-select').value;

  body.innerHTML = '';
  dot.classList.add('running');
  status.textContent = 'Running…';
  btn.disabled = true;

  fetch('/api/execute/' + moduleKey, {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({experiment_name: exp})
  })
  .then(r => r.json())
  .then(data => {
    const runId = data.run_id;
    const es    = new EventSource('/api/stream/' + runId);
    es.onmessage = ev => {
      const d = JSON.parse(ev.data);
      if (d.msg === '__done__') {
        es.close();
        dot.classList.remove('running');
        status.textContent = 'Done';
        btn.disabled = false;
        refreshIntelligence();
        refreshHistory();
        return;
      }
      if (d.level === 'PING') return;
      const line = document.createElement('div');
      line.className = 'log-line log-' + d.level;
      line.textContent = d.msg;
      body.appendChild(line);
      body.scrollTop = body.scrollHeight;
    };
    es.onerror = () => {
      es.close();
      dot.classList.remove('running');
      status.textContent = 'Error';
      btn.disabled = false;
    };
  })
  .catch(e => {
    dot.classList.remove('running');
    status.textContent = 'Error';
    btn.disabled = false;
    logLine('ERR', 'Request failed: ' + e);
  });
}

function logLine(level, msg) {
  const body = document.getElementById('console-body');
  const line = document.createElement('div');
  line.className = 'log-line log-' + level;
  line.textContent = msg;
  body.appendChild(line);
  body.scrollTop = body.scrollHeight;
}

// ── Intelligence tabs ──────────────────────────────────────────────────────
function switchTab(tab) {
  ['insights','warnings','recs'].forEach(t => {
    document.getElementById('intel-' + t).style.display = t === tab ? 'block' : 'none';
  });
  document.querySelectorAll('.intel-tab').forEach((el, i) => {
    el.classList.toggle('active', ['insights','warnings','recs'][i] === tab);
  });
}

function refreshIntelligence() {
  fetch('/api/intelligence')
    .then(r => r.json())
    .then(data => {
      const renderItems = (list) => list.map(i => `
        <div class="insight-item sev-${i.severity}">
          <div class="ins-source">${i.source}</div>
          <div class="ins-msg">${i.message}</div>
          ${i.detail ? `<div class="ins-detail">${i.detail}</div>` : ''}
        </div>`).join('');
      document.getElementById('intel-insights').innerHTML =
        data.insights.length ? renderItems(data.insights) :
        '<div style="color:var(--muted);font-size:12px;padding:20px;text-align:center">No insights yet</div>';
      document.getElementById('intel-warnings').innerHTML =
        data.warnings.length ? renderItems(data.warnings) :
        '<div style="color:var(--green);font-size:12px;padding:20px;text-align:center">✅ No warnings</div>';
      document.getElementById('intel-recs').innerHTML =
        data.recommendations.length ? renderItems(data.recommendations) :
        '<div style="color:var(--muted);font-size:12px;padding:20px;text-align:center">No recommendations yet</div>';
    }).catch(() => {});
}

function refreshHistory() {
  fetch('/api/session')
    .then(r => r.json())
    .then(data => {
      const tbody = document.getElementById('history-body');
      if (!tbody) return;
      tbody.innerHTML = data.history.map(h => `
        <tr>
          <td style="font-family:monospace;color:var(--accent)">${h.module}</td>
          <td><span class="${h.ok ? 'badge-ok' : 'badge-fail'}">${h.ok ? 'OK' : 'FAIL'}</span></td>
          <td style="color:var(--muted)">${h.elapsed}s</td>
          <td style="color:var(--muted)">${h.summary || ''}</td>
        </tr>`).join('') || '<tr><td colspan="4" style="color:var(--muted);text-align:center;padding:20px">No runs yet</td></tr>';
    }).catch(() => {});
}

// ── Experiment selector ────────────────────────────────────────────────────
function loadExperiments() {
  fetch('/api/experiments')
    .then(r => r.json())
    .then(data => {
      const sel  = document.getElementById('exp-select');
      const cmpA = document.getElementById('cmp-a');
      const cmpB = document.getElementById('cmp-b');
      const opts = data.map(e => `<option value="${e.experiment_name}">${e.experiment_name}</option>`).join('');
      const placeholder = '<option value="">— Select experiment —</option>';
      if (sel)  sel.innerHTML  = placeholder + opts;
      if (cmpA) cmpA.innerHTML = placeholder + opts;
      if (cmpB) cmpB.innerHTML = placeholder + opts;
    }).catch(() => {});
}

function selectExperiment(name) {
  if (!name) return;
  fetch('/api/session/select-experiment', {
    method: 'POST', headers: {'Content-Type':'application/json'},
    body: JSON.stringify({name})
  }).then(r => r.json()).then(d => {
    document.getElementById('active-exp-display').textContent = d.active || name;
  });
}

// ── Ask Continum ──────────────────────────────────────────────────────────
function sendAsk() {
  const input    = document.getElementById('ask-input');
  const respEl   = document.getElementById('ask-response');
  const question = input.value.trim();
  if (!question) return;

  respEl.style.display = 'block';
  respEl.textContent   = '…';

  fetch('/api/ask', {
    method: 'POST', headers: {'Content-Type':'application/json'},
    body: JSON.stringify({question})
  })
  .then(r => r.json())
  .then(d => { respEl.textContent = d.response || d.error || '(no response)'; })
  .catch(e => { respEl.textContent = 'Error: ' + e; });
  input.value = '';
}

// ── Compare ────────────────────────────────────────────────────────────────
function runCompare() {
  const a   = document.getElementById('cmp-a').value;
  const b   = document.getElementById('cmp-b').value;
  const out = document.getElementById('compare-result');
  if (!a || !b) { out.innerHTML = '<p style="color:var(--red)">Select both experiments.</p>'; return; }
  out.innerHTML = '<p style="color:var(--muted)">Running analysis…</p>';
  fetch('/api/compare', {
    method: 'POST', headers: {'Content-Type':'application/json'},
    body: JSON.stringify({experiment_a: a, experiment_b: b})
  })
  .then(r => r.json())
  .then(d => {
    if (d.error) { out.innerHTML = `<p style="color:var(--red)">${d.error}</p>`; return; }
    const ma = d.experiment_a.metrics, mb = d.experiment_b.metrics;
    out.innerHTML = `
      <table class="history-table" style="margin-bottom:16px">
        <thead><tr><th>Metric</th><th>${d.experiment_a.name}</th><th>${d.experiment_b.name}</th></tr></thead>
        <tbody>
          <tr><td>Δ (pp)</td><td>${(ma.delta_pp||0).toFixed(4)}</td><td>${(mb.delta_pp||0).toFixed(4)}</td></tr>
          <tr><td>p-value</td><td>${(ma.p_value||1).toFixed(4)}</td><td>${(mb.p_value||1).toFixed(4)}</td></tr>
          <tr><td>Significant</td><td>${ma.is_sig ? '✅ Yes':'❌ No'}</td><td>${mb.is_sig ? '✅ Yes':'❌ No'}</td></tr>
          <tr><td>Verdict</td><td>${ma.verdict||'—'}</td><td>${mb.verdict||'—'}</td></tr>
          <tr><td>Ship Decision</td><td>${(ma.ship||'—').replace(/_/g,' ').toUpperCase()}</td><td>${(mb.ship||'—').replace(/_/g,' ').toUpperCase()}</td></tr>
          <tr><td>SRM</td><td>${ma.srm ? '⚠️ Detected':'✅ Clean'}</td><td>${mb.srm ? '⚠️ Detected':'✅ Clean'}</td></tr>
        </tbody>
      </table>
      <div class="insight-item sev-info">
        <div class="ins-source">Synthesis</div>
        <div class="ins-msg" style="white-space:pre-line">${d.narrative}</div>
      </div>`;
  })
  .catch(e => { out.innerHTML = `<p style="color:var(--red)">Error: ${e}</p>`; });
}

// ── Init ───────────────────────────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', () => {
  populateGrid('dashboard', 'module-grid');
  ['discovery','planning','monitoring','causal'].forEach(p => populateGrid(p, 'grid-' + p));
  loadExperiments();
  setInterval(refreshIntelligence, 5000);  // refresh insights every 5s
});
</script>
</body>
</html>
"""
