"""Glassdoor UI adapter. Shared behavior lives in applier.base."""

from .base import BaseApplier
from ..config import settings
import re
import asyncio


class GlassdoorApplier(BaseApplier):
    platform_name = "glassdoor"
    HOME_URL = "https://www.glassdoor.co.in"
    LOGIN_URL = "https://www.glassdoor.co.in/profile/login_input.htm"
    allowed_domains = ("glassdoor.co.in", "glassdoor.com")
    handoff_domains = ("smartapply.indeed.com",)
    confirmation_timeout_ms = 45000
    external_apply_selectors = ('button[data-test="applyButton"]',)
    handoff_form_selectors = (
        'main:has([data-testid="submit-application-button"])',
        'main:has(input[data-testid="resume-selection-file-resume-radio-card-file-input"])',
        "form:has(button)",
        '[role="main"]:has(input):has(button)',
    )
    submit_selectors = (
        *BaseApplier.submit_selectors,
        'button[data-testid="submit-application-button"]',
    )
    handled_form_selectors = (
        '[data-testid="resume-selection-file-resume-radio-card-file-input"]',
        '[data-testid="resume-selection-file-resume-radio-card-input"]',
    )

    async def wait_for_application_surface(self):
        if not self._active_handoff:
            return await super().wait_for_application_surface()
        deadline = asyncio.get_running_loop().time() + 45
        while True:
            # Dismiss only the observed optional-cookie banner; no essential cookies
            # or browser/session settings are changed.
            reject = self.page.locator("#onetrust-reject-all-handler")
            if await reject.is_visible():
                await reject.click()
            if (
                await self.blocked()
                or await self.visible(self.success_selectors) is not None
            ):
                return
            scope = await self.form_scope()
            if (
                scope is not None
                and await self.visible(
                    self.next_selectors + self.submit_selectors, scope
                )
                is not None
            ):
                return
            if asyncio.get_running_loop().time() >= deadline:
                return
            await asyncio.sleep(0.25)

    async def prepare_form(self, scope):
        if not self._active_handoff:
            return ""
        preview = self.page.locator('iframe[data-testid="application-preview"]')
        uploaded = self.composer.record.get("resume_uploaded")
        if await preview.is_visible() and not uploaded:
            frame = await (await preview.element_handle()).content_frame()
            edit = frame.get_by_role("button", name="Edit resume", exact=True)
            if not await edit.is_visible():
                return "Cannot verify the resume in Indeed's application preview"
            await edit.click()
            await self.page.locator(self.handled_form_selectors[0]).wait_for(
                state="attached", timeout=10000
            )
        upload = self.page.locator(self.handled_form_selectors[0])
        if await upload.count() and not uploaded:
            if not settings.resume_path.is_file():
                return "Upload your resume in My profile before applying"
            await upload.set_input_files(str(settings.resume_path))
            card = self.page.locator(
                '[data-testid="resume-selection-file-resume-radio-card"]'
            )
            await card.get_by_text(settings.resume_path.name, exact=True).wait_for(
                timeout=15000
            )
            if not await card.locator('input[type="radio"]').is_checked():
                return "Select the uploaded resume before continuing"
            self.composer.record["resume_uploaded"] = settings.resume_path.name
        if await preview.is_visible():
            frame = await (await preview.element_handle()).content_frame()
            personal = settings.profile.get("personal", {})
            for test_id, key in (
                ("fullName", "full_name"),
                ("email", "email"),
                ("phone", "phone"),
            ):
                actual = await frame.locator(f'[data-testid="{test_id}"]').inner_text()
                normalize = lambda value: re.sub(r"\W", "", str(value)).casefold()
                if not personal.get(key) or normalize(personal[key]) not in normalize(
                    actual
                ):
                    return f"Indeed preview {key.replace('_', ' ')} differs from My profile; edit it before submitting"
            filename = await frame.locator('[data-testid="fileName"]').inner_text()
            if filename.strip() != settings.resume_path.name:
                return "Indeed preview does not show the uploaded profile resume"
        return ""

    auth_selectors = (
        '[data-test="profile-icon"]',
        '[class*="AccountMenu"]',
        'a[href*="/logout"]',
        'body:has(button[data-test="utility-nav-profile-button"][aria-label="profile"]):has-text("Post anonymously as"):has-text("Create post")',
    )
    apply_selectors = (
        'button[data-test="easyApply"]',
        'button:text-is("Easy Apply")',
        'button:text-is("Easy apply")',
        '[data-test="easy-apply-button"]',
    )
