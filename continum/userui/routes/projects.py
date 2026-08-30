import json
import sqlite3
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, HTTPException, Query
from continum.config import settings

router = APIRouter(prefix="/api/projects", tags=["Projects & Workspaces"])

DB_PATH = "matchview_omnichannel.db"

@router.get("", response_model=List[Dict[str, Any]])
def get_projects():
    """
    Returns all project workspaces stored in matchview_omnichannel.db.
    """
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("SELECT project_id, name, description, objective, channel, data_source, created_at FROM projects")
        rows = cursor.fetchall()
        conn.close()

        projects = []
        for r in rows:
            ds = json.loads(r[5]) if r[5] else {"type": "internal"}
            projects.append({
                "id": r[0],
                "name": r[1],
                "description": r[2] or "",
                "objective": r[3] or "",
                "channel": r[4],
                "dataSource": ds,
                "createdAt": r[6],
            })
        return projects
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Database query error: {str(e)}")


@router.get("/threads", response_model=List[Dict[str, Any]])
def get_threads():
    """
    Returns all chat thread groups grouped by project and experiment from the database.
    """
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("""
            SELECT thread_id, project_id, experiment_name, title, updated_at
            FROM chat_threads
        """)
        rows = cursor.fetchall()
        conn.close()

        groups_map = {}
        for r in rows:
            thread_id, project_id, experiment_name, title, updated_at = r
            key = (project_id, experiment_name)
            if key not in groups_map:
                groups_map[key] = {
                    "projectId": project_id,
                    "experiment": experiment_name,
                    "threads": [],
                }
            groups_map[key]["threads"].append({
                "id": thread_id,
                "title": title,
                "timestamp": updated_at,
            })

        return list(groups_map.values())
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Database query error: {str(e)}")


@router.get("/conversations/{thread_id}", response_model=List[Dict[str, Any]])
def get_conversation_messages(thread_id: str):
    """
    Returns all persisted conversation chat messages for a specific thread_id.
    """
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("""
            SELECT message_id, role, content, kind, timestamp, artifacts_json, module_id, run_id, status, logs_json, params_json, evaluation_json, brief_title, brief_body
            FROM chat_messages
            WHERE thread_id = ?
            ORDER BY timestamp ASC
        """, (thread_id,))
        rows = cursor.fetchall()
        conn.close()

        messages = []
        for r in rows:
            msg = {
                "id": r[0],
                "role": r[1],
                "content": r[2],
                "kind": r[3] or "text",
                "timestamp": r[4],
            }
            if r[5]:
                msg["artifacts"] = json.loads(r[5])
            if r[6]:
                msg["moduleId"] = r[6]
            if r[7]:
                msg["runId"] = r[7]
            if r[8]:
                msg["status"] = r[8]
            if r[9]:
                msg["logs"] = json.loads(r[9])
            if r[10]:
                msg["params"] = json.loads(r[10])
            if r[11]:
                msg["evaluation"] = json.loads(r[11])
            if r[12]:
                msg["briefTitle"] = r[12]
            if r[13]:
                msg["briefBody"] = r[13]
            messages.append(msg)

        return messages
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Database query error: {str(e)}")
