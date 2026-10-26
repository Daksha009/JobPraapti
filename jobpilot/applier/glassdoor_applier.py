"""Glassdoor UI adapter. Shared behavior lives in applier.base."""

from .base import BaseApplier


class GlassdoorApplier(BaseApplier):
    platform_name = "glassdoor"
    HOME_URL = "https://www.glassdoor.co.in"
    LOGIN_URL = "https://www.glassdoor.co.in/profile/login_input.htm"
    allowed_domains = ("glassdoor.co.in", "glassdoor.com")
    handoff_domains = ("smartapply.indeed.com",)
    handoff_form_selectors = (
        "form:has(button)",
        '[role="main"]:has(input):has(button)',
    )
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
