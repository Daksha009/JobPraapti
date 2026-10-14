"""Foundit UI adapter. Shared behavior lives in applier.base."""

from .base import BaseApplier


class FounditApplier(BaseApplier):
    platform_name = "foundit"
    HOME_URL = "https://www.foundit.in"
    LOGIN_URL = "https://www.foundit.in/login"
    allowed_domains = ("foundit.in",)
    auth_selectors = (
        '[class*="userMenu"]',
        '[class*="logged-in"]',
        'a[href*="/logout"]',
    )
    apply_selectors = (
        'button:text-is("Quick Apply")',
        'button:text-is("Apply Now")',
        'button:text-is("Apply")',
    )
