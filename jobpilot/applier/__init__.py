"""Lazy platform factories backed by the shared registry."""

from ..registry import PLATFORMS, load_class

APPLIERS = PLATFORMS


def get_applier(platform: str, **kwargs):
    spec = PLATFORMS.get(platform.lower())
    if spec is None:
        raise ValueError(f"Unknown platform: {platform}. Available: {list(PLATFORMS)}")
    return load_class(spec.applier)(**kwargs)
