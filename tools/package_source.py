"""Build a shareable source ZIP using an allowlist; never include local user data."""

from pathlib import Path
from zipfile import ZipFile, ZIP_DEFLATED


def build(output=None):
    root = Path(__file__).resolve().parents[1]
    output = Path(output) if output else root / "dist/jobpraapti-source.zip"
    paths = [
        root / name
        for name in (
            "README.md",
            "pyproject.toml",
            "requirements.txt",
            ".env.example",
            ".gitignore",
            "Start-JobPilot.cmd",
            "Setup-JobPilot.cmd",
            "Start-JobPraapti.cmd",
            "Setup-JobPraapti.cmd",
        )
    ]
    paths += [root / "config/profile.example.yaml", root / "config/platforms.yaml"]
    for directory in ("jobpilot", "docs", "tests", "tools", ".github"):
        paths += [
            path
            for path in (root / directory).rglob("*")
            if path.is_file()
            and "__pycache__" not in path.parts
            and path.suffix
            in (".py", ".md", ".html", ".css", ".js", ".mjs", ".yml", ".woff2", ".svg")
        ]
    paths += [
        root / "frontend" / name
        for name in (
            "package.json",
            "pnpm-lock.yaml",
            "pnpm-workspace.yaml",
            "tsconfig.json",
            "vite.config.ts",
            "index.html",
        )
    ]
    paths += [
        path
        for path in (root / "frontend/src").rglob("*")
        if path.is_file() and path.suffix in (".ts", ".tsx", ".css", ".svg")
    ]
    output.parent.mkdir(parents=True, exist_ok=True)
    with ZipFile(output, "w", ZIP_DEFLATED) as archive:
        for path in sorted(paths):
            archive.write(path, Path("jobpilot") / path.relative_to(root))
    return output


if __name__ == "__main__":
    print(build())
