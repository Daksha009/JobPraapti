"""Shared application lifecycle. Platform adapters only describe their UI."""

import asyncio
import logging
from dataclasses import dataclass
from urllib.parse import urlparse

from ..browser import BrowserSession
from ..config import DATA_DIR, settings
from ..database import db
from ..progress import emit
from .forms import fill_form

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ApplicationResult:
    status: str
    message: str


class BaseApplier:
    platform_name = ""
    HOME_URL = ""
    LOGIN_URL = ""
    AUTH_URL = ""
    allowed_domains: tuple[str, ...] = ()
    auth_selectors: tuple[str, ...] = ()
    apply_selectors = ('button:text-is("Apply now")', 'button:text-is("Apply")')
    form_selectors = (
        '[role="dialog"]',
        ".modal__wrapper",
        'form:has(input[type="file"])',
    )
    next_selectors = (
        'button:text-is("Next")',
        'button:text-is("Continue")',
        'button:text-is("Review")',
    )
    submit_selectors = (
        'button:text-is("Submit application")',
        'button:text-is("Submit Application")',
        'button:text-is("Send Application")',
        'button:text-is("Submit")',
        'button:text-is("Send")',
        'button:text-is("Apply")',
    )
    success_selectors = (
        "text=/^(Your application was sent|Your application has been sent|Application submitted successfully|Application sent successfully|Successfully applied|Applied successfully|Thank you for applying)[.!]?$/i",
    )
    already_selectors = (
        'button:text-is("Applied")',
        "text=/^You have already applied[.!]?$/i",
    )
    # Cutshort uses a second same-site portal entry before the form.
    portal_path = ""

    def __init__(
        self,
        dry_run=True,
        daily_limit=20,
        min_score=None,
        min_experience=None,
        max_experience=None,
        database=None,
    ):
        if type(daily_limit) is not int or daily_limit < 1:
            raise ValueError("daily_limit must be a positive integer")
        self.config = settings.platforms.get("platforms", {}).get(
            self.platform_name, {}
        )
        for key in (
            "auth_selectors",
            "apply_selectors",
            "form_selectors",
            "next_selectors",
            "submit_selectors",
            "success_selectors",
            "already_selectors",
        ):
            override = self.config.get("application", {}).get(key)
            if override is not None:
                if (
                    not isinstance(override, list)
                    or not override
                    or not all(isinstance(item, str) for item in override)
                ):
                    raise ValueError(
                        f"application.{key} must be a non-empty list of selectors"
                    )
                setattr(self, key, tuple(override))
        self.dry_run = dry_run
        self.daily_limit = min(daily_limit, self.config.get("daily_limit", 20))
        self.min_score = settings.min_match_score if min_score is None else min_score
        self.min_experience = (
            settings.min_experience_years if min_experience is None else min_experience
        )
        self.max_experience = (
            settings.max_experience_years if max_experience is None else max_experience
        )
        if (
            not 0 <= self.min_score <= 100
            or not 0 <= self.min_experience <= self.max_experience
        ):
            raise ValueError("Invalid score or experience range")
        self.db = database or db
        self.session = BrowserSession(self.platform_name)
        self.page = self.context = None

    async def start_browser(self, headless=True):
        await self.session.start(headless)
        self.page, self.context = self.session.page, self.session.context

    async def stop_browser(self):
        await self.session.close()

    def allowed_url(self, url):
        parsed = urlparse(url)
        return (
            parsed.scheme == "https"
            and not parsed.username
            and parsed.port in (None, 443)
            and any(
                parsed.hostname == domain
                or (parsed.hostname or "").endswith("." + domain)
                for domain in self.allowed_domains
            )
        )

    async def visible(self, selectors, scope=None):
        scope = scope if scope is not None else self.page
        for selector in selectors:
            for item in await scope.locator(selector).all():
                if await item.is_visible():
                    return item
        return None

    async def settle(self):
        await asyncio.sleep(self.config.get("delay_seconds", 2))

    async def is_logged_in(self):
        await self.page.goto(
            self.AUTH_URL or self.HOME_URL, wait_until="domcontentloaded"
        )
        return await self.wait_for_authenticated_navigation()

    async def wait_for_authenticated_navigation(self):
        """Wait for client-rendered member controls; a jobs URL alone is not proof."""
        deadline = asyncio.get_running_loop().time() + 10
        while True:
            path = urlparse(self.page.url).path
            if not self.allowed_url(self.page.url) or path.startswith(
                ("/login", "/uas/", "/checkpoint/", "/authwall", "/profile/login")
            ):
                return False
            if await self.visible(self.auth_selectors) is not None:
                return True
            if asyncio.get_running_loop().time() >= deadline:
                return False
            await asyncio.sleep(0.25)

    async def _prefill_login(self):
        email, password = settings.credentials(self.platform_name)
        if not self.allowed_url(self.page.url):
            return
        email_input = await self.visible(
            ('input[type="email"]', "#username", 'input[name="email"]')
        )
        if email_input is not None and email:
            await email_input.fill(email)
        password_input = await self.visible(('input[type="password"]',))
        if password_input is not None and password:
            await password_input.fill(password)

    async def interactive_login(self):
        from ..workspace_browser import open_platform

        try:
            open_platform(self.platform_name)
            await asyncio.to_thread(
                input, "Sign in in regular Chrome, then press Enter here to verify: "
            )
            await self.start_browser(headless=False)
            authenticated = await self.is_logged_in()
            if authenticated:
                from ..sessions import mark_signed_out

                mark_signed_out(self.platform_name, False)
            return authenticated
        finally:
            await self.stop_browser()

    async def authenticate(self):
        from ..sessions import preferences

        if self.platform_name in preferences()["signed_out"]:
            return False
        # Authentication belongs to the user's normal Chrome session. Workers
        # must never repeatedly submit passwords after expiry or a security check.
        return await self.is_logged_in()

    async def blocked(self):
        if not self.allowed_url(self.page.url):
            return "External application site: complete this listing manually"
        if any(
            part in urlparse(self.page.url).path.lower()
            for part in ("checkpoint", "challenge", "login", "signin")
        ):
            return "Login or verification required; run the login command"
        challenge = await self.visible(
            (
                'iframe[src*="recaptcha"]',
                'iframe[src*="hcaptcha"]',
                'input[autocomplete="one-time-code"]',
                "#challenge-running",
            )
        )
        return (
            "Complete the site verification manually" if challenge is not None else ""
        )

    async def apply_to_job(self, job):
        if not self.allowed_url(job.url):
            return ApplicationResult(
                "review", "Job URL is outside the platform's allowed domains"
            )
        await self.page.goto(job.url, wait_until="domcontentloaded")
        await self.settle()
        reason = await self.blocked()
        if reason:
            return ApplicationResult("review", reason)
        if await self.visible(self.already_selectors) is not None:
            return ApplicationResult(
                "already_applied", "Site confirms this application already exists"
            )
        if await self.visible(self.success_selectors) is not None:
            return ApplicationResult(
                "review",
                "Confirmation was already present before applying; verify this listing manually",
            )
        if (
            await self.visible(
                ("text=/^This job is no longer accepting applications[.!]?$/i",)
            )
            is not None
        ):
            return ApplicationResult("expired", "Job no longer accepting applications")
        entry = await self.visible(self.apply_selectors)
        if entry is None:
            return ApplicationResult(
                "review",
                "Apply control not found; inspect the listing or adapter selectors",
            )
        href = await entry.get_attribute("href")
        if href:
            from urllib.parse import urljoin

            if not self.allowed_url(urljoin(self.page.url, href)):
                return ApplicationResult(
                    "review", "External application link requires manual completion"
                )
        if self.dry_run:
            return ApplicationResult(
                "dry_run",
                "Apply control found; no clicks, uploads or submission performed",
            )
        # The first click can itself submit a one-click application. Never retry a click.
        await entry.click()
        await self.settle()
        portal_entered = False
        for _ in range(8):
            if any(
                [
                    await tab.opener() == self.page
                    for tab in self.context.pages
                    if tab != self.page
                ]
            ):
                return ApplicationResult(
                    "review", "Application opened another tab; inspect it manually"
                )
            reason = await self.blocked()
            if reason:
                return ApplicationResult("review", reason)
            if await self.visible(self.success_selectors) is not None:
                return ApplicationResult(
                    "applied", "Site displayed an explicit application confirmation"
                )
            scope = await self.visible(self.form_selectors)
            if scope is None:
                if (
                    self.portal_path
                    and self.portal_path in self.page.url
                    and not portal_entered
                ):
                    portal_entry = await self.visible(self.apply_selectors)
                    if portal_entry is not None:
                        portal_entered = True
                        await portal_entry.click()
                        await self.settle()
                        continue
                return ApplicationResult(
                    "review",
                    "No confirmation or supported application form; verify manually before retrying",
                )
            unanswered = await fill_form(scope, settings.profile, settings.resume_path)
            if unanswered:
                return ApplicationResult(
                    "review",
                    "Add exact answers to application_defaults.answers: "
                    + "; ".join(unanswered),
                )
            validation = await self.visible(
                ('[aria-invalid="true"]', '[role="alert"]'), scope
            )
            if validation is not None:
                return ApplicationResult("review", "Form validation requires review")
            submit = await self.visible(self.submit_selectors, scope)
            if submit is not None:
                await submit.click()
                # Confirmation can be asynchronous. Wait for evidence, never submit twice.
                try:
                    await self.page.locator(
                        ", ".join(self.success_selectors)
                    ).first.wait_for(state="visible", timeout=10000)
                except Exception:
                    pass
                if await self.visible(self.success_selectors) is not None:
                    return ApplicationResult(
                        "applied", "Site displayed an explicit application confirmation"
                    )
                return ApplicationResult(
                    "review",
                    "Submit clicked, but confirmation was not observed; verify before retrying",
                )
            next_button = await self.visible(self.next_selectors, scope)
            if next_button is None:
                return ApplicationResult("review", "No supported next/submit control")
            await next_button.click()
            await self.settle()
        return ApplicationResult(
            "review", "Application exceeded eight steps; inspect manually"
        )

    def _get_jobs_to_apply(self):
        return self.select_candidates()[0]

    def select_candidates(self):
        """Return candidates and mutually exclusive filter counts for the dashboard."""
        jobs = []
        summary = {
            "considered": 0, "below_score": 0, "experience_mismatch": 0,
            "excluded_title": 0, "eligible": 0, "selected": 0,
            "min_score": self.min_score,
        }
        for status in ("matched", "shortlisted"):
            offset = 0
            while True:
                batch = self.db.get_jobs(
                    platform=self.platform_name,
                    status=status,
                    limit=200,
                    offset=offset,
                )
                for job in batch:
                    summary["considered"] += 1
                    if job.match_score < self.min_score:
                        summary["below_score"] += 1
                    elif not job.is_experience_eligible(self.min_experience, self.max_experience)[0]:
                        summary["experience_mismatch"] += 1
                    elif any(
                        keyword.lower() in job.title.lower()
                        for keyword in settings.exclude_keywords
                    ):
                        summary["excluded_title"] += 1
                    else:
                        jobs.append(job)
                if len(batch) < 200:
                    break
                offset += 200
        summary["eligible"] = len(jobs)
        selected = sorted(jobs, key=lambda job: (-job.match_score, job.id))[
            : self.daily_limit
        ]
        summary["selected"] = len(selected)
        return selected, summary

    async def run(self, headless=True):
        results = {
            "platform": self.platform_name,
            "applied": 0,
            "failed": 0,
            "review": 0,
            "dry_run": 0,
            "already_applied": 0,
            "expired": 0,
            "processed": 0,
            "skipped": 0,
            "jobs": [],
        }
        if not self.config.get("enabled", False):
            results["error"] = "Platform disabled in config/platforms.yaml"
            return results
        errors = settings.validate(for_apply=not self.dry_run)
        if errors:
            results["error"] = "; ".join(errors)
            return results
        jobs, results["eligibility"] = self.select_candidates()
        results["selected"] = len(jobs)
        emit(
            "apply",
            f"{len(jobs)} eligible candidates",
            platform=self.platform_name,
            current=0,
            total=len(jobs),
        )
        if not jobs:
            selection = results["eligibility"]
            results["message"] = (
                "No scored or shortlisted jobs yet. Discover and match jobs first."
                if not selection["considered"]
                else f"No eligible jobs: {selection['below_score']} below score {self.min_score:g}, "
                f"{selection['experience_mismatch']} outside your experience range, "
                f"{selection['excluded_title']} excluded by title."
            )
            return results
        try:
            await self.start_browser(headless)
            emit("apply", "Verifying your Chrome session", platform=self.platform_name)
            if not await self.authenticate():
                results["error"] = (
                    f"Sign-in could not be verified for {self.platform_name}. "
                    "Open Platforms, sign in in regular Chrome, then select Verify sign-in."
                )
                results["blocker"] = "authentication"
                return results
            for index, job in enumerate(jobs, 1):
                emit(
                    "apply",
                    f"Checking {job.title} · {job.company}",
                    platform=self.platform_name,
                    current=index - 1,
                    total=len(jobs),
                )
                if not self.dry_run and not self.db.claim_application(
                    job.id, self.daily_limit
                ):
                    results["skipped"] += 1
                    results["processed"] = index
                    emit(
                        "apply",
                        "Skipped: daily limit or existing application claim",
                        platform=self.platform_name,
                        current=index,
                        total=len(jobs),
                    )
                    continue
                try:
                    outcome = await self.apply_to_job(job)
                except Exception as exc:
                    # Any exception may occur after a remote side effect; avoid automatic retry.
                    logger.warning(
                        "Application %s interrupted (%s)", job.id, type(exc).__name__
                    )
                    outcome = ApplicationResult(
                        "review",
                        f"Browser step failed ({type(exc).__name__}); inspect application before retrying",
                    )
                if not self.dry_run:
                    if (
                        outcome.status == "review"
                        and self.page is not None
                        and settings.platforms.get("scraping", {}).get(
                            "screenshot_on_error", True
                        )
                    ):
                        evidence = (
                            DATA_DIR / "review" / f"{self.platform_name}-{job.id}.png"
                        )
                        evidence.parent.mkdir(parents=True, exist_ok=True)
                        try:
                            await self.page.screenshot(
                                path=str(evidence), full_page=True
                            )
                            outcome = ApplicationResult(
                                outcome.status,
                                outcome.message + f"; Screenshot: {evidence}",
                            )
                        except Exception:
                            pass
                    status = (
                        "applied"
                        if outcome.status == "already_applied"
                        else outcome.status
                    )
                    self.db.finish_application(job.id, status, outcome.message)
                results[outcome.status] += 1
                results["processed"] = index
                emit(
                    "apply",
                    f"{job.title} · {outcome.status.replace('_', ' ')}: {outcome.message.split('; Screenshot:')[0]}",
                    platform=self.platform_name,
                    current=index,
                    total=len(jobs),
                    metrics={
                        key: results[key]
                        for key in (
                            "applied",
                            "dry_run",
                            "review",
                            "failed",
                            "expired",
                            "already_applied",
                        )
                    },
                )
                results["jobs"].append(
                    {
                        "id": job.id,
                        "title": job.title,
                        "company": job.company,
                        "status": outcome.status,
                        "message": outcome.message,
                        "success": outcome.status == "applied",
                        "url": job.url,
                    }
                )
        except Exception as exc:
            results["error"] = (
                f"{type(exc).__name__}: could not complete {self.platform_name}; check browser installation and session"
            )
            logger.warning("Platform run failed (%s)", type(exc).__name__)
        finally:
            await self.stop_browser()
        return results
