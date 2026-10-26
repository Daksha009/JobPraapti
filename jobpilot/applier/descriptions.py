"""Extract bounded job text; never use recommendation cards as the job description."""

import re


def description_from_text(platform: str, text: str) -> str:
    boundaries = {
        "linkedin": (
            ("About the job",),
            (
                "Set alert for similar jobs",
                "About the company",
                "Similar jobs",
                "People also viewed",
            ),
        ),
        "wellfound": (
            ("Who we are:", "About the job", "About the role", "Job Description"),
            ("Apply now", "Similar jobs to", "YOUR APPLICATION", "APPLY TO"),
        ),
    }
    if platform not in boundaries:
        return ""
    starts, ends = boundaries[platform]
    start = re.search(
        r"(?im)^\s*(?:" + "|".join(map(re.escape, starts)) + r")\s*$", text
    )
    if not start:
        return ""
    tail = text[start.start() :]
    end = re.search(
        r"(?im)^\s*(?:" + "|".join(map(re.escape, ends)) + r")(?:\s.*)?$",
        tail[start.end() - start.start() :],
    )
    # A known end marker is required to avoid unrelated page content.
    if not end:
        return ""
    result = tail[: start.end() - start.start() + end.start()].strip()
    return result[:20000] if len(result) >= 80 else ""
