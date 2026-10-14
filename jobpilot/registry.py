"""One registration point for discovery, application, CLI and dashboard."""

from dataclasses import dataclass
from importlib import import_module


@dataclass(frozen=True)
class PlatformSpec:
    name: str
    scraper: str
    applier: str


PLATFORMS: dict[str, PlatformSpec] = {}


def register_platform(spec: PlatformSpec) -> None:
    if not spec.name.isidentifier() or spec.name in PLATFORMS:
        raise ValueError(f"Invalid or duplicate platform: {spec.name}")
    PLATFORMS[spec.name] = spec


def load_class(path: str):
    module, name = path.split(":", 1)
    return getattr(import_module(module), name)


def platform_names(selection: str = "all") -> list[str]:
    from .config import settings

    if selection != "all" and selection not in PLATFORMS:
        raise ValueError(f"Unknown platform: {selection}")
    names = list(PLATFORMS) if selection == "all" else [selection]
    config = settings.platforms.get("platforms", {})
    return [name for name in names if config.get(name, {}).get("enabled", False)]


for _name, _class in (
    ("cutshort", "Cutshort"),
    ("wellfound", "Wellfound"),
    ("hirist", "Hirist"),
    ("linkedin", "LinkedIn"),
    ("foundit", "Foundit"),
    ("glassdoor", "Glassdoor"),
):
    register_platform(
        PlatformSpec(
            _name,
            f"jobpilot.scrapers.{_name}:{_class}Scraper",
            f"jobpilot.applier.{_name}_applier:{_class}Applier",
        )
    )
