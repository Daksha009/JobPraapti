"""LinkedIn UI adapter. Shared behavior lives in applier.base."""

from .base import BaseApplier
from ..config import settings
from urllib.parse import urljoin, urlparse
import re


class LinkedInApplier(BaseApplier):
    platform_name = "linkedin"
    HOME_URL = "https://www.linkedin.com"
    LOGIN_URL = "https://www.linkedin.com/login"
    allowed_domains = ("linkedin.com",)
    AUTH_URL = "https://www.linkedin.com/feed/"
    auth_selectors = (
        "#global-nav",
        ".global-nav__me",
        'nav:has(a[href*="/messaging/"]):has(a[href*="/notifications/"])',
    )

    apply_selectors = (
        'button[aria-label="Easy Apply to this job"]',
        'button:has-text("Easy Apply")',
        'button[aria-label*="Easy Apply"]',
    )

    def application_url(self, job):
        match = re.search(r"/jobs/view/(?:[^/]*-)?(\d+)(?:/|$)", urlparse(job.url).path)
        return f"https://www.linkedin.com/jobs/view/{match[1]}/" if match else job.url

    async def prepare_application_entry(self):
        # Legacy country subdomains and slug routes can redirect while React
        # renders controls. Wait for navigation load before the single entry click.
        try:
            await self.page.wait_for_load_state("load", timeout=15000)
        except Exception:
            pass

    form_selectors = (
        '[data-sdui-screen="com.linkedin.sdui.flagshipnav.jobs.easyapply.EasyApply"]',
        ".jobs-easy-apply-modal",
        "dialog[open]",
        '[role="dialog"]',
    )
    interstitial_selectors = (
        '[data-sdui-screen="com.linkedin.sdui.flagshipnav.jobs.PreApplySafetyTipsModal"]',
    )
    expired_selectors = (
        *BaseApplier.expired_selectors,
        "text=/^No longer accepting applications[.!]?$/i",
    )
    next_selectors = (
        'button[aria-label="Continue to next step"]',
        'button[aria-label="Review your application"]',
        'button:text-is("Next")',
        'button:text-is("Review")',
    )

    async def advance_interstitial(self):
        # Current LinkedIn renders its informational reminder outside role=dialog.
        # Match that specific screen; never click arbitrary verification prompts.
        reminder = await self.visible(self.interstitial_selectors)
        if reminder is None:
            return False
        continuation = await self.visible(
            ('a:text-is("Continue applying")', 'button:text-is("Continue applying")'),
            reminder,
        )
        if continuation is None:
            return False
        href = await continuation.get_attribute("href")
        if href and not self.allowed_url(urljoin(self.page.url, href)):
            return False
        await continuation.click()
        await reminder.wait_for(state="hidden", timeout=10000)
        return True

    async def prepare_form(self, scope):
        upload = await self.visible(('button:text-is("Upload resume")',), scope)
        if upload is None or self.composer.record.get("resume_uploaded"):
            return ""
        if not settings.resume_path.is_file():
            return "Upload your resume in My profile before applying"
        try:
            async with self.page.expect_file_chooser(timeout=5000) as chosen:
                await upload.click()
            await (await chosen.value).set_files(str(settings.resume_path))
            import asyncio

            deadline = asyncio.get_running_loop().time() + 15
            while asyncio.get_running_loop().time() < deadline:
                for radio in await scope.locator('input[type="radio"]:checked').all():
                    if (
                        await radio.get_attribute("aria-label")
                        == settings.resume_path.name
                    ):
                        self.composer.record["resume_uploaded"] = (
                            settings.resume_path.name
                        )
                        return ""
                await asyncio.sleep(0.25)
        except Exception:
            pass
        return "Resume upload could not be verified; select your uploaded resume in the open tab"
