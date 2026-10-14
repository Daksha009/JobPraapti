"""LinkedIn UI adapter. Shared behavior lives in applier.base."""

from .base import BaseApplier


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
        'button:has-text("Easy Apply")',
        'button[aria-label*="Easy Apply"]',
    )
    form_selectors = (".jobs-easy-apply-modal", '[role="dialog"]')
    next_selectors = (
        'button[aria-label="Continue to next step"]',
        'button[aria-label="Review your application"]',
        'button:text-is("Next")',
        'button:text-is("Review")',
    )
