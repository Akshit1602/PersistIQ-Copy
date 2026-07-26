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
/* NOTE: do NOT add `transition:grid-template-columns` here — Chromium fails to
   interpolate a var()-driven track change alongside the 1fr track, which leaves
   the collapsed pane stuck at its old width (the C5 collapse silently no-ops).
   Instant collapse is correct and reliable. */
#app{display:none;position:relative;grid-template-columns:var(--sb-w,226px) 1fr var(--rp-w,312px);height:100vh;overflow:hidden}
#app.copilot-mode{grid-template-columns:var(--sb-w,226px) 1fr 0}
/* Collapsible panes (Snowflake-style): collapsing a pane drives its grid column
   to 0 and the pane (overflow:hidden) clips away. A thin floating button at the
   screen edge brings it back. */
#app.sb-collapsed{--sb-w:0px}
#app.rp-collapsed{--rp-w:0px}
.pane-toggle{background:transparent;border:none;color:var(--muted2);cursor:pointer;font-size:12px;padding:4px 6px;border-radius:6px;line-height:1}
.pane-toggle:hover{background:var(--surf2);color:var(--txt)}
.pane-expander{position:fixed;top:64px;z-index:400;background:var(--surf);border:1px solid var(--bdr);color:var(--muted);
  width:22px;height:40px;border-radius:0 8px 8px 0;cursor:pointer;display:none;align-items:center;justify-content:center;
  box-shadow:var(--shadow-sm);font-size:11px}
.pane-expander:hover{color:var(--blue);border-color:var(--blue)}
#sb-expander{left:0}
#rp-expander{right:0;border-radius:8px 0 0 8px}
#app.sb-collapsed #sb-expander{display:flex}
#app.rp-collapsed:not(.copilot-mode) #rp-expander{display:flex}

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
/* ── Run status toasts (#1): outcome surfaced outside the console ── */
#toast-wrap{position:fixed;right:18px;bottom:18px;z-index:9999;display:flex;flex-direction:column;gap:8px;max-width:380px}
.toast{padding:11px 14px;border-radius:10px;font-size:12px;line-height:1.5;box-shadow:var(--shadow-sm);
  border:1px solid var(--bdr);background:var(--surf);color:var(--txt);white-space:pre-wrap;word-break:break-word;
  opacity:0;transform:translateY(8px);transition:opacity .18s,transform .18s}
.toast.show{opacity:1;transform:translateY(0)}
.toast-ok{border-left:3px solid var(--green,#16a34a)}
.toast-err{border-left:3px solid var(--red,#dc2626);background:var(--amber-lt,#fff7ed)}
.toast b{font-weight:700}
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
.rp-tabs{display:flex;border-bottom:1px solid var(--bdr);flex-shrink:0;align-items:stretch}
/* tabs scroll horizontally if they don't fit; the collapse toggle stays pinned+visible (#3) */
.rp-tabs-scroll{display:flex;flex:1;min-width:0;overflow-x:auto;scrollbar-width:none}
.rp-tabs-scroll::-webkit-scrollbar{display:none}
.rp-tabs .pane-toggle{flex-shrink:0;border-left:1px solid var(--bdr)}
.rp-tab{padding:10px 13px;font-size:10.5px;font-weight:600;cursor:pointer;color:var(--muted2);border-bottom:2px solid transparent;transition:all .15s;white-space:nowrap}
.rp-tab.active{color:var(--blue);border-bottom-color:var(--blue)}
.rp-body{flex:1;overflow-y:auto}
.rp-panel{display:none}
.rp-panel.show{display:block}
/* The Ask-AI pane is a flex column (chat history grows, composer pinned to the
   bottom). It must ONLY appear when its tab is active — an inline display:flex
   here used to override .rp-panel{display:none}, leaking the chat onto the
   Insights / Narrative / Evidence tabs. id+class wins over .rp-panel.show. */
#tab-ask{flex-direction:column;height:100%}
#tab-ask.show{display:flex}
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
.cp-select-row{display:flex;align-items:center;gap:8px;flex-wrap:wrap;margin-top:12px}
.cp-select-lbl{font-size:10.5px;font-weight:700;color:var(--muted2);display:inline-flex;align-items:center;gap:5px}
.cp-scope{margin-top:10px;font-size:11.5px;padding:8px 12px;border-radius:8px;line-height:1.5}
.cp-scope.none{background:rgba(239,68,68,.10);color:#fca5a5;border:1px solid rgba(239,68,68,.30)}
.cp-scope.partial{background:rgba(245,158,11,.10);color:#fcd34d;border:1px solid rgba(245,158,11,.28)}
.cp-scope.set{background:rgba(34,197,94,.10);color:#86efac;border:1px solid rgba(34,197,94,.28)}
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
/* Ask-AI side pane: give the shared chat bubbles the same breathing room as
   the full-screen copilot, plus a quick-action chip row that mirrors the
   copilot's .copilot-quick (A4/A5 parity + spacing fix). */
#ask-history{display:flex;flex-direction:column;gap:18px}
#ask-history .chat-msg + .chat-msg{margin-top:0}
#ask-history .chat-msg{max-width:100%}
#ask-history .chat-bubble{max-width:90%;padding:11px 14px}
.ask-quick{display:flex;gap:6px;flex-wrap:wrap;padding:9px 11px 0;flex-shrink:0}
/* Right-pane loading placeholder (#1) */
.rp-loading{padding:20px 18px;color:var(--muted2);font-size:11px;text-align:center;display:flex;align-items:center;justify-content:center;gap:8px}
/* Ask-pane portfolio KPI tiles (compact, fit the narrow right pane) (#2) */
.ask-kpis{display:grid;grid-template-columns:1fr 1fr;gap:7px;padding:9px;border-bottom:1px solid var(--bdr);flex-shrink:0}
.ask-kpi{background:var(--surf2);border:1px solid var(--bdr);border-radius:8px;padding:8px 9px}
.ask-kpi .akl{font-size:8px;text-transform:uppercase;letter-spacing:.4px;color:var(--muted2);font-weight:700;margin-bottom:3px}
.ask-kpi .akl small{text-transform:none;letter-spacing:0;opacity:.8}
.ask-kpi .akv{font-size:15px;font-weight:800;font-family:'JetBrains Mono',monospace;color:var(--txt)}
/* Ask-pane experiment scope chip: makes the active experiment obvious, warns when none (#2/#4) */
.ask-scope{display:flex;align-items:center;gap:7px;font-size:10.5px;padding:8px 11px;border-bottom:1px solid var(--bdr);flex-shrink:0;line-height:1.4}
.ask-scope.none{background:var(--amber-lt,#fff7ed);color:var(--amber,#b45309)}
.ask-scope.set{background:var(--surf2);color:var(--muted)}
.ask-scope b{color:var(--txt)}
.ask-scope .scope-act{margin-left:auto;color:var(--blue);cursor:pointer;font-weight:700;white-space:nowrap}
.ask-scope .scope-act:hover{text-decoration:underline}
.cp-clarify{margin-top:9px;font-size:10.5px;color:var(--muted);display:flex;gap:6px;flex-wrap:wrap;align-items:center}
@keyframes expflash{0%,100%{box-shadow:0 0 0 0 rgba(59,130,246,0)}30%{box-shadow:0 0 0 3px rgba(59,130,246,.45)}}
.exp-flash{animation:expflash 1s ease 2}
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

/* ── Copilot collapsibles (SQL / table / charts) + callouts ── */
.cp-acc{margin-top:9px;border:1px solid var(--bdr);border-radius:9px;background:var(--surf2);overflow:hidden}
.cp-acc>summary{cursor:pointer;list-style:none;padding:8px 11px;font-size:10.5px;font-weight:700;color:var(--muted);
  display:flex;align-items:center;gap:7px;user-select:none}
.cp-acc>summary::-webkit-details-marker{display:none}
.cp-acc>summary::after{content:"\f078";font-family:"Font Awesome 6 Free";font-weight:900;margin-left:auto;font-size:8px;color:var(--muted2);transition:transform .15s}
.cp-acc[open]>summary::after{transform:rotate(180deg)}
.cp-acc>summary:hover{color:var(--txt)}
.cp-acc-body{padding:0 11px 11px}
.cp-sql{font-family:'JetBrains Mono',monospace;font-size:10.5px;background:#0B1220;color:#CBD5E1;border-radius:7px;
  padding:10px 12px;white-space:pre-wrap;word-break:break-word;line-height:1.6;margin:0}
.cp-chart{width:100%}
.cp-tool-desc{margin-top:8px;padding:8px 11px;border-radius:8px;background:var(--blue-lt);border:1px solid var(--bdr);
  color:var(--txt);font-size:11px;line-height:1.5}
.cp-tool-desc i{color:var(--blue);margin-right:5px}
.cp-callout{padding:11px 13px;border-radius:10px;font-size:12px;line-height:1.55}
.cp-callout-warn{background:var(--amber-lt);border:1px solid var(--amber);color:var(--amber)}
.cp-callout-warn i{margin-right:6px}

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
  <button class="pane-expander" id="sb-expander" title="Show sidebar" onclick="togglePane('sb')"><i class="fa-solid fa-angles-right"></i></button>
  <button class="pane-expander" id="rp-expander" title="Show panel" onclick="togglePane('rp')"><i class="fa-solid fa-angles-left"></i></button>
  <div class="rp-resize" id="rp-resize" title="Drag to resize the chat pane"></div>
  <input type="file" id="readout-file-input" multiple style="display:none" accept=".pdf,.txt,.md,.csv,.json,.docx" onchange="uploadReadout(this.files)">
  <aside class="sb" id="sidebar">
    <div class="sb-brand">
      <div class="sb-mark">C</div>
      <div>
        <div class="sb-name">CONTINUM</div>
        <div class="sb-tag">Intelligent Experimentation Platform</div>
      </div>
      <button class="pane-toggle" style="margin-left:auto" title="Collapse sidebar" onclick="togglePane('sb')"><i class="fa-solid fa-angles-left"></i></button>
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
      <span style="margin-left:auto;display:flex;align-items:center;gap:6px;font-size:10.5px;color:var(--muted2);font-weight:600">
        <i class="fa-solid fa-database" style="font-size:11px"></i>Dataset
        <select class="exp-sel" id="ds-select-top" title="Active dataset — switching changes it app-wide" style="width:auto" onchange="switchDataset(this.value)"></select>
      </span>
      <select class="exp-sel" id="exp-select" onchange="selectExperiment(this.value)">
        <option value="">— All experiments —</option>
      </select>
      <button class="btn btn-ghost" id="new-exp-btn" title="Create a new experiment" onclick="openNewExperiment()"><i class="fa-solid fa-plus" style="margin-right:5px"></i>New experiment</button>
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

      <!-- OUTPUT (generated module artifacts — the outputs folder) -->
      <div class="main-section" id="section-output">
        <div class="sec-title" style="display:flex;align-items:center;gap:10px">Generated output
          <button class="btn btn-ghost" style="margin-left:auto;padding:5px 11px" onclick="loadOutputView()"><i class="fa-solid fa-rotate" style="margin-right:5px"></i>Refresh</button>
        </div>
        <div id="output-list"><div style="padding:18px;color:var(--muted2);font-size:11px">Run a module to generate output…</div></div>
      </div>

      <!-- COPILOT FULL PAGE -->
      <div class="main-section" id="section-copilot">
        <div class="copilot-full">
          <div class="copilot-header">
            <h2>CONTINUM AI Copilot</h2>
            <p>Ask anything about your experiments, metrics, and decisions — grounded in live data.</p>
            <div class="cp-select-row">
              <span class="cp-select-lbl"><i class="fa-solid fa-database"></i> Company / dataset</span>
              <select class="exp-sel" id="cp-ds-select" onchange="switchDataset(this.value)"></select>
              <span class="cp-select-lbl"><i class="fa-solid fa-flask"></i> Experiment</span>
              <select class="exp-sel" id="cp-exp-select" onchange="selectExperiment(this.value)"></select>
              <button class="btn btn-ghost" onclick="openNewExperiment()" style="padding:5px 10px;font-size:11px"><i class="fa-solid fa-plus" style="margin-right:5px"></i>New</button>
            </div>
            <div class="cp-scope none" id="cp-scope"></div>
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

  <aside class="rp" id="right-panel">
    <div class="rp-tabs">
      <div class="rp-tabs-scroll">
        <div class="rp-tab active" onclick="switchTab('insights',this)">Insights</div>
        <div class="rp-tab" onclick="switchTab('narrative',this)">Narrative</div>
        <div class="rp-tab" onclick="switchTab('ask',this)">Ask AI</div>
        <div class="rp-tab" onclick="switchTab('evidence',this)">Evidence</div>
        <div class="rp-tab" onclick="switchTab('console',this)">Console</div>
      </div>
      <button class="pane-toggle" title="Collapse panel" onclick="togglePane('rp')"><i class="fa-solid fa-angles-right"></i></button>
    </div>
    <div class="rp-body" id="rp-body">
      <div class="rp-panel show" id="tab-insights"><div id="insights-list" style="padding-top:2px"><div class="rp-loading"><i class="fa-solid fa-spinner fa-spin"></i> Loading insights…</div></div></div>
      <div class="rp-panel" id="tab-narrative"><div id="narrative-list"><div class="rp-loading"><i class="fa-solid fa-spinner fa-spin"></i> Loading narrative…</div></div></div>
      <div class="rp-panel" id="tab-ask">
        <div class="ask-kpis" id="ask-kpis" title="Experimentation portfolio — GMV is measured; margin is a modeled 30% assumption (no spend is recorded in the data)">
          <div class="ask-kpi"><div class="akl">Experiments</div><div class="akv" id="ak-exp">—</div></div>
          <div class="ask-kpi"><div class="akl">Overall IOR</div><div class="akv" id="ak-ior">—</div></div>
          <div class="ask-kpi"><div class="akl">Converted orders</div><div class="akv" id="ak-orders">—</div></div>
          <div class="ask-kpi"><div class="akl">Avg order value</div><div class="akv" id="ak-aov">—</div></div>
          <div class="ask-kpi"><div class="akl">GMV <small>return</small></div><div class="akv" id="ak-gmv">—</div></div>
          <div class="ask-kpi"><div class="akl">Margin <small>modeled 30%</small></div><div class="akv" id="ak-margin">—</div></div>
        </div>
        <div class="ask-scope none" id="ask-scope"></div>
        <div style="flex:1;overflow-y:auto;padding:6px 4px" id="ask-history"></div>
        <div class="ask-resp" id="ask-response"></div>
        <div class="ask-quick" id="ask-quick">
          <button class="quick-btn" onclick="sendQuick('What is the current IOR, AOV and inquiry count?')">Current metrics</button>
          <button class="quick-btn" onclick="sendQuick('Read out the latest experiment results')">Readout</button>
          <button class="quick-btn" onclick="sendQuick('Why did the treatment underperform?')">Diagnose</button>
          <button class="quick-btn" onclick="sendQuick('What should I run next?')">Next step</button>
        </div>
        <div class="ask-wrap">
          <div class="ask-label">Ask CONTINUM IEP</div>
          <div class="ask-row">
            <input type="text" class="ask-in" id="ask-input" placeholder="Why did IOR drop yesterday?" onkeydown="if(event.key==='Enter') sendAsk()">
            <button class="ask-btn" onclick="triggerReadoutUpload()" title="Upload a readout to ask about" style="background:var(--surf2);color:var(--muted);border:1px solid var(--bdr)"><i class="fa-solid fa-paperclip"></i></button>
            <button class="ask-btn" onclick="sendAsk()" title="Ask"><i class="fa-solid fa-wand-magic-sparkles"></i></button>
          </div>
        </div>
      </div>
      <div class="rp-panel" id="tab-evidence">
        <div style="padding:11px 13px;font-size:10px;color:var(--muted);border-bottom:1px solid var(--bdr);font-weight:600">Evidence chain for last query</div>
        <div id="evidence-chain"><div style="padding:18px;color:var(--muted2);font-size:11px;text-align:center">Ask a question to see grounded evidence</div></div>
      </div>
      <div class="rp-panel" id="tab-console">
        <div class="console-wrap" style="margin:11px;border-radius:8px">
          <div class="console-header">
            <div class="dot" id="console-dot"></div>
            <span id="console-label">Idle</span>
            <span class="console-status" id="console-status">Ready</span>
          </div>
          <div class="console-body" id="console-body">
            <div style="color:#64748B;font-size:11px;margin-top:90px;text-align:center">Run a module (from a card or the Ask-AI chat) to see it execute live here.</div>
          </div>
          <div class="console-files" id="console-files"></div>
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

<!-- New experiment modal — create an experiment under a dataset (persisted). -->
<div class="modal-overlay" id="newexp-modal">
  <div class="modal-box">
    <div class="modal-title">New experiment</div>
    <div class="modal-desc">Register a new experiment under a dataset. It appears in the experiment dropdown right away.</div>
    <div id="newexp-fields">
      <div class="field-label">Dataset / company</div>
      <select class="field-input" id="ne-dataset"></select>
      <div class="field-label" style="margin-top:10px">Experiment name</div>
      <input type="text" class="field-input" id="ne-name" placeholder="e.g. checkout_button_color">
      <div class="field-label" style="margin-top:10px">Hypothesis</div>
      <input type="text" class="field-input" id="ne-hypothesis" placeholder="e.g. A green CTA lifts quote→order conversion">
      <div class="field-label" style="margin-top:10px">Variants (comma-separated)</div>
      <input type="text" class="field-input" id="ne-variants" placeholder="control, treatment">
      <div class="field-label" style="margin-top:10px">Primary metric</div>
      <input type="text" class="field-input" id="ne-metric" placeholder="e.g. converted_to_order">
      <div style="display:flex;gap:10px">
        <div style="flex:1"><div class="field-label" style="margin-top:10px">Start date</div>
          <input type="date" class="field-input" id="ne-start"></div>
        <div style="flex:1"><div class="field-label" style="margin-top:10px">End date</div>
          <input type="date" class="field-input" id="ne-end"></div>
      </div>
      <div id="ne-error" style="color:#ef4444;font-size:11px;margin-top:10px;display:none"></div>
    </div>
    <div class="modal-btns">
      <button class="btn-cancel" onclick="closeNewExperiment()">Cancel</button>
      <button class="btn-run-mod" id="ne-create-btn" onclick="submitNewExperiment()"><i class="fa-solid fa-plus" style="margin-right:6px"></i>Create experiment</button>
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

<!-- Module result dialog (#6) — the run's text output, shown in the dialog box
     itself when a module is run from its card, so the user reads the result
     without hunting for the console. -->
<div class="modal-overlay" id="result-modal">
  <div class="modal-box" style="max-width:680px">
    <div class="modal-title" id="result-title">Module result</div>
    <div class="modal-desc" id="result-status" style="display:flex;align-items:center;gap:8px"></div>
    <pre id="result-output" style="font-family:'JetBrains Mono',monospace;font-size:11.5px;line-height:1.55;white-space:pre-wrap;word-break:break-word;background:#0B1220;color:#CBD5E1;border:1px solid #1E293B;border-radius:8px;padding:13px 15px;max-height:48vh;overflow:auto;margin:6px 0 0"></pre>
    <div id="result-files" style="margin-top:10px;display:flex;gap:8px;flex-wrap:wrap"></div>
    <div class="modal-btns">
      <button class="btn-cancel" onclick="closeResultModal()">Close</button>
    </div>
  </div>
</div>

<!-- Run status toasts (#1) — a module's one-line result / failure surfaces here,
     outside the Console tab, so the user sees the outcome without opening it. -->
<div id="toast-wrap"></div>


<script>
// ════════════════════════════════════════════════════════════════════════
// MODULE CATALOG — static metadata (icon/name/description) layered onto
// the live registry returned by GET /api/modules. Field schemas are
// always fetched live from GET /api/module-config/<key> — never hardcoded.
// ════════════════════════════════════════════════════════════════════════
const ROLES = {
  analyst:            { icon:'fa-chart-line',      name:'Analyst',             nav:['discovery','planning','monitoring','analysis','deploy','intelligence','data','copilot','history'] },
  data_scientist:     { icon:'fa-flask',           name:'Data Scientist',      nav:['discovery','planning','monitoring','analysis','deploy','intelligence','data','copilot','history'] },
  product_manager:    { icon:'fa-table-list',      name:'Product Manager',     nav:['planning','monitoring','analysis','intelligence','data','copilot','history'] },
  functional_manager: { icon:'fa-users',           name:'Functional Manager',  nav:['copilot','analysis','data','history'] },
  feature_owner:      { icon:'fa-rocket',          name:'Feature Owner',       nav:['planning','monitoring','analysis','deploy','intelligence','data','copilot','history'] },
  engineering_manager:{ icon:'fa-gears',           name:'Eng Manager',         nav:['discovery','monitoring','intelligence','data','copilot','history'] },
  executive:          { icon:'fa-briefcase',       name:'Executive',           nav:['copilot'] },
  reviewer:           { icon:'fa-magnifying-glass',name:'Reviewer',            nav:['analysis','monitoring','data','copilot','history'] },
  administrator:      { icon:'fa-shield-halved',   name:'Administrator',       nav:['discovery','planning','monitoring','analysis','deploy','intelligence','data','copilot','history'] },
};

const NAV_DEFS = {
  discovery:    { label:'Foundation & discovery', icon:'fa-magnifying-glass-chart', phase:'phase_0' },
  planning:     { label:'Planning',                icon:'fa-clipboard-list',         phase:'phase_1' },
  monitoring:   { label:'Live monitoring',         icon:'fa-satellite-dish',         phase:'phase_2' },
  analysis:     { label:'Analysis & causal',        icon:'fa-flask-vial',             phase:'phase_3' },
  deploy:       { label:'Deploy & targeting',       icon:'fa-rocket',                 phase:'phase_4' },
  intelligence: { label:'Intelligence & tools',     icon:'fa-brain',                  phase:null },
  data:         { label:'Data',                     icon:'fa-table-cells-large',      phase:null },
  copilot:      { label:'AI Copilot',               icon:'fa-wand-magic-sparkles',    phase:null },
  output:       { label:'Output',                   icon:'fa-folder-open',            phase:null },
  history:      { label:'Run history',              icon:'fa-clock-rotate-left',      phase:null },
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
  cross_experiment_learning:             { icon:'fa-diagram-project',         group:'intelligence' },
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
// Per-run output capture (#6) — buffer the streamed lines + generated files so the
// result can be shown as text in a dialog when a module is run from its card.
let runOutputLines = [];
let runOutputFiles = [];
let runShowDialog = false;      // true when the run was launched from a module card

// ════════════════════════════════════════════════════════════════════════
// API CLIENT — thin wrappers, one per real backend route
// ════════════════════════════════════════════════════════════════════════
const Api = {
  async modules() { const r = await fetch('/api/modules'); return r.json(); },
  async moduleConfig(key) { const r = await fetch('/api/module-config/' + encodeURIComponent(key)); return r.json(); },
  async experiments(dataset) {
    const qs = dataset ? ('?dataset=' + encodeURIComponent(dataset)) : '';
    const r = await fetch('/api/experiments' + qs); return r.json();
  },
  async selectExperiment(name) {
    const r = await fetch('/api/experiments/select', { method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({name}) });
    return r.json();
  },
  async createExperiment(rec) {
    const r = await fetch('/api/experiments/create', { method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify(rec) });
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
    // A8 — abort the request if the backend takes too long, so the chat shows a
    // friendly timeout message instead of spinning on "Thinking…" forever.
    const ctrl = new AbortController();
    const timer = setTimeout(() => ctrl.abort(), 60000);
    try {
      const r = await fetch('/api/copilot/ask', { method:'POST', headers:{'Content-Type':'application/json'},
        body: JSON.stringify(body), signal: ctrl.signal });
      return await r.json();
    } finally { clearTimeout(timer); }
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

  // Every role that has a run history can also review module Output (B4).
  if (sections.indexOf('output') === -1) {
    const hi = sections.indexOf('history');
    if (hi !== -1) sections = sections.slice(0, hi).concat(['output'], sections.slice(hi));
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
    liveModules = await Api.modules();
    // Single source of truth for module names — see continum/ExpSuite/registry.py.
    liveModules.forEach(m => { if (m.display_name) LABEL_OVERRIDES[m.name] = m.display_name; });
    renderAllGrids();
  } catch(e) { console.warn('modules fetch failed', e); }

  // Datasets first (sets activeDataset), then experiments filtered by it.
  try { await loadDatasets(); } catch(e) { console.warn('datasets fetch failed', e); }
  try { await loadExperiments(activeDataset); } catch(e) { console.warn('experiments fetch failed', e); }
  try { renderCopilotScope(); } catch(e) {}
  try { renderAskScope(); } catch(e) {}
  try { await refreshKpis(); } catch(e) { console.warn('kpi refresh failed', e); }
  try { await refreshAskKpis(); } catch(e) { console.warn('ask kpi refresh failed', e); }
  try { await refreshInsights(); } catch(e) { console.warn('insights fetch failed', e); }
  try { await refreshNarrative(); } catch(e) { console.warn('narrative fetch failed', e); }
}

// Populate the top-bar (global) + Data-view + Copilot dataset selectors and show
// the active one. Switching is app-wide via switchDataset(). (#1)
// activeDataset is '' when no dataset/company is selected yet (gates the chat).
let activeDataset = '';
let DATASETS = [];
async function loadDatasets() {
  let ds;
  try { ds = await (await fetch('/api/copilot/datasets')).json(); }
  catch(e) { return; }
  activeDataset = ds.active || '';
  DATASETS = ds.datasets || [];
  const blank = '<option value="">— Select dataset —</option>';
  const opts = blank + DATASETS.map(function(d){
    const label = d.display_name || d.name;
    return '<option value="'+escapeAttr(d.name)+'"'+(d.name===activeDataset?' selected':'')+'>'+escapeHtml(label)+'</option>';
  }).join('');
  ['ds-select-top','ds-select','cp-ds-select'].forEach(function(id){
    const sel = document.getElementById(id); if(sel) sel.innerHTML = opts;
  });
}

// Fetch experiments (optionally scoped to a dataset) and paint every experiment
// selector. If the current activeExperiment is no longer in the list, clear it.
async function loadExperiments(dataset) {
  let exps = [];
  try { exps = await Api.experiments(dataset || ''); } catch(e) { console.warn('experiments fetch failed', e); }
  exps = Array.isArray(exps) ? exps : [];
  const names = exps.map(function(e){ return e.experiment_name; });
  if (activeExperiment && names.indexOf(activeExperiment) === -1) {
    activeExperiment = '';
    const sb = document.getElementById('sb-exp'); if(sb) sb.textContent = '—';
  }
  const blank = '<option value="">— ' + (dataset ? 'Select experiment' : 'All experiments') + ' —</option>';
  const opts = blank + exps.map(function(e){
    const meta = (e.n_rows||0) + ' rows, ' + (e.n_variants||'?') + ' variants';
    return '<option value="'+escapeAttr(e.experiment_name)+'"'+(e.experiment_name===activeExperiment?' selected':'')+'>'
      + escapeHtml(e.experiment_name + ' (' + meta + ')') + '</option>';
  }).join('');
  ['exp-select','cp-exp-select'].forEach(function(id){
    const sel = document.getElementById(id); if(sel) sel.innerHTML = opts;
  });
}

async function refreshKpis() {
  // Use ask/chain with a neutral query to pull live db_facts-derived numbers.
  // The deterministic fallback in ask_chain always returns a line shaped like
  // "Current state: IOR=17.830%  AOV=$0  n=24,000" regardless of LLM availability,
  // so KPIs are correct with or without the LLM loaded.
  try {
    const res = await Api.copilotAsk('What is the current overall IOR, AOV, and inquiry count?', 'data', {system:true});
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

// Compact money formatter for the narrow Ask-pane tiles ($1.2M / $980K / $450).
function fmtMoney(n){
  if(n==null || isNaN(n)) return '—';
  const a=Math.abs(n);
  if(a>=1e9) return '$'+(n/1e9).toFixed(1)+'B';
  if(a>=1e6) return '$'+(n/1e6).toFixed(1)+'M';
  if(a>=1e3) return '$'+(n/1e3).toFixed(1)+'K';
  return '$'+Math.round(n);
}

// Portfolio KPI cards for the Ask-AI pane — experiment count + headline metrics +
// modeled GMV/margin (#2). Backed by GET /api/copilot/portfolio (one aggregate query).
async function refreshAskKpis(){
  let d;
  try{ d = await (await fetch('/api/copilot/portfolio')).json(); }catch(e){ return; }
  if(!d || d.error || d.booting) return;
  const set=function(id,v){ const el=document.getElementById(id); if(el) el.textContent=v; };
  const fmtInt=function(n){ return n!=null ? Number(n).toLocaleString() : '—'; };
  set('ak-exp',    d.n_experiments!=null ? d.n_experiments : '—');
  set('ak-ior',    d.ior!=null ? (d.ior*100).toFixed(2)+'%' : '—');
  set('ak-orders', fmtInt(d.converted_orders));
  // Money fields are modeled when the dataset has no order value — mark with '~'.
  set('ak-aov',    (d.aov_modeled ? '~' : '') + fmtMoney(d.aov));
  set('ak-gmv',    (d.gmv_modeled ? '~' : '') + fmtMoney(d.total_gmv));
  set('ak-margin', (d.gmv_modeled ? '~' : '') + fmtMoney(d.modeled_margin));
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

// Display-label overrides — populated from the live registry's display_name
// (GET /api/modules) as soon as it loads, in bootstrapData(). This is the
// SAME name the backend uses for chat replies / guided-flow prose / MatchView
// tool confirmations, so the card grid, modal, run/result labels, and the
// AskAI chatbot can never name a module differently again.
let LABEL_OVERRIDES = {};
function humanize(key) {
  if (LABEL_OVERRIDES[key]) return LABEL_OVERRIDES[key];
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
  if (sec === 'output') loadOutputView();
  if (sec === 'copilot') { try { renderCopilotScope(); } catch(e) {} }
}

// ── OUTPUT VIEW (B4) — the outputs FOLDER: every file a module run generated,
//    downloadable. Backed by GET /api/outputs (the real folder listing). ──────
function _fmtBytes(n){ if(n==null) return ''; if(n<1024) return n+' B'; if(n<1048576) return (n/1024).toFixed(1)+' KB'; return (n/1048576).toFixed(1)+' MB'; }
async function loadOutputView(){
  const box = document.getElementById('output-list');
  if(!box) return;
  let data;
  try{ data = await (await fetch('/api/outputs')).json(); }
  catch(e){ box.innerHTML = '<div class="grid-error">Could not load the outputs folder.</div>'; return; }
  const files = (data && data.files) || [];
  const dirNote = data && data.dir ? ('<div style="font-size:10px;color:var(--muted2);margin:0 0 8px">📁 '+escapeHtml(data.dir)+'</div>') : '';
  if(!files.length){
    box.innerHTML = dirNote + '<div style="padding:18px;color:var(--muted2);font-size:11px">No output files yet. Run a module (from a card or from the Ask-AI chat) — every run saves its generated files here.</div>';
    return;
  }
  box.innerHTML = dirNote + files.map(function(f){
    const ext = (f.ext||'').toUpperCase() || 'FILE';
    return '<div class="ins-item" style="margin:9px 0;display:flex;align-items:center;gap:10px">'
      + '<span class="tier-badge t1">'+escapeHtml(ext)+'</span>'
      + '<div style="flex:1;min-width:0"><div class="ins-msg" style="font-weight:600">'+escapeHtml(f.name)+'</div>'
      + '<div class="ins-det">'+_fmtBytes(f.size)+'</div></div>'
      + '<a class="file-chip" style="color:var(--blue)" href="'+escapeAttr(f.url)+'" target="_blank"><i class="fa-solid fa-download" style="margin-right:5px"></i>Open</a>'
      + '</div>';
  }).join('');
}

// ════════════════════════════════════════════════════════════════════════
// EXPERIMENT SELECTION (real backend call)
// ════════════════════════════════════════════════════════════════════════
async function selectExperiment(name) {
  activeExperiment = name;
  document.getElementById('sb-exp').textContent = name || '—';
  ['exp-select','cp-exp-select'].forEach(function(id){
    const sel = document.getElementById(id); if (sel && sel.value !== (name||'')) sel.value = name || '';
  });
  renderAskScope();
  renderCopilotScope();
  if (name) {
    try { await Api.selectExperiment(name); } catch(e) { console.warn(e); }
  }
}

// Copilot start-window scope banner + selection prompt. Mirrors renderAskScope
// but drives the dataset+experiment gate line in the Copilot header.
function renderCopilotScope() {
  const el = document.getElementById('cp-scope'); if (!el) return;
  if (!activeDataset) {
    el.className = 'cp-scope none';
    el.innerHTML = '<i class="fa-solid fa-circle-exclamation"></i> Select a <b>dataset / company</b> to begin — then pick an experiment for experiment-level questions.';
  } else if (!activeExperiment) {
    el.className = 'cp-scope partial';
    el.innerHTML = '<i class="fa-solid fa-database"></i> Company: <b>' + escapeHtml(datasetLabel(activeDataset)) + '</b> · no experiment selected (answers span all experiments).';
  } else {
    el.className = 'cp-scope set';
    el.innerHTML = '<i class="fa-solid fa-flask"></i> <b>' + escapeHtml(datasetLabel(activeDataset)) + '</b> → <b>' + escapeHtml(activeExperiment) + '</b>';
  }
}

function datasetLabel(name) {
  const d = (DATASETS || []).find(function(x){ return x.name === name; });
  return (d && (d.display_name || d.name)) || name;
}

// Experiment names from the live selector (values are the experiment names).
function experimentNames() {
  return Array.from(document.querySelectorAll('#exp-select option'))
    .map(function(o){ return o.value; }).filter(Boolean);
}

// Ask-pane scope chip — shows the active experiment (obvious) or a warning callout
// when none is selected (#2/#4).
function renderAskScope() {
  const el = document.getElementById('ask-scope'); if (!el) return;
  if (activeExperiment) {
    el.className = 'ask-scope set';
    el.innerHTML = '<i class="fa-solid fa-flask"></i> Answering for <b>' + escapeHtml(activeExperiment) +
      '</b><span class="scope-act" onclick="focusExperimentPicker()">Change</span>';
  } else {
    el.className = 'ask-scope none';
    el.innerHTML = '<i class="fa-solid fa-circle-exclamation"></i> No experiment selected — answers span <b>all experiments</b>' +
      '<span class="scope-act" onclick="focusExperimentPicker()">Select one</span>';
  }
}

// Draw attention to the top-bar experiment dropdown and open it.
function focusExperimentPicker() {
  const sel = document.getElementById('exp-select'); if (!sel) return;
  if (document.getElementById('app').classList.contains('copilot-mode')) togglePane('rp'); // ensure top bar reachable
  sel.scrollIntoView({block:'nearest', behavior:'smooth'});
  sel.classList.add('exp-flash');
  setTimeout(function(){ sel.classList.remove('exp-flash'); }, 2100);
  try { sel.focus(); } catch(e) {}
}

// Clarifier chip handler: scope to an experiment, then re-ask the last question (#2).
async function clarifyExperiment(name, q) {
  await selectExperiment(name);
  if (q) copilotSubmit(q);
}

function runSelected() {
  if (!activeExperiment) { alert('Select an experiment from the dropdown first.'); return; }
  openModuleConfig('experiment_analysis');
}

// ════════════════════════════════════════════════════════════════════════
// MODULE CONFIG MODAL — fields are rendered from the LIVE schema returned
// by GET /api/module-config/<key>. Never hardcoded per-module.
// ════════════════════════════════════════════════════════════════════════
async function openModuleConfig(key) {
  selectedModuleKey = key;
  const cfg = await Api.moduleConfig(key);
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
  await startModuleRun(key, fields, expName || activeExperiment, {showDialog: true});
}

// Shared module runner: opens the execution console, runs the module over the
// real /api/execute + SSE machinery (so interactive input() prompts surface in
// the modal — instead of crashing with EOF — and generated files are captured).
// Used by the config modal AND by chat tool-calls (B4).
async function startModuleRun(key, fields, expName, opts) {
  opts = opts || {};
  runShowDialog = !!opts.showDialog;   // show the result dialog for card-initiated runs (#6)
  runOutputLines = [];
  runOutputFiles = [];
  openConsolePane();                   // execution console lives in the right pane now (#3)
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
    res = await Api.execute(key, fields || {}, expName || activeExperiment);
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
  // Capture for the result dialog (#6). Skip pure-noise levels.
  if (level !== 'PING') runOutputLines.push(msg);
}

// #1 — surface a module's one-line outcome (result or failure) outside the
// console. Plain text only (#2 — one-liners get no markdown). Auto-dismisses.
function showToast(msg, kind) {
  const wrap = document.getElementById('toast-wrap');
  if (!wrap) return;
  const t = document.createElement('div');
  t.className = 'toast toast-' + (kind === 'err' ? 'err' : 'ok');
  t.textContent = msg;
  wrap.appendChild(t);
  requestAnimationFrame(() => t.classList.add('show'));
  const ttl = kind === 'err' ? 9000 : 5000;
  setTimeout(() => {
    t.classList.remove('show');
    setTimeout(() => t.remove(), 220);
  }, ttl);
}

// Show the captured run output as text in a dialog (#6).
function showResultDialog(moduleKey, ok) {
  document.getElementById('result-title').textContent = humanize(moduleKey) + ' — result';
  const statusEl = document.getElementById('result-status');
  statusEl.innerHTML = ok
    ? '<span style="color:var(--green,#16a34a)"><i class="fa-solid fa-circle-check"></i> Completed</span>'
    : '<span style="color:var(--red,#dc2626)"><i class="fa-solid fa-circle-exclamation"></i> Finished with errors</span>';
  const out = runOutputLines.join('\n').trim();
  document.getElementById('result-output').textContent = out || 'The module produced no text output.';
  const filesBox = document.getElementById('result-files');
  filesBox.innerHTML = '';
  runOutputFiles.forEach(function(f) {
    const chip = document.createElement('a');
    chip.className = 'file-chip'; chip.textContent = f.name;
    chip.href = '/api/file?path=' + encodeURIComponent(f.path);
    chip.target = '_blank';
    filesBox.appendChild(chip);
  });
  document.getElementById('result-modal').classList.add('show');
}

function streamRun(runId, moduleKey) {
  if (currentEventSource) { currentEventSource.close(); }
  const es = new EventSource('/api/stream/' + runId);
  currentEventSource = es;
  const dot = document.getElementById('console-dot');
  const label = document.getElementById('console-label');
  const status = document.getElementById('console-status');
  // #1 — track outcome so we can surface a clear one-liner outside the console.
  let sawError = false, runSummary = '', firstErr = '';

  es.onmessage = async (ev) => {
    let data;
    try { data = JSON.parse(ev.data); } catch(e) { return; }
    const level = data.level, msg = data.msg;

    if (level === 'PING') return;

    if (level === 'ERR') {
      sawError = true;
      // Keep the first real error line (the "❌ Type: message" headline).
      if (!firstErr && /\S/.test(msg)) firstErr = String(msg).replace(/^❌\s*/, '').trim();
    } else if (level === 'SUMMARY') {
      runSummary = String(msg).trim();
    }

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
      const filesBox = document.getElementById('console-files');
      filesBox.style.display = 'block';
      const chip = document.createElement('a');
      chip.className = 'file-chip'; chip.textContent = fname.trim();
      chip.href = '/api/file?path=' + encodeURIComponent(fpath);
      chip.target = '_blank';
      filesBox.appendChild(chip);
      runOutputFiles.push({name: fname.trim(), path: fpath});  // capture for the result dialog (#6)
      return;
    }

    if (level === 'DONE') {
      const ok = !sawError;
      dot.classList.remove('run');
      label.textContent = 'Idle';
      status.textContent = ok ? 'Completed' : 'Failed';
      es.close();
      currentEventSource = null;
      const card = document.getElementById('mod-' + moduleKey);
      if (card) card.classList.add(ok ? 'done' : 'failed');
      // #1 — always surface the outcome outside the console: a clear one-line
      // failure, or the module's one-line summary on success.
      const name = humanize(moduleKey);
      if (!ok) {
        showToast('❌ ' + name + ' failed' + (firstErr ? ': ' + firstErr : '. See the Console for details.'), 'err');
      } else {
        showToast('✅ ' + name + (runSummary ? ': ' + runSummary : ' completed'), 'ok');
      }
      // Show the full-text dialog for card runs, and always on failure so the
      // error is never buried in the console.
      if (runShowDialog || !ok) showResultDialog(moduleKey, ok);
      await bootstrapData(); // refresh history + KPIs from real backend
      try { loadOutputView(); } catch(e) {}  // B4 — surface freshly generated output
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
  // A2 — refresh the panel's data the moment it's opened, instead of waiting for
  // the 20s poll / a fresh bootstrap (the old behaviour felt "very slow").
  if (tab === 'insights')      refreshInsights();
  else if (tab === 'narrative') refreshNarrative();
  else if (tab === 'evidence')  renderEvidence();
  else if (tab === 'ask')       { renderChat(); refreshAskKpis(); renderAskScope(); }
}

// Reveal the right-pane Console tab (the execution console now lives there, #3).
function openConsolePane() {
  const app = document.getElementById('app');
  if (app) app.classList.remove('rp-collapsed');
  document.querySelectorAll('.rp-tab').forEach(t => t.classList.remove('active'));
  document.querySelectorAll('.rp-panel').forEach(p => p.classList.remove('show'));
  const panel = document.getElementById('tab-console');
  if (panel) panel.classList.add('show');
  document.querySelectorAll('.rp-tab').forEach(t => {
    if (/switchTab\('console'/.test(t.getAttribute('onclick') || '')) t.classList.add('active');
  });
}

function closeResultModal() {
  document.getElementById('result-modal').classList.remove('show');
}

async function refreshInsights() {
  const list = document.getElementById('insights-list');
  // Show a loading state only on the first load (avoid flicker on the 20s poll).
  if (list && !list.querySelector('.ins-item')) list.innerHTML = '<div class="rp-loading"><i class="fa-solid fa-spinner fa-spin"></i> Loading insights…</div>';
  try {
    const data = await Api.intelligence();
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
  const list = document.getElementById('narrative-list');
  if (list && !list.querySelector('.narr-item')) list.innerHTML = '<div class="rp-loading"><i class="fa-solid fa-spinner fa-spin"></i> Loading narrative…</div>';
  try {
    const stream = await Api.narrative();
    if (!stream || !stream.length) {
      list.innerHTML = '<div style="padding:18px;color:var(--muted2);font-size:11px;text-align:center">No narrative yet</div>';
      return;
    }
    list.innerHTML = stream.map(n => `
      <div class="narr-item">
        <div class="narr-src">${n.source||'observation'}</div>
        <div class="narr-txt">${n.text||''}</div>
        <div class="narr-ts">${(n.created_at||'').slice(0,16)}</div>
      </div>`).join('');
  } catch(e) { console.warn('narrative failed', e); }
}

// ════════════════════════════════════════════════════════════════════════
// COPILOT CHAT — ONE conversation, kept in full sync between the right-panel
// "Ask AI" tab (#ask-history) and the full-screen "AI Copilot" (#copilot-chat).
// Backed by main's tool-calling endpoint /api/copilot/ask (detect→confirm→execute).
// ════════════════════════════════════════════════════════════════════════
let CHAT = { history: [], pending: null, busy: false, lastQ: '' };

function fmtMd(s){ return escapeHtml(String(s==null?'':s)).replace(/\*\*([^*]+)\*\*/g,'<strong>$1</strong>').replace(/\n/g,'<br>'); }
// #2 — a single-line answer needs no markdown; render it plain so short outputs
// aren't dressed up with bold/formatting.
function fmtBody(s){ const t=String(s==null?'':s); return /\n/.test(t.trim()) ? fmtMd(t) : escapeHtml(t); }

function _cpTable(rows, cols){
  if(!rows || !rows.length) return '';
  cols = (cols && cols.length) ? cols : Object.keys(rows[0]);
  const head = cols.map(c=>'<th>'+escapeHtml(c)+'</th>').join('');
  const body = rows.slice(0,12).map(r=>'<tr>'+cols.map(c=>'<td>'+escapeHtml(r[c])+'</td>').join('')+'</tr>').join('');
  return '<div class="tbl-wrap" style="margin-top:9px;max-height:240px;overflow:auto"><table class="dt"><thead><tr>'+head+'</tr></thead><tbody>'+body+'</tbody></table></div>';
}

// A collapsible <details> block (Snowflake-style) — used for SQL, table, charts.
function _cpDetails(label, icon, bodyHtml, open){
  if(!bodyHtml) return '';
  return '<details class="cp-acc"'+(open?' open':'')+'>'
    + '<summary><i class="fa-solid '+icon+'"></i> '+escapeHtml(label)+'</summary>'
    + '<div class="cp-acc-body">'+bodyHtml+'</div></details>';
}

function _cpMsgHtml(m){
  if(m.role === 'user')
    return '<div class="chat-msg user"><div class="chat-bubble">'+escapeHtml(m.text)+'</div></div>';

  // Experiment-not-selected callout (A7): a confirmed analysis/deploy module
  // ran without an active experiment.
  if(m.needs_experiment){
    let warn = '<div class="chat-ai-label"><i class="fa-solid fa-wand-magic-sparkles"></i> CONTINUM Copilot</div>'
      + '<div class="cp-callout cp-callout-warn"><i class="fa-solid fa-circle-exclamation"></i> '
      + fmtMd(m.text || 'Select an experiment first.')
      + '<div style="margin-top:8px;font-size:10.5px;opacity:.9">Pick one from the <b>experiment dropdown</b> in the top bar, then ask again.</div></div>';
    return '<div class="chat-msg ai">'+warn+'</div>';
  }

  // Dataset-not-selected callout: a data question was asked before a company /
  // dataset was picked. Meta/help questions are never gated.
  if(m.needs_dataset){
    let warn = '<div class="chat-ai-label"><i class="fa-solid fa-wand-magic-sparkles"></i> CONTINUM Copilot</div>'
      + '<div class="cp-callout cp-callout-warn"><i class="fa-solid fa-circle-exclamation"></i> '
      + fmtMd(m.text || 'Select a dataset / company first.')
      + '<div style="margin-top:8px;font-size:10.5px;opacity:.9">Pick a <b>dataset / company</b> from the dropdown above, then ask again.</div></div>';
    return '<div class="chat-msg ai">'+warn+'</div>';
  }

  // #5 — error messages get a distinct warning callout.
  if(m.error){
    return '<div class="chat-msg ai"><div class="chat-ai-label"><i class="fa-solid fa-wand-magic-sparkles"></i> CONTINUM Copilot</div>'
      + '<div class="cp-callout cp-callout-warn">'+fmtMd(m.text)+'</div></div>';
  }

  // #5 — rotating loading message with a spinner while the model works.
  const bubble = m.thinking
    ? '<span class="cp-thinking"><i class="fa-solid fa-spinner fa-spin" style="opacity:.7;margin-right:7px"></i><span class="cp-think-txt">'+escapeHtml(m.thinkMsg||'Thinking…')+'</span></span>'
    : fmtBody(m.text);
  let inner = '<div class="chat-ai-label"><i class="fa-solid fa-wand-magic-sparkles"></i> CONTINUM Copilot'
    + (m.meta && m.meta.mode ? ' <span class="conf-badge">'+escapeHtml(m.meta.mode)+'</span>' : '')
    + '</div><div class="chat-bubble">'+bubble+'</div>';
  if(m.confirm){
    // A9 — describe what the tool will do before the user commits.
    if(m.confirm.description)
      inner += '<div class="cp-tool-desc"><i class="fa-solid fa-circle-info"></i> '+fmtMd(m.confirm.description)+'</div>';
    if(m.confirm.deploy_warning)
      inner += '<div style="margin-top:8px;padding:9px 11px;border-radius:8px;background:var(--amber-lt);border:1px solid var(--amber);color:var(--amber);font-size:11px;line-height:1.5">'+fmtMd(m.confirm.deploy_warning)+'</div>';
    inner += '<div style="margin-top:9px;display:flex;gap:8px;flex-wrap:wrap">'
      + '<button onclick="copilotConfirm()" style="background:var(--blue);color:#fff;border:none;border-radius:8px;padding:7px 14px;font-size:11.5px;font-weight:700;cursor:pointer">Yes, use '+escapeHtml(m.confirm.module_name)+'</button>'
      + '<button onclick="copilotDecline()" style="background:var(--surf2);color:var(--muted);border:1px solid var(--bdr);border-radius:8px;padding:7px 14px;font-size:11.5px;cursor:pointer">No, just answer</button></div>';
  }
  // A6 — table, SQL and visualizations, each in a collapsible.
  if(m.meta && m.meta.table && m.meta.table.length)
    inner += _cpDetails('Result table ('+m.meta.table.length+' rows)', 'fa-table', _cpTable(m.meta.table, m.meta.columns), true);
  if(m.meta && m.meta.viz && m.meta.viz.length){
    const cid = (m._cid || (m._cid = 'c'+Math.random().toString(36).slice(2)));
    inner += _cpDetails('Visualization', 'fa-chart-column',
      '<div class="cp-chart" data-cid="'+cid+'" style="min-height:260px"></div>', true);
  }
  if(m.meta && m.meta.sql)
    inner += _cpDetails('SQL', 'fa-code', '<pre class="cp-sql">'+escapeHtml(m.meta.sql)+'</pre>', false);
  if(m.meta && m.meta.next_steps && m.meta.next_steps.length)
    inner += '<div style="margin-top:9px;display:flex;gap:6px;flex-wrap:wrap">'
      + m.meta.next_steps.map(s=>'<button class="quick-btn" data-q="'+escapeAttr(escapeHtml(s))+'" onclick="sendQuick(this.dataset.q)">'+escapeHtml(s)+'</button>').join('') + '</div>';
  // Clarifier chips (#2): answered across all data — offer to re-scope to one experiment.
  if(m.clarify && m.clarify.length)
    inner += '<div class="cp-clarify"><i class="fa-solid fa-flask"></i> Answered across all experiments — focus on one?'
      + m.clarify.map(function(e){ return ' <button class="quick-btn" data-exp="'+escapeAttr(e)+'" data-q="'+escapeAttr(m.clarifyQ||'')+'" onclick="clarifyExperiment(this.dataset.exp,this.dataset.q)">'+escapeHtml(e)+'</button>'; }).join('') + '</div>';
  return '<div class="chat-msg ai">'+inner+'</div>';
}

// ── Lazy Plotly loader + chart renderer (charts render after renderChat). ──
let _plotlyPromise = null;
function ensurePlotly(){
  if(window.Plotly) return Promise.resolve(window.Plotly);
  if(_plotlyPromise) return _plotlyPromise;
  _plotlyPromise = new Promise(function(resolve,reject){
    const s = document.createElement('script');
    s.src = 'https://cdn.plot.ly/plotly-2.27.0.min.js';
    s.onload = function(){ resolve(window.Plotly); };
    s.onerror = function(){ reject(new Error('plotly load failed')); };
    document.head.appendChild(s);
  });
  return _plotlyPromise;
}
function _renderOneChart(el, cfg, rows){
  if(!el || !cfg || !rows || !rows.length) return;
  const type=(cfg.type||'bar').toLowerCase();
  const col=function(name){ return rows.map(function(r){ return r[name]; }); };
  let data=[];
  try{
    if(type==='pie'){
      data=[{type:'pie', labels:col(cfg.names||cfg.x), values:col(cfg.values||cfg.y)}];
    } else if(cfg.color && rows.some(function(r){return r[cfg.color]!=null;})){
      const groups={};
      rows.forEach(function(r){ (groups[r[cfg.color]] = groups[r[cfg.color]]||[]).push(r); });
      data=Object.keys(groups).map(function(g){
        return {type:(type==='line'?'scatter':'bar'), mode:type==='line'?'lines+markers':undefined,
          name:String(g), x:groups[g].map(function(r){return r[cfg.x];}), y:groups[g].map(function(r){return r[cfg.y];})};
      });
    } else {
      data=[{type:(type==='line'?'scatter':'bar'), mode:type==='line'?'lines+markers':undefined, x:col(cfg.x), y:col(cfg.y)}];
    }
    Plotly.newPlot(el, data,
      {title:cfg.title||'', margin:{t:34,r:12,b:40,l:46}, height:270, font:{size:11},
       paper_bgcolor:'rgba(0,0,0,0)', plot_bgcolor:'rgba(0,0,0,0)'},
      {displayModeBar:false, responsive:true});
  }catch(e){ el.innerHTML = '<div style="padding:10px;color:var(--muted);font-size:11px">Chart could not be rendered.</div>'; }
}
function renderPendingCharts(){
  const pending = CHAT.history.filter(function(m){ return m._cid && m.meta && m.meta.viz && m.meta.viz.length; });
  if(!pending.length) return;
  ensurePlotly().then(function(){
    pending.forEach(function(m){
      ['copilot-chat','ask-history'].forEach(function(boxId){
        const box=document.getElementById(boxId); if(!box) return;
        const el=box.querySelector('.cp-chart[data-cid="'+m._cid+'"]');
        if(el && !el.dataset.rendered){ el.dataset.rendered='1'; _renderOneChart(el, m.meta.viz[0], m.meta.table||[]); }
      });
    });
  }).catch(function(){
    // Plotly failed to load (offline / CDN blocked). Don't fail silently — say so
    // in the chart box so a missing chart is diagnosable, not invisible.
    pending.forEach(function(m){
      ['copilot-chat','ask-history'].forEach(function(boxId){
        const box=document.getElementById(boxId); if(!box) return;
        const el=box.querySelector('.cp-chart[data-cid="'+m._cid+'"]');
        if(el && !el.dataset.rendered){ el.dataset.rendered='1';
          el.innerHTML='<div style="padding:10px;color:var(--muted);font-size:11px">Chart library couldn\'t load (offline or the CDN is blocked). The underlying data is in the table above.</div>'; }
      });
    });
  });
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
    box.innerHTML = CHAT.history.map(_cpMsgHtml).join('');
    box.scrollTop = box.scrollHeight;
  });
  const resp = document.getElementById('ask-response'); if(resp){ resp.classList.remove('show'); resp.innerHTML = ''; }
  renderPendingCharts();
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
  const ph = {role:'ai', thinking:true, thinkMsg:_THINK_MSGS[0]}; CHAT.history.push(ph);
  CHAT.busy = true; renderChat();
  startThinking(ph);
  try{
    const extra = {};
    if(opts.confirm_tool) extra.confirm_tool = opts.confirm_tool;
    if(opts.decline)      extra.decline = true;
    const d = await Api.copilotAsk(CHAT.lastQ, 'auto', extra);
    stopThinking();
    CHAT.history = CHAT.history.filter(function(m){ return m !== ph; });
    if(d.mode === 'confirm' && d.pending_tool){
      CHAT.pending = { key:d.pending_tool.key, module_name:d.pending_tool.module_name,
        kind:d.pending_tool.kind, target:d.pending_tool.target || '',
        description:d.pending_tool.description || '', deploy_warning:d.deploy_warning };
      CHAT.history.push({role:'ai', text:d.response, confirm:CHAT.pending});
    } else if(d.mode === 'needs_experiment'){
      CHAT.pending = null;
      CHAT.history.push({role:'ai', needs_experiment:true, text:(d.response || 'Select an experiment first.')});
    } else if(d.mode === 'needs_dataset'){
      CHAT.pending = null;
      CHAT.history.push({role:'ai', needs_dataset:true, text:(d.response || 'Select a dataset / company first.')});
    } else {
      CHAT.pending = null;
      const meta = { table:d.table||[], columns:d.columns||[], sql:d.sql||'', viz:d.visualizations||[],
        next_steps:((d.suggestions && d.suggestions.length) ? d.suggestions : (d.next_steps||[])), mode:d.mode };
      const msg = {role:'ai', text:(d.response || d.error || '(no response)'), meta:meta};
      // #2 — a data answer with no experiment selected: offer clarifier chips to re-scope.
      if(!activeExperiment && !opts.confirm_tool && (d.mode === 'askdata' || d.mode === 'data')){
        const exps = experimentNames();
        if(exps.length){ msg.clarify = exps.slice(0,4); msg.clarifyQ = CHAT.lastQ; }
      }
      CHAT.history.push(msg);
      captureEvidence(CHAT.lastQ, d, meta);
    }
  }catch(e){
    stopThinking();
    CHAT.history = CHAT.history.filter(function(m){ return m !== ph; });
    CHAT.history.push({role:'ai', error:true, text: friendlyError(e)});
  }
  CHAT.busy = false; renderChat();
}

// #5 — rotating "thinking" messages so a slow LLM call feels responsive.
const _THINK_MSGS = ['Understanding your question…','Retrieving the data…',
  'Analysing the results…','Composing the answer…','Almost there…'];
let _thinkTimer = null;
function startThinking(ph){
  let i = 0;
  stopThinking();
  _thinkTimer = setInterval(function(){
    i = (i + 1) % _THINK_MSGS.length;
    ph.thinkMsg = _THINK_MSGS[i];
    // Update the live thinking bubble in place (no full re-render → keeps scroll).
    document.querySelectorAll('.cp-think-txt').forEach(function(el){ el.textContent = _THINK_MSGS[i]; });
  }, 2200);
}
function stopThinking(){ if(_thinkTimer){ clearInterval(_thinkTimer); _thinkTimer = null; } }

// #5 — friendly, actionable error text instead of a raw exception string.
function friendlyError(e){
  const msg = (e && (e.message || e.name)) ? String(e.message || e.name) : String(e || '');
  if(/AbortError|tim[eo]*out|aborted/i.test(msg))
    return '⏱️ That took too long and was cancelled. Try a narrower question, pick an experiment, or ask again — the model may have been busy.';
  if(/Failed to fetch|NetworkError|load failed/i.test(msg))
    return '🔌 I couldn’t reach the server. Check that the app is still running, then try again.';
  return '⚠️ Something went wrong answering that. Please try again — if it keeps happening, rephrase the question or check the server logs.';
}

function copilotConfirm(){
  const p = CHAT.pending;
  if(!p) return;
  // Data look-ups answer inline in chat (table + chart + SQL). Analysis / deploy
  // modules run in the live console (B4): it streams logs, handles interactive
  // input() via the modal, and captures outputs into the Output tab — instead of
  // executing silently in the request (which broke on modules that call input()).
  const runnable = p.target && p.target !== 'askdata' && (p.kind === 'analysis' || p.kind === 'deploy');
  if(!runnable){ copilotSubmit('', {confirm_tool: p.key}); return; }
  if(EXP_MODULES.has(p.target) && !activeExperiment){
    CHAT.history.push({role:'user', text:'Yes — run ' + p.module_name});
    CHAT.history.push({role:'ai', needs_experiment:true,
      text:'**'+p.module_name+'** runs against a single experiment, but none is selected yet.'});
    CHAT.pending = null; renderChat(); return;
  }
  CHAT.history.push({role:'user', text:'Yes — run ' + p.module_name});
  CHAT.history.push({role:'ai',
    text:'▶️ Running **'+p.module_name+'**. Watch the **Console** tab (right panel) for live progress; generated files land in the **Output** view.'});
  const target = p.target; CHAT.pending = null; renderChat();
  startModuleRun(target, {}, activeExperiment);
}
function copilotDecline(){ copilotSubmit('', {decline:true}); }

// Both surfaces + quick chips funnel into the one shared conversation.
function sendAsk(){ const i=document.getElementById('ask-input'); const q=(i.value||'').trim(); if(!q) return; i.value=''; copilotSubmit(q); }
function sendCopilot(){ const i=document.getElementById('copilot-input'); const q=(i.value||'').trim(); if(!q) return; i.value=''; copilotSubmit(q); }
function sendQuick(q){ copilotSubmit(q); }

// ── EVIDENCE (A3) — grounding chain for the most recent Copilot answer ─────────
// /api/copilot/ask returns the mode it resolved to, the SQL it ran, the rows it
// grounded on and the live LLM flag. We snapshot that on every answer and render
// it as the auditable "why did it say that" trail the Evidence tab used to show.
let LAST_EVIDENCE = null;
function captureEvidence(question, d, meta){
  LAST_EVIDENCE = {
    question: question,
    mode: (d && d.mode) || meta.mode || '',
    llm_loaded: !!(d && d.llm_loaded),
    sql: meta.sql || '',
    columns: meta.columns || [],
    rows: meta.table || [],
    answer: (d && d.response) || '',
    error: (d && d.error) || '',
    at: new Date().toLocaleTimeString(),
  };
  renderEvidence();
}
function renderEvidence(){
  const box = document.getElementById('evidence-chain');
  if(!box) return;
  const e = LAST_EVIDENCE;
  if(!e){
    box.innerHTML = '<div style="padding:18px;color:var(--muted2);font-size:11px;text-align:center">Ask a question to see grounded evidence</div>';
    return;
  }
  const step = function(src, html){
    return '<div class="ev-item"><div class="ev-src">'+escapeHtml(src)+'</div><div class="ev-claim">'+html+'</div></div>'; };
  let h = '';
  h += step('Question', escapeHtml(e.question) + ' <span style="color:var(--muted2)">· '+escapeHtml(e.at)+'</span>');
  h += step('Resolution path', '<span class="conf-badge" style="margin:0">'+escapeHtml(e.mode||'—')+'</span> '
        + (e.llm_loaded ? 'grounded + LLM' : 'grounded · deterministic'));
  if(e.sql)
    h += step('SQL executed', '<pre class="cp-sql" style="margin-top:4px">'+escapeHtml(e.sql)+'</pre>');
  if(e.rows && e.rows.length)
    h += step('Data grounded on', e.rows.length + ' row(s)' + (e.columns.length ? ' · ' + escapeHtml(e.columns.join(', ')) : '')
        + _cpTable(e.rows, e.columns));
  if(e.error)
    h += step('Error', '<span style="color:var(--red)">'+escapeHtml(e.error)+'</span>');
  h += step('Answer', fmtMd((e.answer||'').slice(0,600)));
  box.innerHTML = h;
}

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
    box.innerHTML = tables.length ? tables.map(function(t,i){
      const cols = t.columns || (t.rows&&t.rows[0] ? Object.keys(t.rows[0]) : []);
      const head = cols.map(function(c){ return '<th>'+escapeHtml(c)+'</th>'; }).join('');
      const body = (t.rows||[]).slice(0,5).map(function(r){
        return '<tr>'+cols.map(function(c){ return '<td>'+escapeHtml(r[c]==null?'':r[c])+'</td>'; }).join('')+'</tr>'; }).join('');
      const title = (t.name?escapeHtml(t.name):('Table '+(i+1))) + ' · ' + (t.n_rows!=null?t.n_rows:(t.rows||[]).length) + ' rows';
      return '<div class="sec-title" style="margin-top:16px">'+title+'</div>'
        + '<div class="tbl-wrap" style="overflow:auto"><table class="dt"><thead><tr>'+head+'</tr></thead><tbody>'+body+'</tbody></table></div>';
    }).join('') : '<div style="padding:18px;color:var(--muted2);font-size:11px">No tables in this dataset.</div>';
  }catch(e){ box.innerHTML = '<div class="grid-error">Could not load the data preview.</div>'; }
}
async function switchDataset(name){
  if(!name || name === activeDataset) return;   // blank re-select is a no-op (no clear route)
  // Keep every dataset selector in sync immediately (top bar / Data view / Copilot).
  ['ds-select-top','ds-select','cp-ds-select'].forEach(function(id){
    const sel = document.getElementById(id); if(sel) sel.value = name;
  });
  const dv = document.getElementById('data-preview');
  if(dv) dv.innerHTML = '<div style="padding:18px;color:var(--muted2);font-size:11px">Switching dataset…</div>';
  try{
    const r = await fetch('/api/copilot/dataset', {method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({dataset:name})});
    const d = await r.json();
    if(d && d.error){ if(dv) dv.innerHTML = '<div class="grid-error">'+escapeHtml(d.error)+'</div>'; await loadDatasets(); return; }
  }catch(e){}
  activeDataset = name;
  // Experiments are scoped to the dataset — refresh the dropdowns (this also
  // clears activeExperiment if it doesn't belong to the new dataset).
  try { await loadExperiments(activeDataset); } catch(e){}
  renderCopilotScope();
  renderAskScope();
  // Refresh everything that reflects the active dataset.
  try { await refreshKpis(); } catch(e){}
  try { await refreshAskKpis(); } catch(e){}
  if(document.getElementById('section-data').classList.contains('show')) loadDataView();
}

// ════════════════════════════════════════════════════════════════════════
// NEW EXPERIMENT MODAL — create a metadata record under a dataset (persisted).
// ════════════════════════════════════════════════════════════════════════
function openNewExperiment(){
  const sel = document.getElementById('ne-dataset');
  if(sel){
    sel.innerHTML = (DATASETS||[]).map(function(d){
      return '<option value="'+escapeAttr(d.name)+'"'+(d.name===activeDataset?' selected':'')+'>'+escapeHtml(d.display_name||d.name)+'</option>';
    }).join('');
  }
  ['ne-name','ne-hypothesis','ne-variants','ne-metric','ne-start','ne-end'].forEach(function(id){
    const el=document.getElementById(id); if(el) el.value='';
  });
  const err=document.getElementById('ne-error'); if(err){ err.style.display='none'; err.textContent=''; }
  document.getElementById('newexp-modal').classList.add('show');
}
function closeNewExperiment(){ document.getElementById('newexp-modal').classList.remove('show'); }
async function submitNewExperiment(){
  const err = document.getElementById('ne-error');
  const show = function(m){ if(err){ err.textContent=m; err.style.display='block'; } };
  const rec = {
    dataset: (document.getElementById('ne-dataset')||{}).value || '',
    experiment_name: ((document.getElementById('ne-name')||{}).value||'').trim(),
    hypothesis: ((document.getElementById('ne-hypothesis')||{}).value||'').trim(),
    variants: ((document.getElementById('ne-variants')||{}).value||'').trim(),
    primary_metric: ((document.getElementById('ne-metric')||{}).value||'').trim(),
    start_date: (document.getElementById('ne-start')||{}).value||'',
    end_date: (document.getElementById('ne-end')||{}).value||''
  };
  if(!rec.experiment_name){ show('Experiment name is required.'); return; }
  if(!rec.dataset){ show('Pick a dataset.'); return; }
  const btn=document.getElementById('ne-create-btn'); if(btn) btn.disabled=true;
  try{
    const d = await Api.createExperiment(rec);
    if(d && d.error){ show(d.error); if(btn) btn.disabled=false; return; }
    closeNewExperiment();
    // Switch to the experiment's dataset if needed, then select the new experiment.
    if(rec.dataset !== activeDataset){ await switchDataset(rec.dataset); }
    else { await loadExperiments(activeDataset); }
    await selectExperiment(rec.experiment_name);
  }catch(e){ show('Could not create the experiment — try again.'); }
  finally { if(btn) btn.disabled=false; }
}

// ════════════════════════════════════════════════════════════════════════
// READOUT UPLOAD — attach a readout doc for the Copilot to reference; the chatbot
// then answers grounded in it (/api/copilot/readout/upload).
// ════════════════════════════════════════════════════════════════════════
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
        text:'📄 Added **'+ok.length+'** readout'+(ok.length>1?'s':'')+' ('+ok.map(function(a){return a.name;}).join(', ')+'). Ask me anything about '+(ok.length>1?'them':'it')+'.',
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
// ── Collapsible panes (C5) — toggle sidebar / right panel, persisted ──────────
function togglePane(which){
  const app = document.getElementById('app');
  const cls = which === 'sb' ? 'sb-collapsed' : 'rp-collapsed';
  const collapsed = app.classList.toggle(cls);
  // flip the in-pane toggle chevron to point the right way
  try{ localStorage.setItem('pane_'+which, collapsed ? '1' : '0'); }catch(e){}
}
(function(){
  const app = document.getElementById('app');
  try{
    if(localStorage.getItem('pane_sb') === '1') app.classList.add('sb-collapsed');
    if(localStorage.getItem('pane_rp') === '1') app.classList.add('rp-collapsed');
  }catch(e){}
})();

setInterval(() => { if (document.getElementById('app').style.display !== 'none') { refreshInsights(); } }, 20000);
</script>

</body>
</html>
"""
