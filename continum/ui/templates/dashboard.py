DASHBOARD = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>PersistIQ</title>
<link href="https://cdnjs.cloudflare.com/ajax/libs/bootstrap/5.3.2/css/bootstrap.min.css" rel="stylesheet">
<link href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.5.1/css/all.min.css" rel="stylesheet">
<style>
:root{
  --bg:#f0f4f8;--surf:#ffffff;--surf2:#f1f5f9;--bdr:#e2e8f0;
  --txt:#0f172a;--muted:#64748b;--acc:#2563eb;
  --grn:#16a34a;--yel:#d97706;--red:#dc2626;--pur:#7c3aed;--ora:#ea580c;--teal:#0d9488;
  /* Sidebar blue palette */
  --sb-bg:#1e3a5f;--sb-surf:rgba(255,255,255,.07);--sb-bdr:rgba(255,255,255,.12);
  --sb-txt:#f0f6ff;--sb-muted:#93c5fd;--sb-active:rgba(96,165,250,.18);--sb-acc:#60a5fa;
  /* Ask blue palette */
  --ask-bg:#1e3a5f;--ask-bdr:rgba(255,255,255,.15);--ask-inp:#16305a;
}
*{box-sizing:border-box;margin:0;padding:0}
body{background:var(--bg);color:var(--txt);font-family:'Segoe UI',system-ui,sans-serif;height:100vh;display:flex;flex-direction:column;overflow:hidden}
.layout{display:grid;grid-template-columns:200px 1fr 340px;flex:1;overflow:hidden;min-height:0}
/* ── sidebar ── */
.sb{background:var(--sb-bg);border-right:1px solid var(--sb-bdr);display:flex;flex-direction:column;overflow-y:auto;flex-shrink:0}
.sb-brand{padding:14px 16px;border-bottom:1px solid var(--sb-bdr)}
.sb-name{font-size:12px;font-weight:800;letter-spacing:2.5px;color:var(--sb-acc);text-transform:uppercase}
.sb-tag{font-size:9px;color:var(--sb-muted);margin-top:2px}
.sess-pill{margin:8px 12px;background:var(--sb-surf);border:1px solid var(--sb-bdr);border-radius:6px;padding:7px 10px}
.sl{font-size:9px;color:var(--sb-muted);text-transform:uppercase;letter-spacing:.7px}
.sv{font-size:11px;margin-top:1px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;cursor:pointer;color:var(--sb-txt)}
.sv:hover{color:var(--acc)}
.nav-lbl{font-size:9px;color:var(--sb-muted);text-transform:uppercase;letter-spacing:.7px;padding:8px 14px 3px}
.nav-a{display:flex;align-items:center;gap:8px;padding:6px 14px;font-size:11px;color:var(--sb-muted);cursor:pointer;border-left:2px solid transparent;transition:all .1s;text-decoration:none}
.nav-a:hover{background:var(--sb-surf);color:var(--sb-txt)}
.nav-a.active{color:var(--sb-acc);border-left-color:var(--sb-acc);background:var(--sb-active)}
.nav-a .ic{width:13px;text-align:center;font-size:10px}
.nb{width:5px;height:5px;border-radius:50%;margin-left:auto}
.nb-g{background:var(--grn)}.nb-y{background:var(--yel)}
/* ── main ── */
.main{display:flex;flex-direction:column;overflow:hidden}
.topbar{background:var(--surf);border-bottom:1px solid var(--bdr);padding:8px 16px;display:flex;align-items:center;gap:10px;flex-shrink:0}
.exp-sel{background:var(--surf2);border:1px solid var(--bdr);color:var(--txt);border-radius:5px;padding:4px 8px;font-size:11px;flex:1;max-width:320px}
.exp-sel:focus{outline:none;border-color:var(--acc)}
.btn-stop{background:#ef4444;color:#fff;border:none;border-radius:5px;
  padding:6px 16px;font-size:11px;font-weight:700;cursor:pointer;
  transition:background .15s}
.btn-stop:hover{background:#dc2626}
.btn-run{background:var(--acc);color:#0d1117;border:none;border-radius:5px;padding:5px 14px;font-size:11px;font-weight:700;cursor:pointer}
.btn-run:hover{opacity:.85}.btn-run:disabled{opacity:.35;cursor:not-allowed}
.btn-sm{background:var(--surf2);border:1px solid var(--bdr);border-radius:5px;padding:4px 10px;font-size:11px;cursor:pointer;color:var(--muted)}
.btn-sm:hover{color:var(--txt);border-color:var(--acc)}
.btn-fork{color:var(--pur)}.btn-snap{color:var(--muted)}
/* ── content ── */
.content{flex:1;overflow-y:auto;padding:14px 16px}
.sec-title{font-size:9px;text-transform:uppercase;letter-spacing:.7px;color:var(--muted);margin-bottom:8px;margin-top:2px}
/* ── module grid ── */
.mod-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(120px,1fr));gap:7px;margin-bottom:14px}
.mod-card{background:var(--surf);border:1px solid var(--bdr);border-radius:6px;padding:10px;cursor:pointer;transition:all .1s;position:relative}
.mod-card:hover{border-color:var(--acc);background:var(--surf2)}
.mod-card.sel{border-color:var(--acc);background:rgba(88,166,255,.07)}
.mod-card.done{border-color:var(--grn)}
.mod-card.done::after{content:"✓";position:absolute;top:5px;right:7px;font-size:8px;color:var(--grn)}
.mod-icon{font-size:16px;margin-bottom:5px}
.mod-name{font-size:10px;font-weight:600;line-height:1.3}
.mod-phase{font-size:8px;color:var(--muted);margin-top:1px}
/* ── console ── */
.console{display:block;margin-top:10px;border:1px solid var(--bdr);border-radius:6px;background:var(--surf);}
.con-hdr{padding:6px 12px;border-bottom:1px solid var(--bdr);display:flex;align-items:center;gap:7px;font-size:10px;font-weight:600;color:var(--muted)}
.con-dot{width:6px;height:6px;border-radius:50%;background:var(--bdr)}
.con-dot.run{background:var(--grn);animation:pulse 1s infinite}
.con-body{font-family:'Consolas','Fira Mono',monospace;font-size:11px;padding:10px 14px;height:420px;overflow-y:auto;background:#0d1117;border-radius:0 0 6px 6px;line-height:1.6;white-space:pre-wrap;word-break:break-all}
.log{margin:1px 0;line-height:1.5}
.log-INFO::before{content:"[INFO] ";color:#60a5fa;font-size:9px}
.log-WARN::before{content:"[WARN] ";color:#fbbf24;font-size:9px}
.log-ERR::before{content:"[ERR ] ";color:#f87171;font-size:9px}
.log-OK::before{content:"[ OK ] ";color:#4ade80;font-size:9px}
.log-DONE{color:#4ade80;font-weight:700}
.log-PING{display:none}
.log-OUT{color:#e2e8f0}
.log-OUT::before{content:"";color:var(--muted)}
.log-SEP{color:#334155;user-select:none}
.log-OK{color:#4ade80;font-weight:700}
.log-OK::before{content:"[  OK  ] ";color:#4ade80}
.log-ERR{color:#f87171}
.log-ERR::before{content:"[ ERR  ] ";color:#f87171}
.log-WARN{color:#fbbf24}
.log-WARN::before{content:"[ WARN ] ";color:#fbbf24}
.log-INFO{color:#93c5fd}
.log-INFO::before{content:"[ INFO ] ";color:#93c5fd}
.log-FILES{color:#a78bfa;font-weight:700}
.log-FILES::before{content:"[ OUT  ] ";color:#a78bfa}
.log-FILE{color:#60a5fa;text-decoration:underline;cursor:pointer}
.log-FILE::before{content:"[ FILE ] ";color:#60a5fa}
.log-INSIGHT{color:#34d399}
.log-INSIGHT::before{content:"[ 💡   ] ";color:#34d399}
.log-NEXT{color:#a78bfa}
.log-NEXT::before{content:"[ →    ] ";color:#a78bfa}
.log-SUMMARY{color:#fbbf24;font-weight:600;font-size:12px}
.log-SUMMARY::before{content:"[ SUM  ] ";color:#fbbf24}
.con-status-run{color:#60a5fa;animation:pulse 1s infinite}
.con-status-ok{color:#4ade80}
.con-status-err{color:#f87171}
.out-line-hdr{color:#7c3aed;font-weight:700}
.out-line-positive{color:#4ade80}
.out-line-negative{color:#f87171}
.out-line-warn{color:#fbbf24}
.out-line-box{color:#60a5fa}
.file-badge{display:inline-block;background:rgba(96,165,250,.12);border:1px solid rgba(96,165,250,.3);border-radius:4px;padding:2px 8px;margin:2px 0;font-size:10px;color:#60a5fa;text-decoration:none}
.file-badge:hover{background:rgba(96,165,250,.2)}
.con-files{padding:8px 14px;background:#0d1117;border-top:1px solid #1e293b;display:none}
.con-files-title{font-size:9px;color:#64748b;text-transform:uppercase;letter-spacing:.7px;margin-bottom:6px}
/* ── history ── */
.hist-table{width:100%;border-collapse:collapse;font-size:10px}
.hist-table th{padding:4px 8px;font-size:8px;text-transform:uppercase;letter-spacing:.7px;color:var(--muted);border-bottom:1px solid var(--bdr);text-align:left}
.hist-table td{padding:5px 8px;border-bottom:1px solid var(--bdr)}
.hist-table tr:last-child td{border-bottom:none}
.bok{background:rgba(63,185,80,.1);color:var(--grn);padding:1px 6px;border-radius:7px;font-size:8px}
.bfail{background:rgba(248,81,73,.1);color:var(--red);padding:1px 6px;border-radius:7px;font-size:8px}
/* ── CONFIG PANEL ── */
.cfg-panel{background:var(--surf);border:1px solid var(--acc);border-radius:6px;padding:12px;margin-bottom:14px;display:none;box-shadow:0 2px 12px rgba(37,99,235,.1)}
.cfg-panel-title{font-size:10px;font-weight:700;color:var(--txt);margin-bottom:4px}
.cfg-panel-desc{font-size:9px;color:var(--muted);margin-bottom:10px}
.cfg-inp{width:100%;background:var(--surf2);border:1px solid var(--bdr);color:var(--txt);border-radius:4px;padding:4px 7px;font-size:11px}
.cfg-inp:focus{outline:none;border-color:var(--acc)}
.cfg-sel{width:100%;background:var(--surf2);border:1px solid var(--bdr);color:var(--txt);border-radius:4px;padding:4px 7px;font-size:11px}
.log-OUT{color:var(--txt)}
.log-OUT::before{content:"[    ] ";color:var(--muted);font-size:9px}
/* ── section ── */
.main-sec{display:none}.main-sec.show{display:block}
/* ── REASONING SURFACE (right panel) ── */
.rp{background:var(--surf);border-left:1px solid var(--bdr);display:flex;flex-direction:column;overflow:hidden}
.rp-tabs{display:flex;border-bottom:1px solid var(--bdr);flex-shrink:0;overflow-x:auto;scrollbar-width:none}
.rp-tabs::-webkit-scrollbar{display:none}
.rp-tab{padding:7px 11px;font-size:10px;cursor:pointer;color:var(--muted);border-bottom:2px solid transparent;white-space:nowrap;transition:all .1s}
.rp-tab.active{color:var(--acc);border-bottom-color:var(--acc)}
.rp-body{flex:1;overflow-y:auto;padding:0}
.rp-panel{display:none;height:100%}.rp-panel.show{display:flex;flex-direction:column}
/* ── NARRATIVE STREAM ── */
.narr-stream{flex:1;overflow-y:auto;padding:12px}
.narr-item{padding:8px 0;border-bottom:1px solid var(--bdr);animation:fadein .4s ease}
.narr-item:last-child{border-bottom:none}
.narr-src{font-size:8px;color:var(--muted);text-transform:uppercase;letter-spacing:.6px;margin-bottom:3px}
.narr-txt{font-size:12px;color:var(--txt);line-height:1.5}
.narr-ts{font-size:8px;color:var(--muted);margin-top:2px}
.narr-empty{padding:20px;text-align:center;color:var(--muted);font-size:11px}
/* ── INSIGHTS ── */
.ins-item{background:var(--surf2);border:1px solid var(--bdr);border-radius:5px;padding:7px 9px;margin:8px;font-size:10px}
.ins-src{font-size:8px;color:var(--muted);text-transform:uppercase;letter-spacing:.5px;margin-bottom:2px}
.ins-msg{color:var(--txt);line-height:1.4}
.ins-det{color:var(--muted);font-size:9px;margin-top:2px}
.sev-warning{border-left:2px solid var(--yel)}.sev-critical{border-left:2px solid var(--red)}
.sev-info{border-left:2px solid var(--bdr)}.sev-success{border-left:2px solid var(--grn)}
/* ── ASK CONTINUM ── */
.ask-wrap{padding:10px;border-top:1px solid var(--sb-bdr);flex-shrink:0;background:var(--ask-bg);border-radius:0 0 0 0}
.ask-lbl{font-size:8px;color:var(--sb-muted);text-transform:uppercase;letter-spacing:.7px;margin-bottom:6px}
.ask-row{display:flex;gap:5px}
.ask-in{flex:1;background:var(--ask-inp);border:1px solid var(--sb-bdr);color:var(--sb-txt);border-radius:5px;padding:5px 8px;font-size:11px}
.ask-in:focus{outline:none;border-color:var(--sb-acc)}
.ask-sub{background:var(--pur);color:#0d1117;border:none;border-radius:5px;padding:5px 10px;font-size:11px;font-weight:700;cursor:pointer}
.ask-resp{padding:8px;margin:0 8px 8px;background:var(--ask-inp);border-radius:5px;font-size:11px;line-height:1.6;white-space:pre-wrap;max-height:200px;overflow-y:auto;display:none;border:1px solid var(--sb-bdr);color:var(--sb-txt)}
/* ── INSPECT PANEL ── */
.insp-btns{display:grid;grid-template-columns:1fr 1fr;gap:5px;padding:10px}
.insp-btn{background:var(--surf2);border:1px solid var(--bdr);border-radius:5px;padding:7px;font-size:10px;cursor:pointer;color:var(--muted);text-align:left}
.insp-btn:hover{border-color:var(--acc);color:var(--txt)}
.insp-result{font-family:monospace;font-size:10px;background:var(--surf2);margin:0 10px 10px;border-radius:5px;padding:8px;white-space:pre-wrap;max-height:300px;overflow-y:auto;border:1px solid var(--bdr);line-height:1.4}
/* ── SESSION TREE ── */
.tree{padding:10px;font-size:10px;font-family:monospace;overflow-y:auto;max-height:400px}
.tree-node{cursor:pointer;user-select:none}
.tree-key{color:var(--acc)}.tree-val{color:var(--grn)}.tree-str{color:var(--ora)}
.tree-null{color:var(--muted)}.tree-bool{color:var(--pur)}
.tree-children{margin-left:16px;border-left:1px solid var(--bdr);padding-left:6px}
/* ── WORKFLOW GRAPH ── */
.graph-wrap{padding:10px;overflow:auto}
.wf-graph{display:grid;gap:6px}
.wf-row{display:flex;align-items:center;gap:6px;justify-content:center}
.wf-node{background:var(--surf2);border:1px solid var(--bdr);border-radius:5px;padding:5px 9px;font-size:9px;text-align:center;min-width:80px;transition:all .1s;cursor:pointer}
.wf-node:hover{border-color:var(--acc)}
.wf-node.done{border-color:var(--grn);background:rgba(63,185,80,.07)}
.wf-node.running{border-color:var(--acc);animation:pulse .8s infinite}
.wf-node.failed{border-color:var(--red);background:rgba(248,81,73,.07)}
.wf-node .wn-icon{font-size:13px;display:block;margin-bottom:2px}
.wf-node .wn-name{font-size:8px;color:var(--muted)}
.wf-arrow{color:var(--bdr);font-size:10px}
/* ── COMPARE ── */
.cmp-sel{background:var(--surf2);border:1px solid var(--bdr);color:var(--txt);border-radius:5px;padding:4px 7px;font-size:10px;width:100%}
.cmp-table{width:100%;border-collapse:collapse;font-size:10px;margin-top:7px}
.cmp-table th{padding:3px 7px;font-size:8px;text-transform:uppercase;color:var(--muted);border-bottom:1px solid var(--bdr);text-align:left}
.cmp-table td{padding:4px 7px;border-bottom:1px solid var(--bdr)}
/* ── REASONING CHAIN ── */
.chain-item{padding:7px 10px;border-bottom:1px solid var(--bdr);font-size:10px}
.chain-src{font-size:8px;color:var(--muted);margin-bottom:2px}
.chain-claim{color:var(--txt)}
.chain-bar{height:3px;border-radius:2px;margin-top:4px;background:var(--bdr)}
.chain-bar-fill{height:100%;border-radius:2px;transition:width .3s}
.chain-supports .chain-bar-fill{background:var(--grn)}
.chain-contradicts .chain-bar-fill{background:var(--red)}
.chain-uncertain .chain-bar-fill{background:var(--yel)}
/* ── LINEAGE / AUDIT ── */
.lin-row{display:flex;align-items:center;gap:6px;padding:5px 10px;border-bottom:1px solid var(--bdr);font-size:10px}
.lin-row:last-child{border-bottom:none}
/* ── PATTERNS ── */
.pat-metric{padding:6px 10px;border-bottom:1px solid var(--bdr);font-size:10px;display:flex;align-items:center;gap:8px}
.pat-bar{height:4px;border-radius:2px;background:var(--acc);flex-shrink:0}
/* ── PROCESSING OVERLAY ── */
.proc-overlay{position:fixed;inset:0;z-index:9000;display:none;align-items:center;justify-content:center;backdrop-filter:blur(5px) brightness(.96);-webkit-backdrop-filter:blur(5px) brightness(.96);background:rgba(15,23,42,.15)}
.proc-overlay.active{display:flex}
.proc-card{background:#fff;border-radius:14px;padding:28px 36px;box-shadow:0 8px 48px rgba(30,58,95,.22);text-align:center;min-width:300px;max-width:420px;border:1px solid #e2e8f0}
.proc-icon{width:52px;height:52px;border-radius:50%;background:linear-gradient(135deg,#1e3a5f,#2563eb);margin:0 auto 16px;display:flex;align-items:center;justify-content:center;animation:proc-pulse 1.6s ease-in-out infinite}
.proc-icon svg{width:26px;height:26px;stroke:#fff;fill:none;stroke-width:2.5;stroke-linecap:round}
.proc-title{font-size:14px;font-weight:700;color:#0f172a;margin-bottom:6px}
.proc-module{font-size:11px;color:#2563eb;font-weight:600;margin-bottom:10px}
.proc-status{font-size:11px;color:#64748b;min-height:32px;line-height:1.5;max-width:340px}
.proc-bar{height:3px;background:#e2e8f0;border-radius:2px;margin-top:14px;overflow:hidden}
.proc-bar-fill{height:100%;background:linear-gradient(90deg,#1e3a5f,#2563eb,#60a5fa);background-size:200% 100%;animation:proc-shimmer 1.4s linear infinite;border-radius:2px;width:100%}
/* ── animations ── */
@keyframes proc-pulse{0%,100%{box-shadow:0 0 0 0 rgba(37,99,235,.35)}50%{box-shadow:0 0 0 10px rgba(37,99,235,0)}}
@keyframes proc-shimmer{0%{background-position:200% 0}100%{background-position:-200% 0}}
@keyframes pulse{0%,100%{opacity:1}50%{opacity:.3}}
@keyframes fadein{from{opacity:0;transform:translateY(-4px)}to{opacity:1;transform:translateY(0)}}
</style>
</head>
<body>
<div class="layout">
<!-- ══ SIDEBAR ═══════════════════════════════════════════════════════ -->
<aside class="sb">
  <div class="sb-brand">
    <div class="sb-name">PersistIQ</div>
    <div class="sb-tag">Experimentation Intelligence</div>
  </div>
  <div class="sess-pill">
    <div class="sl">Session</div>
    <div class="sv" id="sb-session" onclick="showRight('tree')">{{ session_id }}</div>
    <div class="sl" style="margin-top:5px">Experiment</div>
    <div class="sv" id="sb-exp">{{ active_exp }}</div>
    <div class="sl" style="margin-top:5px">Metrics</div>
    <div class="sv" id="sb-metrics">{{ active_metrics }}</div>
  </div>

  <div class="nav-lbl">Workflow</div>
  <a class="nav-a" onclick="goHome()" id="nav-home"><i class="ic fas fa-home"></i>Home</a>
  <a class="nav-a active" id="nav-dashboard" onclick="showMain('dashboard')"><i class="ic fas fa-th-large"></i>Dashboard</a>
  <a class="nav-a" onclick="showMain('discovery')"><i class="ic fas fa-search"></i>Discovery</a>
  <a class="nav-a" onclick="showMain('planning')"><i class="ic fas fa-clipboard-list"></i>Planning</a>
  <a class="nav-a" onclick="showMain('monitoring')"><i class="ic fas fa-heartbeat"></i>Monitoring<span class="nb nb-y" id="warn-dot" style="display:none"></span></a>
  <a class="nav-a" onclick="showMain('analysis')"><i class="ic fas fa-flask"></i>Analysis<span class="nb nb-g" id="analysis-dot" style="display:none"></span></a>

  <div class="nav-lbl">Surfaces</div>
  <a class="nav-a" onclick="showRight('reasoning')"><i class="ic fas fa-brain"></i>Reasoning</a>
  <a class="nav-a" onclick="showRight('graph')"><i class="ic fas fa-project-diagram"></i>Workflow Graph</a>
  <a class="nav-a" onclick="showRight('compare')"><i class="ic fas fa-columns"></i>Compare</a>
  <a class="nav-a" onclick="showRight('patterns')"><i class="ic fas fa-chart-line"></i>Patterns</a>
  <a class="nav-a" onclick="showRight('inspect')"><i class="ic fas fa-microscope"></i>Inspect</a>
  <a class="nav-a" onclick="showRight('audit')"><i class="ic fas fa-shield-alt"></i>Audit</a>

  <div style="margin-top:auto;padding:10px 14px;font-size:9px;color:var(--sb-muted)">
    <span id="sb-runs">{{ n_runs }}</span> runs &nbsp;·&nbsp; <span id="sb-mem">{{ n_memory }}</span> memory
  </div>
</aside>

<!-- ══ MAIN ════════════════════════════════════════════════════════════ -->
<main class="main">
  <div class="topbar">
    <select class="exp-sel" id="exp-sel" onchange="selectExp(this.value)">
      <option value="">— Select experiment —</option>
    </select>
    <button class="btn-run" id="run-btn" onclick="runSelected()">▶ Run</button>
    <button class="btn-stop" id="stop-btn" onclick="stopRunning()"
      style="display:none;background:#ef4444;color:#fff;border:none;border-radius:5px;
             padding:6px 16px;font-size:11px;font-weight:700;cursor:pointer;
             margin-left:8px;transition:opacity .15s">⛔ Stop</button>
    <button class="btn-sm btn-fork" onclick="forkSession()" title="Fork session"><i class="fas fa-code-branch"></i> Fork</button>
    <button class="btn-sm btn-snap" onclick="takeSnapshot()" title="Snapshot"><i class="fas fa-camera"></i></button>
    <div id="llm-status-pill" onclick="toggleLLM()" title="Click to load/unload LLM"
         style="display:flex;align-items:center;gap:5px;padding:4px 10px;border-radius:5px;cursor:pointer;
                background:var(--surf2);border:1px solid var(--bdr);font-size:10px;color:var(--muted)">
      <span id="llm-dot" style="width:7px;height:7px;border-radius:50%;background:var(--bdr)"></span>
      <span id="llm-label">LLM</span>
    </div>
  </div>

  <div class="content" id="main-content">
    <!-- Config panel: GLOBAL — always accessible regardless of active section -->
    <div class="cfg-panel" id="config-panel">
      <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:6px">
        <div>
          <div class="cfg-panel-title" id="config-title">Module Configuration</div>
          <div class="cfg-panel-desc" id="config-desc"></div>
        </div>
        
      </div>
      <div id="config-form"></div>
    </div>

    <div class="main-sec show" id="sec-dashboard">
      <div class="sec-title">Modules</div>
      <div class="mod-grid" id="grid-dashboard"></div>

      <div class="console" id="console-panel">
        <div class="con-hdr" style="cursor:pointer" onclick="toggleConsole()">
          <div class="con-dot" id="con-dot"></div>
          <span id="con-module-label" style="font-weight:600;color:var(--acc)">Analytics Console</span>
          <span id="con-status" style="margin-left:auto;font-size:9px;color:var(--muted)">Idle</span>
          <span id="con-timer" style="margin-left:8px;font-size:9px;font-family:monospace;color:var(--muted)"></span>
          <span style="margin-left:8px;font-size:10px;color:var(--muted)" id="con-collapse-btn">▾</span>
        </div>
        <div class="con-body" id="con-body">
          <div class="log log-INFO">PersistIQ ready. Select a module and click ▶ Run.</div>
        </div>
        <div class="con-files" id="con-files">
          <div class="con-files-title">Output Files</div>
          <div id="con-files-list"></div>
        </div>
      </div>
      <div class="sec-title">Run History</div>
      <div style="background:var(--surf);border:1px solid var(--bdr);border-radius:6px;overflow:hidden">
        <table class="hist-table">
          <thead><tr><th>Module</th><th>Status</th><th>Phase</th><th>Duration</th><th>Summary</th></tr></thead>
          <tbody id="hist-body"><tr><td colspan="5" style="text-align:center;color:var(--muted);padding:14px">No runs yet</td></tr></tbody>
        </table>
      </div>
    </div>
    <div class="main-sec" id="sec-discovery"><div class="sec-title">Discovery</div><div class="mod-grid" id="grid-discovery"></div></div>
    <div class="main-sec" id="sec-planning"><div class="sec-title">Planning</div><div class="mod-grid" id="grid-planning"></div></div>
    <div class="main-sec" id="sec-monitoring"><div class="sec-title">Monitoring</div><div class="mod-grid" id="grid-monitoring"></div></div>
    <div class="main-sec" id="sec-analysis"><div class="sec-title">Analysis</div><div class="mod-grid" id="grid-analysis"></div></div>
  </div>
</main>

<!-- ══ REASONING SURFACE (right panel) ════════════════════════════════ -->
<aside class="rp">
  <div class="rp-tabs">
    <div class="rp-tab active" onclick="showRight('reasoning')">Reasoning</div>
    <div class="rp-tab" onclick="showRight('insights')">Insights</div>
    <div class="rp-tab" onclick="showRight('compare')">Compare</div>
    <div class="rp-tab" onclick="showRight('graph')">Graph</div>
    <div class="rp-tab" onclick="showRight('patterns')">Patterns</div>
    <div class="rp-tab" onclick="showRight('inspect')">Inspect</div>
    <div class="rp-tab" onclick="showRight('tree')">Session</div>
    <div class="rp-tab" onclick="showRight('audit')">Audit</div>
  </div>
  <div class="rp-body">

    <!-- REASONING: continuous narrative stream + ask -->
    <div class="rp-panel show" id="rp-reasoning" style="flex-direction:column">
      <div class="narr-stream" id="narr-stream">
        <div class="narr-empty">Loading reasoning stream…</div>
      </div>
      <!-- Ask Continum integrated into reasoning surface -->
      <div class="ask-wrap">
        <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:6px">
          <div class="ask-lbl"><i class="fas fa-comment-dots"></i> Ask Continum</div>
          <div style="font-size:7px; color:var(--sb-muted); border:1px solid var(--sb-bdr); border-radius:3px; padding:1px 4px; background:var(--sb-surf)">Unified Engine</div>
        </div>
        <div style="display:flex;flex-wrap:wrap;gap:3px;margin-bottom:5px">
          <button onclick="quickAsk('What is the current IOR and AOV?')" style="background:var(--ask-inp);border:1px solid var(--sb-bdr);color:var(--sb-muted);border-radius:3px;padding:2px 6px;font-size:9px;cursor:pointer;white-space:nowrap">📊 IOR &amp; AOV</button>
          <button onclick="quickAsk('Is the experiment significant? Show me the result.')" style="background:var(--ask-inp);border:1px solid var(--sb-bdr);color:var(--sb-muted);border-radius:3px;padding:2px 6px;font-size:9px;cursor:pointer;white-space:nowrap">🔬 Significant?</button>
          <button onclick="quickAsk('What should I run next?')" style="background:var(--ask-inp);border:1px solid var(--sb-bdr);color:var(--sb-muted);border-radius:3px;padding:2px 6px;font-size:9px;cursor:pointer;white-space:nowrap">→ Next step</button>
          <button onclick="quickAsk('Show me the segment breakdown')" style="background:var(--ask-inp);border:1px solid var(--sb-bdr);color:var(--sb-muted);border-radius:3px;padding:2px 6px;font-size:9px;cursor:pointer;white-space:nowrap">📋 Segments</button>
          <button onclick="quickAsk('Are there any anomalies or guardrail violations?')" style="background:var(--ask-inp);border:1px solid var(--sb-bdr);color:var(--sb-muted);border-radius:3px;padding:2px 6px;font-size:9px;cursor:pointer;white-space:nowrap">⚠️ Anomalies</button>
        </div>
        <div class="ask-row">
          <input class="ask-in" id="ask-in" placeholder="Why did conversion drop? What next?" onkeydown="if(event.key==='Enter')sendAsk()">
          <button class="ask-sub" onclick="sendAsk()"><i class="fas fa-paper-plane"></i></button>
        </div>
        <div class="ask-resp" id="ask-resp"></div>
        <div id="chain-panel" style="display:none;margin-top:8px"></div>
      </div>
    </div>

    <!-- INSIGHTS -->
    <div class="rp-panel" id="rp-insights">
      <div id="ins-tabs" style="display:flex;border-bottom:1px solid var(--bdr);flex-shrink:0">
        <span style="padding:6px 10px;font-size:10px;cursor:pointer;color:var(--acc);border-bottom:2px solid var(--acc)" onclick="loadInsights('all')">All</span>
        <span style="padding:6px 10px;font-size:10px;cursor:pointer;color:var(--muted)" onclick="loadInsights('warnings')">Warnings</span>
        <span style="padding:6px 10px;font-size:10px;cursor:pointer;color:var(--muted)" onclick="loadInsights('recs')">Next Steps</span>
      </div>
      <div id="ins-list" style="flex:1;overflow-y:auto">
        <div style="color:var(--muted);font-size:10px;padding:16px;text-align:center">Run modules to generate insights</div>
      </div>
    </div>

    <!-- COMPARE -->
    <div class="rp-panel" id="rp-compare">
      <div style="padding:10px">
        <div class="sec-title">Comparative Analysis</div>
        <div style="margin-bottom:5px"><div style="font-size:9px;color:var(--muted);margin-bottom:3px">Experiment A</div><select class="cmp-sel" id="cmp-a"><option value="">Select…</option></select></div>
        <div style="margin-bottom:8px"><div style="font-size:9px;color:var(--muted);margin-bottom:3px">Experiment B</div><select class="cmp-sel" id="cmp-b"><option value="">Select…</option></select></div>
        <button class="btn-run" style="width:100%;font-size:10px" onclick="runCompare()">Compare</button>
        <div id="cmp-result" style="margin-top:10px"></div>
      </div>
    </div>

    <!-- WORKFLOW GRAPH -->
    <div class="rp-panel" id="rp-graph">
      <div class="graph-wrap" id="graph-content"></div>
    </div>

    <!-- PATTERNS -->
    <div class="rp-panel" id="rp-patterns">
      <div style="flex:1;overflow-y:auto">
        <div style="padding:10px" id="patterns-content">
          <div style="color:var(--muted);font-size:10px;text-align:center;padding:16px">Click to load patterns</div>
        </div>
        <button class="btn-sm" style="margin:0 10px 10px;width:calc(100% - 20px)" onclick="loadPatterns()">Load Cross-Experiment Patterns</button>
      </div>
    </div>

    <!-- INSPECT -->
    <div class="rp-panel" id="rp-inspect">
      <div class="insp-btns">
        <button class="insp-btn" onclick="runInspect('session')">📋 Session</button>
        <button class="insp-btn" onclick="runInspect('semantic')">🧠 Semantic</button>
        <button class="insp-btn" onclick="runInspect('metrics')">📊 Metrics</button>
        <button class="insp-btn" onclick="runInspect('assumptions')">⚙️ Assumptions</button>
        <button class="insp-btn" onclick="runInspect('cohorts')">👥 Cohorts</button>
        <button class="insp-btn" onclick="runInspect('lineage')">🔗 Lineage</button>
      </div>
      <div class="insp-result" id="insp-result" style="display:none"></div>
    </div>

    <!-- SESSION TREE -->
    <div class="rp-panel" id="rp-tree">
      <div class="tree" id="tree-content">
        <div style="color:var(--muted);text-align:center;padding:16px;font-size:10px">Click to load session tree</div>
      </div>
      <div style="padding:8px;display:flex;gap:6px;flex-shrink:0">
        <button class="btn-sm" style="flex:1" onclick="loadTree()">Refresh Tree</button>
        <button class="btn-sm" style="flex:1;color:var(--pur)" onclick="loadForks()">View Forks</button>
      </div>
    </div>

    <!-- AUDIT -->
    <div class="rp-panel" id="rp-audit">
      <div style="flex:1;overflow-y:auto" id="audit-list">
        <div style="color:var(--muted);font-size:10px;text-align:center;padding:16px">Click to load audit trail</div>
      </div>
      <div style="padding:8px;display:flex;gap:6px;flex-shrink:0">
        <button class="btn-sm" style="flex:1" onclick="loadAudit()">Load Audit Log</button>
        <button class="btn-run" style="flex:1;font-size:10px;background:var(--grn)" onclick="requestShip()">Request Ship</button>
      </div>
    </div>

  </div>
</aside>
</div>

<script>
// ── Module definitions ─────────────────────────────────────────────────────
const MODULES = {
  dashboard:[
    {i:"🔍",n:"Schema Discovery",k:"schema_discovery",p:"discovery"},
    {i:"✅",n:"Data Validation",  k:"data_validation",  p:"discovery"},
    {i:"📋",n:"Opportunity",      k:"opportunity_sizing",p:"planning"},
    {i:"⚡",n:"Power Calc",       k:"power_calculator",  p:"planning"},
    {i:"📄",n:"Brief",            k:"brief_generator",   p:"planning"},
    {i:"🩺",n:"Health Monitor",   k:"health_monitor",    p:"monitoring"},
    {i:"🔬",n:"A/B Readout",      k:"experiment_analysis",p:"analysis"},
    {i:"🔗",n:"Causal",           k:"causal_analysis",   p:"analysis"},
    {i:"🔀",n:"Simpson's",        k:"simpsons_paradox",  p:"analysis"},
    {i:"💰",n:"ROI Tracker",      k:"roi_tracker",       p:"analysis"},
    {i:"🧠",n:"Learnings",        k:"learnings_repository",p:"analysis"},
    {i:"🚀",n:"Uplift",           k:"uplift_modeller",   p:"analysis"},
  ],
  discovery:[
    {i:"🔍",n:"Schema Discovery",k:"schema_discovery"},
    {i:"✅",n:"Data Validation", k:"data_validation"},
    {i:"📐",n:"Dimension Setup", k:"dimension_setup"},
    {i:"❤️",n:"Pipeline Health",k:"pipeline_health"},
    {i:"👁️",n:"Watchtower",      k:"watchtower"},
  ],
  planning:[
    {i:"📄",n:"Brief Generator", k:"brief_generator"},
    {i:"📋",n:"Opportunity",     k:"opportunity_sizing"},
    {i:"⚡",n:"Power Calculator",k:"power_calculator"},
    {i:"📊",n:"KPI & Tracking",  k:"metrics_and_tracking"},
    {i:"👥",n:"Audience",        k:"audience_selection"},
  ],
  monitoring:[
    {i:"🩺",n:"Health Monitor",   k:"health_monitor"},
    {i:"📈",n:"Sequential Test",  k:"sequential_testing"},
    {i:"❤️",n:"Pipeline Health", k:"pipeline_health"},
  ],
  analysis:[
    {i:"🔬",n:"A/B Readout",     k:"experiment_analysis"},
    {i:"🔗",n:"Causal Analysis", k:"causal_analysis"},
    {i:"📈",n:"Pre-Post",        k:"pre_post_analysis"},
    {i:"🔀",n:"Simpson's",       k:"simpsons_paradox"},
    {i:"💰",n:"ROI Tracker",     k:"roi_tracker"},
    {i:"🧠",n:"Learnings",       k:"learnings_repository"},
    {i:"🚀",n:"Uplift",          k:"uplift_modeller"},
    {i:"🎯",n:"Decision Engine", k:"decision_engine"},
  ],
};

let selectedMod = null;
let currentSec  = 'dashboard';
let doneSet     = new Set();

// ── Grids ──────────────────────────────────────────────────────────────────
function populateGrid(sec, gid){
  const g = document.getElementById(gid);
  if(!g) return;
  g.innerHTML = (MODULES[sec]||[]).map(m=>`
    <div class="mod-card${doneSet.has(m.k)?' done':''}" id="card-${m.k}" onclick="selectMod('${m.k}','${m.n}')">
      <div class="mod-icon">${m.i}</div>
      <div class="mod-name">${m.n}</div>
      <div class="mod-phase">${m.p||''}</div>
    </div>`).join('');
}
function selectMod(key,name){
  selectedMod = key;
  document.querySelectorAll('.mod-card').forEach(c=>c.classList.remove('sel'));
  const card = document.getElementById('card-'+key);
  if(card) card.classList.add('sel');
  // Update BOTH run buttons
  document.getElementById('run-btn').textContent = '▶ '+name;
  const cfgBtn = null;  // removed — single run-btn only
  if(cfgBtn) cfgBtn.textContent = '▶ Run: '+name;
  // Load config form — panel is global, always visible
  loadModuleConfig(key);
}

function loadModuleConfig(key){
  const panel = document.getElementById('config-panel');
  const form  = document.getElementById('config-form');
  panel.style.display = 'none';
  form.innerHTML = '<div style="color:var(--muted);font-size:10px">Loading…</div>';
  fetch('/api/module-config/'+key)
  .then(r=>r.json())
  .then(cfg=>{
    renderConfigForm(cfg, key);
    panel.style.display = 'block';
  }).catch(()=>{ panel.style.display = 'none'; });
}

function renderConfigForm(cfg, key){
  document.getElementById('config-title').textContent = cfg.title || '';
  document.getElementById('config-desc').textContent  = cfg.description || '';
  const form = document.getElementById('config-form');
  const fields = cfg.fields || [];
  if(!fields.length){
    form.innerHTML = '<div style="font-size:10px;color:var(--muted);padding:6px 0">No configuration required — click ▶ Run.</div>';
    return;
  }
  let html = '';
  fields.forEach(f=>{
    const id = 'field_'+f.key.replace(/[^a-z0-9]/gi,'_');
    html += '<div style="margin-bottom:9px">';
    html += `<label style="font-size:9px;color:var(--muted);text-transform:uppercase;letter-spacing:.6px;display:block;margin-bottom:3px">${escapeHtml(f.label)}</label>`;
    if(f.help) html += `<div style="font-size:9px;color:var(--teal);margin-bottom:3px">${escapeHtml(f.help)}</div>`;
    if(f.type==='select'||f.type==='experiment_select'){
      const opts = f.type==='experiment_select'
        ? (f.options||[]).map((e,i)=>`<option value="${escapeAttr(e.name)}" ${i===0?'selected':''}>
            ${escapeHtml(e.name)} (${e.n} rows, ${e.variants} variants)
          </option>`).join('')
        : (f.options||[]).map((o,i)=>{
            const v = f.option_values ? f.option_values[i] : o;
            return `<option value="${escapeAttr(v)}" ${v===String(f.default)?'selected':''}>
              ${escapeHtml(String(o))}
            </option>`;
          }).join('');
      html += `<select id="${id}" data-key="${escapeAttr(f.key)}" class="cfg-sel">${opts}</select>`;
    } else if(f.type==='text'){
      html += `<input id="${id}" data-key="${escapeAttr(f.key)}" type="text" class="cfg-inp"
               value="${escapeAttr(String(f.default||''))}"
               placeholder="${escapeAttr(f.label)}">`;
    } else {
      const step = f.type==='int' ? '1' : 'any';
      html += `<input id="${id}" data-key="${escapeAttr(f.key)}" type="number"
               class="cfg-inp" value="${f.default}" step="${step}"
               ${f.min!==undefined?'min="'+f.min+'"':''} ${f.max!==undefined?'max="'+f.max+'"':''}>`;
    }
    html += '</div>';
  });
  form.innerHTML = html;
}

function collectFormValues(){
  const fields = {};
  document.querySelectorAll('#config-form [data-key]').forEach(el=>{
    const k = el.getAttribute('data-key');
    const v = el.value.trim();
    if(k && v!=='') fields[k] = el.type==='number' ? Number(v) : v;
  });
  return fields;
}
function showMain(name){
  currentSec = name;
  document.querySelectorAll('.main-sec').forEach(e=>e.classList.remove('show'));
  const el = document.getElementById('sec-'+name);
  if(el) el.classList.add('show');
  document.querySelectorAll('.nav-a').forEach(a=>a.classList.remove('active'));
  if(MODULES[name]) populateGrid(name,'grid-'+name);
}

// ── Right panel ────────────────────────────────────────────────────────────
let _currentRunId = null;   // tracks the active run for the stop button

function stopRunning(){
  if(!_currentRunId) return;
  fetch('/api/stop/'+_currentRunId, {method:'POST'})
    .then(r=>r.json())
    .then(d=>{
      const sb = document.getElementById('stop-btn');
      const cs = document.getElementById('con-status');
      if(sb) sb.style.display='none';
      if(cs){ cs.textContent='⛔ Stopped'; cs.style.color='#f87171'; }
      addLog('WARN','⛔ Stop requested — waiting for current step to finish…');
      _currentRunId = null;
    }).catch(()=>{});
}

function goHome(){
  const conBody = document.getElementById('con-body');
  if(conBody) conBody.innerHTML = '<div class="log log-INFO">PersistIQ ready. Select a module and click ▶ Run.</div>';
  const conStatus = document.getElementById('con-status');
  if(conStatus){ conStatus.textContent='Idle'; conStatus.className=''; }
  const conDot = document.getElementById('con-dot');
  if(conDot){ conDot.className='con-dot'; conDot.style.background=''; }
  const conTimer = document.getElementById('con-timer');
  if(conTimer) conTimer.textContent='';
  const conFiles = document.getElementById('con-files');
  if(conFiles) conFiles.style.display='none';
  const cfgPanel = document.getElementById('config-panel');
  if(cfgPanel) cfgPanel.style.display='none';
  selectedMod = null;
  document.querySelectorAll('.mod-card').forEach(c=>c.classList.remove('sel'));
  showMain('dashboard');
  document.querySelectorAll('.nav-a').forEach(a=>a.classList.remove('active'));
  const nh = document.getElementById('nav-home');
  if(nh) nh.classList.add('active');
}
function showRight(tab){
  document.querySelectorAll('.rp-panel').forEach(p=>p.classList.remove('show'));
  document.querySelectorAll('.rp-tab').forEach(t=>t.classList.remove('active'));
  const panel = document.getElementById('rp-'+tab);
  if(panel) panel.classList.add('show');
  const tabs={'reasoning':0,'insights':1,'compare':2,'graph':3,'patterns':4,'inspect':5,'tree':6,'audit':7};
  const idx = tabs[tab];
  if(idx!==undefined){
    const tabEls = document.querySelectorAll('.rp-tab');
    if(tabEls[idx]) tabEls[idx].classList.add('active');
  }
  // Always refresh data when switching tabs
  if(tab==='reasoning') loadNarrativeStream();
  if(tab==='insights')  loadInsights('all');
  if(tab==='graph')     buildWorkflowGraph();
  if(tab==='tree')      loadTree();
  if(tab==='patterns')  loadPatterns();
  if(tab==='audit')     loadAudit();
  if(tab==='lineage')   loadLineage();
  if(tab==='compare')   loadExperiments();  // refresh experiment dropdowns
}

// ── Execute ─────────────────────────────────────────────────────────────────
function runSelected(){
  if(!selectedMod){ alert('Select a module first'); return; }
  const fields = collectFormValues();
  runModuleWithFields(selectedMod, fields);
}
function runModuleWithFields(key, fields){
  const btn    = document.getElementById('run-btn');
  const cfgBtn = null;  // removed — single run-btn only
  const exp    = document.getElementById('exp-sel').value || fields.experiment_name || '';
  btn.disabled = true;
  if(cfgBtn) cfgBtn.disabled = true;

  // Set up console for this run
  const conBody   = document.getElementById('con-body');
  const conDot    = document.getElementById('con-dot');
  const conStatus = document.getElementById('con-status');
  const conTimer  = document.getElementById('con-timer');
  const conLabel  = document.getElementById('con-module-label');
  const conFiles  = document.getElementById('con-files');
  const conFilesList = document.getElementById('con-files-list');
  const allMods   = Object.values(MODULES).flat();
  const modMeta   = allMods.find(m=>m.k===key);
  const modName   = modMeta ? modMeta.n : key.replace(/_/g,' ');

  // Clear console and show running state
  conBody.innerHTML = '';
  if(conFiles) { conFiles.style.display = 'none'; conFilesList.innerHTML = ''; }
  if(conLabel)  conLabel.textContent  = modName + (exp ? ' — ' + exp : '');
  if(conStatus) { conStatus.textContent = '● RUNNING'; conStatus.className = 'con-status-run'; }
  if(conDot)    { conDot.className = 'con-dot run'; }

  // Scroll console into view
  const consolePanel = document.getElementById('console-panel');
  if(consolePanel) consolePanel.scrollIntoView({behavior:'smooth', block:'nearest'});

  // Show stop button, hide run button during execution
  const stopBtn = document.getElementById('stop-btn');
  if(stopBtn) stopBtn.style.display = 'inline-block';

  // Running timer
  const t0 = Date.now();
  const timerInterval = setInterval(()=>{
    const s = ((Date.now()-t0)/1000).toFixed(1);
    if(conTimer) conTimer.textContent = s + 's';
  }, 100);

  addLog('INFO', '══ ' + modName.toUpperCase() + (exp?' — '+exp:'') + ' ══');
  addLog('INFO', 'Started at ' + new Date().toLocaleTimeString());

  let fileLinks = [];

  fetch('/api/execute/'+key, {
    method:'POST',
    headers:{'Content-Type':'application/json'},
    body: JSON.stringify({experiment_name:exp, fields:fields})
  })
  .then(r=>r.json())
  .then(d=>{
    _currentRunId = d.run_id;
    const es = new EventSource('/api/stream/'+d.run_id);
    es.onmessage = ev=>{
      try {
        const msg = JSON.parse(ev.data);

        if(msg.msg === '__done__'){
          es.close();
          clearInterval(timerInterval);
          btn.disabled = false;
          if(cfgBtn) cfgBtn.disabled = false;
          if(stopBtn) stopBtn.style.display = 'none';
          _currentRunId = null;
          doneSet.add(key);

          const elapsed = ((Date.now()-t0)/1000).toFixed(1);
          if(conTimer)  conTimer.textContent  = elapsed + 's';
          if(conStatus) { conStatus.textContent = '✓ DONE — '+elapsed+'s'; conStatus.className='con-status-ok'; }
          if(conDot)    { conDot.className = 'con-dot'; conDot.style.background='var(--grn)'; }

          // Show file panel if files were emitted
          if(fileLinks.length > 0 && conFiles){
            conFiles.style.display = '';
            conFilesList.innerHTML = fileLinks.join('');
          }

          refreshAll();
          setTimeout(loadNarrativeStream, 800);
          return;
        }

        if(msg.level === 'PING') return;

        // Render to console
        const level = msg.level || 'OUT';
        const text  = (msg.msg || '').trim();
        if(!text) return;

        // Collect file links separately
        if(level === 'FILE'){
          const parts = text.split('||');
          const fname = parts[0].trim();
          const fpath = parts[1] || '';
          const ext   = fname.split('.').pop().toUpperCase();
          const extC  = {PDF:'#ef4444',PNG:'#8b5cf6',CSV:'#10b981',JSON:'#f59e0b'}[ext]||'#60a5fa';
          fileLinks.push(
            `<a class="file-badge" href="/api/file?path=${encodeURIComponent(fpath)}" ` +
            `target="_blank" style="border-color:${extC}44;color:${extC};margin-right:6px">` +
            `<span style="font-weight:700">[${ext}]</span> ${escapeHtml(fname)}</a>`
          );
          addLog('FILE', text);
          return;
        }

        // Update status bar with last meaningful message
        if(level !== 'OUT' || text.length > 3){
          if(conStatus && level !== 'DONE' && level !== 'FILE'){
            const preview = text.length > 55 ? text.slice(0,55)+'…' : text;
            conStatus.textContent = '● ' + preview;
          }
        }

        addLog(level, text);

      } catch(e){ console.warn('SSE parse error:', e); }
    };

    es.onerror = (e)=>{
      es.close();
      clearInterval(timerInterval);
      btn.disabled = false;
      if(cfgBtn) cfgBtn.disabled = false;
      if(conStatus){ conStatus.textContent='✗ CONNECTION ERROR'; conStatus.className='con-status-err'; }
      if(conDot){ conDot.className='con-dot'; conDot.style.background='var(--red)'; }
      addLog('ERR', 'SSE connection lost');
    };
  })
  .catch(err=>{
    clearInterval(timerInterval);
    btn.disabled = false;
    if(cfgBtn) cfgBtn.disabled = false;
    if(conStatus){ conStatus.textContent='✗ FETCH ERROR'; conStatus.className='con-status-err'; }
    addLog('ERR', 'Request failed: '+err);
  });
}
function addLog(level, msg){
  const body = document.getElementById('con-body');
  if(!body) return;
  const div  = document.createElement('div');
  div.className = 'log log-' + (level||'OUT');

  // Classify output lines for rich colouring
  if(level === 'OUT'){
    const m = msg || '';
    if(/[✅☑]/.test(m) || /\bSIG\b|\bsignificant\b/.test(m))       div.classList.add('out-line-positive');
    else if(/[❌⚠️🚨]/.test(m) || /\bERR\b|\bfail/i.test(m))        div.classList.add('out-line-negative');
    else if(/[⚠️]/.test(m))                                         div.classList.add('out-line-warn');
    else if(/^[═─╔╚║╗╝┌└├┤]/.test(m.trim()))                       div.classList.add('out-line-box');
  }

  if(level === 'FILE'){
    // Render as download link — format: "  filename.pdf||/full/path"
    const parts = msg.split('||');
    const fname = parts[0].trim();
    const fpath = parts[1] || '';
    const ext   = fname.split('.').pop().toUpperCase();
    const extColors = {PDF:'#ef4444',PNG:'#8b5cf6',CSV:'#10b981',JSON:'#f59e0b'};
    const col   = extColors[ext] || '#60a5fa';
    div.innerHTML = `<span style="color:${col};font-weight:700">[${ext}]</span> ` +
      `<a class="file-badge" href="/api/file?path=${encodeURIComponent(fpath)}" target="_blank"` +
      ` style="border-color:${col}33;color:${col}">${escapeHtml(fname)}</a>`;
  } else {
    div.textContent = msg || '';
  }

  body.appendChild(div);
  body.scrollTop = body.scrollHeight;
}
function toggleConsole(){
  const body = document.getElementById('con-body');
  const btn  = document.getElementById('con-collapse-btn');
  if(!body) return;
  const collapsed = body.style.display === 'none';
  body.style.display = collapsed ? '' : 'none';
  if(btn) btn.textContent = collapsed ? '▾' : '▸';
}

// ── Narrative stream ────────────────────────────────────────────────────────
function loadNarrativeStream(){
  fetch('/api/narrative').then(r=>r.json()).then(items=>{
    const el=document.getElementById('narr-stream');
    if(!items||!items.length){
      el.innerHTML='<div class="narr-empty">No narrative yet. Run a module to start.</div>';
      return;
    }
    el.innerHTML = items.map(item=>`
      <div class="narr-item">
        <div class="narr-src">${srcLabel(item.source)}</div>
        <div class="narr-txt">${escapeHtml(item.text)}</div>
        <div class="narr-ts">${item.created_at}</div>
      </div>`).join('');
  }).catch(()=>{});
}
function srcLabel(src){
  const map={'observation':'💭 System thought','narrative':'📝 Commentary','session':'📂 Session',
    'transition':'→ Transition','experiment_analysis':'🔬 Analysis','causal_analysis':'🔗 Causal',
    'health_monitor':'🩺 Health','power_calculator':'⚡ Power','schema_discovery':'🔍 Discovery'};
  return map[src]||src;
}

// ── Ask Continum ─────────────────────────────────────────────────────────────
function quickAsk(q){ document.getElementById('ask-in').value=q; sendAsk(); }
function sendAsk(){
  const inp=document.getElementById('ask-in'),resp=document.getElementById('ask-resp');
  const engine='askdata';
  const chainPanel=document.getElementById('chain-panel');
  const q=inp.value.trim(); if(!q) return;
  resp.style.display='block'; resp.textContent='Reasoning…';
  chainPanel.style.display='none';

  const ui_context = {
    active_module: currentSec,
    active_experiment: document.getElementById('exp-sel').value || document.getElementById('sb-exp').textContent,
    compare_a: document.getElementById('cmp-a') ? document.getElementById('cmp-a').value : null,
    compare_b: document.getElementById('cmp-b') ? document.getElementById('cmp-b').value : null
  };

  const t0 = Date.now();
  fetch('/api/ask',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({question:q, engine:engine, ui_context:ui_context})})
  .then(r=>r.json())
  .then(d=>{
    const elapsed = ((Date.now()-t0)/1000).toFixed(1);
    const llmBadge = d.llm_used
      ? '<span style="font-size:8px;background:rgba(124,58,237,.2);color:#a78bfa;border-radius:3px;padding:1px 5px;margin-left:4px">LLM</span>'
      : '<span style="font-size:8px;background:rgba(96,165,250,.15);color:#60a5fa;border-radius:3px;padding:1px 5px;margin-left:4px">DB</span>';

    const responseText = d.response || d.error || '(no response)';
    // Format response: bold **text** and newlines
    const formatted = escapeHtml(responseText)
      .replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>')
      .replace(/\n/g, '<br>');

    resp.style.display='block';
    resp.innerHTML = `
      <div style="font-size:8px;color:var(--sb-muted);margin-bottom:5px;display:flex;align-items:center;gap:4px">
        Ask Continum ${llmBadge}
        <span style="margin-left:auto;opacity:.6">${elapsed}s</span>
      </div>
      <div style="line-height:1.6;font-size:11px">${formatted}</div>`;

    if(d.chain && d.chain.evidence && d.chain.evidence.length){
      chainPanel.style.display='block';
      const evHtml = d.chain.evidence.map(e=>`
        <div class="chain-item chain-${e.valence||'supports'}">
          <div class="chain-src">${escapeHtml(e.source||'')}</div>
          <div class="chain-claim" style="white-space:pre-wrap">${escapeHtml(e.claim||'')}</div>
          <div class="chain-bar"><div class="chain-bar-fill" style="width:${Math.round((e.confidence||0)*100)}%"></div></div>
        </div>`).join('');
      chainPanel.innerHTML = `
        <div style="font-size:8px;color:var(--muted);text-transform:uppercase;letter-spacing:.7px;padding:5px 8px 3px">
          Evidence (${d.chain.evidence.length} sources)
        </div>
        ${evHtml}`;
    } else {
      chainPanel.style.display='none';
    }
    setTimeout(loadNarrativeStream, 400);
  })
  .catch(e=>{
    resp.style.display='block';
    resp.innerHTML='<span style="color:var(--red)">Error: '+escapeHtml(String(e))+'</span>';
  });
  inp.value='';
}

// ── Insights ──────────────────────────────────────────────────────────────────
function loadInsights(which){
  fetch('/api/intelligence').then(r=>r.json()).then(data=>{
    const map={'all':data.insights,'warnings':data.warnings,'recs':data.recommendations};
    const items = map[which]||data.insights||[];
    const el=document.getElementById('ins-list');
    el.innerHTML = items.length ? items.map(i=>`
      <div class="ins-item sev-${i.severity||'info'}">
        <div class="ins-src">${i.source||''}</div>
        <div class="ins-msg">${i.message||''}</div>
        ${i.detail?`<div class="ins-det">${i.detail}</div>`:''}
      </div>`).join('') : `<div style="color:var(--muted);font-size:10px;padding:14px;text-align:center">No items</div>`;
  }).catch(()=>{});
}

// ── History ───────────────────────────────────────────────────────────────────
function refreshHistory(){
  fetch('/api/session').then(r=>r.json()).then(data=>{
    const tb=document.getElementById('hist-body');
    if(!tb) return;
    document.getElementById('sb-runs').textContent=data.n_runs||0;
    if(!data.history||!data.history.length){
      tb.innerHTML='<tr><td colspan="5" style="text-align:center;color:var(--muted);padding:12px">No runs yet</td></tr>';
      return;
    }
    tb.innerHTML = data.history.map(h=>`
      <tr>
        <td style="color:var(--acc);font-family:monospace">${h.module}</td>
        <td><span class="${h.ok?'bok':'bfail'}">${h.ok?'OK':'FAIL'}</span></td>
        <td style="color:var(--muted)">${h.phase||''}</td>
        <td style="color:var(--muted)">${h.elapsed}s</td>
        <td style="color:var(--muted)">${(h.summary||'').slice(0,55)}</td>
      </tr>`).join('');
    data.history.forEach(h=>{ if(h.ok) doneSet.add(h.module); });
    populateGrid(currentSec,'grid-'+currentSec);
    populateGrid('dashboard','grid-dashboard');
    // Update dots
    const hasSig = data.history.some(h=>h.module==='experiment_analysis' && h.ok);
    if(hasSig) document.getElementById('analysis-dot').style.display='';
  }).catch(()=>{});
}

// ── Workflow graph ─────────────────────────────────────────────────────────────
function buildWorkflowGraph(){
  const phases=[
    {label:'Discovery',modules:['schema_discovery','data_validation','dimension_setup']},
    {label:'Planning', modules:['opportunity_sizing','power_calculator','brief_generator']},
    {label:'Monitoring',modules:['health_monitor','sequential_testing']},
    {label:'Analysis', modules:['experiment_analysis','causal_analysis','simpsons_paradox']},
    {label:'Deploy',   modules:['learnings_repository','roi_tracker','uplift_modeller']},
  ];
  const ICONS={'schema_discovery':'🔍','data_validation':'✅','dimension_setup':'📐',
    'opportunity_sizing':'📋','power_calculator':'⚡','brief_generator':'📄',
    'health_monitor':'🩺','sequential_testing':'📈',
    'experiment_analysis':'🔬','causal_analysis':'🔗','simpsons_paradox':'🔀',
    'learnings_repository':'🧠','roi_tracker':'💰','uplift_modeller':'🚀'};

  let html='<div style="font-size:9px;text-transform:uppercase;letter-spacing:.7px;color:var(--muted);margin-bottom:8px;padding:10px 10px 0">Workflow DAG</div>';
  phases.forEach((phase,pi)=>{
    html+=`<div style="margin:0 10px 2px;font-size:8px;color:var(--muted);text-transform:uppercase;letter-spacing:.7px">${phase.label}</div>`;
    html+='<div class="wf-row" style="padding:0 10px 6px;flex-wrap:wrap">';
    phase.modules.forEach((k,i)=>{
      const status = doneSet.has(k)?'done':'';
      html+=`<div class="wf-node ${status}" onclick="selectMod('${k}','${k.replace(/_/g,' ')}');showMain('dashboard')">
        <span class="wn-icon">${ICONS[k]||'•'}</span>
        <span class="wn-name">${k.replace(/_/g,'<br>')}</span>
      </div>`;
      if(i<phase.modules.length-1) html+='<span class="wf-arrow">→</span>';
    });
    html+='</div>';
    if(pi<phases.length-1) html+='<div style="text-align:center;color:var(--bdr);font-size:14px;margin:0 0 2px">↓</div>';
  });
  document.getElementById('graph-content').innerHTML=html;
}

// ── Session tree ────────────────────────────────────────────────────────────
function loadTree(){
  fetch('/api/session').then(r=>r.json()).then(data=>{
    document.getElementById('tree-content').innerHTML = renderTree(data, 0);
  }).catch(()=>{});
}
function renderTree(obj, depth){
  if(depth>4) return '<span style="color:var(--muted)">…</span>';
  if(obj===null) return '<span class="tree-null">null</span>';
  if(typeof obj==='boolean') return `<span class="tree-bool">${obj}</span>`;
  if(typeof obj==='number')  return `<span class="tree-val">${obj}</span>`;
  if(typeof obj==='string'){
    const s = obj.length>60 ? obj.slice(0,60)+'…' : obj;
    return `<span class="tree-str">"${escapeHtml(s)}"</span>`;
  }
  if(Array.isArray(obj)){
    if(!obj.length) return '<span class="tree-null">[]</span>';
    if(depth>=3) return `<span class="tree-null">[${obj.length} items]</span>`;
    const inner = obj.slice(0,5).map(v=>`<div style="margin-left:12px">${renderTree(v,depth+1)}</div>`).join('');
    const more  = obj.length>5?`<div style="margin-left:12px;color:var(--muted)">… ${obj.length-5} more</div>`:'';
    return `<div>[${inner}${more}]</div>`;
  }
  if(typeof obj==='object'){
    const keys=Object.keys(obj);
    if(!keys.length) return '<span class="tree-null">{}</span>';
    const inner = keys.slice(0,12).map(k=>{
      const val = renderTree(obj[k], depth+1);
      return `<div style="margin-left:12px"><span class="tree-key">${escapeHtml(k)}</span>: ${val}</div>`;
    }).join('');
    const more  = keys.length>12?`<div style="margin-left:12px;color:var(--muted)">… ${keys.length-12} more</div>`:'';
    return `<div>{${inner}${more}}</div>`;
  }
  return escapeHtml(String(obj));
}
function loadForks(){
  fetch('/api/session/snapshots').then(r=>r.json()).then(snaps=>{
    const el=document.getElementById('tree-content');
    if(!snaps.length){
      el.innerHTML='<div style="color:var(--muted);padding:14px;font-size:10px;text-align:center">No snapshots yet. Take snapshots to build a history.</div>';
      return;
    }
    el.innerHTML='<div style="font-size:9px;color:var(--muted);padding:10px;text-transform:uppercase;letter-spacing:.7px">Snapshots</div>'+
      snaps.map(s=>`
        <div class="lin-row">
          <span style="color:var(--acc);font-size:9px;font-family:monospace">${s.snapshot_id}</span>
          <span style="font-size:9px;color:var(--muted)">${s.label||'—'}</span>
          <span style="font-size:9px;color:var(--muted);margin-left:auto">${(s.taken_at||'').slice(11,19)}</span>
        </div>`).join('');
  }).catch(()=>{});
}

// ── Patterns ──────────────────────────────────────────────────────────────────
function loadPatterns(){
  const el=document.getElementById('patterns-content');
  el.innerHTML='<div style="color:var(--muted);font-size:10px;text-align:center;padding:14px">Loading patterns…</div>';
  fetch('/api/patterns').then(r=>r.json()).then(data=>{
    if(data.status==='no memory'){
      el.innerHTML='<div style="color:var(--muted);font-size:10px;padding:14px">No memory yet. Run and store experiments to build patterns.</div>';
      return;
    }
    let html=`<div style="padding:10px">
      <div class="sec-title">Organizational Intelligence (${data.experiment_count||0} experiments)</div>
      <div style="font-size:11px;line-height:1.6;color:var(--txt);margin-bottom:12px;white-space:pre-line">${escapeHtml(data.summary||'')}</div>`;

    const sig=data.significance_rate||{};
    if(sig.n_total>0){
      html+=`<div class="sec-title">Significance Rate</div>
        <div style="font-size:10px;margin-bottom:10px">
          <div style="display:flex;justify-content:space-between;margin-bottom:3px">
            <span style="color:var(--muted)">${sig.n_sig||0} / ${sig.n_total} significant</span>
            <span style="color:var(--acc)">${((sig.sig_rate||0)*100).toFixed(0)}%</span>
          </div>
          <div style="height:4px;background:var(--bdr);border-radius:2px">
            <div style="height:100%;width:${((sig.sig_rate||0)*100).toFixed(0)}%;background:var(--acc);border-radius:2px"></div>
          </div>
        </div>`;
    }

    const metrics=data.metric_patterns||[];
    if(metrics.length){
      html+=`<div class="sec-title">Metric Performance</div>`;
      metrics.slice(0,5).forEach(m=>{
        html+=`<div class="pat-metric">
          <span style="font-size:9px;color:var(--acc);flex:1">${escapeHtml(m.metric)}</span>
          <span style="font-size:9px;color:var(--muted)">${m.n_exps} exp</span>
          <div class="pat-bar" style="width:${Math.round((m.sig_rate||0)*50)}px"></div>
          <span style="font-size:9px;color:var(--grn)">${((m.sig_rate||0)*100).toFixed(0)}%</span>
        </div>`;
      });
    }

    if(data.prior){
      const prior=data.prior;
      html+=`<div class="sec-title" style="margin-top:8px">Prior for Active Experiment</div>
        <div style="font-size:10px;line-height:1.6;color:var(--txt);padding-bottom:8px;white-space:pre-line">${escapeHtml(prior.narrative||'')}</div>`;
    }

    html+='</div>';
    el.innerHTML=html;
  }).catch(e=>{ el.innerHTML=`<div style="color:var(--red);font-size:10px;padding:14px">Error: ${e}</div>`; });
}

// ── Inspect ───────────────────────────────────────────────────────────────────
function runInspect(what){
  const el=document.getElementById('insp-result');
  el.style.display='block'; el.textContent='Loading…';
  fetch('/api/inspect/'+what).then(r=>r.json()).then(d=>{
    el.textContent=JSON.stringify(d,null,2);
  }).catch(e=>{ el.textContent='Error: '+e; });
}

// ── Audit ─────────────────────────────────────────────────────────────────────
function loadAudit(){
  fetch('/api/audit?n=40').then(r=>r.json()).then(entries=>{
    const el=document.getElementById('audit-list');
    if(!entries.length){ el.innerHTML='<div style="color:var(--muted);font-size:10px;padding:14px;text-align:center">No entries</div>'; return; }
    el.innerHTML = [...entries].reverse().map(e=>`
      <div class="lin-row">
        <span style="color:${e.ok?'var(--grn)':'var(--red)'}">${e.ok?'✅':'❌'}</span>
        <span style="font-family:monospace;font-size:9px;color:var(--acc)">${e.action}</span>
        <span style="font-size:9px;color:var(--muted);flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">${e.subject}</span>
        <span style="font-size:8px;color:var(--muted)">${(e.timestamp||'').slice(11,19)}</span>
      </div>`).join('');
  }).catch(()=>{});
}

// ── Compare ───────────────────────────────────────────────────────────────────
function runCompare(){
  const a=document.getElementById('cmp-a').value,b=document.getElementById('cmp-b').value;
  const out=document.getElementById('cmp-result');
  if(!a||!b){ out.innerHTML='<p style="color:var(--red);font-size:10px">Select both</p>'; return; }
  out.innerHTML='<p style="color:var(--muted);font-size:10px">Running…</p>';
  fetch('/api/compare',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({experiment_a:a,experiment_b:b})})
  .then(r=>r.json())
  .then(d=>{
    if(d.error){ out.innerHTML=`<p style="color:var(--red);font-size:10px">${d.error}</p>`; return; }
    const ma=d.experiment_a.metrics,mb=d.experiment_b.metrics;
    const row=(l,va,vb)=>`<tr><td style="color:var(--muted)">${l}</td><td>${escapeHtml(String(va))}</td><td>${escapeHtml(String(vb))}</td></tr>`;
    out.innerHTML=`
      <table class="cmp-table">
        <thead><tr><th></th><th>${escapeHtml(d.experiment_a.name.slice(0,16))}</th><th>${escapeHtml(d.experiment_b.name.slice(0,16))}</th></tr></thead>
        <tbody>
          ${row('Δ (pp)',(ma.delta_pp||0).toFixed(4),(mb.delta_pp||0).toFixed(4))}
          ${row('p-value',(ma.p_value||1).toFixed(4),(mb.p_value||1).toFixed(4))}
          ${row('Significant',ma.is_sig?'✅':'❌',mb.is_sig?'✅':'❌')}
          ${row('Verdict',ma.verdict||'—',mb.verdict||'—')}
          ${row('SRM',ma.srm?'⚠️':'✅',mb.srm?'⚠️':'✅')}
        </tbody>
      </table>
      <div class="ins-item sev-info" style="margin-top:8px">
        <div class="ins-src">Synthesis</div>
        <div class="ins-msg" style="white-space:pre-line">${escapeHtml(d.narrative)}</div>
      </div>`;
  }).catch(e=>{ out.innerHTML=`<p style="color:var(--red);font-size:10px">Error: ${e}</p>`; });
}

// ── Experiment select ──────────────────────────────────────────────────────────
function loadExperiments(){
  fetch('/api/experiments').then(r=>r.json()).then(data=>{
    const opts=data.map(e=>`<option value="${escapeAttr(e.experiment_name)}">${escapeHtml(e.experiment_name)}</option>`).join('');
    const ph='<option value="">— Select experiment —</option>';
    ['exp-sel','cmp-a','cmp-b'].forEach(id=>{ const el=document.getElementById(id); if(el) el.innerHTML=ph+opts; });
  }).catch(()=>{});
}
function selectExp(name){
  if(!name) return;
  fetch('/api/experiments/select',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({name})})
  .then(r=>r.json()).then(d=>{ document.getElementById('sb-exp').textContent=d.active||name; });
}

// ── Fork / Snapshot ────────────────────────────────────────────────────────────
function forkSession(){
  const label=prompt('Fork label (optional):','');
  if(label===null) return;
  fetch('/api/session/fork',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({label})})
  .then(r=>r.json()).then(d=>{
    document.getElementById('sb-session').textContent=d.session_id;
    addLog('OK','Forked → '+d.session_id);
  }).catch(e=>alert('Fork error: '+e));
}
function takeSnapshot(){
  const label=prompt('Snapshot label (optional):','');
  if(label===null) return;
  fetch('/api/session/snapshot',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({label})})
  .then(r=>r.json()).then(d=>{ addLog('OK','Snapshot: '+d.snapshot_id); }).catch(e=>alert(''+e));
}

// ── Ship governance ────────────────────────────────────────────────────────────
function requestShip(){
  const exp=document.getElementById('exp-sel').value||document.getElementById('sb-exp').textContent;
  if(!exp||exp==='—'){ alert('Select an experiment first'); return; }
  fetch('/api/governance/request-ship',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({experiment_id:exp,analyst:'analyst'})})
  .then(r=>r.json()).then(d=>{ addLog('OK','Ship requested for '+d.experiment_id+' — '+d.status); }).catch(e=>alert(''+e));
}

// ── Refresh ────────────────────────────────────────────────────────────────────
function refreshAll(){
  refreshHistory();
  loadNarrativeStream();
  fetch('/api/intelligence').then(r=>r.json()).then(data=>{
    const nw=data.warnings&&data.warnings.length;
    document.getElementById('warn-dot').style.display=nw?'':'none';
    document.getElementById('sb-mem').textContent='';
  }).catch(()=>{});
}

// ── Utilities ──────────────────────────────────────────────────────────────────
function escapeHtml(s){ return String(s||'').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;'); }
function escapeAttr(s){ return String(s||'').replace(/"/g,'&quot;'); }

// ── LLM status + control ──────────────────────────────────────────────────────
function refreshLLMStatus(){
  fetch('/api/llm/status').then(r=>r.json()).then(d=>{
    const dot   = document.getElementById('llm-dot');
    const label = document.getElementById('llm-label');
    if(!dot||!label) return;
    if(d.is_loaded){
      dot.style.background   = 'var(--grn)';
      label.textContent      = 'LLM ✓';
      label.style.color      = 'var(--grn)';
    } else if(d.available){
      dot.style.background   = 'var(--yel)';
      label.textContent      = 'LLM (idle)';
      label.style.color      = 'var(--yel)';
    } else {
      dot.style.background   = 'var(--bdr)';
      label.textContent      = 'LLM';
      label.style.color      = 'var(--muted)';
    }
  }).catch(()=>{});
}

function toggleLLM(){
  fetch('/api/llm/status').then(r=>r.json()).then(d=>{
    if(d.is_loaded){
      if(!confirm('Unload LLM from memory?')) return;
      fetch('/api/llm/unload',{method:'POST'}).then(()=>{ setTimeout(refreshLLMStatus,800); });
    } else {
      const pill = document.getElementById('llm-label');
      if(pill) pill.textContent='Loading…';
      fetch('/api/llm/load',{method:'POST'}).then(r=>r.json()).then(d=>{
        // Poll until loaded
        const poll = setInterval(()=>{
          refreshLLMStatus();
          fetch('/api/llm/status').then(r=>r.json()).then(s=>{
            if(s.is_loaded) clearInterval(poll);
          });
        }, 3000);
        setTimeout(()=>clearInterval(poll), 300000); // 5min timeout
      });
    }
  });
}

// ── Init ───────────────────────────────────────────────────────────────────────
document.addEventListener('DOMContentLoaded',()=>{
  Object.keys(MODULES).forEach(s=>populateGrid(s,'grid-'+s));
  loadExperiments();
  refreshHistory();
  loadNarrativeStream();
  refreshLLMStatus();

  // Auto-load LLM in background on startup
  fetch('/api/llm/status').then(r=>r.json()).then(d=>{
    if(!d.is_loaded){
      // Trigger background load silently
      fetch('/api/llm/load',{method:'POST'}).then(()=>{
        console.log('LLM loading in background...');
        // Poll until loaded
        const poll = setInterval(()=>{
          refreshLLMStatus();
          fetch('/api/llm/status').then(r=>r.json()).then(s=>{
            if(s.is_loaded) clearInterval(poll);
          });
        }, 5000);
        setTimeout(()=>clearInterval(poll), 600000); // 10min max
      }).catch(()=>{});
    }
  }).catch(()=>{});

  // Load initial right panel data
  loadInsights('all');

  // Refresh reasoning stream every 8s
  setInterval(()=>{ if(document.getElementById('rp-reasoning').classList.contains('show')) loadNarrativeStream(); }, 8000);
  setInterval(refreshAll, 15000);
  setInterval(refreshLLMStatus, 30000);
});
</script>
</body>
</html>
"""
