"""Wellfound UI adapter. Shared behavior lives in applier.base."""

from .base import BaseApplier


class WellfoundApplier(BaseApplier):
    platform_name = "wellfound"
    HOME_URL = "https://wellfound.com"
    LOGIN_URL = "https://wellfound.com/login"
    AUTH_URL = "https://wellfound.com/jobs/home"
    allowed_domains = ("wellfound.com",)
    description_selectors = ('[class*="styles_description__"]',)
    success_selectors = (
        *BaseApplier.success_selectors,
        r"text=/^SUCCESS! YOUR APPLICATION HAS BEEN SENT\.$/i",
    )
    already_selectors = (
        *BaseApplier.already_selectors,
        r"text=/^✓\s*Applied$/",
    )
    auth_selectors = (
        '[class*="UserMenu"]',
        'a[href="/settings"]',
        'a[href*="/logout"]',
        'body:has(a[href="/profile/edit/overview"]):has(a[href="/jobs/applications"]):has(a[href="/jobs/messages"])',
    )
    apply_selectors = (
        'button:text-is("Apply")',
        'button:text-is("Apply now")',
        'button:text-is("Apply for this job")',
    )
    expired_selectors = (
        *BaseApplier.expired_selectors,
        "text=/^The job listing is no longer available[.!]?$/i",
    )
