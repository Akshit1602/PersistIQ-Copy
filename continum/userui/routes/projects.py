import os
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional
import duckdb
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

projects_router = APIRouter(prefix="/api/projects", tags=["Projects & Conversations"])

DB_PATH = Path(__file__).resolve().parents[2] / "matchview_omnichannel.db"
if not DB_PATH.exists():
    DB_PATH = Path("matchview_omnichannel.db")


def get_db_connection():
    if not DB_PATH.exists():
        raise HTTPException(status_code=500, detail="Database file matchview_omnichannel.db not found.")
    return duckdb.connect(str(DB_PATH))


def init_chat_tables():
    conn = get_db_connection()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS chat_threads (
            id VARCHAR PRIMARY KEY,
            project_id VARCHAR,
            title VARCHAR,
            channel VARCHAR,
            updated_at VARCHAR
        )
    """)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS chat_messages (
            id VARCHAR PRIMARY KEY,
            thread_id VARCHAR,
            role VARCHAR,
            content VARCHAR,
            timestamp VARCHAR
        )
    """)

    threads_count = conn.execute("SELECT COUNT(*) FROM chat_threads").fetchone()[0]
    if threads_count == 0:
        seed_threads = [
            ("t1", "p1", "Dynamic Pricing Strategy - Q3 Optimization", "ecomm", datetime.now().isoformat()),
            ("t2", "p1", "E-Commerce Checkout Cart Abandonment", "ecomm", datetime.now().isoformat()),
            ("t3", "p2", "Physical Store Endcap Placement Test", "store", datetime.now().isoformat()),
            ("t4", "p2", "Store Foot Traffic & POS Analytics", "store", datetime.now().isoformat()),
            ("t5", "p3", "Omnichannel Fulfillment SLA Impact", "omnichannel", datetime.now().isoformat()),
        ]

        for t in seed_threads:
            conn.execute("INSERT INTO chat_threads VALUES (?, ?, ?, ?, ?)", t)

        seed_msgs = [
            (str(uuid.uuid4()), "t1", "user", "What were the main learnings from our dynamic pricing experiment on consumer electronics?", datetime.now().isoformat()),
            (str(uuid.uuid4()), "t1", "assistant", "The dynamic pricing experiment on consumer electronics yielded a 4.2% lift in gross margin with no significant decline in conversion rate. High-tier SKUs saw optimal volume at a 3% price reduction during peak traffic hours.", datetime.now().isoformat()),
            (str(uuid.uuid4()), "t2", "user", "Analyze cart abandonment rates across different payment gateways.", datetime.now().isoformat()),
            (str(uuid.uuid4()), "t2", "assistant", "Analysis shows 1-click Express Checkout reduced cart abandonment by 14.8% compared to standard credit card checkout forms.", datetime.now().isoformat()),
            (str(uuid.uuid4()), "t3", "user", "How did store endcap placements perform for seasonal snacks in Region 4?", datetime.now().isoformat()),
            (str(uuid.uuid4()), "t3", "assistant", "Endcap displays in Region 4 increased impulse purchase units by 22.3% per store week, with statistical significance p = 0.004.", datetime.now().isoformat()),
            (str(uuid.uuid4()), "t4", "user", "Compare weekend foot traffic vs weekday POS basket size.", datetime.now().isoformat()),
            (str(uuid.uuid4()), "t4", "assistant", "Weekend foot traffic is 38% higher, but weekday basket sizes average $42.50 vs $31.10 on weekends.", datetime.now().isoformat()),
            (str(uuid.uuid4()), "t5", "user", "What is the correlation between standard delivery delay and customer retention?", datetime.now().isoformat()),
            (str(uuid.uuid4()), "t5", "assistant", "Fulfillment delays exceeding 48 hours beyond estimated SLA result in a 28% decrease in 90-day repurchase likelihood.", datetime.now().isoformat()),
        ]

        for m in seed_msgs:
            conn.execute("INSERT INTO chat_messages VALUES (?, ?, ?, ?, ?)", m)

    conn.close()


try:
    init_chat_tables()
except Exception:
    pass


class CreateThreadRequest(BaseModel):
    project_id: str
    title: str
    channel: Optional[str] = "ecomm"


class CreateMessageRequest(BaseModel):
    role: str
    content: str


@projects_router.get("")
def get_projects():
    """
    Returns dynamically computed projects summary using database metrics.
    """
    try:
        conn = get_db_connection()

        ecomm_exp_count = conn.execute("SELECT COUNT(*) FROM ecomm_experiments").fetchone()[0]
        store_exp_count = conn.execute("SELECT COUNT(*) FROM store_experiments").fetchone()[0]
        ecomm_orders_count = conn.execute("SELECT COUNT(*) FROM ecomm_orders").fetchone()[0]
        store_pos_count = conn.execute("SELECT COUNT(*) FROM store_pos_transactions").fetchone()[0]

        threads = conn.execute("SELECT project_id, COUNT(*) FROM chat_threads GROUP BY project_id").fetchall()
        thread_counts = {t[0]: t[1] for t in threads}

        conn.close()

        projects = [
            {
                "id": "p1",
                "name": "E-Commerce Digital Storefront",
                "channel": "ecomm",
                "description": "Digital conversion rate optimization, cart abandonment tests, and dynamic pricing models.",
                "experiments_count": ecomm_exp_count,
                "total_records": ecomm_orders_count,
                "threads_count": thread_counts.get("p1", 0),
                "updated_at": "Just now"
            },
            {
                "id": "p2",
                "name": "Physical Retail Retail Outlets",
                "channel": "store",
                "description": "In-store layout matching, foot-traffic sensor telemetry, and POS basket analysis.",
                "experiments_count": store_exp_count,
                "total_records": store_pos_count,
                "threads_count": thread_counts.get("p2", 0),
                "updated_at": "2 hours ago"
            },
            {
                "id": "p3",
                "name": "Omnichannel Unified Experience",
                "channel": "omnichannel",
                "description": "BOPIS (Buy Online Pick Up In Store) workflow optimization and cross-channel customer journeys.",
                "experiments_count": ecomm_exp_count + store_exp_count,
                "total_records": ecomm_orders_count + store_pos_count,
                "threads_count": thread_counts.get("p3", 0),
                "updated_at": "1 day ago"
            }
        ]

        return {"status": "success", "projects": projects}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to load projects: {str(e)}")


@projects_router.get("/threads")
def get_thread_groups(project_id: Optional[str] = None):
    try:
        conn = get_db_connection()
        if project_id:
            res = conn.execute("SELECT id, project_id, title, channel, updated_at FROM chat_threads WHERE project_id = ? ORDER BY updated_at DESC", (project_id,)).fetchall()
        else:
            res = conn.execute("SELECT id, project_id, title, channel, updated_at FROM chat_threads ORDER BY updated_at DESC").fetchall()

        threads = [
            {
                "id": r[0],
                "project_id": r[1],
                "title": r[2],
                "channel": r[3],
                "updated_at": r[4]
            }
            for r in res
        ]
        conn.close()
        return {"status": "success", "threads": threads}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch threads: {str(e)}")


@projects_router.post("/{project_id}/threads")
def create_thread(project_id: str, req: CreateThreadRequest):
    try:
        conn = get_db_connection()
        thread_id = str(uuid.uuid4())
        now_str = datetime.now().isoformat()
        conn.execute("INSERT INTO chat_threads VALUES (?, ?, ?, ?, ?)", (thread_id, project_id, req.title, req.channel or "ecomm", now_str))
        conn.close()
        return {
            "status": "success",
            "thread": {
                "id": thread_id,
                "project_id": project_id,
                "title": req.title,
                "channel": req.channel,
                "updated_at": now_str
            }
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to create thread: {str(e)}")


@projects_router.get("/threads/{thread_id}/messages")
def get_thread_messages(thread_id: str):
    try:
        conn = get_db_connection()
        res = conn.execute("SELECT id, thread_id, role, content, timestamp FROM chat_messages WHERE thread_id = ? ORDER BY timestamp ASC", (thread_id,)).fetchall()
        messages = [
            {
                "id": r[0],
                "thread_id": r[1],
                "role": r[2],
                "content": r[3],
                "timestamp": r[4]
            }
            for r in res
        ]
        conn.close()
        return {"status": "success", "thread_id": thread_id, "messages": messages}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch messages: {str(e)}")


@projects_router.post("/threads/{thread_id}/messages")
def post_thread_message(thread_id: str, req: CreateMessageRequest):
    try:
        conn = get_db_connection()
        msg_id = str(uuid.uuid4())
        now_str = datetime.now().isoformat()
        conn.execute("INSERT INTO chat_messages VALUES (?, ?, ?, ?, ?)", (msg_id, thread_id, req.role, req.content, now_str))
        conn.execute("UPDATE chat_threads SET updated_at = ? WHERE id = ?", (now_str, thread_id))
        conn.close()
        return {
            "status": "success",
            "message": {
                "id": msg_id,
                "thread_id": thread_id,
                "role": req.role,
                "content": req.content,
                "timestamp": now_str
            }
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to post message: {str(e)}")
