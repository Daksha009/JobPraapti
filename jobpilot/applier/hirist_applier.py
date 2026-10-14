"""Hirist UI adapter. Shared behavior lives in applier.base."""

from .base import BaseApplier


class HiristApplier(BaseApplier):
    platform_name = "hirist"
    HOME_URL = "https://www.hirist.tech"
    LOGIN_URL = "https://www.hirist.tech/login"
    AUTH_URL = "https://www.hirist.tech/jobfeed"
    allowed_domains = ("hirist.tech",)
    auth_selectors = (
        'a[href*="/my-applications"]',
        '[data-testid*="user_profile"]',
        'a[href*="/logout"]',
        '[data-testid="header-profile-avatar-image"][alt="user_profile"]',
    )
