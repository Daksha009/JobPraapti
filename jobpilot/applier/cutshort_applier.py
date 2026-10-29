"""Cutshort UI adapter. Shared behavior lives in applier.base."""

import asyncio

from .base import ApplicationResult, BaseApplier
from ..config import settings
from urllib.parse import parse_qs, urlsplit


class CutshortApplier(BaseApplier):
    platform_name = "cutshort"
    HOME_URL = "https://cutshort.io"
    LOGIN_URL = "https://cutshort.io"
    allowed_domains = ("cutshort.io",)
    AUTH_URL = "https://cutshort.io/profile/all-jobs"
    auth_selectors = (
        'a[href*="/logout"]',
        'button:text-is("Logout")',
        'a[href="/profile/edit"]',
        'a[href="/profile/candidate-dashboard"]',
    )
    apply_selectors = (
        'button[class~="sc-8c2323fe-0"]:text-is("Apply to this job")',
        'a:text-is("Apply to this job")',
        'button:text-is("Apply to this job")',
    )
    portal_path = "/profile/"
    description_selectors = ('[class~="sc-54ec2143-2"].prose',)
    form_selectors = ('[role="dialog"]:has(textarea[name="message"])',)
    handled_form_selectors = ('textarea[name="message"]', 'input[type="file"]')

    async def portal_entry(self, job):
        url = urlsplit(self.page.url)
        if url.path != "/profile/all-jobs" or not parse_qs(url.query).get("jobid"):
            return None
        card = self.page.locator('[class~="sc-963106f5-1"]').filter(
            has=self.page.get_by_role("heading", name=job.title, exact=True)
        )
        if await card.count() != 1:
            return None
        return await self.visible(('button:text-is("Apply now")',), card)

    async def blocked(self):
        reason = await super().blocked()
        if reason:
            return reason
        if await self.page.get_by_text(
            "You already have an active conversation on this job", exact=True
        ).count():
            return (
                "An existing Cutshort conversation needs review before applying again"
            )
        return ""

    async def post_submit(self):
        # Cutshort replaces Apply with a link to the new awaiting conversation.
        # Only treat that transition as evidence after Send has been clicked.
        for _ in range(120):
            card = self.page.locator('[class~="sc-963106f5-1"]').filter(
                has=self.page.get_by_role(
                    "heading", name=self.composer.job.title, exact=True
                )
            )
            if (
                await card.count() == 1
                and await self.visible(
                    (
                        'a[href*="/profile/conversations/candidate"][href*="stage=awaiting"]:text-is("View conversation")',
                    ),
                    card,
                )
                is not None
            ):
                return ApplicationResult(
                    "applied",
                    "Cutshort created an awaiting recruiter conversation for this application",
                )
            if await self.visible(self.success_selectors) is not None:
                return None
            await asyncio.sleep(0.25)
        return None

    async def prepare_form(self, scope):
        survey_close = self.page.locator(
            '#wootric-modal #wootric-close[aria-label="Close survey"]'
        )
        if await survey_close.count() and await survey_close.is_visible():
            await survey_close.click()
        if not self.composer.record.get("resume_uploaded"):
            filename = scope.locator('[class~="sc-d023fd03-8"]')
            previous = await filename.inner_text() if await filename.count() else ""
            await scope.get_by_text("Upload another resume", exact=True).click()
            upload = self.page.locator('input[type="file"]').last
            await upload.wait_for(state="attached", timeout=10000)
            await upload.set_input_files(str(settings.resume_path))
            await filename.wait_for(state="visible", timeout=45000)
            await self.page.wait_for_function(
                """({stem, previous}) => {
                  const el = document.querySelector('[role="dialog"] [class~="sc-d023fd03-8"]');
                  const value = el?.textContent?.trim() || '';
                  return value !== previous && (value === stem || value.startsWith(stem + '_'));
                }""",
                arg={"stem": settings.resume_path.stem, "previous": previous.strip()},
                timeout=45000,
            )
            self.composer.record["resume_uploaded"] = settings.resume_path.name
        field = scope.locator('textarea[name="message"]')
        question = "Introduce yourself and describe your relevant experience"
        answer = settings.profile.get("application_defaults", {}).get(
            "intro_message"
        ) or self.composer.narrative(question, "textarea")
        if not answer:
            return "Add an introduction or enable resume-grounded written answers in My profile"
        await field.fill(answer)
        # This is an optional company-follow subscription, separate from applying.
        follow = scope.locator("label").filter(has_text="to get alerts for new job")
        checked = follow.locator('img[src*="success_icon_p"]')
        if (
            await checked.count()
            and float(await checked.evaluate("e => getComputedStyle(e).opacity")) > 0.5
        ):
            await follow.click()
            for _ in range(20):
                if (
                    not await checked.count()
                    or float(await checked.evaluate("e => getComputedStyle(e).opacity"))
                    < 0.05
                ):
                    break
                await asyncio.sleep(0.1)
            else:
                return "Review the optional company-follow setting before submitting"
        return ""
