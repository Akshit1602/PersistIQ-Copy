"""
CONTINUM — Intelligent Experimentation Platform
Production UI shell.

This module replaces the legacy continum/ui/templates/dashboard.py rendering.
It performs NO backend logic -- it renders a single self-contained page that
calls the existing, unmodified /api/* routes via fetch()/EventSource.
"""

DASHBOARD = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>CONTINUM — Intelligent Experimentation Platform</title>
<!-- CDN stylesheets loaded asynchronously (media=print -> all on load) so a
     slow or network-blocked CDN can NEVER stall the inline <script> below.
     A still-loading stylesheet blocks script execution in Chrome/Firefox,
     which would otherwise leave every button handler undefined on a network
     that can't reach these CDNs (icons/fonts simply fill in once/if loaded). -->
<link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.5.1/css/all.min.css" media="print" onload="this.media='all'">
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&family=JetBrains+Mono:wght@400;500;600&display=swap" media="print" onload="this.media='all'">
<script src="https://cdn.plot.ly/plotly-2.27.0.min.js" charset="utf-8"></script>
<noscript>
<link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.5.1/css/all.min.css">
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&family=JetBrains+Mono:wght@400;500;600&display=swap">
</noscript>
<style>
:root{
  --bg:#F6F8FC; --surf:#FFFFFF; --surf2:#F1F4F9; --surf3:#E8EDF5;
  --bdr:#E2E8F2; --bdr2:#CBD5E6;
  --txt:#0F172A; --muted:#64748B; --muted2:#94A3B8;
  --blue:#2563EB; --blue-lt:#EFF6FF; --blue-d:#1D4ED8;
  --violet:#7C3AED; --violet-lt:#F5F3FF;
  --teal:#0D9488; --teal-lt:#F0FDFA;
  --green:#16A34A; --green-lt:#F0FDF4;
  --amber:#D97706; --amber-lt:#FFFBEB;
  --red:#DC2626; --red-lt:#FEF2F2;
  --pink:#DB2777; --pink-lt:#FDF2F8;
  --shadow-sm:0 1px 2px rgba(15,23,42,.04),0 1px 1px rgba(15,23,42,.03);
  --shadow-md:0 4px 10px rgba(15,23,42,.06),0 1px 3px rgba(15,23,42,.04);
  --shadow-lg:0 12px 28px rgba(15,23,42,.10),0 2px 6px rgba(15,23,42,.05);
  --radius:10px; --radius-lg:14px;
}
*{box-sizing:border-box;margin:0;padding:0}
html,body{height:100%}
body{background:var(--bg);color:var(--txt);font-family:'Inter',system-ui,sans-serif;font-size:13px;overflow:hidden}
a{color:inherit}
::-webkit-scrollbar{width:8px;height:8px}
::-webkit-scrollbar-thumb{background:var(--bdr2);border-radius:8px}
::-webkit-scrollbar-track{background:transparent}

/* ══ ROLE GATEWAY ══════════════════════════════════════════════════════ */
#gateway{position:fixed;inset:0;z-index:9999;background:linear-gradient(160deg,#F6F8FC 0%,#EEF2FB 60%,#E9EEFA 100%);
  display:flex;flex-direction:column;align-items:center;justify-content:center;animation:fadeIn .4s ease}
.gw-eyebrow{font-size:11px;font-weight:700;letter-spacing:3px;color:var(--blue);text-transform:uppercase;margin-bottom:6px}
.gw-title{font-size:30px;font-weight:800;color:var(--txt);margin-bottom:8px;letter-spacing:-.5px}
.gw-sub{font-size:13px;color:var(--muted);margin-bottom:36px;text-align:center;max-width:420px;line-height:1.6}
.gw-label{font-size:10px;font-weight:700;letter-spacing:1.5px;text-transform:uppercase;color:var(--muted2);margin-bottom:18px}
.role-grid{display:grid;grid-template-columns:repeat(3,206px);gap:14px;margin-bottom:30px}
.role-card{background:var(--surf);border:1px solid var(--bdr);border-radius:var(--radius-lg);padding:18px 16px;
  cursor:pointer;transition:all .2s cubic-bezier(.16,1,.3,1);position:relative;box-shadow:var(--shadow-sm)}
.role-card:hover{border-color:var(--blue);transform:translateY(-3px);box-shadow:var(--shadow-md)}
.role-card.selected{border-color:var(--blue);background:var(--blue-lt);box-shadow:0 0 0 2px var(--blue),var(--shadow-md)}
.role-card .rc-icon{width:38px;height:38px;border-radius:10px;display:flex;align-items:center;justify-content:center;font-size:17px;margin-bottom:10px}
.role-card .rc-name{font-size:13.5px;font-weight:700;color:var(--txt);margin-bottom:4px}
.role-card .rc-desc{font-size:10.5px;color:var(--muted);line-height:1.45}
.role-card .rc-mode{position:absolute;top:14px;right:14px;font-size:8px;font-weight:700;letter-spacing:.4px;padding:3px 8px;border-radius:6px;text-transform:uppercase}
.mode-nav{background:var(--green-lt);color:var(--green)}
.mode-ai{background:var(--violet-lt);color:var(--violet)}
.mode-hybrid{background:var(--blue-lt);color:var(--blue)}
.gw-btn{background:var(--blue);color:#fff;border:none;border-radius:10px;padding:13px 44px;font-size:14px;font-weight:700;
  cursor:pointer;transition:all .2s;opacity:.35;pointer-events:none;box-shadow:var(--shadow-md);font-family:inherit}
.gw-btn.active{opacity:1;pointer-events:all}
.gw-btn.active:hover{background:var(--blue-d);transform:translateY(-1px);box-shadow:0 8px 24px rgba(37,99,235,.35)}

/* ══ APP SHELL ══════════════════════════════════════════════════════════ */
#app{display:none;position:relative;grid-template-columns:var(--sb-w, 226px) 1fr var(--rp-w,312px);height:100vh;overflow:hidden}
#app.copilot-mode{grid-template-columns:var(--sb-w, 226px) 1fr 0}
#app.sb-collapsed { --sb-w: 0px !important; }
#app.rp-collapsed { --rp-w: 0px !important; }

/* ── Sidebar ── */
.sb{background:var(--surf);border-right:1px solid var(--bdr);display:flex;flex-direction:column;overflow:hidden}
.sb-brand{padding:18px 18px 14px;border-bottom:1px solid var(--bdr);display:flex;align-items:center;gap:10px}
.sb-mark{width:30px;height:30px;border-radius:8px;background:linear-gradient(135deg,var(--blue),var(--violet));
  display:flex;align-items:center;justify-content:center;color:#fff;font-weight:800;font-size:13px;flex-shrink:0}
.sb-name{font-size:13px;font-weight:800;letter-spacing:1px;color:var(--txt)}
.sb-tag{font-size:8.5px;color:var(--muted);letter-spacing:.3px}
.sb-role{margin:12px 14px 6px;background:var(--surf2);border:1px solid var(--bdr);border-radius:8px;padding:8px 11px;
  display:flex;align-items:center;gap:8px;font-size:10.5px;color:var(--muted)}
.sb-role .rp-icon{font-size:13px}
.sb-role b{color:var(--txt);font-weight:600}
.sb-switch{margin-left:auto;font-size:9px;color:var(--blue);cursor:pointer;font-weight:600}
.nav-wrap{flex:1;overflow-y:auto;padding:6px 0}
.nav-label{font-size:9px;text-transform:uppercase;letter-spacing:1px;color:var(--muted2);padding:12px 18px 6px;font-weight:700}
.nav-item{display:flex;align-items:center;gap:10px;padding:8px 18px;font-size:12px;font-weight:500;color:var(--muted);
  cursor:pointer;border-left:3px solid transparent;transition:all .15s;text-decoration:none}
.nav-item:hover{background:var(--surf2);color:var(--txt)}
.nav-item.active{color:var(--blue);border-left-color:var(--blue);background:var(--blue-lt);font-weight:600}
.nav-item .ni{width:16px;text-align:center;font-size:13px}
.nb{margin-left:auto;font-size:8.5px;font-weight:700;padding:1px 6px;border-radius:8px}
.nb-warn{background:var(--amber-lt);color:var(--amber)}
.nb-ok{background:var(--green-lt);color:var(--green)}
.sb-foot{padding:12px 18px;border-top:1px solid var(--bdr);font-size:10px;color:var(--muted2)}
.sb-foot div{margin-bottom:2px}
.sb-foot b{color:var(--muted)}

/* ── Main ── */
.main{display:flex;flex-direction:column;overflow:hidden;background:var(--bg)}
.topbar{background:var(--surf);border-bottom:1px solid var(--bdr);padding:11px 22px;display:flex;align-items:center;gap:12px;flex-shrink:0}
.tb-title{font-size:14.5px;font-weight:700;color:var(--txt);flex:1}
.tb-title .tb-sub{font-size:10.5px;color:var(--muted);font-weight:400;margin-left:8px}
.exp-sel{background:var(--surf2);border:1px solid var(--bdr);color:var(--txt);border-radius:8px;padding:7px 12px;
  font-size:11.5px;width:260px;font-family:inherit;cursor:pointer}
.exp-sel:focus{outline:none;border-color:var(--blue)}
.btn{border:none;border-radius:8px;padding:8px 16px;font-size:11.5px;font-weight:600;cursor:pointer;transition:all .15s;font-family:inherit}
.btn-primary{background:var(--blue);color:#fff;box-shadow:0 1px 2px rgba(37,99,235,.3)}
.btn-primary:hover{background:var(--blue-d)}
.btn-primary:disabled{opacity:.4;cursor:not-allowed}
.btn-ghost{background:var(--surf2);color:var(--muted);border:1px solid var(--bdr)}
.btn-ghost:hover{color:var(--txt);border-color:var(--bdr2)}
.content{flex:1;overflow-y:auto;padding:22px 24px}
.sec-title{font-size:10px;text-transform:uppercase;letter-spacing:1px;color:var(--muted2);margin-bottom:12px;font-weight:700}

/* ── KPI / stat cards ── */
.stat-row{display:grid;grid-template-columns:repeat(4,1fr);gap:14px;margin-bottom:22px}
.stat-card{background:var(--surf);border:1px solid var(--bdr);border-radius:var(--radius);padding:15px 16px;box-shadow:var(--shadow-sm)}
.stat-label{font-size:9.5px;text-transform:uppercase;letter-spacing:.7px;color:var(--muted2);margin-bottom:7px;font-weight:700}
.stat-value{font-size:22px;font-weight:800;color:var(--txt);font-family:'JetBrains Mono',monospace;letter-spacing:-.5px}
.stat-trend{font-size:10.5px;margin-top:4px;font-weight:600}
.st-pos{color:var(--green)} .st-neg{color:var(--red)} .st-neu{color:var(--muted)}

/* ── Phase cards ── */
.phase-grid{display:grid;grid-template-columns:1fr 1fr;gap:14px;margin-bottom:24px}
.phase-card{background:var(--surf);border:1px solid var(--bdr);border-radius:var(--radius-lg);padding:20px;cursor:pointer;
  transition:all .2s;position:relative;overflow:hidden;box-shadow:var(--shadow-sm)}
.phase-card:hover{border-color:var(--blue);transform:translateY(-2px);box-shadow:var(--shadow-md)}
.phase-accent{position:absolute;top:0;left:0;right:0;height:3px}
.ph-0 .phase-accent{background:linear-gradient(90deg,#2563EB,#60A5FA)}
.ph-1 .phase-accent{background:linear-gradient(90deg,#0D9488,#2DD4BF)}
.ph-2 .phase-accent{background:linear-gradient(90deg,#D97706,#FBBF24)}
.ph-3 .phase-accent{background:linear-gradient(90deg,#7C3AED,#A78BFA)}
.ph-4 .phase-accent{background:linear-gradient(90deg,#DB2777,#F472B6)}
.ph-tools .phase-accent{background:linear-gradient(90deg,#0891B2,#22D3EE)}
.pc-icon{width:42px;height:42px;border-radius:10px;display:flex;align-items:center;justify-content:center;font-size:19px;margin-bottom:12px}
.ph-0 .pc-icon{background:var(--blue-lt);color:var(--blue)}
.ph-1 .pc-icon{background:var(--teal-lt);color:var(--teal)}
.ph-2 .pc-icon{background:var(--amber-lt);color:var(--amber)}
.ph-3 .pc-icon{background:var(--violet-lt);color:var(--violet)}
.ph-4 .pc-icon{background:var(--pink-lt);color:var(--pink)}
.ph-tools .pc-icon{background:#ECFEFF;color:#0891B2}
.pc-title{font-size:14.5px;font-weight:700;color:var(--txt);margin-bottom:5px}
.pc-desc{font-size:11px;color:var(--muted);line-height:1.55}
.pc-count{position:absolute;top:16px;right:16px;font-size:9px;font-weight:700;background:var(--surf2);border:1px solid var(--bdr);
  border-radius:10px;padding:3px 9px;color:var(--muted)}

/* ── Module grid ── */
.mod-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(148px,1fr));gap:10px;margin-bottom:22px}
.grid-error{grid-column:1/-1;padding:14px 16px;border-radius:8px;background:var(--surf2);color:var(--muted);font-size:12px}
.mod-card{background:var(--surf);border:1px solid var(--bdr);border-radius:var(--radius);padding:13px;cursor:pointer;
  transition:all .18s;position:relative;box-shadow:var(--shadow-sm)}
.mod-card:hover{border-color:var(--blue);box-shadow:var(--shadow-md);transform:translateY(-1px)}
.mod-card.done{border-color:var(--green)}
.mod-card.done::after{content:"\f00c";font-family:"Font Awesome 6 Free";font-weight:900;position:absolute;top:8px;right:10px;font-size:9px;color:var(--green)}
.mod-icon{width:30px;height:30px;border-radius:8px;display:flex;align-items:center;justify-content:center;font-size:13.5px;margin-bottom:9px}
.mod-name{font-size:11px;font-weight:600;line-height:1.35;color:var(--txt);margin-bottom:6px}
.tier-badge{display:inline-block;font-size:7.5px;font-weight:700;letter-spacing:.3px;padding:2px 7px;border-radius:5px;text-transform:uppercase}
.t1{background:var(--teal-lt);color:var(--teal)}
.t2{background:var(--blue-lt);color:var(--blue)}
.t3{background:var(--violet-lt);color:var(--violet)}

/* ── Execution console ── */
.console-wrap{background:var(--surf);border:1px solid var(--bdr);border-radius:var(--radius-lg);margin-bottom:22px;overflow:hidden;box-shadow:var(--shadow-sm)}
.console-header{padding:11px 16px;border-bottom:1px solid var(--bdr);display:flex;align-items:center;gap:10px;background:var(--surf2);font-size:11.5px;font-weight:600;color:var(--muted)}
.dot{width:8px;height:8px;border-radius:50%;background:var(--bdr2)}
.dot.run{background:var(--green);animation:pulse 1.1s infinite}
.console-status{margin-left:auto;font-size:9.5px;color:var(--muted2);font-weight:600}
.console-body{font-family:'JetBrains Mono',monospace;font-size:11.5px;padding:13px 16px;height:240px;overflow-y:auto;
  background:#0B1220;line-height:1.7;white-space:pre-wrap;word-break:break-all;color:#CBD5E1}
.log-INFO{color:#7DD3FC}.log-INFO::before{content:"[ INFO ] ";color:#38BDF8;font-size:9px}
.log-OK{color:#5EEAD4;font-weight:700}.log-OK::before{content:"[  OK  ] ";color:#2DD4BF}
.log-ERR{color:#FCA5A5}.log-ERR::before{content:"[ ERR  ] ";color:#F87171}
.log-WARN{color:#FDE68A}.log-WARN::before{content:"[ WARN ] ";color:#FBBF24}
.log-DONE{color:#5EEAD4;font-weight:700}
.log-OUT{color:#CBD5E1}
.log-SUMMARY{color:#FBBF24;font-weight:700;font-size:12px}
.log-FILE{color:#7DD3FC;text-decoration:underline;cursor:pointer}.log-FILE::before{content:"[ FILE ] ";color:#38BDF8}
.log-INPUT{color:#FBBF24;font-weight:600}
.log-PING{display:none}
.console-files{padding:10px 16px;background:#0B1220;border-top:1px solid #1E293B;display:none}
.file-chip{display:inline-block;background:rgba(56,189,248,.12);border:1px solid rgba(56,189,248,.25);border-radius:6px;
  padding:4px 10px;margin:3px 4px 0 0;font-size:10.5px;color:#7DD3FC;text-decoration:none;cursor:pointer}
.file-chip:hover{background:rgba(56,189,248,.22)}

/* ── tables ── */
.tbl-wrap{background:var(--surf);border:1px solid var(--bdr);border-radius:var(--radius);overflow:hidden;box-shadow:var(--shadow-sm)}
table.dt{width:100%;border-collapse:collapse;font-size:11.5px}
table.dt th{padding:9px 14px;font-size:9.5px;text-transform:uppercase;letter-spacing:.6px;color:var(--muted2);
  border-bottom:1px solid var(--bdr);text-align:left;font-weight:700;background:var(--surf2)}
table.dt td{padding:9px 14px;border-bottom:1px solid var(--bdr);color:var(--txt)}
table.dt tr:last-child td{border-bottom:none}
table.dt tr:hover td{background:var(--surf2)}
.b-ok{background:var(--green-lt);color:var(--green);padding:2px 9px;border-radius:8px;font-size:9.5px;font-weight:700}
.b-fail{background:var(--red-lt);color:var(--red);padding:2px 9px;border-radius:8px;font-size:9.5px;font-weight:700}

/* ── Right panel ── */
.rp{background:var(--surf);border-left:1px solid var(--bdr);display:flex;flex-direction:column;overflow:hidden;position:relative}
#rp-resize{position:absolute;top:0;bottom:0;right:var(--rp-w,312px);width:10px;margin-right:-5px;cursor:col-resize;z-index:300;background:transparent;transition:background .15s}
#rp-resize::after{content:'';position:absolute;top:50%;left:50%;transform:translate(-50%,-50%);width:2px;height:42px;border-radius:2px;background:var(--bdr2);transition:all .15s}
#rp-resize:hover,#rp-resize.dragging{background:rgba(37,99,235,.10)}
#rp-resize:hover::after,#rp-resize.dragging::after{background:var(--blue);height:100%;border-radius:0}
#app.copilot-mode #rp-resize{display:none}
.rp-tabs{display:flex;border-bottom:1px solid var(--bdr);flex-shrink:0}
.rp-tab{padding:10px 13px;font-size:10.5px;font-weight:600;cursor:pointer;color:var(--muted2);border-bottom:2px solid transparent;transition:all .15s;white-space:nowrap}
.rp-tab.active{color:var(--blue);border-bottom-color:var(--blue)}
.rp-body{flex:1;overflow-y:auto}
.rp-panel{display:none}
.rp-panel.show{display:block}
.ins-item{background:var(--surf2);border:1px solid var(--bdr);border-radius:9px;padding:10px 12px;margin:9px;font-size:10.5px}
.ins-src{font-size:8.5px;color:var(--muted2);text-transform:uppercase;letter-spacing:.4px;margin-bottom:4px;font-weight:700}
.ins-msg{color:var(--txt);line-height:1.45;font-weight:500}
.ins-det{color:var(--muted);font-size:9.5px;margin-top:4px}
.sev-warning{border-left:3px solid var(--amber)}
.sev-critical{border-left:3px solid var(--red)}
.sev-success{border-left:3px solid var(--green)}
.sev-info{border-left:3px solid var(--blue)}

/* ── Ask panel ── */
.ask-wrap{padding:11px;border-top:1px solid var(--bdr);flex-shrink:0}
.ask-label{font-size:8.5px;color:var(--muted2);text-transform:uppercase;letter-spacing:.5px;margin-bottom:7px;font-weight:700}
.ask-row{display:flex;gap:7px}
.ask-in{flex:1;background:var(--surf2);border:1px solid var(--bdr);color:var(--txt);border-radius:9px;padding:8px 11px;font-size:11.5px;font-family:inherit}
.ask-in:focus{outline:none;border-color:var(--blue)}
.ask-btn{background:var(--violet);color:#fff;border:none;border-radius:9px;padding:8px 13px;font-size:12px;font-weight:700;cursor:pointer}
.ask-btn:hover{background:#6D28D9}
.ask-resp{margin:9px;background:var(--surf2);border-radius:9px;padding:11px 13px;font-size:11px;line-height:1.65;
  white-space:pre-wrap;max-height:280px;overflow-y:auto;border:1px solid var(--bdr);color:var(--txt);display:none}
.ask-resp.show{display:block}
.ev-item{padding:9px 12px;border-bottom:1px solid var(--bdr);font-size:10.5px}
.ev-src{font-size:8.5px;color:var(--muted2);margin-bottom:3px;font-weight:700;text-transform:uppercase}
.ev-claim{color:var(--txt)}
.ev-bar{height:3px;border-radius:2px;margin-top:5px;background:var(--bdr)}
.ev-fill{height:100%;border-radius:2px;background:var(--green)}
.ev-fill.neg{background:var(--red)}
.narr-item{padding:10px 12px;border-bottom:1px solid var(--bdr)}
.narr-src{font-size:8.5px;color:var(--muted2);text-transform:uppercase;letter-spacing:.4px;margin-bottom:4px;font-weight:700}
.narr-txt{font-size:11px;color:var(--txt);line-height:1.55}
.narr-ts{font-size:9px;color:var(--muted2);margin-top:4px}

/* ── Copilot full mode ── */
.copilot-full{display:flex;flex-direction:column;height:100%}
.copilot-header{padding:22px 30px;border-bottom:1px solid var(--bdr);background:var(--surf)}
.copilot-header h2{font-size:19px;font-weight:800;color:var(--txt);margin-bottom:4px}
.copilot-header p{font-size:12px;color:var(--muted)}
.kpi-row{display:flex;gap:14px;padding:16px 30px;border-bottom:1px solid var(--bdr);background:var(--surf)}
.kpi-card{background:var(--surf2);border:1px solid var(--bdr);border-radius:var(--radius);padding:13px 17px;flex:1}
.kpi-label{font-size:9.5px;text-transform:uppercase;letter-spacing:.7px;color:var(--muted2);margin-bottom:5px;font-weight:700}
.kpi-value{font-size:22px;font-weight:800;color:var(--txt);font-family:'JetBrains Mono',monospace}
.kpi-trend{font-size:10.5px;margin-top:4px;font-weight:600}
.kpi-trend.pos{color:var(--green)}.kpi-trend.neg{color:var(--red)}
.copilot-chat{flex:1;overflow-y:auto;padding:22px 30px;display:flex;flex-direction:column;gap:24px}
.chat-msg{max-width:700px}
.chat-msg.user{align-self:flex-end;text-align:right}
.chat-msg.ai{align-self:flex-start;text-align:left}
.chat-bubble{display:inline-block;max-width:85%;padding:13px 17px;border-radius:14px;font-size:12.5px;line-height:1.65;white-space:pre-wrap;text-align:left}
.chat-msg.user .chat-bubble{background:var(--blue);color:#fff;border-radius:14px 14px 4px 14px}
.chat-msg.ai .chat-bubble{background:var(--surf);border:1px solid var(--bdr);color:var(--txt);border-radius:14px 14px 14px 4px;box-shadow:var(--shadow-sm)}
.chat-ai-label{font-size:9.5px;color:var(--violet);text-transform:uppercase;letter-spacing:.5px;margin-bottom:5px;display:flex;align-items:center;gap:5px;font-weight:700}
.conf-badge{font-size:8.5px;background:var(--violet-lt);color:var(--violet);padding:2px 7px;border-radius:5px;margin-left:auto;font-weight:700}
#ask-history .chat-msg + .chat-msg{margin-top:24px}   /* same breathing room as .copilot-chat, for the Ask-AI side pane */
.copilot-input-wrap{padding:16px 30px;border-top:1px solid var(--bdr);background:var(--surf);display:flex;gap:10px;align-items:flex-end}
.copilot-quick{display:flex;gap:7px;margin-bottom:9px;flex-wrap:wrap;padding:0 30px}
.quick-btn{background:var(--surf2);border:1px solid var(--bdr);color:var(--muted);border-radius:18px;padding:5px 13px;
  font-size:10.5px;cursor:pointer;transition:all .15s;font-family:inherit;font-weight:500}
.quick-btn:hover{border-color:var(--blue);color:var(--blue)}
.copilot-textarea{flex:1;background:var(--surf2);border:1px solid var(--bdr);color:var(--txt);border-radius:10px;
  padding:11px 13px;font-size:12.5px;font-family:inherit;resize:none;min-height:46px;max-height:120px}
.copilot-textarea:focus{outline:none;border-color:var(--blue)}
.copilot-send{background:var(--blue);color:#fff;border:none;border-radius:10px;padding:11px 20px;font-size:13px;
  font-weight:700;cursor:pointer;height:46px;font-family:inherit}
.copilot-send:hover{background:var(--blue-d)}

/* ── sections ── */
.main-section{display:none}
.main-section.show{display:block;animation:fadeIn .25s ease}

/* ── modal ── */
.modal-overlay{position:fixed;inset:0;z-index:8000;background:rgba(15,23,42,.45);backdrop-filter:blur(3px);display:none;
  align-items:center;justify-content:center}
.modal-overlay.show{display:flex;animation:fadeIn .2s ease}
.modal-box{background:var(--surf);border:1px solid var(--bdr);border-radius:16px;padding:26px;width:540px;
  max-height:82vh;overflow-y:auto;box-shadow:var(--shadow-lg)}
.modal-title{font-size:15.5px;font-weight:700;color:var(--txt);margin-bottom:4px}
.modal-desc{font-size:11.5px;color:var(--muted);margin-bottom:18px;line-height:1.5}
.field-label{font-size:10.5px;color:var(--muted);margin-bottom:5px;font-weight:600}
.field-help{font-size:9.5px;color:var(--muted2);margin:-3px 0 8px;line-height:1.4}
.field-input{width:100%;background:var(--surf2);border:1px solid var(--bdr);color:var(--txt);border-radius:8px;
  padding:9px 11px;font-size:12px;font-family:inherit;margin-bottom:4px}
.field-input:focus{outline:none;border-color:var(--blue)}
textarea.field-input{resize:vertical;min-height:64px}
.modal-btns{display:flex;gap:9px;justify-content:flex-end;margin-top:18px}
.btn-cancel{background:var(--surf2);border:1px solid var(--bdr);color:var(--muted);border-radius:8px;padding:9px 18px;
  font-size:12px;cursor:pointer;font-family:inherit;font-weight:600}
.btn-cancel:hover{color:var(--txt)}
.btn-run-mod{background:var(--blue);color:#fff;border:none;border-radius:8px;padding:9px 22px;font-size:12px;
  font-weight:700;cursor:pointer;font-family:inherit}
.btn-run-mod:hover{background:var(--blue-d)}
.btn-run-mod:disabled{opacity:.45;cursor:not-allowed}

/* ── input prompt modal (interactive module input()) ── */
.input-modal{background:var(--surf);border:1px solid var(--bdr);border-radius:14px;padding:22px 24px;min-width:380px;
  max-width:480px;box-shadow:var(--shadow-lg)}
.input-modal h3{margin:0 0 8px;font-size:13.5px;color:var(--blue);font-weight:700}
.input-modal p{margin:0 0 12px;font-size:11px;color:var(--muted);line-height:1.55}

/* ── upload zone ── */
.upload-zone{border:2px dashed var(--bdr2);border-radius:10px;padding:16px;text-align:center;cursor:pointer;
  transition:all .2s;margin-bottom:10px;background:var(--surf2)}
.upload-zone:hover{border-color:var(--blue);background:var(--blue-lt)}
.upload-zone.dragover{border-color:var(--blue);background:var(--blue-lt)}
.uz-icon{font-size:22px;color:var(--muted2);margin-bottom:5px}
.uz-text{font-size:10.5px;color:var(--muted)}
.uz-file{font-size:10.5px;color:var(--green);font-weight:700;margin-top:6px}

@keyframes fadeIn{from{opacity:0;transform:translateY(6px)}to{opacity:1;transform:none}}
@keyframes pulse{0%,100%{opacity:1}50%{opacity:.4}}
</style>
</head>
<body>

<!-- ══ ROLE GATEWAY ════════════════════════════════════════════════════ -->
<div id="gateway">
  <div class="gw-eyebrow">Continum</div>
  <div class="gw-title">Intelligent Experimentation Platform</div>
  <div class="gw-sub">Select your role to personalise navigation, workflows, and the AI copilot for how you work.</div>
  <div class="gw-label">Who are you?</div>
  <div class="role-grid" id="role-grid">
    <div class="role-card" data-role="analyst" data-mode="nav" onclick="selectRole(this)">
      <span class="rc-mode mode-nav">Navigation</span>
      <div class="rc-icon" style="background:var(--blue-lt);color:var(--blue)"><i class="fa-solid fa-chart-line"></i></div>
      <div class="rc-name">Analyst</div>
      <div class="rc-desc">Full platform access, statistical controls, diagnostic workbenches</div>
    </div>
    <div class="role-card" data-role="data_scientist" data-mode="nav" onclick="selectRole(this)">
      <span class="rc-mode mode-nav">Navigation</span>
      <div class="rc-icon" style="background:var(--violet-lt);color:var(--violet)"><i class="fa-solid fa-flask"></i></div>
      <div class="rc-name">Data Scientist</div>
      <div class="rc-desc">Causal inference, advanced analytics, experiment methodology</div>
    </div>
    <div class="role-card" data-role="product_manager" data-mode="hybrid" onclick="selectRole(this)">
      <span class="rc-mode mode-hybrid">Hybrid</span>
      <div class="rc-icon" style="background:var(--teal-lt);color:var(--teal)"><i class="fa-solid fa-table-list"></i></div>
      <div class="rc-name">Product Manager</div>
      <div class="rc-desc">Experiment pipeline, briefs, feature tracking, copilot assist</div>
    </div>
    <div class="role-card" data-role="functional_manager" data-mode="ai" onclick="selectRole(this)">
      <span class="rc-mode mode-ai">AI Copilot</span>
      <div class="rc-icon" style="background:var(--pink-lt);color:var(--pink)"><i class="fa-solid fa-users"></i></div>
      <div class="rc-name">Functional Manager</div>
      <div class="rc-desc">Portfolio overview, team impact, decision support</div>
    </div>
    <div class="role-card" data-role="feature_owner" data-mode="hybrid" onclick="selectRole(this)">
      <span class="rc-mode mode-hybrid">Hybrid</span>
      <div class="rc-icon" style="background:var(--amber-lt);color:var(--amber)"><i class="fa-solid fa-rocket"></i></div>
      <div class="rc-name">Feature Owner</div>
      <div class="rc-desc">Ship decisions, readouts, audience segmentation</div>
    </div>
    <div class="role-card" data-role="engineering_manager" data-mode="nav" onclick="selectRole(this)">
      <span class="rc-mode mode-nav">Navigation</span>
      <div class="rc-icon" style="background:var(--blue-lt);color:var(--blue)"><i class="fa-solid fa-gears"></i></div>
      <div class="rc-name">Engineering Manager</div>
      <div class="rc-desc">Pipeline health, data quality, system monitoring</div>
    </div>
    <div class="role-card" data-role="executive" data-mode="ai" onclick="selectRole(this)">
      <span class="rc-mode mode-ai">AI Copilot</span>
      <div class="rc-icon" style="background:var(--violet-lt);color:var(--violet)"><i class="fa-solid fa-briefcase"></i></div>
      <div class="rc-name">Executive</div>
      <div class="rc-desc">Strategic briefings, portfolio summary, AI-powered insights</div>
    </div>
    <div class="role-card" data-role="reviewer" data-mode="nav" onclick="selectRole(this)">
      <span class="rc-mode mode-nav">Navigation</span>
      <div class="rc-icon" style="background:var(--teal-lt);color:var(--teal)"><i class="fa-solid fa-magnifying-glass"></i></div>
      <div class="rc-name">Experiment Reviewer</div>
      <div class="rc-desc">Readout review, approval workflow, causal validity checks</div>
    </div>
    <div class="role-card" data-role="administrator" data-mode="nav" onclick="selectRole(this)">
      <span class="rc-mode mode-nav">Navigation</span>
      <div class="rc-icon" style="background:var(--red-lt);color:var(--red)"><i class="fa-solid fa-shield-halved"></i></div>
      <div class="rc-name">Administrator</div>
      <div class="rc-desc">RBAC, audit logs, governance, system configuration</div>
    </div>
  </div>
  <button class="gw-btn" id="gw-enter" onclick="enterPlatform()">Enter platform →</button>
</div>

<!-- ══ APP SHELL ═══════════════════════════════════════════════════════ -->
<div id="app">
  <div class="rp-resize" id="rp-resize" title="Drag to resize the chat pane"></div>
  <input type="file" id="readout-file-input" multiple style="display:none" accept=".pdf,.txt,.md,.csv,.json,.docx" onchange="uploadReadout(this.files)">
  <aside class="sb" id="sidebar" style="position:relative; overflow:visible">
    <button onclick="toggleSidebar()" style="position:absolute; top:18px; right:-12px; width:24px; height:24px; border-radius:50%; background:var(--surf); border:1px solid var(--bdr); z-index:2000; cursor:pointer; display:flex; align-items:center; justify-content:center; box-shadow:var(--shadow-sm)">
        <i class="fa-solid fa-chevron-left" id="sb-toggle-icon"></i>
    </button>
    <div class="sb-brand">
      <div class="sb-mark">C</div>
      <div>
        <div class="sb-name">CONTINUM</div>
        <div class="sb-tag">Intelligent Experimentation Platform</div>
      </div>
    </div>
    <div class="sb-role">
      <span class="rp-icon" id="sb-role-icon"><i class="fa-solid fa-chart-line"></i></span>
      <span>Signed in as <b id="sb-role-name">Analyst</b></span>
      <span class="sb-switch" onclick="switchRole()">Switch</span>
    </div>
    <div class="nav-wrap" id="nav-menu"></div>
    <div class="sb-foot">
      <div><b>Session</b> <span id="sb-session">—</span></div>
      <div><b>Experiment</b> <span id="sb-exp">—</span></div>
      <div><b>Runs</b> <span id="sb-runs">0</span></div>
    </div>
  </aside>

  <main class="main" id="main-area">
    <div class="topbar">
      <div class="tb-title" id="topbar-title">Dashboard<span class="tb-sub" id="topbar-sub"></span></div>
      <select class="exp-sel" id="exp-select" onchange="selectExperiment(this.value)">
        <option value="">— Select experiment —</option>
      </select>
      <button class="btn btn-primary" id="run-btn" onclick="runSelected()"><i class="fa-solid fa-play" style="margin-right:6px"></i>Run readout</button>
      <button class="btn btn-ghost" onclick="showSection('history')">History</button>
    </div>

    <div class="content" id="content">

      <!-- DASHBOARD -->
      <div class="main-section show" id="section-dashboard">
        <div class="sec-title">Live platform metrics</div>
        <div class="stat-row" id="dash-stats">
          <div class="stat-card"><div class="stat-label">Total inquiries</div><div class="stat-value" id="stat-n">—</div><div class="stat-trend st-neu" id="stat-n-trend">loading…</div></div>
          <div class="stat-card"><div class="stat-label">Overall IOR</div><div class="stat-value" id="stat-ior">—</div><div class="stat-trend st-neu" id="stat-ior-trend">loading…</div></div>
          <div class="stat-card"><div class="stat-label">Avg order value</div><div class="stat-value" id="stat-aov">—</div><div class="stat-trend st-neu" id="stat-aov-trend">loading…</div></div>
          <div class="stat-card"><div class="stat-label">Experiments</div><div class="stat-value" id="stat-exp">—</div><div class="stat-trend st-neu" id="stat-exp-trend">loading…</div></div>
        </div>

        <div class="sec-title">Phase overview</div>
        <div class="phase-grid">
          <div class="phase-card ph-0" onclick="showSection('discovery')">
            <div class="phase-accent"></div><div class="pc-count" id="count-discovery">— modules</div>
            <div class="pc-icon"><i class="fa-solid fa-magnifying-glass-chart"></i></div>
            <div class="pc-title">Foundation &amp; discovery</div>
            <div class="pc-desc">Schema discovery, data validation, pipeline health, dimension setup, Watchtower anomaly detection</div>
          </div>
          <div class="phase-card ph-1" onclick="showSection('planning')">
            <div class="phase-accent"></div><div class="pc-count" id="count-planning">— modules</div>
            <div class="pc-icon"><i class="fa-solid fa-clipboard-list"></i></div>
            <div class="pc-title">Planning</div>
            <div class="pc-desc">Power calculator, opportunity sizing, audience selection, brief generator, KPI tracking</div>
          </div>
          <div class="phase-card ph-2" onclick="showSection('monitoring')">
            <div class="phase-accent"></div><div class="pc-count" id="count-monitoring">— modules</div>
            <div class="pc-icon"><i class="fa-solid fa-satellite-dish"></i></div>
            <div class="pc-title">Live monitoring</div>
            <div class="pc-desc">Health monitor, mSPRT sequential testing, full experiment analysis pipeline</div>
          </div>
          <div class="phase-card ph-3" onclick="showSection('analysis')">
            <div class="phase-accent"></div><div class="pc-count" id="count-analysis">— modules</div>
            <div class="pc-icon"><i class="fa-solid fa-flask-vial"></i></div>
            <div class="pc-title">Analysis &amp; causal inference</div>
            <div class="pc-desc">DiD, ITS, PSM, RDD, Synthetic Control, Bayesian A/B, segments, ROI, learnings</div>
          </div>
          <div class="phase-card ph-4" onclick="showSection('deploy')">
            <div class="phase-accent"></div><div class="pc-count" id="count-deploy">— modules</div>
            <div class="pc-icon"><i class="fa-solid fa-rocket"></i></div>
            <div class="pc-title">Deploy &amp; targeting</div>
            <div class="pc-desc">Uplift modelling, budget-constrained decision engine</div>
          </div>
          <div class="phase-card ph-tools" onclick="showSection('intelligence')">
            <div class="phase-accent"></div><div class="pc-count" id="count-intelligence">— modules</div>
            <div class="pc-icon"><i class="fa-solid fa-brain"></i></div>
            <div class="pc-title">Intelligence &amp; pre-planning</div>
            <div class="pc-desc">Funnel, cohort, retention, churn, journey analysis, hypothesis generation</div>
          </div>
        </div>

        <div class="sec-title" style="display:flex; align-items:center; gap:8px">
            Execution console
            <button onclick="toggleConsole()" class="btn btn-ghost" style="padding:2px 6px; font-size:9px" id="console-toggle-btn">Collapse</button>
        </div>
        <div class="console-wrap" id="console-wrapper">
          <div class="console-header" style="cursor:pointer" onclick="toggleConsole()">
            <div class="dot" id="console-dot"></div>
            <span id="console-label">Idle</span>
            <span class="console-status" id="console-status">Ready</span>
            <i class="fa-solid fa-chevron-up" id="console-chevron" style="margin-left:8px; font-size:10px"></i>
          </div>
          <div class="console-body" id="console-body">
            <div style="color:#64748B;font-size:11px;margin-top:90px;text-align:center">Select a module from any phase and press Run to execute it live against the backend.</div>
          </div>
          <div class="console-files" id="console-files"></div>
        </div>

        <div class="sec-title">Recent runs</div>
        <div class="tbl-wrap">
          <table class="dt">
            <thead><tr><th>Module</th><th>Phase</th><th>Status</th><th>Duration</th><th>Summary</th></tr></thead>
            <tbody id="history-tbody"><tr><td colspan="5" style="color:var(--muted2);text-align:center;padding:18px">No runs yet this session</td></tr></tbody>
          </table>
        </div>
      </div>

      <!-- PHASE SECTIONS (module grids populated by JS) -->
      <div class="main-section" id="section-discovery"><div class="sec-title">Phase 0 — Foundation &amp; discovery</div><div class="mod-grid" id="grid-discovery"></div></div>
      <div class="main-section" id="section-planning"><div class="sec-title">Phase 1 — Planning</div><div class="mod-grid" id="grid-planning"></div></div>
      <div class="main-section" id="section-monitoring"><div class="sec-title">Phase 2 — Live monitoring</div><div class="mod-grid" id="grid-monitoring"></div></div>
      <div class="main-section" id="section-analysis"><div class="sec-title">Phase 3 — Analysis &amp; causal inference</div><div class="mod-grid" id="grid-analysis"></div></div>
      <div class="main-section" id="section-deploy"><div class="sec-title">Phase 4 — Deploy &amp; targeting</div><div class="mod-grid" id="grid-deploy"></div></div>
      <div class="main-section" id="section-intelligence">
        <div class="sec-title">Pre-planning</div><div class="mod-grid" id="grid-preplanning"></div>
        <div class="sec-title" style="margin-top:18px">Intelligence layer</div><div class="mod-grid" id="grid-intelligence"></div>
        <div class="sec-title" style="margin-top:18px">Tools</div><div class="mod-grid" id="grid-tools"></div>
      </div>

      <!-- HISTORY -->
      <div class="main-section" id="section-history">
        <div class="sec-title">Full run history</div>
        <div class="tbl-wrap">
          <table class="dt">
            <thead><tr><th>Module</th><th>Phase</th><th>Status</th><th>Duration</th><th>Summary</th></tr></thead>
            <tbody id="hist-full-tbody"><tr><td colspan="5" style="color:var(--muted2);text-align:center;padding:18px">No runs yet this session</td></tr></tbody>
          </table>
        </div>
      </div>

      <!-- DATA VIEW -->
      <div class="main-section" id="section-data">
        <div class="sec-title" style="display:flex;align-items:center;gap:12px;flex-wrap:wrap">Connected dataset
          <select class="exp-sel" id="ds-select" style="width:auto" onchange="switchDataset(this.value)"></select>
          <span id="ds-context" style="font-size:11px;color:var(--muted);font-weight:400;text-transform:none;letter-spacing:0"></span>
        </div>
        <div id="data-preview"><div style="padding:18px;color:var(--muted2);font-size:11px">Loading dataset…</div></div>
      </div>

      <!-- OUTPUTS VIEW -->
      <div class="main-section" id="section-outputs">
        <div class="sec-title">Generated Session Outputs</div>
        <div class="tbl-wrap">
          <table class="dt">
            <thead><tr><th>File</th><th>Type</th><th>Generated At</th><th>Action</th></tr></thead>
            <tbody id="outputs-tbody"><tr><td colspan="4" style="color:var(--muted2);text-align:center;padding:18px">No outputs yet this session</td></tr></tbody>
          </table>
        </div>
      </div>

      <!-- COPILOT FULL PAGE -->
      <div class="main-section" id="section-copilot">
        <div class="copilot-full">
          <div class="copilot-header">
            <h2>CONTINUM AI Copilot</h2>
            <p>Ask anything about your experiments, metrics, and decisions — grounded in live data.</p>
          </div>
          <div class="kpi-row" id="copilot-kpis">
            <div class="kpi-card"><div class="kpi-label">Overall IOR</div><div class="kpi-value" id="ck-ior">—</div><div class="kpi-trend" id="ck-ior-trend"></div></div>
            <div class="kpi-card"><div class="kpi-label">Avg order value</div><div class="kpi-value" id="ck-aov">—</div><div class="kpi-trend" id="ck-aov-trend"></div></div>
            <div class="kpi-card"><div class="kpi-label">Total inquiries</div><div class="kpi-value" id="ck-n">—</div><div class="kpi-trend" id="ck-n-trend"></div></div>
            <div class="kpi-card"><div class="kpi-label">Modules run</div><div class="kpi-value" id="ck-runs">0</div><div class="kpi-trend" id="ck-runs-trend"></div></div>
          </div>
          <div class="copilot-chat" id="copilot-chat"></div>
          <div class="copilot-quick">
            <button class="quick-btn" onclick="sendQuick('Show me experiments impacting revenue')">Revenue impact</button>
            <button class="quick-btn" onclick="sendQuick('Why did the treatment underperform?')">Diagnose underperformance</button>
            <button class="quick-btn" onclick="sendQuick('Generate an executive summary for the active experiment')">Executive summary</button>
            <button class="quick-btn" onclick="sendQuick('What should we ship this week?')">Ship recommendations</button>
            <button class="quick-btn" onclick="sendQuick('Compare segments for the active experiment')">Compare segments</button>
          </div>
          <div class="copilot-input-wrap">
            <textarea class="copilot-textarea" id="copilot-input" placeholder="Ask anything about your experiments..." rows="1"
              onkeydown="if(event.key==='Enter'&&!event.shiftKey){event.preventDefault();sendCopilot();}"></textarea>
            <button class="copilot-send" onclick="triggerReadoutUpload()" title="Upload a readout to ask about" style="background:var(--surf2);color:var(--muted);border:1px solid var(--bdr);padding:11px 14px"><i class="fa-solid fa-paperclip"></i></button>
            <button class="copilot-send" onclick="sendCopilot()">Send <i class="fa-solid fa-arrow-up" style="margin-left:5px"></i></button>
          </div>
        </div>
      </div>

    </div>
  </main>

  <aside class="rp" id="right-panel" style="overflow:visible">
    <button onclick="toggleRightPanel()" style="position:absolute; top:18px; left:-12px; width:24px; height:24px; border-radius:50%; background:var(--surf); border:1px solid var(--bdr); z-index:2000; cursor:pointer; display:flex; align-items:center; justify-content:center; box-shadow:var(--shadow-sm)">
        <i class="fa-solid fa-chevron-right" id="rp-toggle-icon"></i>
    </button>
    <div class="rp-tabs">
      <div class="rp-tab active" onclick="switchTab('insights',this)">Insights</div>
      <div class="rp-tab" onclick="switchTab('narrative',this)">Narrative</div>
      <div class="rp-tab" onclick="switchTab('ask',this)">Ask AI</div>
      <div class="rp-tab" onclick="switchTab('outputs',this)">Outputs</div>
    </div>
    <div class="rp-body" id="rp-body">
      <div class="rp-panel show" id="tab-insights"><div id="insights-list" style="padding-top:2px"></div></div>
      <div class="rp-panel" id="tab-narrative"><div id="narrative-list"></div></div>
      <div class="rp-panel" id="tab-outputs">
        <div style="padding:15px; font-size:11px; color:var(--muted); text-align:center" id="outputs-empty">Run a module to see generated output files</div>
        <div id="outputs-list" style="padding:10px"></div>
      </div>
      <div class="rp-panel" id="tab-ask" style="display:flex;flex-direction:column;height:100%">
        <div style="flex:1;overflow-y:auto;padding:20px" id="ask-history"></div>
        <div class="ask-resp" id="ask-response"></div>
        <div class="ask-wrap">
          <div class="ask-label">Ask CONTINUM IEP</div>
          <div class="ask-row">
            <input type="text" class="ask-in" id="ask-input" placeholder="Why did IOR drop yesterday?" onkeydown="if(event.key==='Enter') sendAsk()">
            <button class="ask-btn" onclick="triggerReadoutUpload()" title="Upload a readout to ask about" style="background:var(--surf2);color:var(--muted);border:1px solid var(--bdr)"><i class="fa-solid fa-paperclip"></i></button>
            <button class="ask-btn" onclick="sendAsk()"><i class="fa-solid fa-wand-magic-sparkles"></i></button>
          </div>
        </div>
      </div>
    </div>
  </aside>
</div>

<!-- Module config modal -->
<div class="modal-overlay" id="config-modal">
  <div class="modal-box">
    <div class="modal-title" id="modal-title">Module configuration</div>
    <div class="modal-desc" id="modal-desc">Configure and run this module</div>
    <div id="modal-fields"></div>
    <div class="modal-btns">
      <button class="btn-cancel" onclick="closeModal()">Cancel</button>
      <button class="btn-run-mod" id="modal-run-btn" onclick="executeModule()"><i class="fa-solid fa-play" style="margin-right:6px"></i>Run module</button>
    </div>
  </div>
</div>

<!-- Interactive input() modal (server requests input mid-run) -->
<div class="modal-overlay" id="input-overlay">
  <div class="input-modal">
    <h3 id="input-prompt-title">Module needs input</h3>
    <p id="input-prompt-text"></p>
    <input type="text" class="field-input" id="input-prompt-field" placeholder="Your answer">
    <div class="modal-btns">
      <button class="btn-run-mod" onclick="submitPromptInput()">Submit</button>
    </div>
  </div>
</div>


<script>
// ════════════════════════════════════════════════════════════════════════
// MODULE CATALOG — static metadata (icon/name/description) layered onto
// the live registry returned by GET /api/modules. Field schemas are
// always fetched live from GET /api/module-config/<key> — never hardcoded.
// ════════════════════════════════════════════════════════════════════════
const ROLES = {
  analyst:            { icon:'fa-chart-line',      name:'Analyst',             nav:['discovery','planning','monitoring','analysis','deploy','intelligence','data','outputs','copilot','run_history'] },
  data_scientist:     { icon:'fa-flask',           name:'Data Scientist',      nav:['discovery','planning','monitoring','analysis','deploy','intelligence','data','outputs','copilot','run_history'] },
  product_manager:    { icon:'fa-table-list',      name:'Product Manager',     nav:['planning','monitoring','analysis','intelligence','data','outputs','copilot','run_history'] },
  functional_manager: { icon:'fa-users',           name:'Functional Manager',  nav:['copilot','analysis','data','outputs','run_history'] },
  feature_owner:      { icon:'fa-rocket',          name:'Feature Owner',       nav:['planning','monitoring','analysis','deploy','intelligence','data','outputs','copilot','run_history'] },
  engineering_manager:{ icon:'fa-gears',           name:'Eng Manager',         nav:['discovery','monitoring','intelligence','data','outputs','copilot','run_history'] },
  executive:          { icon:'fa-briefcase',       name:'Executive',           nav:['copilot','outputs'] },
  reviewer:           { icon:'fa-magnifying-glass',name:'Reviewer',            nav:['analysis','monitoring','data','outputs','copilot','run_history'] },
  administrator:      { icon:'fa-shield-halved',   name:'Administrator',       nav:['discovery','planning','monitoring','analysis','deploy','intelligence','data','outputs','copilot','run_history'] },
};

const NAV_DEFS = {
  discovery:    { label:'Foundation & discovery', icon:'fa-magnifying-glass-chart', phase:'phase_0' },
  planning:     { label:'Planning',                icon:'fa-clipboard-list',         phase:'phase_1' },
  monitoring:   { label:'Live monitoring',         icon:'fa-satellite-dish',         phase:'phase_2' },
  analysis:     { label:'Analysis & causal',        icon:'fa-flask-vial',             phase:'phase_3' },
  deploy:       { label:'Deploy & targeting',       icon:'fa-rocket',                 phase:'phase_4' },
  intelligence: { label:'Intelligence & tools',     icon:'fa-brain',                  phase:null },
  data:         { label:'Data',                     icon:'fa-table-cells-large',      phase:null },
  outputs:      { label:'Outputs',                  icon:'fa-file-arrow-down',        phase:null },
  copilot:      { label:'AI Copilot',               icon:'fa-wand-magic-sparkles',    phase:null },
  run_history:  { label:'Run history',              icon:'fa-clock-rotate-left',      phase:null },
};

// Icon + short description per module key (purely cosmetic — backend truth
// for fields/description comes from /api/module-config/<key>)
const MOD_META = {
  schema_discovery:        { icon:'fa-table-cells',        group:'discovery' },
  data_validation:         { icon:'fa-check-double',       group:'discovery' },
  dimension_setup:         { icon:'fa-ruler-combined',     group:'discovery' },
  pipeline_health:         { icon:'fa-heart-pulse',        group:'discovery' },
  watchtower:               { icon:'fa-eye',                group:'discovery' },
  distribution_shift:       { icon:'fa-arrows-left-right',  group:'discovery' },

  power_calculator:         { icon:'fa-bolt',                group:'planning' },
  opportunity_sizing:       { icon:'fa-sack-dollar',         group:'planning' },
  opportunity_sizing_v2:    { icon:'fa-sack-dollar',         group:'planning' },
  audience_selection:       { icon:'fa-bullseye',            group:'planning' },
  brief_generator:          { icon:'fa-file-lines',          group:'planning' },
  metrics_and_tracking:     { icon:'fa-chart-simple',        group:'planning' },
  balance_diagnostics:      { icon:'fa-scale-balanced',      group:'planning' },

  health_monitor:           { icon:'fa-heart-pulse',         group:'monitoring' },
  sequential_testing:       { icon:'fa-chart-line',          group:'monitoring' },
  experiment_analysis:      { icon:'fa-vial-circle-check',   group:'monitoring' },

  causal_analysis:          { icon:'fa-link',                group:'analysis' },
  causal_analysis_full:     { icon:'fa-diagram-project',     group:'analysis' },
  forecasting:               { icon:'fa-chart-area',          group:'analysis' },
  pre_post_analysis:         { icon:'fa-arrows-split-up-and-left', group:'analysis' },
  simpsons_paradox:           { icon:'fa-shuffle',             group:'analysis' },
  roi_tracker:                { icon:'fa-money-bill-trend-up', group:'analysis' },
  roi_synthesis:               { icon:'fa-money-bill-trend-up', group:'analysis' },
  learnings_repository:        { icon:'fa-brain',                group:'analysis' },
  sequential_tester_core:      { icon:'fa-chart-line',           group:'analysis' },
  bayesian_analysis:           { icon:'fa-dice',                  group:'analysis' },
  segment_deep_dive:            { icon:'fa-users-rectangle',       group:'analysis' },
  driver_discovery:             { icon:'fa-key',                    group:'analysis' },
  readout_generator:            { icon:'fa-file-pen',               group:'analysis' },
  executive_summary:            { icon:'fa-file-contract',          group:'analysis' },
  long_term_effects:            { icon:'fa-hourglass-half',         group:'analysis' },
  portfolio_management:         { icon:'fa-chart-pie',               group:'tools' },

  uplift_modeller:               { icon:'fa-rocket',                  group:'deploy' },
  decision_engine:                { icon:'fa-bullseye',                group:'deploy' },

  kpi_synthesis:                   { icon:'fa-chart-simple',            group:'intelligence' },
  guardrail_generation:             { icon:'fa-shield-halved',           group:'intelligence' },
  tracking_plan:                     { icon:'fa-satellite-dish',          group:'intelligence' },
  historical_learning:               { icon:'fa-clock-rotate-left',       group:'intelligence' },
  next_step_generation:               { icon:'fa-forward',                 group:'intelligence' },
  anomaly_synthesis:                   { icon:'fa-triangle-exclamation',    group:'intelligence' },
  analytical_chain:                     { icon:'fa-link',                    group:'intelligence' },
  cross_experiment_learning:             { icon:'fa-diagram-project',         group:'intelligence' },
  adaptive_recommendations:               { icon:'fa-lightbulb',               group:'intelligence' },
  ask_v2:                                  { icon:'fa-comment-dots',            group:'intelligence' },
  open_questions:                           { icon:'fa-circle-question',         group:'intelligence' },
  root_cause:                                { icon:'fa-magnifying-glass',        group:'intelligence' },

  funnel_analysis:                            { icon:'fa-filter',                  group:'preplanning' },
  cohort_analysis:                             { icon:'fa-people-group',            group:'preplanning' },
  retention_analysis:                           { icon:'fa-arrow-rotate-left',        group:'preplanning' },
  churn_analysis:                                { icon:'fa-user-slash',              group:'preplanning' },
  journey_analysis:                               { icon:'fa-route',                   group:'preplanning' },
  opportunity_ranking:                             { icon:'fa-ranking-star',             group:'preplanning' },
  hypothesis_generation:                            { icon:'fa-lightbulb',                group:'preplanning' },
  experiment_design:                                 { icon:'fa-drafting-compass',          group:'preplanning' },
};

const EXP_MODULES = new Set(['health_monitor','sequential_testing','experiment_analysis',
  'causal_analysis','simpsons_paradox','roi_tracker','uplift_modeller','decision_engine',
  'learnings_repository','brief_generator','bayesian_analysis','segment_deep_dive',
  'readout_generator','executive_summary','long_term_effects','driver_discovery']);

// ════════════════════════════════════════════════════════════════════════
// STATE
// ════════════════════════════════════════════════════════════════════════
let currentRole = null;
let liveModules = [];           // from GET /api/modules
let activeExperiment = '';
let currentRunId = null;
let currentEventSource = null;
let selectedModuleKey = null;
let liveConfigCache = {};       // module_key -> config payload

// ════════════════════════════════════════════════════════════════════════
// API CLIENT — thin wrappers, one per real backend route
// ════════════════════════════════════════════════════════════════════════
const Api = {
  async modules() { const r = await fetch('/api/modules'); return r.json(); },
  async moduleConfig(key) { const r = await fetch('/api/module-config/' + encodeURIComponent(key)); return r.json(); },
  async experiments() { const r = await fetch('/api/experiments'); return r.json(); },
  async selectExperiment(name) {
    const r = await fetch('/api/experiments/select', { method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({name}) });
    return r.json();
  },
  async execute(key, fields, experiment_name) {
    const r = await fetch('/api/execute/' + encodeURIComponent(key), {
      method:'POST', headers:{'Content-Type':'application/json'},
      body: JSON.stringify({ fields: fields || {}, experiment_name: experiment_name || undefined })
    });
    return r.json();
  },
  async stop(runId) { const r = await fetch('/api/stop/' + runId, { method:'POST' }); return r.json(); },
  async submitInput(runId, answer) {
    const r = await fetch('/api/input/' + runId, { method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({answer}) });
    return r.json();
  },
  async outputs(runId) { const r = await fetch('/api/outputs/' + runId); return r.json(); },
  async session() { const r = await fetch('/api/session'); return r.json(); },
  async intelligence() { const r = await fetch('/api/intelligence'); return r.json(); },
  async narrative() { const r = await fetch('/api/narrative'); return r.json(); },
  async ask(question, ui_context) {
    const r = await fetch('/api/ask', { method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({question, ui_context: ui_context||{}}) });
    return r.json();
  },
  async askChain(question) {
    const r = await fetch('/api/ask/chain', { method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({question}) });
    return r.json();
  },
  async copilotAsk(question, mode, extra) {
    const body = Object.assign({ question, mode: mode || 'auto',
      ui_context: { active_experiment: (typeof activeExperiment !== 'undefined' ? activeExperiment : '') } }, extra || {});
    const r = await fetch('/api/copilot/ask', { method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify(body) });
    return r.json();
  },
  async compare(a,b) {
    const r = await fetch('/api/compare', { method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({experiment_a:a, experiment_b:b}) });
    return r.json();
  },
  async uploadTemplate(file) {
    const fd = new FormData(); fd.append('file', file);
    const r = await fetch('/api/upload-template', { method:'POST', body: fd });
    return r.json();
  },
};

// ════════════════════════════════════════════════════════════════════════
// ROLE GATEWAY
// ════════════════════════════════════════════════════════════════════════
function selectRole(card) {
  document.querySelectorAll('.role-card').forEach(c => c.classList.remove('selected'));
  card.classList.add('selected');
  currentRole = card.dataset.role;
  document.getElementById('gw-enter').classList.add('active');
}

function switchRole() {
  document.getElementById('app').style.display = 'none';
  document.getElementById('gateway').style.display = 'flex';
  document.querySelectorAll('.role-card').forEach(c => c.classList.remove('selected'));
  document.getElementById('gw-enter').classList.remove('active');
}

async function enterPlatform() {
  if (!currentRole) return;
  const roleInfo = ROLES[currentRole];
  document.getElementById('sb-role-icon').innerHTML = '<i class="fa-solid ' + roleInfo.icon + '"></i>';
  document.getElementById('sb-role-name').textContent = roleInfo.name;

  document.getElementById('gateway').style.display = 'none';
  const app = document.getElementById('app');
  app.style.display = 'grid';

  buildNav(roleInfo.nav);

  if (currentRole === 'executive' || currentRole === 'functional_manager') {
    app.classList.add('copilot-mode');
    showSection('copilot');
  } else {
    app.classList.remove('copilot-mode');
    showSection('dashboard');
  }

  await bootstrapData();
  startIntelligenceStream();
}

function buildNav(sections) {
  const menu = document.getElementById('nav-menu');
  menu.innerHTML = '';
  const label = document.createElement('div');
  label.className = 'nav-label'; label.textContent = 'Workspace';
  menu.appendChild(label);

  // Dashboard always first unless pure-copilot role
  if (sections.length > 1 || sections[0] !== 'copilot') {
    const homeItem = document.createElement('div');
    homeItem.className = 'nav-item active';
    homeItem.innerHTML = '<span class="ni"><i class="fa-solid fa-house"></i></span><span>Dashboard</span>';
    homeItem.onclick = () => showSection('dashboard');
    menu.appendChild(homeItem);
  }

  sections.forEach(sec => {
    const def = NAV_DEFS[sec];
    const item = document.createElement('div');
    item.className = 'nav-item';
    item.innerHTML = `<span class="ni"><i class="fa-solid ${def.icon}"></i></span><span>${def.label}</span>`;
    item.dataset.sec = sec;
    item.onclick = () => showSection(sec);
    menu.appendChild(item);
  });
}

// ════════════════════════════════════════════════════════════════════════
// BOOTSTRAP — pull live state from the real backend
// ════════════════════════════════════════════════════════════════════════
async function bootstrapData() {
  try {
    const sess = await Api.session();
    document.getElementById('sb-session').textContent = sess.session_id || '—';
    document.getElementById('sb-exp').textContent = sess.active_experiment || '—';
    document.getElementById('sb-runs').textContent = sess.n_runs || 0;
    if (sess.active_experiment) activeExperiment = sess.active_experiment;
    renderHistory(sess.history || []);
  } catch(e) { console.warn('session fetch failed', e); }

  try {
    const exps = await Api.experiments();
    const sel = document.getElementById('exp-select');
    sel.innerHTML = '<option value="">— Select experiment —</option>';
    (Array.isArray(exps) ? exps : []).forEach(e => {
      const opt = document.createElement('option');
      opt.value = e.experiment_name; opt.textContent = `${e.experiment_name} (${e.n_rows||0} rows, ${e.n_variants||'?'} variants)`;
      if (e.experiment_name === activeExperiment) opt.selected = true;
      sel.appendChild(opt);
    });
  } catch(e) { console.warn('experiments fetch failed', e); }

  try {
    liveModules = await Api.modules();
    renderAllGrids();
  } catch(e) { console.warn('modules fetch failed', e); }

  try { await refreshKpis(); } catch(e) { console.warn('kpi refresh failed', e); }
  try { await refreshInsights(); } catch(e) { console.warn('insights fetch failed', e); }
  try { await refreshNarrative(); } catch(e) { console.warn('narrative fetch failed', e); }
}

async function refreshKpis() {
  // Use ask/chain with a neutral query to pull live db_facts-derived numbers.
  // The deterministic fallback in ask_chain always returns a line shaped like
  // "Current state: IOR=17.830%  AOV=$0  n=24,000" regardless of LLM availability,
  // so KPIs are correct with or without the LLM loaded.
  try {
    const res = await Api.copilotAsk('What is the current overall IOR, AOV, and inquiry count?', 'data');
    const txt = (res.response || '');
    const n = extractFirstNumber(txt, /n[=:]\s*([\d,]+)/i) || extractFirstNumber(txt, /across\s+([\d,]+)\s+inquir/i);
    const ior = extractFirstPct(txt);
    const aov = extractFirstDollar(txt);
    document.getElementById('stat-n').textContent = n || '—';
    document.getElementById('stat-ior').textContent = ior || '—';
    document.getElementById('stat-aov').textContent = aov !== null ? aov : '—';
    document.getElementById('stat-n-trend').textContent = 'live · gold_experiment_analysis';
    document.getElementById('stat-ior-trend').textContent = res.llm_loaded ? 'grounded + LLM' : 'grounded · deterministic';
    document.getElementById('stat-aov-trend').textContent = res.llm_loaded ? 'grounded + LLM' : 'grounded · deterministic';
    document.getElementById('ck-ior').textContent = ior || '—';
    document.getElementById('ck-aov').textContent = aov !== null ? aov : '—';
    document.getElementById('ck-n').textContent = n || '—';
  } catch(e) { console.warn('kpi refresh failed', e); }
  try {
    const exps = await Api.experiments();
    const count = Array.isArray(exps) ? exps.length : 0;
    document.getElementById('stat-exp').textContent = count;
    document.getElementById('stat-exp-trend').textContent = count + ' total in gold_experiment_analysis';
  } catch(e) {}
  try {
    const sess = await Api.session();
    document.getElementById('ck-runs').textContent = sess.n_runs || 0;
  } catch(e) {}
}

function extractFirstPct(txt) { const m = txt.match(/(\d+\.\d+)%/); return m ? m[1]+'%' : null; }
function extractFirstDollar(txt) { const m = txt.match(/AOV=\$?([\d,]+(?:\.\d+)?)/i) || txt.match(/\$([\d,]+(?:\.\d+)?)/); return m ? '$'+m[1] : null; }
function extractFirstNumber(txt, re) { const m = txt.match(re); return m ? m[1] : null; }

// ════════════════════════════════════════════════════════════════════════
// MODULE GRIDS — built from the LIVE registry (/api/modules), grouped by phase
// ════════════════════════════════════════════════════════════════════════
function renderAllGrids() {
  const byPhase = { phase_0:[], phase_1:[], phase_2:[], phase_3:[], phase_4:[],
                     intelligence:[], pre_planning:[], post_analysis:[], tools:[] };
  liveModules.forEach(m => { (byPhase[m.phase] || (byPhase[m.phase]=[])).push(m); });

  // BUGFIX ("nothing shows when clicking on any phase"): buildGrid() calls
  // used to run back-to-back with no error isolation. buildGrid() sorts on
  // mod.name with no guard, so a single malformed/incomplete module entry
  // anywhere in the registry throws, and since nothing caught it, every
  // grid AFTER the failing one in this list — and ALL of them, if the
  // first call fails — never rendered, with no visible error at all.
  // Each call is now isolated: one bad phase's data degrades to an empty
  // (not broken) grid for just that phase, logged to console, while every
  // other phase still renders normally.
  const safeBuildGrid = (containerId, modules) => {
    try {
      buildGrid(containerId, modules);
    } catch (e) {
      console.error(`Failed to render ${containerId}:`, e);
      const el = document.getElementById(containerId);
      if (el) el.innerHTML = '<div class="grid-error">Some modules in this section could not be displayed. Check the console for details.</div>';
    }
  };

  safeBuildGrid('grid-discovery', byPhase.phase_0 || []);
  safeBuildGrid('grid-planning', byPhase.phase_1 || []);
  safeBuildGrid('grid-monitoring', byPhase.phase_2 || []);
  safeBuildGrid('grid-analysis', [...(byPhase.phase_3||[]), ...(byPhase.post_analysis||[])]);
  safeBuildGrid('grid-deploy', byPhase.phase_4 || []);
  safeBuildGrid('grid-preplanning', byPhase.pre_planning || []);
  safeBuildGrid('grid-intelligence', byPhase.intelligence || []);
  safeBuildGrid('grid-tools', byPhase.tools || []);

  document.getElementById('count-discovery').textContent = (byPhase.phase_0||[]).length + ' modules';
  document.getElementById('count-planning').textContent = (byPhase.phase_1||[]).length + ' modules';
  document.getElementById('count-monitoring').textContent = (byPhase.phase_2||[]).length + ' modules';
  document.getElementById('count-analysis').textContent = ((byPhase.phase_3||[]).length + (byPhase.post_analysis||[]).length) + ' modules';
  document.getElementById('count-deploy').textContent = (byPhase.phase_4||[]).length + ' modules';
  document.getElementById('count-intelligence').textContent =
    ((byPhase.intelligence||[]).length + (byPhase.pre_planning||[]).length + (byPhase.tools||[]).length) + ' modules';
}

function tierForModule(m) {
  if (m.requires_llm) return 3;
  // Tier 2 heuristic: modules whose live config carries fields but isn't pure-LLM
  return 1;
}

function buildGrid(containerId, modules) {
  const container = document.getElementById(containerId);
  if (!container) return;
  container.innerHTML = '';
  // Null-safe sort: a module with a missing/non-string name sorts last
  // instead of throwing (String(undefined) === "undefined", a stable,
  // harmless sort key) — this is the actual line that used to take down
  // every grid rendered after it, see renderAllGrids()'s safeBuildGrid.
  modules.sort((a,b) => String(a && a.name).localeCompare(String(b && b.name)));
  modules.forEach(mod => {
    try {
      if (!mod || !mod.name) { console.warn('Skipping module with no name:', mod); return; }
      const meta = MOD_META[mod.name] || { icon:'fa-cube' };
      const tier = tierForModule(mod);
      const tierClass = tier === 1 ? 't1' : tier === 2 ? 't2' : 't3';
      const card = document.createElement('div');
      card.className = 'mod-card';
      card.id = 'mod-' + mod.name;
      const iconBg = tier === 3 ? 'var(--violet-lt)' : tier === 2 ? 'var(--blue-lt)' : 'var(--teal-lt)';
      const iconFg = tier === 3 ? 'var(--violet)' : tier === 2 ? 'var(--blue)' : 'var(--teal)';
      card.innerHTML = `
        <div class="mod-icon" style="background:${iconBg};color:${iconFg}"><i class="fa-solid ${meta.icon}"></i></div>
        <div class="mod-name">${humanize(mod.name)}</div>
        <span class="tier-badge ${tierClass}">${mod.requires_llm ? 'LLM' : 'Tier 1'}</span>
      `;
      card.title = mod.description || '';
      card.onclick = () => openModuleConfig(mod.name);
      container.appendChild(card);
    } catch (e) {
      // One malformed module must not blank out every other module card
      // in this same grid.
      console.error('Failed to render module card for', mod, e);
    }
  });
}

function humanize(key) {
  return key.split('_').map(w => w.charAt(0).toUpperCase()+w.slice(1)).join(' ');
}

// ════════════════════════════════════════════════════════════════════════
// NAVIGATION
// ════════════════════════════════════════════════════════════════════════
function showSection(sec) {
  document.querySelectorAll('.main-section').forEach(s => s.classList.remove('show'));
  document.querySelectorAll('.nav-item').forEach(n => n.classList.remove('active'));
  const el = document.getElementById('section-' + sec);
  if (el) el.classList.add('show');
  document.querySelectorAll('.nav-item').forEach(n => { if (n.dataset.sec === sec) n.classList.add('active'); });
  if (sec === 'dashboard') {
    const home = document.querySelector('.nav-item:not([data-sec])');
    if (home) home.classList.add('active');
  }
  const def = NAV_DEFS[sec];
  document.getElementById('topbar-title').innerHTML = (def ? def.label : 'Dashboard');
  if (sec === 'history') refreshFullHistory();
  if (sec === 'data') loadDataView();
}

// ════════════════════════════════════════════════════════════════════════
// EXPERIMENT SELECTION (real backend call)
// ════════════════════════════════════════════════════════════════════════
async function selectExperiment(name) {
  activeExperiment = name;
  document.getElementById('sb-exp').textContent = name || '—';
  const sel = document.getElementById('exp-select');
  if (sel) {
      if (!name) sel.style.borderColor = 'var(--red)';
      else sel.style.borderColor = '';
  }
  if (name) {
    try { await Api.selectExperiment(name); } catch(e) { console.warn(e); }
  }
}

function runSelected() {
  if (!activeExperiment) {
      const sel = document.getElementById('exp-select');
      if (sel) {
          sel.style.borderColor = 'var(--red)';
          sel.focus();
      }
      alert('Select an experiment from the dropdown first.');
      return;
  }
  openModuleConfig('experiment_analysis');
}

// ════════════════════════════════════════════════════════════════════════
// MODULE CONFIG MODAL — fields are rendered from the LIVE schema returned
// by GET /api/module-config/<key>. Never hardcoded per-module.
// ════════════════════════════════════════════════════════════════════════
async function openModuleConfig(key) {
  selectedModuleKey = key;

  // Show description in the execution console area before modal opens
  const consoleLabel = document.getElementById('console-label');
  const consoleBody = document.getElementById('console-body');
  if (consoleLabel) consoleLabel.textContent = humanize(key);
  if (consoleBody) consoleBody.innerHTML = '<div style="padding:20px; color:var(--muted)">Fetching module details...</div>';

  const cfg = await Api.moduleConfig(key);

  if (consoleBody) {
      consoleBody.innerHTML = `<div style="padding:20px; color:var(--blue); font-size:13px; font-weight:600">${cfg.description || 'No description available.'}</div>`
          + `<div style="padding:0 20px; color:var(--muted); font-size:11px">Configure this module in the popup and click Run.</div>`;
  }
  liveConfigCache[key] = cfg;

  document.getElementById('modal-title').textContent = humanize(key);
  document.getElementById('modal-desc').textContent = cfg.description || '';

  const fields = document.getElementById('modal-fields');
  fields.innerHTML = '';

  if (cfg.needs_experiment) {
    const wrap = document.createElement('div');
    wrap.innerHTML = `<div class="field-label">Experiment</div>`;
    const sel = document.createElement('select');
    sel.className = 'field-input'; sel.id = 'f-experiment_name';
    sel.innerHTML = '<option value="">— Use active session experiment —</option>';
    (cfg.experiments || []).forEach(e => {
      const opt = document.createElement('option');
      opt.value = e.name; opt.textContent = `${e.name} (n=${e.n}, ${e.variants} variants)`;
      if (e.name === activeExperiment) opt.selected = true;
      sel.appendChild(opt);
    });
    wrap.appendChild(sel);
    fields.appendChild(wrap);
  }

  (cfg.fields || []).forEach(f => {
    if (f.key === 'experiment_name') return; // already handled above
    const wrap = document.createElement('div');
    const labelHtml = `<div class="field-label">${f.label || f.key}</div>`;
    const helpHtml = f.help ? `<div class="field-help">${f.help}</div>` : '';
    let inputHtml = '';
    const fid = 'f-' + sanitizeId(f.key);

    if (f.type === 'select' || f.type === 'experiment_select') {
      const opts = f.type === 'experiment_select' ? (cfg.experiments||[]).map(e=>({v:e.name,t:`${e.name} (n=${e.n})`})) : null;
      inputHtml = `<select class="field-input" id="${fid}" data-key="${escapeAttr(f.key)}">`;
      if (opts) {
        inputHtml += '<option value="">— Select —</option>';
        opts.forEach(o => { inputHtml += `<option value="${escapeAttr(o.v)}">${o.t}</option>`; });
      } else {
        const optionValues = f.option_values || f.options || [];
        const optionLabels = f.options || optionValues;
        optionValues.forEach((v,i) => {
          const sel = (String(v) === String(f.default)) ? 'selected' : '';
          inputHtml += `<option value="${escapeAttr(v)}" ${sel}>${optionLabels[i] || v}</option>`;
        });
      }
      inputHtml += `</select>`;
    } else if (f.type === 'textarea' || f.type === 'text') {
      const tag = f.type === 'textarea' ? 'textarea' : 'input';
      const typeAttr = f.type === 'text' ? 'type="text"' : '';
      inputHtml = `<${tag} class="field-input" id="${fid}" data-key="${escapeAttr(f.key)}" ${typeAttr}
        placeholder="${escapeAttr(f.help||'')}">${f.default ? escapeHtml(f.default) : ''}</${tag}>`;
    } else if (f.type === 'int' || f.type === 'float') {
      const step = f.type === 'int' ? '1' : 'any';
      inputHtml = `<input type="number" step="${step}" class="field-input" id="${fid}" data-key="${escapeAttr(f.key)}"
        value="${f.default !== undefined ? f.default : ''}" ${f.min!==undefined?`min="${f.min}"`:''} ${f.max!==undefined?`max="${f.max}"`:''}>`;
    } else {
      inputHtml = `<input type="text" class="field-input" id="${fid}" data-key="${escapeAttr(f.key)}" value="${f.default!==undefined?escapeAttr(f.default):''}">`;
    }

    wrap.innerHTML = labelHtml + helpHtml + inputHtml;
    fields.appendChild(wrap);
  });

  // (Template upload removed — main's backend exposes no /api/upload-template
  //  route. Readout upload lives in the chat pane via /api/copilot/readout/upload.)

  document.getElementById('config-modal').classList.add('show');
}

function sanitizeId(s) { return s.replace(/[^a-zA-Z0-9]/g, '_'); }
function escapeAttr(s) { return String(s).replace(/"/g,'&quot;'); }
function escapeHtml(s) { return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;'); }

function closeModal() {
  document.getElementById('config-modal').classList.remove('show');
  selectedModuleKey = null;
}

// ════════════════════════════════════════════════════════════════════════
// MODULE EXECUTION — real /api/execute + SSE /api/stream
// ════════════════════════════════════════════════════════════════════════
async function executeModule() {
  if (!selectedModuleKey) return;
  const key = selectedModuleKey;
  const cfg = liveConfigCache[key] || {};

  // Gather field values
  const fieldEls = document.querySelectorAll('#modal-fields [data-key]');
  const fields = {};
  fieldEls.forEach(el => { fields[el.dataset.key] = el.value; });

  const expEl = document.getElementById('f-experiment_name');
  const expName = expEl ? expEl.value : '';

  // Attach uploaded template path if present
  const uz = document.querySelector('.upload-zone');
  if (uz && uz.dataset.templatePath) fields['_template_path'] = uz.dataset.templatePath;

  closeModal();
  showSection('dashboard');

  const dot = document.getElementById('console-dot');
  const label = document.getElementById('console-label');
  const status = document.getElementById('console-status');
  const body = document.getElementById('console-body');
  const filesBox = document.getElementById('console-files');
  dot.classList.add('run');
  label.textContent = 'Running: ' + humanize(key);
  status.textContent = 'Executing…';
  body.innerHTML = '';
  filesBox.style.display = 'none';
  filesBox.innerHTML = '';

  let res;
  try {
    res = await Api.execute(key, fields, expName || activeExperiment);
  } catch (e) {
    appendConsoleLine('ERR', 'Failed to start module: ' + e.message);
    dot.classList.remove('run'); status.textContent = 'Failed'; return;
  }
  if (!res.run_id) {
    appendConsoleLine('ERR', 'Server did not return a run_id');
    dot.classList.remove('run'); status.textContent = 'Failed'; return;
  }

  currentRunId = res.run_id;
  streamRun(res.run_id, key);
}

function appendConsoleLine(level, msg) {
  const body = document.getElementById('console-body');
  const line = document.createElement('div');
  line.className = 'log log-' + level;
  line.textContent = msg;
  body.appendChild(line);
  body.scrollTop = body.scrollHeight;
}

function streamRun(runId, moduleKey) {
  if (currentEventSource) { currentEventSource.close(); }
  const es = new EventSource('/api/stream/' + runId);
  currentEventSource = es;
  const dot = document.getElementById('console-dot');
  const label = document.getElementById('console-label');
  const status = document.getElementById('console-status');

  es.onmessage = async (ev) => {
    let data;
    try { data = JSON.parse(ev.data); } catch(e) { return; }
    const level = data.level, msg = data.msg;

    if (level === 'PING') return;

    if (level === 'INPUT') {
      // msg is itself a JSON string: {"prompt":..., "default":...}
      let payload = {};
      try { payload = JSON.parse(msg); } catch(e) { payload = {prompt: msg, default: ''}; }
      showInputPrompt(runId, payload.prompt, payload.default);
      return;
    }

    if (level === 'FILE') {
      const parts = msg.split('||');
      const fname = parts[0].replace(/^\s+/, '');
      const fpath = parts[1] || '';

      // Update Console
      const filesBox = document.getElementById('console-files');
      filesBox.style.display = 'block';
      const chip = document.createElement('a');
      chip.className = 'file-chip'; chip.textContent = fname.trim();
      chip.href = '/api/file?path=' + encodeURIComponent(fpath);
      chip.target = '_blank';
      filesBox.appendChild(chip);

      // Update Outputs Tab (Right Panel)
      const outList = document.getElementById('outputs-list');
      const outEmpty = document.getElementById('outputs-empty');
      if (outEmpty) outEmpty.style.display = 'none';
      const outItem = document.createElement('div');
      outItem.style.padding = '8px 12px';
      outItem.style.borderBottom = '1px solid var(--bdr)';
      outItem.style.display = 'flex';
      outItem.style.alignItems = 'center';
      outItem.style.gap = '10px';
      outItem.innerHTML = `
        <i class="fa-solid fa-file-arrow-down" style="color:var(--blue)"></i>
        <div style="flex:1">
          <div style="font-weight:600; font-size:12px; color:var(--txt)">${escapeHtml(fname.trim())}</div>
          <div style="font-size:10px; color:var(--muted)">${new Date().toLocaleTimeString()}</div>
        </div>
        <a href="/api/file?path=${encodeURIComponent(fpath)}" target="_blank" class="btn btn-ghost" style="padding:4px 8px; font-size:10px">Download</a>
      `;
      if (outList) outList.prepend(outItem);

      // Update Outputs Section (Left Nav)
      const outTbody = document.getElementById('outputs-tbody');
      if (outTbody) {
        if (outTbody.innerHTML.includes('No outputs yet')) outTbody.innerHTML = '';
        const tr = document.createElement('tr');
        const ext = fname.split('.').pop().toUpperCase();
        tr.innerHTML = `
          <td><b>${escapeHtml(fname.trim())}</b></td>
          <td>${ext}</td>
          <td>${new Date().toLocaleTimeString()}</td>
          <td><a href="/api/file?path=${encodeURIComponent(fpath)}" target="_blank" class="btn btn-ghost" style="padding:4px 8px; font-size:10px">Download</a></td>
        `;
        outTbody.prepend(tr);
      }

      return;
    }

    if (level === 'DONE') {
      dot.classList.remove('run');
      label.textContent = 'Idle';
      status.textContent = 'Completed';
      es.close();
      currentEventSource = null;
      const card = document.getElementById('mod-' + moduleKey);
      if (card) card.classList.add('done');
      await bootstrapData(); // refresh history + KPIs from real backend
      return;
    }

    appendConsoleLine(level, msg);
  };

  es.onerror = () => {
    status.textContent = 'Stream error';
    dot.classList.remove('run');
  };
}

function showInputPrompt(runId, prompt, defaultVal) {
  document.getElementById('input-prompt-title').textContent = 'Module needs input';
  document.getElementById('input-prompt-text').textContent = prompt;
  const field = document.getElementById('input-prompt-field');
  field.value = defaultVal || '';
  field.dataset.runId = runId;
  document.getElementById('input-overlay').classList.add('show');
  field.focus();
}

async function submitPromptInput() {
  const field = document.getElementById('input-prompt-field');
  const runId = field.dataset.runId;
  const answer = field.value;
  document.getElementById('input-overlay').classList.remove('show');
  await Api.submitInput(runId, answer);
}

// ════════════════════════════════════════════════════════════════════════
// HISTORY RENDERING (from /api/session)
// ════════════════════════════════════════════════════════════════════════
function renderHistory(history) {
  const tbody = document.getElementById('history-tbody');
  if (!history || !history.length) {
    tbody.innerHTML = '<tr><td colspan="5" style="color:var(--muted2);text-align:center;padding:18px">No runs yet this session</td></tr>';
    return;
  }
  tbody.innerHTML = history.slice(-8).reverse().map(r => `
    <tr>
      <td>${humanize(r.module)}</td>
      <td style="color:var(--muted)">${r.phase || '—'}</td>
      <td>${r.ok ? '<span class="b-ok">OK</span>' : '<span class="b-fail">FAIL</span>'}</td>
      <td>${(r.elapsed||0).toFixed ? r.elapsed.toFixed(2) : r.elapsed}s</td>
      <td style="color:var(--muted)">${(r.summary||'').slice(0,80)}</td>
    </tr>`).join('');
}

async function refreshFullHistory() {
  try {
    const sess = await Api.session();
    const tbody = document.getElementById('hist-full-tbody');
    const history = sess.history || [];
    if (!history.length) {
      tbody.innerHTML = '<tr><td colspan="5" style="color:var(--muted2);text-align:center;padding:18px">No runs yet this session</td></tr>';
      return;
    }
    tbody.innerHTML = history.slice().reverse().map(r => `
      <tr>
        <td>${humanize(r.module)}</td>
        <td style="color:var(--muted)">${r.phase || '—'}</td>
        <td>${r.ok ? '<span class="b-ok">OK</span>' : '<span class="b-fail">FAIL</span>'}</td>
        <td>${(r.elapsed||0).toFixed ? r.elapsed.toFixed(2) : r.elapsed}s</td>
        <td style="color:var(--muted)">${(r.summary||'').slice(0,100)}</td>
      </tr>`).join('');
  } catch(e) { console.warn(e); }
}

// ════════════════════════════════════════════════════════════════════════
// RIGHT PANEL — Insights / Narrative / Ask / Evidence
// ════════════════════════════════════════════════════════════════════════
function switchTab(tab, el) {
  document.querySelectorAll('.rp-tab').forEach(t => t.classList.remove('active'));
  document.querySelectorAll('.rp-panel').forEach(p => p.classList.remove('show'));
  el.classList.add('active');
  const panel = document.getElementById('tab-' + tab);
  if (panel) panel.classList.add('show');
}

async function refreshInsights() {
  try {
    const data = await Api.intelligence();
    const list = document.getElementById('insights-list');
    const items = (data.insights || []).slice(-10).reverse();
    if (!items.length) {
      list.innerHTML = '<div style="padding:18px;color:var(--muted2);font-size:11px;text-align:center">No insights yet — run a module to generate some</div>';
      return;
    }
    list.innerHTML = items.map(i => `
      <div class="ins-item sev-${(i.severity||'info').toLowerCase()}">
        <div class="ins-src">${i.source||''} · ${(i.created_at||'').slice(0,16)}</div>
        <div class="ins-msg">${i.message||''}</div>
        ${i.detail ? `<div class="ins-det">${i.detail}</div>` : ''}
      </div>`).join('');
  } catch(e) { console.warn('insights failed', e); }
}

async function refreshNarrative() {
  try {
    const stream = await Api.narrative();
    const list = document.getElementById('narrative-list');
    if (!stream || !stream.length) {
      list.innerHTML = '<div style="padding:18px;color:var(--muted2);font-size:11px;text-align:center">No narrative yet</div>';
      return;
    }
    list.innerHTML = stream.map(n => `
      <div class="narr-item">
        <div class="narr-src">${escapeHtml(n.source||'observation')}</div>
        <div class="narr-txt">${escapeHtml(n.text||'')}</div>
        <div class="narr-ts">${(n.created_at||'').slice(0,16)}</div>
      </div>`).join('');
  } catch(e) { console.warn('narrative failed', e); }
}

let intelligenceES = null;
function startIntelligenceStream() {
  if (intelligenceES) intelligenceES.close();
  intelligenceES = new EventSource('/api/intelligence/stream');
  intelligenceES.onmessage = (ev) => {
    const data = JSON.parse(ev.data);
    if (data.level === 'PING') return;

    // Process Insight
    const insList = document.getElementById('insights-list');
    const narrList = document.getElementById('narrative-list');

    // Narrative if type is 'narrative'
    if (data.type === 'narrative') {
      const nItem = document.createElement('div');
      nItem.className = 'narr-item';
      nItem.style.animation = 'fadeIn 0.4s ease';
      nItem.innerHTML = `
        <div class="narr-src">${escapeHtml(data.source || 'observation')}</div>
        <div class="narr-txt">${escapeHtml(data.message || '')}</div>
        <div class="narr-ts">${(data.created_at || '').slice(0, 16)}</div>`;
      if (narrList && (narrList.innerHTML.includes('No narrative yet') || narrList.innerHTML.trim() === '')) narrList.innerHTML = '';
      if (narrList) {
          narrList.prepend(nItem);
          while (narrList.children.length > 20) narrList.lastChild.remove();
      }
    }

    // Always add to Insights
    const iItem = document.createElement('div');
    iItem.className = 'ins-item sev-' + (data.severity || 'info').toLowerCase();
    iItem.style.animation = 'fadeIn 0.4s ease';
    iItem.innerHTML = `
      <div class="ins-src">${escapeHtml(data.source || '')} · ${(data.created_at || '').slice(0, 16)}</div>
      <div class="ins-msg">${escapeHtml(data.message || '')}</div>
      ${data.detail ? `<div class="ins-det">${escapeHtml(data.detail)}</div>` : ''}`;
    if (insList && insList.innerHTML.includes('No insights yet')) insList.innerHTML = '';
    if (insList) {
        insList.prepend(iItem);
        while (insList.children.length > 30) insList.lastChild.remove();
    }
  };
  intelligenceES.onerror = () => {
    intelligenceES.close();
    setTimeout(startIntelligenceStream, 5000);
  };
}

// ════════════════════════════════════════════════════════════════════════
// COPILOT CHAT — ONE conversation, kept in full sync between the right-panel
// "Ask AI" tab (#ask-history) and the full-screen "AI Copilot" (#copilot-chat).
// Backed by main's tool-calling endpoint /api/copilot/ask (detect→confirm→execute).
// ════════════════════════════════════════════════════════════════════════
let CHAT = { history: [], pending: null, busy: false, lastQ: '' };

function fmtMd(s){ return escapeHtml(String(s==null?'':s)).replace(/\*\*([^*]+)\*\*/g,'<strong>$1</strong>').replace(/\n/g,'<br>'); }

function _cpTable(rows, cols){
  if(!rows || !rows.length) return '';
  cols = (cols && cols.length) ? cols : Object.keys(rows[0]);
  const head = cols.map(c=>'<th>'+escapeHtml(c)+'</th>').join('');
  const body = rows.slice(0,12).map(r=>'<tr>'+cols.map(c=>'<td>'+escapeHtml(r[c])+'</td>').join('')+'</tr>').join('');
  return '<div class="tbl-wrap" style="max-height:300px;overflow:auto"><table class="dt"><thead><tr>'+head+'</tr></thead><tbody>'+body+'</tbody></table></div>';
}

function _cpAccordion(title, content, id) {
  return `
    <div style="margin-top:10px; border:1px solid var(--bdr); border-radius:8px; overflow:hidden">
      <div onclick="const el=document.getElementById('${id}'); el.style.display = el.style.display === 'none' ? 'block' : 'none'; window.dispatchEvent(new Event('resize'));"
           style="background:var(--surf2); padding:8px 12px; font-size:11px; font-weight:700; cursor:pointer; display:flex; align-items:center; gap:8px">
        <i class="fa-solid fa-chevron-down" style="font-size:9px"></i> ${title}
      </div>
      <div id="${id}" style="display:none; border-top:1px solid var(--bdr); background:var(--surf)">
        ${content}
      </div>
    </div>`;
}

function _cpMsgHtml(m, idx){
  if(m.role === 'user')
    return '<div class="chat-msg user"><div class="chat-bubble">'+escapeHtml(m.text)+'</div></div>';

  let inner = '<div class="chat-ai-label"><i class="fa-solid fa-wand-magic-sparkles"></i> CONTINUM Copilot'
    + (m.meta && m.meta.mode ? ' <span class="conf-badge">'+escapeHtml(m.meta.mode)+'</span>' : '')
    + '</div><div class="chat-bubble">'+(m.thinking ? '<i style="opacity:.7">Thinking…</i>' : fmtMd(m.text))+'</div>';

  if(m.confirm){
    if(m.confirm.deploy_warning)
      inner += '<div style="margin-top:8px;padding:9px 11px;border-radius:8px;background:var(--amber-lt);border:1px solid var(--amber);color:var(--amber);font-size:11px;line-height:1.5">'+fmtMd(m.confirm.deploy_warning)+'</div>';
    inner += '<div style="margin-top:9px;display:flex;gap:8px;flex-wrap:wrap">'
      + '<button onclick="copilotConfirm()" style="background:var(--blue);color:#fff;border:none;border-radius:8px;padding:7px 14px;font-size:11.5px;font-weight:700;cursor:pointer">Yes, use '+escapeHtml(m.confirm.module_name)+'</button>'
      + '<button onclick="copilotDecline()" style="background:var(--surf2);color:var(--muted);border:1px solid var(--bdr);border-radius:8px;padding:7px 14px;font-size:11.5px;cursor:pointer">No, just answer</button></div>';
  }

  // SQL Accordion
  if(m.meta && m.meta.sql) {
    inner += _cpAccordion('View generated SQL', `<pre style="padding:12px; font-family:'JetBrains Mono'; font-size:11px; background:#0B1220; color:#CBD5E1; margin:0; white-space:pre-wrap">${escapeHtml(m.meta.sql)}</pre>`, 'sql-' + idx);
  }

  // Table Accordion
  if(m.meta && m.meta.table && m.meta.table.length) {
    inner += _cpAccordion(`View result table (${m.meta.table.length} rows)`, _cpTable(m.meta.table, m.meta.columns), 'tbl-' + idx);
  }

  // Visualizations
  if(m.meta && m.meta.visualizations && m.meta.visualizations.length) {
    m.meta.visualizations.forEach((viz, vIdx) => {
        const vizId = `viz-${idx}-${vIdx}`;
        const vizHtml = `<div id="${vizId}" style="width:100%; height:300px; background:var(--surf)"></div>`;
        inner += _cpAccordion('View Visualization', vizHtml, 'viz-box-' + idx + '-' + vIdx);
        setTimeout(() => {
            if(window.Plotly) Plotly.newPlot(vizId, viz.data, viz.layout, {responsive: true, displayModeBar: false});
            else console.warn('Plotly not loaded');
        }, 100);
    });
  }

  if(m.meta && m.meta.next_steps && m.meta.next_steps.length)
    inner += '<div style="margin-top:9px;display:flex;gap:6px;flex-wrap:wrap">'
      + m.meta.next_steps.map(s=>'<button class="quick-btn" data-q="'+escapeAttr(escapeHtml(s))+'" onclick="sendQuick(this.dataset.q)">'+escapeHtml(s)+'</button>').join('') + '</div>';

  return '<div class="chat-msg ai">'+inner+'</div>';
}

// Render the single shared conversation into BOTH chat surfaces (sync).
function renderChat(){
  ['copilot-chat','ask-history'].forEach(function(id){
    const box = document.getElementById(id);
    if(!box) return;
    if(!CHAT.history.length){
      box.innerHTML = (id === 'ask-history')
        ? '<div style="padding:18px;color:var(--muted2);font-size:11px;text-align:center;line-height:1.6">Ask about your experiments, or ask me to run a module<br>(e.g. &quot;read out the latest experiment results&quot;).</div>'
        : '';
      return;
    }
    box.innerHTML = CHAT.history.map((m, i) => _cpMsgHtml(m, i)).join('');
    box.scrollTop = box.scrollHeight;
  });
  const resp = document.getElementById('ask-response'); if(resp){ resp.classList.remove('show'); resp.innerHTML = ''; }
}

// Single entry point for every chat surface + quick chips + confirm/decline.
async function copilotSubmit(question, opts){
  opts = opts || {};
  question = (question || '').trim();
  if(CHAT.busy) return;
  if(!question && !opts.confirm_tool && !opts.decline) return;
  if(opts.confirm_tool)      CHAT.history.push({role:'user', text:'Yes — use ' + ((CHAT.pending && CHAT.pending.module_name) || 'the module')});
  else if(opts.decline)      CHAT.history.push({role:'user', text:'No — just answer'});
  else { CHAT.history.push({role:'user', text:question}); CHAT.lastQ = question; }
  const ph = {role:'ai', thinking:true}; CHAT.history.push(ph);
  CHAT.busy = true; renderChat();

  const timeoutPromise = new Promise((_, reject) =>
    setTimeout(() => reject(new Error('Request timed out after 60 seconds')), 60000)
  );

  try{
    const extra = {};
    if(opts.confirm_tool) extra.confirm_tool = opts.confirm_tool;
    if(opts.decline)      extra.decline = true;
    const d = await Promise.race([
        Api.copilotAsk(CHAT.lastQ, 'auto', extra),
        timeoutPromise
    ]);
    CHAT.history = CHAT.history.filter(function(m){ return m !== ph; });
    if(d.mode === 'confirm' && d.pending_tool){
      CHAT.pending = { key:d.pending_tool.key, module_name:d.pending_tool.module_name, kind:d.pending_tool.kind, deploy_warning:d.deploy_warning };
      CHAT.history.push({role:'ai', text:d.response, confirm:CHAT.pending});
    } else {
      CHAT.pending = null;
      CHAT.history.push({role:'ai', text:(d.response || d.error || '(no response)'),
        meta:{
          table:d.table||[],
          columns:d.columns||[],
          sql: d.sql,
          visualizations: d.visualizations || [],
          next_steps:((d.suggestions && d.suggestions.length) ? d.suggestions : (d.next_steps||[])),
          mode:d.mode
        }
      });
    }
  }catch(e){
    CHAT.history = CHAT.history.filter(function(m){ return m !== ph; });
    CHAT.history.push({role:'ai', text:'Request failed: ' + e.message});
  }
  CHAT.busy = false; renderChat();
}

function copilotConfirm(){
  if(CHAT.pending) {
      showSection('dashboard');
      const body = document.getElementById('console-body');
      if (body) {
          body.innerHTML = `<div style="padding:15px; color:var(--blue); font-size:12px"><b>Executing ${CHAT.pending.module_name}...</b></div>`;
      }
      copilotSubmit('', {confirm_tool: CHAT.pending.key});
  }
}
function copilotDecline(){ copilotSubmit('', {decline:true}); }

// Both surfaces + quick chips funnel into the one shared conversation.
function sendAsk(){
  const i=document.getElementById('ask-input');
  const q=(i.value||'').trim();
  if(!q) return;
  if (!activeExperiment && (q.toLowerCase().includes('experiment') || q.toLowerCase().includes('result') || q.toLowerCase().includes('this'))) {
      alert('Please select an experiment first so I have context to answer your question.');
      const sel = document.getElementById('exp-select');
      if (sel) { sel.style.borderColor = 'var(--red)'; sel.focus(); }
      return;
  }
  i.value='';
  copilotSubmit(q);
}
function sendCopilot(){ const i=document.getElementById('copilot-input'); const q=(i.value||'').trim(); if(!q) return; i.value=''; copilotSubmit(q); }
function sendQuick(q){ copilotSubmit(q); }
function renderEvidence(){ /* /api/copilot/ask does not return an evidence chain */ }

// ════════════════════════════════════════════════════════════════════════
// Periodic refresh for insights/narrative (light polling, real endpoints)
// ════════════════════════════════════════════════════════════════════════
// ════════════════════════════════════════════════════════════════════════
// DATA VIEW — dataset switcher + sample-row preview
// (/api/copilot/datasets, /api/copilot/dataset, /api/copilot/data-preview)
// ════════════════════════════════════════════════════════════════════════
async function loadDataView(){
  const box = document.getElementById('data-preview');
  try{
    const ds = await (await fetch('/api/copilot/datasets')).json();
    const sel = document.getElementById('ds-select');
    if(sel) sel.innerHTML = (ds.datasets||[]).map(function(d){
      return '<option value="'+escapeAttr(d.name)+'"'+(d.name===ds.active?' selected':'')+'>'+escapeHtml(d.name)+'</option>'; }).join('');
  }catch(e){ console.warn('datasets fetch failed', e); }
  box.innerHTML = '<div style="padding:18px;color:var(--muted2);font-size:11px">Loading dataset…</div>';
  try{
    const d = await (await fetch('/api/copilot/data-preview')).json();
    if(d.error){ box.innerHTML = '<div class="grid-error">'+escapeHtml(d.error)+'</div>'; return; }
    const ctx = document.getElementById('ds-context'); if(ctx) ctx.textContent = d.domain_context ? ('— '+d.domain_context) : '';
    const tables = d.tables || [];
    // Sort tables so Silver/Gold are first
    tables.sort((a,b) => {
        const order = ['gold_experiment_analysis', 'silver_inquiries', 'silver_users', 'silver_orders', 'silver_quotes'];
        const ai = order.indexOf(a.table), bi = order.indexOf(b.table);
        if (ai === -1 && bi === -1) return a.table.localeCompare(b.table);
        if (ai === -1) return 1;
        if (bi === -1) return -1;
        return ai - bi;
    });
    box.innerHTML = tables.length ? tables.map(function(t,i){
      const cols = t.columns || (t.rows&&t.rows[0] ? Object.keys(t.rows[0]) : []);
      const head = cols.map(function(c){ return '<th>'+escapeHtml(c)+'</th>'; }).join('');
      const body = (t.rows||[]).slice(0,10).map(function(r){
        return '<tr>'+cols.map(function(c){ return '<td>'+escapeHtml(r[c]==null?'':r[c])+'</td>'; }).join('')+'</tr>'; }).join('');
      const title = (t.table?escapeHtml(t.table):('Table '+(i+1))) + ' · ' + (t.n_rows!=null?t.n_rows:(t.rows||[]).length) + ' rows';
      return '<div class="sec-title" style="margin-top:16px; font-weight:800; color:var(--blue)">'+title+'</div>'
        + '<div class="tbl-wrap" style="overflow:auto"><table class="dt"><thead><tr>'+head+'</tr></thead><tbody>'+body+'</tbody></table></div>';
    }).join('') : '<div style="padding:18px;color:var(--muted2);font-size:11px">No tables in this dataset.</div>';
  }catch(e){ box.innerHTML = '<div class="grid-error">Could not load the data preview.</div>'; }
}
async function switchDataset(name){
  if(!name) return;
  document.getElementById('data-preview').innerHTML = '<div style="padding:18px;color:var(--muted2);font-size:11px">Switching dataset…</div>';
  try{ await fetch('/api/copilot/dataset', {method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({dataset:name})}); }catch(e){}
  loadDataView();
}

// ════════════════════════════════════════════════════════════════════════
// READOUT UPLOAD — attach a readout doc to the Copilot library; the chatbot
// then answers grounded in it (/api/copilot/readout/upload).
// ════════════════════════════════════════════════════════════════════════
function toggleSidebar() {
  const app = document.getElementById('app');
  const icon = document.getElementById('sb-toggle-icon');
  app.classList.toggle('sb-collapsed');
  const collapsed = app.classList.contains('sb-collapsed');
  icon.className = collapsed ? 'fa-solid fa-chevron-right' : 'fa-solid fa-chevron-left';
  if (collapsed) {
      document.getElementById('sidebar').style.minWidth = '0';
      document.getElementById('sidebar').style.width = '0';
  } else {
      document.getElementById('sidebar').style.minWidth = '';
      document.getElementById('sidebar').style.width = '';
  }
}

function toggleRightPanel() {
  const app = document.getElementById('app');
  const icon = document.getElementById('rp-toggle-icon');
  app.classList.toggle('rp-collapsed');
  const collapsed = app.classList.contains('rp-collapsed');
  icon.className = collapsed ? 'fa-solid fa-chevron-left' : 'fa-solid fa-chevron-right';
}

function toggleConsole() {
  const body = document.getElementById('console-body');
  const files = document.getElementById('console-files');
  const chevron = document.getElementById('console-chevron');
  const btn = document.getElementById('console-toggle-btn');
  const isCollapsed = body.style.display === 'none';

  body.style.display = isCollapsed ? 'block' : 'none';
  if (files.innerHTML !== '') files.style.display = isCollapsed ? 'block' : 'none';

  chevron.className = isCollapsed ? 'fa-solid fa-chevron-up' : 'fa-solid fa-chevron-down';
  btn.textContent = isCollapsed ? 'Collapse' : 'Expand';
}

function triggerReadoutUpload(){ const i = document.getElementById('readout-file-input'); if(i) i.click(); }
async function uploadReadout(files){
  if(!files || !files.length) return;
  const names = Array.from(files).map(function(f){ return f.name; }).join(', ');
  CHAT.history.push({role:'user', text:'📎 Uploading readout: ' + names});
  const ph = {role:'ai', thinking:true}; CHAT.history.push(ph); renderChat();
  try{
    const fd = new FormData(); Array.from(files).forEach(function(f){ fd.append('files', f); });
    const d = await (await fetch('/api/copilot/readout/upload', {method:'POST', body:fd})).json();
    CHAT.history = CHAT.history.filter(function(m){ return m !== ph; });
    const ok = (d.added||[]).filter(function(a){ return !a.error; });
    if(ok.length){
      CHAT.history.push({role:'ai',
        text:'📄 Added **'+ok.length+'** readout'+(ok.length>1?'s':'')+' to the library ('+ok.map(function(a){return a.name;}).join(', ')+'). Ask me anything about '+(ok.length>1?'them':'it')+'.',
        meta:{ next_steps:['Summarize the readout','What did the readout recommend?','What are the key risks in the readout?'] }});
    } else {
      CHAT.history.push({role:'ai', text:'Upload failed: ' + ((((d.added||[])[0]||{}).error) || d.error || 'unknown error')});
    }
  }catch(e){
    CHAT.history = CHAT.history.filter(function(m){ return m !== ph; });
    CHAT.history.push({role:'ai', text:'Upload failed: ' + e.message});
  }
  const fi = document.getElementById('readout-file-input'); if(fi) fi.value = '';
  renderChat();
}

// ── Resizable right panel (chat pane): drag its left edge ──────────────────
(function(){
  const handle = document.getElementById('rp-resize');
  const app = document.getElementById('app');
  if(!handle || !app) return;
  const MIN=260, MAX=720;
  let dragging=false, lastW=312;
  try { const s=parseInt(localStorage.getItem('rpWidth')||'',10); if(s>=MIN && s<=MAX){ lastW=s; app.style.setProperty('--rp-w', s+'px'); } } catch(e){}
  handle.addEventListener('mousedown', function(e){
    if(app.classList.contains('copilot-mode')) return;
    dragging=true; handle.classList.add('dragging');
    document.body.style.userSelect='none'; document.body.style.cursor='col-resize'; e.preventDefault();
  });
  document.addEventListener('mousemove', function(e){
    if(!dragging) return;
    let w = window.innerWidth - e.clientX;
    if(w<MIN) w=MIN; if(w>MAX) w=MAX;
    lastW=w; app.style.setProperty('--rp-w', w+'px');
  });
  document.addEventListener('mouseup', function(){
    if(!dragging) return;
    dragging=false; handle.classList.remove('dragging');
    document.body.style.userSelect=''; document.body.style.cursor='';
    try { localStorage.setItem('rpWidth', lastW); } catch(e){}
  });
})();
</script>

</body>
</html>
"""
