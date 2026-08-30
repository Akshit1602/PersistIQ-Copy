import sqlite3
import json
from datetime import datetime

DB_PATH = "matchview_omnichannel.db"

def populate_db():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # 1. Projects Table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS projects (
            project_id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            description TEXT,
            objective TEXT,
            channel TEXT NOT NULL,
            data_source TEXT,
            created_at TEXT NOT NULL
        )
    """)

    # 2. Chat Threads Table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS chat_threads (
            thread_id TEXT PRIMARY KEY,
            project_id TEXT NOT NULL,
            experiment_name TEXT NOT NULL,
            title TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            FOREIGN KEY (project_id) REFERENCES projects(project_id)
        )
    """)

    # 3. Chat Messages Table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS chat_messages (
            message_id TEXT PRIMARY KEY,
            thread_id TEXT NOT NULL,
            role TEXT NOT NULL,
            content TEXT NOT NULL,
            kind TEXT DEFAULT 'text',
            timestamp TEXT NOT NULL,
            artifacts_json TEXT,
            module_id TEXT,
            run_id TEXT,
            status TEXT,
            logs_json TEXT,
            params_json TEXT,
            evaluation_json TEXT,
            brief_title TEXT,
            brief_body TEXT,
            FOREIGN KEY (thread_id) REFERENCES chat_threads(thread_id)
        )
    """)

    # Clear old domain metadata tables if re-running
    cursor.execute("DELETE FROM projects")
    cursor.execute("DELETE FROM chat_threads")
    cursor.execute("DELETE FROM chat_messages")

    # Seed Projects
    projects_data = [
        ("proj-walmart-digital", "Walmart Digital Growth", "Checkout, banner, and promo experiments for digital storefront conversion.", "Maximize ecommerce revenue and approval rates.", "digital", '{"type":"internal"}', "2026-06-01"),
        ("proj-cart-reliability", "Cart Reliability", "Funnel and checkout flow diagnostics for cart abandonment reduction.", "Improve checkout completion and reduce latency drop-offs.", "digital", '{"type":"internal"}', "2026-06-15"),
        ("proj-store-concurrent", "Store Concurrent Impact", "Panel-matched concurrent lift testing for staffing, format, assortment, and pricing initiatives across retail stores.", "Drive store foot traffic, basket conversion, and register throughput.", "store", '{"type":"internal"}', "2026-07-01"),
    ]

    cursor.executemany("""
        INSERT INTO projects (project_id, name, description, objective, channel, data_source, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, projects_data)

    # Seed Experiments into ecomm_experiments & store_experiments
    cursor.execute("DELETE FROM ecomm_experiments")
    cursor.execute("DELETE FROM store_experiments")

    ecomm_exps = [
        ("EXP_E01", "ACC_0030", "Instant CAD Pricing Widget", "Test instant quote conversion and automated quote approval speed.", "Concluded", "MTR_E01", "2026-06-01", "2026-06-21"),
        ("EXP_E02", "ACC_0004", "Checkout Net-30 Default", "Test payment terms lift and buyer re-order velocity.", "Active", "MTR_E02", "2026-07-01", None),
        ("EXP_E03", "ACC_0012", "Walmart Banner Redesign", "Redesign homepage banners with high-contrast borders and clear calls-to-action.", "Active", "MTR_E03", "2026-07-10", None),
        ("EXP_E04", "ACC_0015", "Cart Flow Optimization", "Reduce checkout flow steps from 4 to 2 to minimize cart abandonment.", "Active", "MTR_E04", "2026-07-15", None),
    ]
    cursor.executemany("""
        INSERT INTO ecomm_experiments (experiment_id, account_id, name, hypothesis, status, target_metric, start_date, end_date)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, ecomm_exps)

    store_exps = [
        ("EXP_S01", "Self-Checkout Kiosk Placement", "Adding kiosks reduces register queue time and raises basket size.", "Store-Level", "Concluded", "MTR_S01", "2026-05-01", "2026-05-21"),
        ("EXP_S02", "Dedicated Cashier Staffing Rollout", "Adding dedicated cashiers during peak hours raises basket conversion without increasing labour cost per transaction.", "Store-Level", "Active", "MTR_S02", "2026-07-01", None),
        ("EXP_S03", "Paint-and-Powder Store Remodel (Wave 2)", "Remodeling hardware and paint zones increases dwell time and basket conversion.", "Store-Level", "Active", "MTR_S03", "2026-07-05", None),
    ]
    cursor.executemany("""
        INSERT INTO store_experiments (experiment_id, name, hypothesis, allocation_level, status, target_metric, start_date, end_date)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, store_exps)

    # Seed Chat Threads
    threads_data = [
        ("t1", "proj-walmart-digital", "Instant CAD Pricing Widget", "Instant CAD Pricing Evaluation", "2026-08-30 14:00"),
        ("t2", "proj-walmart-digital", "Checkout Net-30 Default", "Net-30 Payment Terms Analysis", "2026-08-30 15:00"),
        ("t3", "proj-walmart-digital", "Walmart Banner Redesign", "Homepage Banner Conversion Diagnostics", "2026-08-30 16:00"),
        ("t4", "proj-cart-reliability", "Cart Flow Optimization", "Cart Abandonment & Funnel Bottlenecks", "2026-08-30 16:30"),
        ("t5", "proj-store-concurrent", "Self-Checkout Kiosk Placement", "Store Kiosk Foot Traffic & Dwell Time", "2026-08-30 17:00"),
        ("t6", "proj-store-concurrent", "Dedicated Cashier Staffing Rollout", "Staffing Panel Match & Causal DiD", "2026-08-30 17:30"),
    ]
    cursor.executemany("""
        INSERT INTO chat_threads (thread_id, project_id, experiment_name, title, updated_at)
        VALUES (?, ?, ?, ?, ?)
    """, threads_data)

    # Seed Chat Messages
    messages_data = [
        # Thread t1 (Instant CAD Pricing Widget)
        ("m1_1", "t1", "assistant", "This is the active thread for **Instant CAD Pricing Widget**. What analytical queries or statistical tests would you like to run on quote approvals and conversion rates?", "text", "2026-08-30 14:00", None, None, None, None, None, None, None, None, None),
        ("m1_2", "t1", "user", "What was the conversion lift for Instant CAD Pricing?", "text", "2026-08-30 14:01", None, None, None, None, None, None, None, None, None),
        ("m1_3", "t1", "assistant", "The Instant CAD Pricing experiment demonstrated a statistically significant lift of **+9.09%** in quote approval conversion (p-value: 0.012). Cuped variance reduction reduced pre-period noise by 18.4%.", "text", "2026-08-30 14:02",
         json.dumps([{
             "artifact_id": "art_e01_stat",
             "type": "stat_results_card",
             "title": "Instant CAD Pricing Conversion Analysis",
             "payload": {
                 "experiment": "Instant CAD Pricing Widget",
                 "metric": "Quote Approval Rate",
                 "relative_lift_pct": 9.09,
                 "p_value": 0.012,
                 "is_stat_sig": True,
                 "sample_size": 12450,
                 "cuped_variance_reduction_pct": 18.4
             }
         }]), None, None, None, None, None, None, None, None),

        # Thread t2 (Checkout Net-30 Default)
        ("m2_1", "t2", "assistant", "This is the discussion thread for **Checkout Net-30 Default**. I can help you evaluate buyer re-order velocity, sample sizing, or SRM health.", "text", "2026-08-30 15:00", None, None, None, None, None, None, None, None, None),
        ("m2_2", "t2", "user", "Check sample ratio mismatch and SRM health.", "text", "2026-08-30 15:01", None, None, None, None, None, None, None, None, None),
        ("m2_3", "t2", "assistant", "Sample Ratio Mismatch check completed: **HEALTHY**. Assigned traffic ratio between Control (15,000 users) and Variant (14,980 users) yields chi-square p-value = 0.908.", "text", "2026-08-30 15:02",
         json.dumps([{
             "artifact_id": "art_e02_srm",
             "type": "stat_results_card",
             "title": "SRM Health Check: Net-30 Default",
             "payload": {
                 "experiment": "Checkout Net-30 Default",
                 "metric": "Traffic Allocation Ratio",
                 "status": "HEALTHY",
                 "control_count": 15000,
                 "treatment_count": 14980,
                 "p_value": 0.908
             }
         }]), "health-monitor", "run_e02_1", "success", json.dumps(["[INFO] Fetching user exposures", "[SUCCESS] Chi-Square p-value = 0.908"]), json.dumps({"experiment": "Checkout Net-30 Default"}), json.dumps({"summary": "Traffic allocation balanced cleanly."}), None, None),

        # Thread t5 (Self-Checkout Kiosk Placement)
        ("m5_1", "t5", "assistant", "Discussion thread for **Self-Checkout Kiosk Placement**. Ask questions regarding store foot traffic, register queue dwell time, or basket sizes across store clusters.", "text", "2026-08-30 17:00", None, None, None, None, None, None, None, None, None),
        ("m5_2", "t5", "user", "Which stores showed higher dwell time in Endcap B and kiosk zones?", "text", "2026-08-30 17:01", None, None, None, None, None, None, None, None, None),
        ("m5_3", "t5", "assistant", "In the Self-Checkout Kiosk trial, Treatment stores (Store IDs: STR_101, STR_104) exhibited an average dwell time of 215 seconds in Endcap B vs 340 seconds in Control stores, reducing register queue times by **+3.94%** basket conversion.", "text", "2026-08-30 17:02",
         json.dumps([{
             "artifact_id": "art_s01_dwell",
             "type": "stat_results_card",
             "title": "Store Foot Traffic & Dwell Time Analysis",
             "payload": {
                 "experiment": "Self-Checkout Kiosk Placement",
                 "metric": "Basket Size Lift",
                 "relative_lift_pct": 3.94,
                 "p_value": 0.038,
                 "is_stat_sig": True,
                 "treatment_stores": ["STR_101", "STR_104"],
                 "control_stores": ["STR_102", "STR_103"]
             }
         }]), None, None, None, None, None, None, None, None),

        # Thread t6 (Dedicated Cashier Staffing Rollout)
        ("m6_1", "t6", "assistant", "Discussion thread for **Dedicated Cashier Staffing Rollout**. Causal DiD and Synthetic Control matching models ready for store cluster analysis.", "text", "2026-08-30 17:30", None, None, None, None, None, None, None, None, None),
    ]

    cursor.executemany("""
        INSERT INTO chat_messages (
            message_id, thread_id, role, content, kind, timestamp,
            artifacts_json, module_id, run_id, status, logs_json,
            params_json, evaluation_json, brief_title, brief_body
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, messages_data)

    conn.commit()
    conn.close()
    print("Successfully populated matchview_omnichannel.db with real projects, experiments, threads, and chat history.")

if __name__ == "__main__":
    populate_db()
