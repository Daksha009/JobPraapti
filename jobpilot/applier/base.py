"""Shared application lifecycle. Platform adapters only describe their UI."""

import asyncio
import logging
import re
from dataclasses import dataclass
from urllib.parse import urlparse

from ..browser import BrowserConnectionError, BrowserSession
from ..config import DATA_DIR, settings
from ..database import db
from ..progress import emit
from .forms import fill_form, validation_errors

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ApplicationResult:
    status: str
    message: str
    continue_queue: bool = False


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
        "dialog[open]",
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
        'button:text-is("Send application")',
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
    expired_selectors = ("text=/^This job is no longer accepting applications[.!]?$/i",)
    # Cutshort uses a second same-site portal entry before the form.
    portal_path = ""
    interstitial_selectors: tuple[str, ...] = ()
    handoff_domains: tuple[str, ...] = ()
    handoff_form_selectors: tuple[str, ...] = ()
    description_selectors: tuple[str, ...] = ()
    external_apply_selectors: tuple[str, ...] = ()
    handled_form_selectors: tuple[str, ...] = ()
    confirmation_timeout_ms = 30000
    application_surface_timeout_ms = 10000

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
            "expired_selectors",
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
        self.daily_quota = self.config.get("daily_limit", 20)
        if type(self.daily_quota) is not int or self.daily_quota < 1:
            raise ValueError("Platform daily_limit must be a positive integer")
        # The legacy argument is the maximum attempts for this run. It must not
        # replace the platform's persistent daily quota when reserving a job.
        self.daily_limit = min(daily_limit, self.daily_quota)
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
        self._active_handoff = False
        self.composer = None

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
                + (self.handoff_domains if self._active_handoff else ())
            )
        )

    async def visible(self, selectors, scope=None):
        scope = scope if scope is not None else self.page
        for selector in selectors:
            # :text-is matches the smallest text element. A button containing
            # nested spans (current LinkedIn SDUI) needs an accessible-name lookup.
            exact = re.fullmatch(r'(button|a):text-is\("([^"\n]+)"\)', selector)
            locator = (
                scope.get_by_role(
                    "button" if exact[1] == "button" else "link",
                    name=exact[2],
                    exact=True,
                )
                if exact
                else scope.locator(selector)
            )
            for item in await locator.all():
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
                'iframe[src*="recaptcha"]:not([src*="/anchor?"][src*="size=invisible"])',
                'iframe[src*="hcaptcha"]',
                'input[autocomplete="one-time-code"]',
                "#challenge-running",
            )
        )
        return (
            "Complete the site verification manually" if challenge is not None else ""
        )

    async def advance_interstitial(self):
        """Adapters may advance a recognized informational step before the form."""
        return False

    def application_url(self, job):
        return job.url

    async def prepare_application_entry(self):
        """Optional platform-specific readiness before the first application click."""

    async def portal_entry(self, job):
        """Find a second same-site application control, if the adapter supports it."""
        return await self.visible(self.apply_selectors)

    async def prepare_form(self, scope):
        """Adapters may handle a specific resume-upload widget before generic fields."""
        return ""

    async def post_submit(self):
        """Return an outcome for a recognized post-submit handoff, if any."""
        return None

    async def form_scope(self):
        selectors = (
            self.handoff_form_selectors if self._active_handoff else self.form_selectors
        )
        return await self.visible(selectors)

    async def follow_handoff(self):
        tabs = [
            p
            for p in self.context.pages
            if p != self.page and await p.opener() == self.page
        ]
        if len(tabs) > 1:
            return "Multiple application tabs opened; inspect them before continuing"
        target = tabs[0] if tabs else self.page
        if target == self.page and self.allowed_url(target.url):
            return ""
        if target.url == "about:blank":
            try:
                await target.wait_for_url(
                    lambda url: str(url) != "about:blank", timeout=5000
                )
            except Exception:
                return "Application tab has not loaded; inspect it before continuing"
        parsed = urlparse(target.url)
        known = (
            parsed.scheme == "https"
            and parsed.hostname in self.handoff_domains
            and parsed.port in (None, 443)
            and not parsed.username
        )
        if not known:
            if tabs:
                return f"Application opened another tab on {parsed.hostname or 'an unknown site'}; complete this employer flow manually"
            return ""  # blocked() reports an unknown same-tab redirect.
        self._active_handoff = True
        if target != self.page:
            self.session.extra_pages.append(target)
            self.page = target
        self.composer.record["handoff_url"] = target.url
        emit(
            "apply",
            f"Continuing application on {parsed.hostname}",
            platform=self.platform_name,
        )
        await self.wait_for_application_surface()
        return ""

    async def form_fingerprint(self, scope):
        return await scope.evaluate("el => el.innerText.replace(/\\s+/g, ' ').trim()")

    async def wait_for_form_change(self, before):
        deadline = asyncio.get_running_loop().time() + 15
        while asyncio.get_running_loop().time() < deadline:
            if any(
                [
                    await tab.opener() == self.page
                    for tab in self.context.pages
                    if tab != self.page
                ]
            ):
                return True
            if (
                await self.blocked()
                or await self.visible(self.success_selectors) is not None
            ):
                return True
            scope = await self.form_scope()
            if scope is None:
                # A saved step may close its dialog and render the next surface later.
                return True
            if scope is not None:
                if await self.form_fingerprint(scope) != before:
                    return True
                if (
                    await self.visible(
                        ('[aria-invalid="true"]', '[role="alert"]'), scope
                    )
                    is not None
                ):
                    return False
            await asyncio.sleep(0.25)
        return False

    async def wait_for_application_surface(self):
        """Apply clicks can hydrate a modal after the initial page has settled."""
        deadline = (
            asyncio.get_running_loop().time()
            + self.application_surface_timeout_ms / 1000
        )
        while True:
            scope = await self.form_scope()
            form_ready = (
                scope is not None
                and await self.visible(
                    self.next_selectors + self.submit_selectors, scope
                )
                is not None
            )
            if (
                await self.blocked()
                or await self.visible(self.success_selectors) is not None
                or form_ready
                or await self.visible(self.interstitial_selectors) is not None
                or (self.portal_path and self.portal_path in self.page.url)
            ):
                return
            for tab in self.context.pages:
                if tab != self.page and await tab.opener() == self.page:
                    return
            if asyncio.get_running_loop().time() >= deadline:
                return
            await asyncio.sleep(0.25)

    async def apply_to_job(self, job):
        self._active_handoff = False
        self.composer = None
        if not self.allowed_url(job.url):
            return ApplicationResult(
                "review", "Job URL is outside the platform's allowed domains"
            )
        from .answers import AnswerComposer, read_resume

        self.composer = AnswerComposer(
            settings.profile, job, read_resume(settings.resume_path)
        )
        response = await self.page.goto(
            self.application_url(job), wait_until="domcontentloaded"
        )
        if response is not None and response.status in (404, 410):
            return ApplicationResult("expired", "Job listing is no longer available")
        await self.settle()
        await self.prepare_application_entry()
        deadline = asyncio.get_running_loop().time() + 10
        while True:
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
            if await self.visible(self.expired_selectors) is not None:
                return ApplicationResult(
                    "expired", "Job no longer accepting applications"
                )
            entry = await self.visible(self.apply_selectors)
            if entry is not None or asyncio.get_running_loop().time() >= deadline:
                break
            await asyncio.sleep(0.25)
        if entry is None:
            if await self.visible(self.external_apply_selectors) is not None:
                return ApplicationResult(
                    "review",
                    "Employer-site application requires a supported employer adapter; other jobs will continue",
                    True,
                )
            return ApplicationResult(
                "review",
                "Apply control not found; inspect the listing or adapter selectors",
                True,
            )
        if not self.dry_run:
            from .descriptions import description_from_text

            description = ""
            section = await self.visible(self.description_selectors)
            if section is not None:
                candidate = (await section.inner_text()).strip()
                if len(candidate) >= 80:
                    description = candidate[:20000]
            if not description:
                description = description_from_text(
                    self.platform_name, await self.page.locator("body").inner_text()
                )
            if description:
                job.description = description
                self.composer.record["description_source"] = self.page.url
                self.db.save_job_description(job.id, description)
                # Some sites mislabel a senior listing as "Fresher" in its card.
                # Recheck explicit, standalone experience requirements in the JD.
                from ..models import is_experience_eligible

                for line in description.splitlines():
                    requirement = re.match(
                        r"^\s*[•*-]?\s*(\d+(?:\.\d+)?\s*(?:\+|[-–]\s*\d+(?:\.\d+)?)?\s*(?:years?|yrs?))\s+(?:of\s+)?(?:relevant\s+)?experience\b",
                        line,
                        re.I,
                    )
                    if (
                        requirement
                        and not is_experience_eligible(
                            requirement[1], self.min_experience, self.max_experience
                        )[0]
                    ):
                        return ApplicationResult(
                            "review",
                            "The job description's experience requirement exceeds your saved range",
                            True,
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
        self.composer.record["entry_clicked"] = True
        self.db.save_application_answers(job.id, self.composer.record)
        await entry.click()
        await self.settle()
        portal_entered = False
        for _ in range(8):
            await self.wait_for_application_surface()
            handoff_error = await self.follow_handoff()
            if handoff_error:
                return ApplicationResult("review", handoff_error)
            reason = await self.blocked()
            if reason:
                return ApplicationResult("review", reason)
            if await self.visible(self.success_selectors) is not None:
                return ApplicationResult(
                    "applied", "Site displayed an explicit application confirmation"
                )
            if await self.advance_interstitial():
                await self.settle()
                continue
            scope = await self.form_scope()
            if scope is None:
                if (
                    self.portal_path
                    and self.portal_path in self.page.url
                    and not portal_entered
                ):
                    portal_entry = await self.portal_entry(job)
                    if portal_entry is not None:
                        portal_entered = True
                        await portal_entry.click()
                        await self.settle()
                        continue
                return ApplicationResult(
                    "review",
                    "No confirmation or supported application form; verify manually before retrying",
                )
            preparation_error = await self.prepare_form(scope)
            if preparation_error:
                return ApplicationResult("review", preparation_error)
            # Resume editing may navigate from review back to a different form.
            scope = await self.form_scope()
            if scope is None:
                return ApplicationResult(
                    "review",
                    "Application form changed during preparation; inspect the open tab",
                )
            unanswered = await fill_form(
                scope,
                settings.profile,
                settings.resume_path,
                self.composer,
                handled_selectors=self.handled_form_selectors,
            )
            self.db.save_application_answers(job.id, self.composer.record)
            if unanswered:
                return ApplicationResult(
                    "review",
                    (
                        "Site rejected saved answers: "
                        if self.composer.record.get("validation_errors")
                        else "Saved answers needed: "
                    )
                    + "; ".join(unanswered),
                    True,
                )
            validation = await self.visible(
                ('[aria-invalid="true"]', '[role="alert"]'), scope
            )
            if validation is not None:
                return ApplicationResult(
                    "review", "Form validation requires review", True
                )
            submit = await self.visible(self.submit_selectors, scope)
            if submit is not None:
                self.composer.record["submission_started"] = True
                self.db.save_application_answers(job.id, self.composer.record)
                await submit.click()
                handoff = await self.post_submit()
                if handoff is not None:
                    return handoff
                # Confirmation can be asynchronous. Wait for evidence, never submit twice.
                try:
                    await self.page.locator(
                        ", ".join(self.success_selectors)
                    ).first.wait_for(
                        state="visible", timeout=self.confirmation_timeout_ms
                    )
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
                return ApplicationResult(
                    "review", "No supported next/submit control", True
                )
            before = await self.form_fingerprint(scope)
            await next_button.click()
            if not await self.wait_for_form_change(before):
                rejected = await validation_errors(scope)
                if rejected:
                    self.composer.record["unresolved"] = rejected
                    self.composer.record["validation_errors"] = rejected
                    self.db.save_application_answers(job.id, self.composer.record)
                    return ApplicationResult(
                        "review",
                        "Site rejected saved answers: " + "; ".join(rejected),
                        True,
                    )
                return ApplicationResult(
                    "review",
                    "The form did not advance or reported validation errors; inspect the open tab",
                )
        return ApplicationResult(
            "review", "Application exceeded eight steps; inspect manually"
        )

    def _get_jobs_to_apply(self):
        return self.select_candidates()[0]

    def select_candidates(self):
        """Return candidates and mutually exclusive filter counts for the dashboard."""
        jobs = []
        summary = {
            "considered": 0,
            "below_score": 0,
            "experience_mismatch": 0,
            "excluded_title": 0,
            "eligible": 0,
            "selected": 0,
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
                    # Older offline scoring assigned 15 points even when neither
                    # a role nor a skill matched. Do not treat that as 10% relevance.
                    legacy_no_match = (
                        status == "matched"
                        and self.min_score > 0
                        and job.match_score == 15
                        and job.match_reason.startswith(
                            "Matched role keywords and 0 core skills (general)."
                        )
                    )
                    if job.match_score < self.min_score or legacy_no_match:
                        summary["below_score"] += 1
                    elif not job.is_experience_eligible(
                        self.min_experience, self.max_experience
                    )[0]:
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
            emit(
                "apply",
                "Connecting to regular Chrome. Allow the debugging connection if Chrome asks.",
                platform=self.platform_name,
            )
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
                    job.id, self.daily_quota
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
                    self.composer = None
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
                    if self.composer is not None:
                        self.db.save_application_answers(job.id, self.composer.record)
                    if outcome.status == "review" and self.page is not None:
                        # Preserve the incomplete form for the user instead of discarding it.
                        self.session.keep_page = True
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
                                path=str(evidence), full_page=True, timeout=5000
                            )
                            outcome = ApplicationResult(
                                outcome.status,
                                outcome.message + f"; Screenshot: {evidence}",
                                outcome.continue_queue,
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
                if outcome.status == "review":
                    if outcome.continue_queue:
                        results["message"] = (
                            "Jobs needing answers remain in Review; other eligible jobs continue."
                        )
                        if index < len(jobs):
                            self.page = await self.context.new_page()
                            self.session.extra_pages.append(self.page)
                        continue
                    results["message"] = (
                        "Paused this platform at an incomplete application; its Chrome tab remains open."
                    )
                    break
        except BrowserConnectionError as exc:
            results["error"] = str(exc)
            results["blocker"] = "browser_connection"
        except Exception as exc:
            results["error"] = (
                f"{type(exc).__name__}: could not complete {self.platform_name}; check browser installation and session"
            )
            logger.warning("Platform run failed (%s)", type(exc).__name__)
        finally:
            await self.stop_browser()
        return results
