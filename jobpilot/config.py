"""
Configuration loader for JobPilot.
Loads profile, platform configs, and environment variables.
"""

import os
import math
import yaml
from pathlib import Path
from dotenv import load_dotenv

# Base paths
BASE_DIR = Path(
    os.environ.get("JOBPILOT_HOME", Path(__file__).resolve().parent.parent)
).resolve()
load_dotenv(BASE_DIR / ".env")
CONFIG_DIR = BASE_DIR / "config"
DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)


def load_yaml(filepath: Path) -> dict:
    """Load a YAML configuration file."""
    with open(filepath, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    if not isinstance(data, dict):
        raise ValueError(f"{filepath.name} must contain a YAML mapping")
    return data


def get_profile() -> dict:
    """Load user profile configuration."""
    return load_yaml(CONFIG_DIR / "profile.yaml")


def get_platforms() -> dict:
    """Load platform-specific configuration."""
    return load_yaml(CONFIG_DIR / "platforms.yaml")


def get_env(key: str, default: str = None) -> str:
    """Get an environment variable with optional default."""
    from .vault import SECRET_KEYS, Vault

    if key in SECRET_KEYS:
        protected = Vault(DATA_DIR / "credentials.dpapi").read().get(key)
        if protected:
            return protected
    value = os.getenv(key, default)
    if isinstance(value, str) and (
        value.startswith("your_") or value == "your.email@example.com"
    ):
        return default
    return value


# Frequently accessed config values
class Settings:
    """Central settings object."""

    def __init__(self):
        self._profile = None
        self._platforms = None

    get_env = staticmethod(get_env)

    def credentials(self, platform: str) -> tuple[str, str]:
        return get_env(f"{platform.upper()}_EMAIL", ""), get_env(
            f"{platform.upper()}_PASSWORD", ""
        )

    @property
    def gemini_model(self) -> str:
        return get_env("GEMINI_MODEL", "gemini-3.8-flash")

    def validate(self, *, for_apply=False) -> list[str]:
        errors = []
        try:
            profile = self.profile
            for section in (
                "personal",
                "preferences",
                "resume",
                "application_defaults",
            ):
                if not isinstance(profile.get(section, {}), dict):
                    errors.append(f"profile.{section} must be a mapping")
            if errors:
                return errors
            for field in (
                "roles",
                "skills",
                "locations",
                "exclude_keywords",
                "search_keywords",
            ):
                value = profile.get("preferences", {}).get(field, [])
                if not isinstance(value, list) or any(
                    not isinstance(item, str) for item in value
                ):
                    errors.append(f"preferences.{field} must be a list of strings")
            if not 0 <= float(self.min_match_score) <= 100:
                errors.append("min_match_score must be between 0 and 100")
            if not 0 <= self.min_experience_years <= self.max_experience_years:
                errors.append("Experience range must satisfy 0 <= minimum <= maximum")
            answers = profile.get("application_defaults", {}).get("answers", {})
            if not isinstance(answers, dict):
                errors.append("application_defaults.answers must be a mapping")
            defaults = profile.get("application_defaults", {})
            for key in (
                "compose_narrative_answers",
                "visa_sponsorship_required",
                "background_check_consent",
                "willing_to_work_hybrid_or_onsite_india",
            ):
                if key in defaults and type(defaults[key]) is not bool:
                    errors.append(f"application_defaults.{key} must be true or false")
            single_salary = defaults.get("expected_salary_single_lpa")
            if single_salary is not None and (
                type(single_salary) not in (int, float)
                or not math.isfinite(single_salary)
                or single_salary < 0
            ):
                errors.append(
                    "application_defaults.expected_salary_single_lpa must be a nonnegative number"
                )
            authorization = defaults.get("work_authorization", {})
            if not isinstance(authorization, dict) or any(
                not isinstance(country, str) or type(value) is not bool
                for country, value in authorization.items()
            ):
                errors.append(
                    "application_defaults.work_authorization must map countries to true/false"
                )
            if for_apply:
                personal = profile.get("personal", {})
                for field in ("full_name", "email", "phone"):
                    value = str(personal.get(field, "")).strip()
                    if (
                        not value
                        or value.lower().startswith("your")
                        or "example.com" in value
                    ):
                        errors.append(f"Set personal.{field} before applying")
                if not self.resume_path.is_file():
                    errors.append(f"Resume missing: {self.resume_path}")
            platforms = self.platforms.get("platforms", {})
            from .registry import PLATFORMS

            for name, config in platforms.items():
                if name not in PLATFORMS:
                    errors.append(f"Unregistered platform: {name}")
                if not isinstance(config, dict) or not isinstance(
                    config.get("enabled", False), bool
                ):
                    errors.append(f"platforms.{name}.enabled must be true or false")
                    continue
                for key in ("max_pages", "max_jobs", "daily_limit"):
                    if key in config and (
                        type(config[key]) is not int or config[key] < 1
                    ):
                        errors.append(
                            f"platforms.{name}.{key} must be a positive integer"
                        )
                delay = config.get("delay_seconds", 2)
                if not isinstance(delay, (int, float)) or not 0 <= delay <= 300:
                    errors.append(
                        f"platforms.{name}.delay_seconds must be between 0 and 300"
                    )
            scraping = self.platforms.get("scraping", {})
            for key in ("max_retries", "timeout_seconds"):
                if key in scraping and (
                    type(scraping[key]) is not int or scraping[key] < 1
                ):
                    errors.append(f"scraping.{key} must be a positive integer")
        except (OSError, ValueError, TypeError, AttributeError, yaml.YAMLError) as exc:
            errors.append(f"Invalid configuration: {exc}")
        return errors

    @property
    def profile(self) -> dict:
        if self._profile is None:
            self._profile = get_profile()
        return self._profile

    @property
    def platforms(self) -> dict:
        if self._platforms is None:
            self._platforms = get_platforms()
        return self._platforms

    @property
    def gemini_api_key(self) -> str:
        return get_env("GEMINI_API_KEY", "")

    @property
    def linkedin_email(self) -> str:
        return get_env("LINKEDIN_EMAIL", "")

    @property
    def linkedin_password(self) -> str:
        return get_env("LINKEDIN_PASSWORD", "")

    @property
    def cutshort_email(self) -> str:
        return get_env("CUTSHORT_EMAIL", "")

    @property
    def hirist_email(self) -> str:
        return get_env("HIRIST_EMAIL", "")

    @property
    def hirist_password(self) -> str:
        return get_env("HIRIST_PASSWORD", "")

    @property
    def wellfound_email(self) -> str:
        return get_env("WELLFOUND_EMAIL", "")

    @property
    def wellfound_password(self) -> str:
        return get_env("WELLFOUND_PASSWORD", "")

    @property
    def foundit_email(self) -> str:
        return get_env("FOUNDIT_EMAIL", "")

    @property
    def foundit_password(self) -> str:
        return get_env("FOUNDIT_PASSWORD", "")

    @property
    def glassdoor_email(self) -> str:
        return get_env("GLASSDOOR_EMAIL", "")

    @property
    def glassdoor_password(self) -> str:
        return get_env("GLASSDOOR_PASSWORD", "")

    @property
    def db_path(self) -> Path:
        return DATA_DIR / "jobpilot.db"

    @property
    def dashboard_port(self) -> int:
        return int(get_env("DASHBOARD_PORT", "5000"))

    @property
    def dashboard_host(self) -> str:
        return get_env("DASHBOARD_HOST", "127.0.0.1")

    @property
    def scrape_delay_min(self) -> int:
        return int(get_env("SCRAPE_DELAY_MIN", "2"))

    @property
    def scrape_delay_max(self) -> int:
        return int(get_env("SCRAPE_DELAY_MAX", "5"))

    @property
    def max_jobs_per_platform(self) -> int:
        return int(get_env("MAX_JOBS_PER_PLATFORM", "50"))

    @property
    def user_roles(self) -> list:
        return self.profile.get("preferences", {}).get("roles", [])

    @property
    def user_skills(self) -> list:
        return self.profile.get("preferences", {}).get("skills", [])

    @property
    def search_keywords(self) -> list:
        return self.profile.get("preferences", {}).get("search_keywords", [])

    @property
    def search_queries(self) -> list:
        """Put editable resume keywords into supported platform query inputs."""
        from .resume_insights import unique

        roles = self.user_roles
        queries = [
            f"{roles[index % len(roles)]} {keyword}" if roles else keyword
            for index, keyword in enumerate(self.search_keywords)
        ]
        return unique(queries + roles) or ["Software Engineer"]

    @property
    def user_locations(self) -> list:
        return self.profile.get("preferences", {}).get("locations", [])

    @property
    def exclude_keywords(self) -> list:
        return self.profile.get("preferences", {}).get("exclude_keywords", [])

    @property
    def min_match_score(self) -> int:
        return float(self.profile.get("preferences", {}).get("min_match_score", 50))

    @property
    def min_experience_years(self) -> float:
        return float(self.profile.get("preferences", {}).get("min_experience_years", 0))

    @property
    def max_experience_years(self) -> float:
        return float(self.profile.get("preferences", {}).get("max_experience_years", 2))

    @property
    def resume_summary(self) -> str:
        return self.profile.get("resume", {}).get("summary", "")

    @property
    def resume_path(self) -> Path:
        """Resolve path to the resume PDF."""
        configured = self.profile.get("resume", {}).get("path")
        if configured:
            p = (
                (BASE_DIR / configured)
                if not Path(configured).is_absolute()
                else Path(configured)
            )
            return p.resolve()
        default_p = CONFIG_DIR / "resume.pdf"
        if default_p.exists():
            return default_p
        return default_p

    def reload(self):
        """Force reload all configurations."""
        self._profile = None
        self._platforms = None


# Singleton settings instance
settings = Settings()
