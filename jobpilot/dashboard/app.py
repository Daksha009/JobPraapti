"""Local dashboard with validated inputs and same-origin mutation protection."""

import asyncio
import secrets
from urllib.parse import urlparse
from flask import Flask, jsonify, render_template, request, send_from_directory
from pathlib import Path
from filelock import FileLock, Timeout
from ..config import DATA_DIR, settings
from ..database import db
from ..registry import PLATFORMS, platform_names
from ..models import JobStatus


def create_app(database=None):
    database = database or db
    app = Flask(__name__)
    app.config.update(
        MAX_CONTENT_LENGTH=6 * 1024 * 1024, JOBPILOT_TOKEN=secrets.token_urlsafe(32)
    )
    from .web_api import web_blueprint

    app.register_blueprint(web_blueprint(database))

    @app.before_request
    def protect_local_api():
        if urlparse(request.host_url).hostname not in ("127.0.0.1", "localhost", "::1"):
            return jsonify(error="Dashboard is localhost-only"), 403
        if request.method == "POST":
            origin = request.headers.get("Origin")
            if origin and origin.rstrip("/") != request.host_url.rstrip("/"):
                return jsonify(error="Cross-origin requests are not allowed"), 403
            if not secrets.compare_digest(
                request.headers.get("X-JobPilot-Token", ""),
                app.config["JOBPILOT_TOKEN"],
            ):
                return jsonify(
                    error="Reload the dashboard to refresh its request token"
                ), 403
            if request.path == "/api/resume":
                return None
            if request.content_length and request.content_length > 65536:
                return jsonify(error="Request is too large"), 413
            if not request.is_json or not isinstance(
                request.get_json(silent=True), dict
            ):
                return jsonify(error="A JSON object is required"), 400

    @app.errorhandler(ValueError)
    def invalid_input(exc):
        return jsonify(error=str(exc)), 400

    @app.errorhandler(Timeout)
    def busy(exc):
        return jsonify(
            error="An operation is already running; wait for it to finish"
        ), 409

    @app.errorhandler(RuntimeError)
    def runtime_error(exc):
        return jsonify(
            error="The local service could not access its resources. Start JobPilot using the Windows account that saved your credentials."
        ), 503

    def validate_platform(selection):
        if not isinstance(selection, str):
            raise ValueError("platform must be a string")
        if not platform_names(selection):
            raise ValueError("No selected platforms are enabled")
        return selection

    def number(value, low, high, integer=False):
        if isinstance(value, bool) or not isinstance(value, (str, float, int)):
            raise ValueError("Invalid numeric input")
        parsed = float(value)
        if not low <= parsed <= high or (integer and not parsed.is_integer()):
            raise ValueError(f"Value must be between {low} and {high}")
        return int(parsed) if integer else parsed

    def operation(awaitable):
        try:
            with FileLock(str(DATA_DIR / "dashboard-operation.lock")).acquire(
                timeout=0
            ):
                return asyncio.run(awaitable)
        except BaseException:
            awaitable.close()
            raise

    @app.route("/")
    def index():
        web = Path(__file__).parent / "web"
        if (web / "index.html").exists():
            return send_from_directory(web, "index.html")
        return legacy()

    @app.get("/web/<path:filename>")
    def web_assets(filename):
        return send_from_directory(Path(__file__).parent / "web", filename)

    @app.after_request
    def response_security(response):
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; font-src 'self'; connect-src 'self'; frame-ancestors 'none'; base-uri 'self'; form-action 'self'"
        )
        if request.path == "/legacy":
            # Compatibility UI has static inline event handlers. The React
            # workspace retains the stricter script policy above.
            response.headers["Content-Security-Policy"] = response.headers[
                "Content-Security-Policy"
            ].replace("script-src 'self';", "script-src 'self' 'unsafe-inline';")
        if request.path.startswith("/api/") or request.path in ("/", "/legacy"):
            response.headers["Cache-Control"] = "no-store"
        return response

    @app.route("/legacy")
    def legacy():
        return render_template(
            "index.html",
            request_token=app.config["JOBPILOT_TOKEN"],
            platforms=PLATFORMS,
        )

    @app.route("/api/platforms")
    def platforms():
        return jsonify(platforms=list(PLATFORMS), enabled=platform_names())

    @app.route("/api/jobs")
    def jobs():
        status = request.args.get("status")
        platform = request.args.get("platform")
        if status not in (None, "", "all") and status not in {
            s.value for s in JobStatus
        }:
            raise ValueError("Invalid status")
        if platform not in (None, "all") and platform not in PLATFORMS:
            raise ValueError("Unknown platform")
        rows = database.get_jobs(
            status=None if status == "all" else status,
            platform=None if platform == "all" else platform,
            min_score=number(request.args["min_score"], 0, 100)
            if "min_score" in request.args
            else None,
            limit=number(request.args.get("limit", 100), 1, 1000, True),
            offset=number(request.args.get("offset", 0), 0, 1000000, True),
            search=request.args.get("search", "").strip(),
        )
        return jsonify(
            jobs=[job.to_dict() | {"id": job.id} for job in rows],
            count=len(rows),
            total=database.count_jobs(
                status=None if status == "all" else status,
                platform=None if platform == "all" else platform,
                min_score=number(request.args["min_score"], 0, 100)
                if "min_score" in request.args
                else None,
                search=request.args.get("search", "").strip(),
            ),
        )

    @app.route("/api/jobs/<int:job_id>")
    def detail(job_id):
        job = database.get_job(job_id)
        if not job:
            return jsonify(error="Job not found"), 404
        return jsonify(
            job.to_dict()
            | {
                "id": job.id,
                "application_history": database.get_application_history(job_id),
            }
        )

    @app.route("/api/jobs/<int:job_id>/status", methods=["POST"])
    def status(job_id):
        status = request.get_json().get("status")
        if not database.manual_status(job_id, status):
            return jsonify(error="Job not found"), 404
        return jsonify(success=True, status=status)

    @app.route("/api/stats")
    def stats():
        return jsonify(database.get_stats())

    @app.route("/api/history")
    def history():
        limit = number(request.args.get("limit", 20), 1, 1000, True)
        return jsonify(history=database.get_scrape_history(limit=limit))

    @app.route("/api/scrape", methods=["POST"])
    def scrape():
        from ..pipeline import scrape_platforms

        platform = validate_platform(request.get_json().get("platform", "all"))
        return jsonify(results=operation(scrape_platforms(platform)))

    @app.route("/api/match", methods=["POST"])
    def match():
        from ..ai.matcher import JobMatcher

        return jsonify(scored=operation(JobMatcher().score_jobs()))

    @app.route("/api/jobs/<int:job_id>/cover-letter", methods=["POST"])
    def cover_letter(job_id):
        from ..ai.matcher import CoverLetterGenerator

        job = database.get_job(job_id)
        if not job:
            return jsonify(error="Job not found"), 404
        if not settings.gemini_api_key:
            raise ValueError("Set GEMINI_API_KEY to generate cover letters")
        return jsonify(cover_letter=operation(CoverLetterGenerator().generate(job)))

    @app.route("/api/apply", methods=["POST"])
    def apply():
        from ..pipeline import apply_platforms

        data = request.get_json()
        platform = validate_platform(data.get("platform", "all"))
        dry_run = data.get("dry_run", True)
        if type(dry_run) is not bool:
            raise ValueError("dry_run must be a JSON boolean")
        limit = number(data.get("limit", 20), 1, 1000, True)
        min_score = number(data.get("min_score", settings.min_match_score), 0, 100)
        return jsonify(
            results=operation(
                apply_platforms(
                    platform, dry_run=dry_run, limit=limit, min_score=min_score
                )
            )
        )

    return app
