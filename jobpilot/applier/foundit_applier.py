"""Foundit UI adapter. Shared behavior lives in applier.base."""

import re
import asyncio

from .base import ApplicationResult, BaseApplier
from ..config import settings


class FounditApplier(BaseApplier):
    platform_name = "foundit"
    HOME_URL = "https://www.foundit.in"
    LOGIN_URL = "https://www.foundit.in/login"
    AUTH_URL = "https://www.foundit.in/home/user"
    allowed_domains = ("foundit.in",)
    auth_selectors = (
        '[class*="userMenu"]',
        '[class*="logged-in"]',
        'a[href*="/logout"]',
        'a[href="https://www.foundit.in/seeker/profile-performance"]',
    )
    apply_selectors = (
        'button:text-is("Quick Apply")',
        'button:text-is("Apply Now")',
        'button:text-is("Apply")',
    )
    description_selectors = ("#descriptionContent.job-description__content",)
    application_surface_timeout_ms = 30000
    success_selectors = (
        *BaseApplier.success_selectors,
        r"text=/^Application sent \(\d{1,2} [A-Za-z]{3} \d{4}\)$/",
    )
    form_selectors = (
        "#employmentDetailsForm",
        '#resumeUploadDetailsForm:has(button:text-is("Confirm & Apply"))',
        *BaseApplier.form_selectors,
    )
    next_selectors = ('button:text-is("Save")', *BaseApplier.next_selectors)
    submit_selectors = (
        'button:text-is("Confirm & Apply")',
        *BaseApplier.submit_selectors,
    )
    handled_form_selectors = tuple(
        f"#employmentDetailsForm {selector}"
        for selector in (
            "#jobTitle",
            "#company",
            "#startYear",
            "#startMonth",
            "#checkbox",
            "#country-dropdown",
            'input[placeholder="Enter Salary"]',
            "#notice",
            "#industries",
        )
    ) + (
        "#resumeUploadDetailsForm #country-dropdown",
        '#resumeUploadDetailsForm input[placeholder="Enter Annual Salary"]',
        "#resumeUploadDetailsForm #notice",
        '#resumeUploadDetailsForm input[type="file"][name="resume"]',
    )

    async def dismiss_cookie_banner(self):
        # The site's fixed cookie notice can cover the profile form's Save button.
        button = self.page.locator(
            "#cookieBannerWrapper .cookie-content button#acceptAll"
        )
        if await button.count() and await button.is_visible():
            await button.click()

    async def prepare_application_entry(self):
        await self.dismiss_cookie_banner()

    async def follow_handoff(self):
        # A one-click Foundit application can open its own success tab while the
        # original job page updates with a dated "Application sent" status.
        children = [
            p
            for p in self.context.pages
            if p != self.page and await p.opener() == self.page
        ]
        for child in children:
            if child.url == "about:blank":
                try:
                    await child.wait_for_url(
                        lambda url: str(url) != "about:blank", timeout=5000
                    )
                except Exception:
                    pass
        if children and all(self.allowed_url(p.url) for p in children):
            for _ in range(30):
                if await self.visible(self.success_selectors) is not None:
                    self.session.extra_pages.extend(
                        p for p in children if p not in self.session.extra_pages
                    )
                    return ""
                await asyncio.sleep(0.25)
        return await super().follow_handoff()

    async def post_submit(self):
        for _ in range(40):
            if await self.visible(self.success_selectors) is not None:
                return None
            for page in self.context.pages:
                if page == self.page or await page.opener() != self.page:
                    continue
                if (
                    not self.allowed_url(page.url)
                    or "/srp/applied-success" not in page.url
                ):
                    continue
                expected = f"You have successfully applied to {self.composer.job.title} at {self.composer.job.company}"
                if await page.get_by_text(expected, exact=True).count():
                    self.session.extra_pages.append(page)
                    return ApplicationResult(
                        "applied",
                        "Foundit confirmed the application for this job and company",
                    )
                if await page.get_by_text(
                    "Redirecting you to apply on company site.", exact=True
                ).count():
                    self.session.extra_pages.append(page)
                    return ApplicationResult(
                        "review",
                        "Foundit opened the employer site; complete the external application and verify before retrying",
                    )
            await asyncio.sleep(0.25)
        return None

    async def prepare_form(self, scope):
        kind = await scope.get_attribute("id")
        if kind not in ("employmentDetailsForm", "resumeUploadDetailsForm"):
            return ""
        await self.dismiss_cookie_banner()
        if kind == "resumeUploadDetailsForm":
            title = (await scope.locator(".apop__jobCardTitle").inner_text()).strip()
            if title != self.composer.job.title:
                return "Foundit application title differs from the selected job"
            resume = scope.locator('input[type="file"][name="resume"]')
            if await resume.count():
                await resume.set_input_files(str(settings.resume_path))
                await scope.get_by_text(settings.resume_path.name, exact=True).wait_for(
                    timeout=30000
                )
                self.composer.record["resume_uploaded"] = settings.resume_path.name
                return ""
        ctc = str(
            settings.profile.get("application_defaults", {}).get("current_ctc", "")
        )
        amount = re.fullmatch(r"\s*(\d+(?:\.\d+)?)\s*LPA\s*", ctc, re.I)
        if not amount:
            return "Confirm current annual CTC in LPA for Foundit"
        notice = settings.profile.get("application_defaults", {}).get(
            "notice_period", ""
        )
        if str(notice).strip().lower() not in ("immediate", "immediately available"):
            return "Choose your confirmed notice period in the Foundit employment form"
        if kind == "resumeUploadDetailsForm":
            currency = scope.locator("#country-dropdown")
            if await currency.input_value() != "INR":
                box = scope.locator(".dropdown-list-box")
                if not await box.count() or not await box.is_visible():
                    await currency.click()
                for index in range(70):
                    option = box.get_by_text("India (INR)", exact=True)
                    if await option.count():
                        await option.click()
                        break
                    await box.evaluate(
                        '(el, n) => {el.scrollTop = n; el.dispatchEvent(new Event("scroll", {bubbles:true}));}',
                        index * 150,
                    )
                    await asyncio.sleep(0.12)
                if await currency.input_value() != "INR":
                    return "Choose INR for the Foundit salary field"
            await scope.get_by_placeholder("Enter Annual Salary", exact=True).fill(
                str(round(float(amount[1]) * 100000))
            )
            notice_field = scope.locator("#notice")
            if await notice_field.input_value() != "Immediately available":
                await notice_field.click()
                await scope.get_by_text("Immediately available", exact=True).click()
            self.composer.remember(
                "Current Salary (Annually)",
                round(float(amount[1]) * 100000),
                "profile",
                "Current CTC in LPA converted to INR per year",
            )
            self.composer.remember("Notice Period", "Immediately available", "profile")
            return ""
        # Preserve the user's existing employment record; never infer employer/dates.
        for identity in ("jobTitle", "company", "startYear", "startMonth"):
            if not (await scope.locator("#" + identity).input_value()).strip():
                return "Complete the missing employment history in your Foundit profile"
        if not await scope.locator("#checkbox").is_checked():
            return "Review your Foundit employment status before continuing"
        currency = await scope.locator("#country-dropdown").input_value()
        if currency != "INR" or not amount:
            return "Confirm current annual CTC in LPA and INR currency for Foundit"
        await scope.get_by_placeholder("Enter Salary", exact=True).fill(
            str(round(float(amount[1]) * 100000))
        )
        await scope.locator("#notice").click()
        await scope.get_by_text("Immediately available", exact=True).click()
        self.composer.remember(
            "Current Salary (Annually)",
            round(float(amount[1]) * 100000),
            "profile",
            "Current CTC in LPA converted to INR per year",
        )
        self.composer.remember("Notice Period", "Immediately available", "profile")
        return ""
