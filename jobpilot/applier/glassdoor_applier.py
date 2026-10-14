"""Glassdoor UI adapter. Shared behavior lives in applier.base."""

from .base import BaseApplier


class GlassdoorApplier(BaseApplier):
    platform_name = "glassdoor"
    HOME_URL = "https://www.glassdoor.co.in"
    LOGIN_URL = "https://www.glassdoor.co.in/profile/login_input.htm"
    allowed_domains = ("glassdoor.co.in", "glassdoor.com")
    auth_selectors = (
        '[data-test="profile-icon"]',
        '[class*="AccountMenu"]',
        'a[href*="/logout"]',
    )
    apply_selectors = (
        'button:text-is("Easy Apply")',
        'button:text-is("Easy apply")',
        '[data-test="easy-apply-button"]',
    )
