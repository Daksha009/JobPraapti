"""Wellfound UI adapter. Shared behavior lives in applier.base."""

from .base import BaseApplier


class WellfoundApplier(BaseApplier):
    platform_name = "wellfound"
    HOME_URL = "https://wellfound.com"
    LOGIN_URL = "https://wellfound.com/login"
    allowed_domains = ("wellfound.com",)
    auth_selectors = (
        '[class*="UserMenu"]',
        'a[href="/settings"]',
        'a[href*="/logout"]',
    )
    apply_selectors = (
        'button:text-is("Apply")',
        'button:text-is("Apply now")',
        'button:text-is("Apply for this job")',
    )
