"""Single background worker with persisted run state and cooperative cancellation."""

import asyncio
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from datetime import datetime, timezone
import json
import threading
import uuid
from filelock import FileLock, Timeout
from ..config import DATA_DIR
from ..progress import reporting_to, emit


def now():
    return datetime.now(timezone.utc).isoformat()


class Runner:
    def __init__(self, database):
        self.db = database
        self.executor = ThreadPoolExecutor(
            max_workers=1, thread_name_prefix="jobpilot-web"
        )
        self.lock = FileLock(str(DATA_DIR / "web-worker.lock"))
        self.login_done = threading.Event()
        self.loop = self.task = None
        with closing(self.db._get_connection()) as conn, conn:
            conn.execute("""CREATE TABLE IF NOT EXISTS web_runs (
                id TEXT PRIMARY KEY, action TEXT NOT NULL, platform TEXT NOT NULL,
                state TEXT NOT NULL, started_at TEXT NOT NULL, finished_at TEXT,
                options TEXT NOT NULL, result TEXT, message TEXT NOT NULL DEFAULT '')""")
            conn.execute("""CREATE TABLE IF NOT EXISTS web_run_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT, run_id TEXT NOT NULL,
                timestamp TEXT NOT NULL, payload TEXT NOT NULL)""")
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_run_events ON web_run_events(run_id,id)"
            )
        # Reclaim only when no other web process owns the worker lock.
        try:
            with self.lock.acquire(timeout=0):
                with closing(self.db._get_connection()) as conn, conn:
                    conn.execute(
                        "UPDATE web_runs SET state='interrupted', finished_at=?, message=? WHERE state IN ('queued','running')",
                        (
                            now(),
                            "Server stopped during this run. Inspect any applying jobs before retrying.",
                        ),
                    )
        except Timeout:
            pass

    def list(self):
        with closing(self.db._get_connection()) as conn:
            rows = [
                dict(row)
                for row in conn.execute(
                    "SELECT * FROM web_runs ORDER BY started_at DESC LIMIT 30"
                )
            ]
        for row in rows:
            row["options"] = json.loads(row["options"])
            row["result"] = json.loads(row["result"]) if row["result"] else None
            with closing(self.db._get_connection()) as conn:
                events = [
                    {
                        "id": event["id"],
                        "timestamp": event["timestamp"],
                        **json.loads(event["payload"]),
                    }
                    for event in conn.execute(
                        "SELECT * FROM web_run_events WHERE run_id=? ORDER BY id",
                        (row["id"],),
                    )
                ]
            progress = {}
            for event in events:
                key = (event["stage"], event.get("platform"))
                previous = progress.get(key, {})
                progress[key] = {
                    **previous,
                    **{k: v for k, v in event.items() if v is not None},
                    "metrics": {
                        **previous.get("metrics", {}),
                        **(event.get("metrics") or {}),
                    },
                }
            row["events"] = events[-200:]
            row["event_count"] = len(events)
            row["progress"] = list(progress.values())
        return rows

    def events(self, run_id):
        with closing(self.db._get_connection()) as conn:
            return [
                {
                    "id": row["id"],
                    "timestamp": row["timestamp"],
                    **json.loads(row["payload"]),
                }
                for row in conn.execute(
                    "SELECT * FROM web_run_events WHERE run_id=? ORDER BY id", (run_id,)
                )
            ]

    def event(self, run_id, payload):
        with closing(self.db._get_connection()) as conn, conn:
            conn.execute(
                "INSERT INTO web_run_events(run_id,timestamp,payload) VALUES (?,?,?)",
                (run_id, now(), json.dumps(payload)),
            )
            conn.execute(
                "UPDATE web_runs SET message=? WHERE id=? AND state='running'",
                (payload["message"], run_id),
            )

    def start(self, action, platform, options):
        # Acquired in the submitting thread; reserve DB state before executor dispatch.
        with closing(self.db._get_connection()) as conn, conn:
            conn.execute("BEGIN IMMEDIATE")
            if conn.execute(
                "SELECT 1 FROM web_runs WHERE state IN ('queued','running')"
            ).fetchone():
                raise ValueError(
                    "Another run is active. Wait for it to finish or stop it first."
                )
            run_id = uuid.uuid4().hex
            conn.execute(
                "INSERT INTO web_runs(id,action,platform,state,started_at,options,message) VALUES (?,?,?,'queued',?,?,?)",
                (
                    run_id,
                    action,
                    platform,
                    now(),
                    json.dumps(options),
                    "Waiting for the local worker",
                ),
            )
        self.login_done.clear()
        self.executor.submit(self._execute, run_id, action, platform, options)
        return run_id

    def _update(self, run_id, state, message, result=None):
        with closing(self.db._get_connection()) as conn, conn:
            conn.execute(
                "UPDATE web_runs SET state=?,message=?,result=?,finished_at=? WHERE id=?",
                (
                    state,
                    message,
                    json.dumps(result) if result is not None else None,
                    None if state in ("queued", "running") else now(),
                    run_id,
                ),
            )

    def _execute(self, run_id, action, platform, options):
        try:
            with self.lock.acquire(timeout=0):
                message = (
                    "Complete sign-in in the opened browser, then click Verify sign-in."
                    if action == "login"
                    else "Working on your selected platforms"
                )
                self._update(run_id, "running", message)
                self.loop = asyncio.new_event_loop()
                with reporting_to(lambda payload: self.event(run_id, payload)):
                    self.task = self.loop.create_task(
                        self._perform(action, platform, options)
                    )
                result = self.loop.run_until_complete(self.task)

                def problems(value):
                    if isinstance(value, dict):
                        return bool(
                            value.get("error")
                            or value.get("errors")
                            or value.get("failed")
                            or value.get("review")
                            or (
                                value.get("success") is False
                                and value.get("status")
                                not in ("dry_run", "already_applied", "expired")
                            )
                            or value.get("status")
                            in ("action_required", "unavailable", "model_unavailable")
                        ) or any(
                            problems(v)
                            for v in value.values()
                            if isinstance(v, (dict, list))
                        )
                    return isinstance(value, list) and any(problems(v) for v in value)

                partial = problems(result)
                self._update(
                    run_id,
                    "attention" if partial else "completed",
                    "Run finished with items that need your attention"
                    if partial
                    else "Run completed",
                    result,
                )
        except asyncio.CancelledError:
            self._update(
                run_id,
                "cancelled",
                "Stopped. Inspect any applying jobs before retrying.",
            )
        except Exception as exc:
            self._update(
                run_id,
                "failed",
                f"Run could not finish ({type(exc).__name__}). Check connections and configuration.",
            )
        finally:
            if self.loop:
                self.loop.run_until_complete(self.loop.shutdown_asyncgens())
                self.loop.close()
            self.loop = self.task = None

    async def _perform(self, action, platform, options):
        from ..browser import reuse_browser

        async with reuse_browser():
            return await self._perform_connected(action, platform, options)

    async def _perform_connected(self, action, platform, options):
        from ..pipeline import run_pipeline, scrape_platforms, apply_platforms
        from ..registry import platform_names
        from .connections import check_platform, check_gemini, browser_login

        if action == "login":
            return await browser_login(platform, self.login_done)
        if action == "check":
            emit("connect", "Checking AI key and model availability", platform="gemini")
            rows = [await check_gemini()]
            emit(
                "connect",
                rows[0]["message"],
                platform="gemini",
                state="completed"
                if rows[0]["status"] in ("connected", "not_configured")
                else "attention",
            )
            for name in platform_names(platform):
                emit("connect", "Checking the shared Chrome session", platform=name)
                rows.append(await check_platform(name))
                emit(
                    "connect",
                    rows[-1]["message"],
                    platform=name,
                    state="completed"
                    if rows[-1]["status"] == "connected"
                    else "attention",
                )
            return rows
        if action == "match":
            from ..ai.matcher import JobMatcher

            emit("match", "Scoring unscored opportunities")
            scored = await JobMatcher().score_jobs()
            emit(
                "match",
                "Matching finished",
                state="completed",
                metrics={"scored": scored},
            )
            return {"scored": scored}
        if action == "scrape":
            return await scrape_platforms(platform)
        if action == "apply":
            return await apply_platforms(
                platform, dry_run=options["dry_run"], limit=options["limit"]
            )
        return await run_pipeline(
            platform, dry_run=options["dry_run"], apply_limit=options["limit"]
        )

    def cancel(self):
        if self.loop and self.task:
            self.loop.call_soon_threadsafe(self.task.cancel)
            return True
        return False
