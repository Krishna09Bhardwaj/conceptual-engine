"""
APScheduler jobs running inside FastAPI's lifespan.
All times in IST (Asia/Kolkata).
"""
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
import pytz

IST = pytz.timezone("Asia/Kolkata")
_scheduler = AsyncIOScheduler(timezone=IST)


async def _daily_risk_scan():
    """8AM IST: scan all clients for new at-risk conditions."""
    try:
        from risk_engine import scan_all_clients_risk
        flagged = scan_all_clients_risk()
        if flagged:
            print(f"[Scheduler] Daily risk scan: flagged {len(flagged)} new at-risk clients: {flagged}")
        else:
            print("[Scheduler] Daily risk scan: no new at-risk clients.")
    except Exception as e:
        print(f"[Scheduler] Risk scan error: {e}")


async def _morning_digest():
    """9AM IST: generate per-PM digest of priority clients."""
    try:
        from database import get_all_clients, store_digest
        from risk_engine import rule_based_risk
        clients = get_all_clients()
        pm_digests: dict = {}
        for client in clients:
            level = rule_based_risk(client)
            if level in ("at_risk", "watch"):
                pm = client.get("assigned_pm") or "unassigned"
                pm_digests.setdefault(pm, []).append((client, level))
        for pm_name, items in pm_digests.items():
            lines = [f"Today's Focus — {len(items)} priority client(s):"]
            for client, level in sorted(items, key=lambda x: x[1] == "at_risk", reverse=True):
                lines.append(
                    f"• {client['name']} ({client['case_type']}) — {level.upper()}"
                    f" | Deadline: {client.get('deadline') or 'Not set'}"
                )
            store_digest(pm_name, "\n".join(lines))
        print(f"[Scheduler] Morning digest generated for {len(pm_digests)} PMs.")
    except Exception as e:
        print(f"[Scheduler] Digest error: {e}")


async def _weekly_reindex():
    """Sunday midnight IST: rebuild all ChromaDB collections from SQLite."""
    try:
        from database import get_all_clients
        from vector_store import rebuild_client_index
        clients = get_all_clients()
        for client in clients:
            rebuild_client_index(client["id"])
        print(f"[Scheduler] Weekly re-index complete for {len(clients)} clients.")
    except Exception as e:
        print(f"[Scheduler] Re-index error: {e}")


def start_scheduler():
    _scheduler.add_job(_daily_risk_scan, CronTrigger(hour=8, minute=0, timezone=IST), id="daily_risk")
    _scheduler.add_job(_morning_digest, CronTrigger(hour=9, minute=0, timezone=IST), id="morning_digest")
    _scheduler.add_job(_weekly_reindex, CronTrigger(day_of_week="sun", hour=0, minute=0, timezone=IST), id="weekly_reindex")
    _scheduler.start()
    print("✅ Scheduler started — daily risk scan 8AM IST, digest 9AM IST, re-index Sunday midnight IST")


def stop_scheduler():
    if _scheduler.running:
        _scheduler.shutdown(wait=False)
