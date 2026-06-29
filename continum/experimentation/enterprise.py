from __future__ import annotations

import hashlib
import json
import logging
import os
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional
from uuid import uuid4

from continum.crosscutting.runtime_config import RUNTIME_DATA_DIR, ensure_runtime_data_dir

logger = logging.getLogger("continum.experimentation.enterprise")

ensure_runtime_data_dir()
AUDIT_FILE      = os.path.join(RUNTIME_DATA_DIR, ".continum_audit.ndjson")
SNAPSHOT_DIR    = os.path.join(RUNTIME_DATA_DIR, ".continum_snapshots")
GOVERNANCE_FILE = os.path.join(RUNTIME_DATA_DIR, ".continum_governance.json")


# ─────────────────────────────────────────────────────────────────────────────
# AUDIT LOG
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class AuditEntry:
    entry_id:    str
    timestamp:   str
    actor:       str            # "system" | "analyst:<name>" | "ui"
    action:      str            # "module_run" | "session_fork" | "ship_approved" | ...
    subject:     str            # what the action was performed on
    details:     Dict[str, Any]
    session_id:  str            = ""
    ok:          bool           = True
    hash:        str            = ""

    def to_dict(self) -> Dict:
        return self.__dict__.copy()

    def compute_hash(self) -> str:
        content = json.dumps({
            "entry_id": self.entry_id,
            "timestamp": self.timestamp,
            "actor":  self.actor,
            "action": self.action,
            "subject":self.subject,
        }, sort_keys=True)
        return hashlib.sha256(content.encode()).hexdigest()[:16]


class AuditLog:

    def __init__(self, path: str = AUDIT_FILE):
        self.path = Path(path)

    def record(
        self,
        action: str,
        subject: str,
        details: Optional[Dict] = None,
        actor: str = "system",
        session_id: str = "",
        ok: bool = True,
    ) -> AuditEntry:
        entry = AuditEntry(
            entry_id=str(uuid4())[:8],
            timestamp=datetime.utcnow().isoformat(),
            actor=actor,
            action=action,
            subject=subject,
            details=details or {},
            session_id=session_id,
            ok=ok,
        )
        entry.hash = entry.compute_hash()
        self._append(entry)
        return entry

    def _append(self, entry: AuditEntry) -> None:
        try:
            with open(self.path, "a", encoding="utf-8") as f:
                f.write(json.dumps(entry.to_dict(), default=str) + "\n")
        except Exception as e:
            logger.warning("Audit log write failed: %s", e)

    def read_all(self) -> List[Dict]:
        if not self.path.exists():
            return []
        entries = []
        try:
            with open(self.path, encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line:
                        entries.append(json.loads(line))
        except Exception as e:
            logger.warning("Audit log read failed: %s", e)
        return entries

    def read_for_session(self, session_id: str) -> List[Dict]:
        return [e for e in self.read_all() if e.get("session_id") == session_id]

    def read_for_subject(self, subject: str) -> List[Dict]:
        return [e for e in self.read_all() if e.get("subject") == subject]

    def tail(self, n: int = 20) -> List[Dict]:
        return self.read_all()[-n:]

    def render_table(self, entries: Optional[List[Dict]] = None, n: int = 20) -> str:
        rows = entries or self.tail(n)
        if not rows:
            return "  No audit entries yet."
        lines = [f"  {'Timestamp':<22}  {'Actor':<12}  {'Action':<22}  Subject"]
        lines.append(f"  {'─' * 72}")
        for e in rows:
            ts  = str(e.get("timestamp", ""))[:19]
            act = str(e.get("actor", ""))[:12]
            act_str = str(e.get("action", ""))[:22]
            subj = str(e.get("subject", ""))[:30]
            ok_icon = "✅" if e.get("ok", True) else "❌"
            lines.append(f"  {ok_icon} {ts}  {act:<12}  {act_str:<22}  {subj}")
        return "\n".join(lines)


# ─────────────────────────────────────────────────────────────────────────────
# GOVERNANCE LAYER
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class ShipApproval:
    experiment_id: str
    requested_by:  str
    requested_at:  str
    status:        str              # "pending" | "approved" | "rejected"
    reviewed_by:   str              = ""
    reviewed_at:   str              = ""
    comment:       str              = ""
    conditions:    List[str]        = field(default_factory=list)

    def to_dict(self) -> Dict:
        return self.__dict__.copy()


class GovernanceLayer:

    def __init__(self, path: str = GOVERNANCE_FILE, audit: Optional[AuditLog] = None):
        self.path  = Path(path)
        self.audit = audit or AuditLog()
        self._approvals: Dict[str, ShipApproval] = {}
        self._load()

    def request_ship(
        self,
        experiment_id: str,
        requested_by: str = "analyst",
        conditions: Optional[List[str]] = None,
    ) -> ShipApproval:
        approval = ShipApproval(
            experiment_id=experiment_id,
            requested_by=requested_by,
            requested_at=datetime.utcnow().isoformat(),
            status="pending",
            conditions=conditions or [],
        )
        self._approvals[experiment_id] = approval
        self._save()
        self.audit.record(
            action="ship_requested",
            subject=experiment_id,
            details={"requested_by": requested_by, "conditions": conditions},
            actor=requested_by,
        )
        logger.info("Ship request created for %s by %s", experiment_id, requested_by)
        return approval

    def approve_ship(
        self,
        experiment_id: str,
        reviewed_by: str,
        comment: str = "",
    ) -> Optional[ShipApproval]:
        a = self._approvals.get(experiment_id)
        if not a:
            return None
        a.status      = "approved"
        a.reviewed_by = reviewed_by
        a.reviewed_at = datetime.utcnow().isoformat()
        a.comment     = comment
        self._save()
        self.audit.record(
            action="ship_approved",
            subject=experiment_id,
            details={"reviewed_by": reviewed_by, "comment": comment},
            actor=reviewed_by,
        )
        return a

    def reject_ship(
        self,
        experiment_id: str,
        reviewed_by: str,
        comment: str,
    ) -> Optional[ShipApproval]:
        a = self._approvals.get(experiment_id)
        if not a:
            return None
        a.status      = "rejected"
        a.reviewed_by = reviewed_by
        a.reviewed_at = datetime.utcnow().isoformat()
        a.comment     = comment
        self._save()
        self.audit.record(
            action="ship_rejected",
            subject=experiment_id,
            details={"reviewed_by": reviewed_by, "comment": comment},
            actor=reviewed_by,
        )
        return a

    def get_approval(self, experiment_id: str) -> Optional[ShipApproval]:
        return self._approvals.get(experiment_id)

    def pending(self) -> List[ShipApproval]:
        return [a for a in self._approvals.values() if a.status == "pending"]

    def _save(self) -> None:
        try:
            data = {k: v.to_dict() for k, v in self._approvals.items()}
            with open(self.path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, default=str)
        except Exception as e:
            logger.warning("Governance save failed: %s", e)

    def _load(self) -> None:
        if not self.path.exists():
            return
        try:
            with open(self.path, encoding="utf-8") as f:
                data = json.load(f)
            for k, v in data.items():
                self._approvals[k] = ShipApproval(**v)
        except Exception as e:
            logger.warning("Governance load failed: %s", e)


# ─────────────────────────────────────────────────────────────────────────────
# EXECUTION SNAPSHOT
# ─────────────────────────────────────────────────────────────────────────────

class ExecutionSnapshot:

    def __init__(self, directory: str = SNAPSHOT_DIR):
        self.dir = Path(directory)
        self.dir.mkdir(exist_ok=True)

    def take(self, session, bus=None, label: str = "") -> str:
        snap_id = f"{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}_{str(uuid4())[:6]}"
        data = {
            "snapshot_id": snap_id,
            "label":       label,
            "taken_at":    datetime.utcnow().isoformat(),
            "session":     session.to_dict(),
            "insights":    [
                {"type": i.insight_type, "severity": i.severity,
                 "source": i.source_module, "message": i.message}
                for i in (bus.all() if bus else [])
            ],
        }
        path = self.dir / f"snapshot_{snap_id}.json"
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, default=str)
            logger.info("Snapshot taken: %s", snap_id)
        except Exception as e:
            logger.warning("Snapshot failed: %s", e)
        return snap_id

    def list_snapshots(self) -> List[Dict]:
        snapshots = []
        for path in sorted(self.dir.glob("snapshot_*.json"), reverse=True)[:20]:
            try:
                with open(path, encoding="utf-8") as f:
                    d = json.load(f)
                snapshots.append({
                    "snapshot_id": d.get("snapshot_id"),
                    "label":       d.get("label"),
                    "taken_at":    d.get("taken_at", "")[:19],
                    "session_id":  d.get("session", {}).get("session_id"),
                    "n_runs":      len(d.get("session", {}).get("execution_history", [])),
                })
            except Exception:
                pass
        return snapshots

    def load(self, snapshot_id: str) -> Optional[Dict]:
        path = self.dir / f"snapshot_{snapshot_id}.json"
        if not path.exists():
            return None
        try:
            with open(path, encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logger.warning("Snapshot load failed: %s", e)
            return None


# ─────────────────────────────────────────────────────────────────────────────
# COMPLIANCE REPORT
# ─────────────────────────────────────────────────────────────────────────────

def generate_compliance_report(
    experiment_id: str,
    session=None,
    audit: Optional[AuditLog] = None,
    governance: Optional[GovernanceLayer] = None,
) -> Dict:
    audit = audit or AuditLog()
    governance = governance or GovernanceLayer(audit=audit)

    audit_trail = audit.read_for_subject(experiment_id)
    approval    = governance.get_approval(experiment_id)

    session_runs = []
    if session:
        session_runs = [
            r.to_dict() for r in session.execution_history
            if hasattr(r, "to_dict")
        ]

    return {
        "report_id":     str(uuid4())[:8],
        "generated_at":  datetime.utcnow().isoformat(),
        "experiment_id": experiment_id,
        "analyst":       session.client_name if session else "unknown",
        "session_id":    session.session_id if session else "unknown",
        "audit_trail":   audit_trail,
        "approval":      approval.to_dict() if approval else None,
        "session_runs":  session_runs,
        "n_audit_entries": len(audit_trail),
        "ship_status":   approval.status if approval else "not_requested",
    }


# ─────────────────────────────────────────────────────────────────────────────
# GLOBAL SINGLETONS
# ─────────────────────────────────────────────────────────────────────────────

_AUDIT:      Optional[AuditLog]      = None
_GOVERNANCE: Optional[GovernanceLayer] = None
_SNAPSHOTS:  Optional[ExecutionSnapshot] = None


def get_audit() -> AuditLog:
    global _AUDIT
    if _AUDIT is None:
        _AUDIT = AuditLog()
    return _AUDIT


def get_governance() -> GovernanceLayer:
    global _GOVERNANCE
    if _GOVERNANCE is None:
        _GOVERNANCE = GovernanceLayer(audit=get_audit())
    return _GOVERNANCE


def get_snapshots() -> ExecutionSnapshot:
    global _SNAPSHOTS
    if _SNAPSHOTS is None:
        _SNAPSHOTS = ExecutionSnapshot()
    return _SNAPSHOTS


__all__ = [
    "AuditLog", "GovernanceLayer", "ExecutionSnapshot",
    "AuditEntry", "ShipApproval",
    "get_audit", "get_governance", "get_snapshots",
    "generate_compliance_report",
]
