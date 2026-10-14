"""Cutshort UI adapter. Shared behavior lives in applier.base."""

from .base import BaseApplier


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
    )
    apply_selectors = (
        'button:text-is("Apply now")',
        'a:text-is("Apply to this job")',
        'button:text-is("Apply to this job")',
    )
    portal_path = "/profile/"
