"""Private web application API. Secrets are write-only from browser clients."""

from copy import deepcopy
import json
import threading
from functools import wraps
import yaml
from flask import Blueprint, current_app, jsonify, request, Response
from ..config import settings, Settings, CONFIG_DIR, DATA_DIR
from ..registry import PLATFORMS, platform_names
from ..vault import Vault
from .analytics import overview, applications, csv_export
from .connections import connection_status
from .runner import Runner


def write_profile(data):
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    temporary = CONFIG_DIR / "profile.tmp"
    temporary.write_text(
        yaml.safe_dump(data, sort_keys=False, allow_unicode=True), encoding="utf-8"
    )
    temporary.replace(CONFIG_DIR / "profile.yaml")
    settings._profile = data


def merge_resume_insights(profile, insights):
    from ..resume_insights import unique

    prefs = profile.setdefault("preferences", {})
    for key in ("skills", "search_keywords"):
        prefs[key] = unique(prefs.get(key, []) + insights[key])
    return prefs


def web_blueprint(database):
    api = Blueprint("web_api", __name__)
    runner = Runner(database)
    configuration_lock = threading.RLock()

    @api.get("/api/browser")
    def browser_state():
        from ..workspace_browser import status, COOKIE

        return jsonify(status(request.cookies.get(COOKIE)))

    @api.get("/api/runs/<run_id>/events")
    def run_events(run_id):
        return Response(
            json.dumps(runner.events(run_id), indent=2),
            mimetype="application/json",
            headers={
                "Content-Disposition": 'attachment; filename="jobpilot-run-events.json"'
            },
        )

    @api.post("/api/browser/open")
    def browser_open():
        import asyncio
        from ..workspace_browser import open_workspace

        try:
            asyncio.run(open_workspace())
        except Exception:
            return jsonify(
                error="Could not open regular Chrome. Check that Google Chrome is installed, then try again."
            ), 503
        return jsonify(opened=True)

    @api.post("/api/browser/open-platform")
    def browser_open_platform():
        from ..workspace_browser import open_platform

        name = request.get_json().get("platform")
        if not isinstance(name, str):
            raise ValueError("Choose an enabled platform")
        open_platform(name)
        return jsonify(opened=True)

    @api.post("/api/browser/setup")
    def browser_setup():
        from ..workspace_browser import open_regular, SETUP_URL

        open_regular(SETUP_URL)
        return jsonify(opened=True)

    def configuration_edit(function):
        @wraps(function)
        def guarded(*args, **kwargs):
            with configuration_lock:
                if any(run["state"] in ("queued", "running") for run in runner.list()):
                    raise ValueError(
                        "Stop the active run before changing your profile or credentials"
                    )
                return function(*args, **kwargs)

        return guarded

    @api.post("/api/browser/connect")
    @configuration_edit
    def browser_connect():
        import asyncio
        from ..workspace_browser import verify_browser

        return jsonify(asyncio.run(verify_browser()))

    @api.post("/api/browser/preferences")
    @configuration_edit
    def browser_preferences():
        import asyncio
        from ..sessions import manage_sessions

        value = request.get_json().get("remember")
        if type(value) is not bool:
            raise ValueError("Choose whether to remember platform sessions")
        return jsonify(asyncio.run(manage_sessions(remember=value)))

    @api.post("/api/browser/sign-out")
    @configuration_edit
    def sign_out():
        import asyncio
        from ..sessions import manage_sessions

        name = request.get_json().get("platform")
        if not isinstance(name, str) or name not in (*PLATFORMS, "all"):
            raise ValueError("Choose a known platform")
        asyncio.run(manage_sessions(platform=name))
        return jsonify(signed_out=True)

    @api.post("/api/jobs/<int:job_id>/recover")
    def recover(job_id):
        from filelock import FileLock

        job = database.get_job(job_id)
        if not job or job.status != "applying":
            raise ValueError("Only an interrupted applying job can be recovered")
        with FileLock(str(DATA_DIR / f"{job.platform}.browser.lock")).acquire(
            timeout=0
        ):
            database.finish_application(
                job_id,
                "review",
                "Recovered interrupted run. Verify on the platform before any retry.",
            )
        return jsonify(recovered=True)

    def timezone_name():
        import pytz

        value = settings.get_env("JOBPILOT_TIMEZONE", "Asia/Kolkata")
        return value if value in pytz.all_timezones_set else "Asia/Kolkata"

    @api.get("/api/bootstrap")
    def bootstrap():
        personal = settings.profile.get("personal", {})
        return jsonify(
            token=current_app.config["JOBPILOT_TOKEN"],
            user={
                "name": personal.get("full_name", "Your workspace"),
                "location": personal.get("location", ""),
            },
            timezone=timezone_name(),
            version="0.3.0",
        )

    @api.get("/api/overview")
    def summary():
        try:
            days = int(request.args.get("days", 14))
        except ValueError:
            raise ValueError("Invalid chart period")
        if days not in (7, 14, 30, 90):
            raise ValueError("Choose 7, 14, 30 or 90 days")
        return jsonify(overview(database, days, timezone_name()))

    def filtered_applications():
        platform = request.args.get("platform")
        if platform and platform not in PLATFORMS:
            raise ValueError("Unknown platform")
        return applications(
            database,
            platform=platform,
            search=request.args.get("search", ""),
            start=request.args.get("from"),
            end=request.args.get("to"),
            tz=timezone_name(),
        )

    @api.get("/api/applications")
    def application_list():
        rows = filtered_applications()
        page = max(1, int(request.args.get("page", 1)))
        return jsonify(
            applications=rows[(page - 1) * 20 : page * 20],
            total=len(rows),
            page=page,
            page_size=20,
        )

    @api.get("/api/applications/export")
    def export():
        return Response(
            csv_export(filtered_applications()),
            mimetype="text/csv",
            headers={
                "Content-Disposition": 'attachment; filename="jobpilot-applications.csv"'
            },
        )

    @api.get("/api/connections")
    def connections():
        saved = DATA_DIR / "connections/gemini.json"
        ai = (
            json.loads(saved.read_text(encoding="utf-8"))
            if saved.exists()
            else {"status": "not_checked"}
        )
        return jsonify(
            platforms=connection_status(),
            ai=ai
            | {
                "key_saved": bool(settings.gemini_api_key),
                "model": settings.gemini_model,
            },
        )

    @api.post("/api/credentials")
    @configuration_edit
    def credentials():
        data = request.get_json()
        name = data.get("platform")
        if not isinstance(name, str) or (name not in PLATFORMS and name != "gemini"):
            raise ValueError("Unknown credential provider")
        updates = {}
        for field in ("api_key",) if name == "gemini" else ("email", "password"):
            value = data.get(field)
            if value is not None:
                if not isinstance(value, str):
                    raise ValueError("Credential values must be strings")
                # Empty password fields preserve existing secrets; deletion is explicit.
                if value:
                    updates[
                        "GEMINI_API_KEY"
                        if name == "gemini"
                        else f"{name.upper()}_{field.upper()}"
                    ] = value
        if not updates:
            raise ValueError("Enter at least one new credential value")
        Vault(DATA_DIR / "credentials.dpapi").update(updates)
        return jsonify(saved=True)

    @api.get("/api/profile")
    def profile():
        data = deepcopy(settings.profile)
        # The user is editing their own profile. Credentials are never included.
        return jsonify(
            profile=data,
            resume_present=settings.resume_path.is_file(),
            resume_name=settings.resume_path.name,
        )

    @api.post("/api/profile")
    @configuration_edit
    def save_profile():
        data = request.get_json().get("profile")
        if not isinstance(data, dict) or set(data) - {
            "personal",
            "preferences",
            "application_defaults",
            "resume",
        }:
            raise ValueError("Invalid profile sections")
        new = deepcopy(settings.profile)
        for section, values in data.items():
            if not isinstance(values, dict):
                raise ValueError("Profile sections must be objects")
            if section == "resume":
                values = {
                    key: value for key, value in values.items() if key == "summary"
                }
            new.setdefault(section, {}).update(values)
        candidate = Settings()
        candidate._profile = new
        candidate._platforms = settings.platforms
        errors = candidate.validate()
        if errors:
            raise ValueError("; ".join(errors))
        write_profile(new)
        return jsonify(saved=True)

    @api.post("/api/resume")
    @configuration_edit
    def resume_upload():
        upload = request.files.get("resume")
        if not upload:
            raise ValueError("Choose a PDF resume")
        payload = upload.read(5 * 1024 * 1024 + 1)
        if len(payload) > 5 * 1024 * 1024 or not payload.startswith(b"%PDF-"):
            raise ValueError("Resume must be a PDF up to 5 MB")
        from ..resume_insights import inspect_pdf

        insights = inspect_pdf(payload)
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        path = CONFIG_DIR / "resume.pdf"
        path.with_suffix(".tmp").write_bytes(payload)
        path.with_suffix(".tmp").replace(path)
        new = deepcopy(settings.profile)
        new.setdefault("resume", {})["path"] = "config/resume.pdf"
        prefs = merge_resume_insights(new, insights)
        write_profile(new)
        return jsonify(
            saved=True, name="resume.pdf", insights=insights, preferences=prefs
        )

    @api.post("/api/resume/extract")
    @configuration_edit
    def resume_extract():
        from ..resume_insights import inspect_pdf

        if not settings.resume_path.is_file():
            raise ValueError("Upload a resume first")
        with settings.resume_path.open("rb") as resume:
            insights = inspect_pdf(resume.read(5 * 1024 * 1024 + 1))
        new = deepcopy(settings.profile)
        prefs = merge_resume_insights(new, insights)
        write_profile(new)
        return jsonify(saved=True, insights=insights, preferences=prefs)

    @api.get("/api/runs")
    def runs():
        return jsonify(runs=runner.list())

    @api.post("/api/runs")
    def start_run():
        data = request.get_json()
        action, platform = data.get("action", "pipeline"), data.get("platform", "all")
        if action not in ("pipeline", "scrape", "match", "apply", "check", "login"):
            raise ValueError("Unknown operation")
        if not isinstance(platform, str) or not platform_names(platform):
            raise ValueError("Choose an enabled platform")
        if action == "login" and platform == "all":
            raise ValueError("Choose one platform to sign in")
        dry_run, limit = data.get("dry_run", True), data.get("limit", 5)
        if type(dry_run) is not bool or type(limit) is not int or not 1 <= limit <= 100:
            raise ValueError("Invalid dry_run or limit setting")
        if (
            action in ("apply", "pipeline")
            and not dry_run
            and data.get("confirm_live") is not True
        ):
            raise ValueError("Confirm live application submission first")
        if action in ("apply", "pipeline"):
            errors = settings.validate(for_apply=not dry_run)
            if errors:
                raise ValueError("; ".join(errors))
        with configuration_lock:
            run_id = runner.start(
                action, platform, {"dry_run": dry_run, "limit": limit}
            )
        return jsonify(id=run_id), 202

    @api.post("/api/runs/cancel")
    def cancel():
        return jsonify(cancelled=runner.cancel())

    @api.post("/api/runs/verify-login")
    def verify_login():
        runner.login_done.set()
        return jsonify(requested=True)

    return api
