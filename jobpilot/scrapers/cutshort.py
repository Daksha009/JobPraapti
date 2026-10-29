"""
Cutshort job scraper.
Scrapes job listings from cutshort.io using Playwright.
"""

import logging
import re
from urllib.parse import parse_qs, urlencode, urlparse, urlunparse
from typing import List, Optional

from .base import BaseScraper
from ..models import Job
from ..config import settings

logger = logging.getLogger(__name__)


class CutshortScraper(BaseScraper):
    """Scraper for Cutshort.io job listings."""

    platform_name = "cutshort"

    # Verified category URLs for Cutshort (filtered by 0-2 yrs in post-processing)
    TARGET_URLS = [
        "https://cutshort.io/jobs/internship-jobs",
        "https://cutshort.io/jobs/remote-web-development-jobs",
        "https://cutshort.io/jobs/remote-frontend-developer-jobs",
        "https://cutshort.io/jobs/remote-reactjs-jobs",
        "https://cutshort.io/jobs/remote-nodejs-jobs",
        "https://cutshort.io/jobs/remote-python-jobs",
        "https://cutshort.io/jobs/remote-java-jobs",
        "https://cutshort.io/jobs/remote-javascript-jobs",
        "https://cutshort.io/jobs/frontend-developer-jobs",
        "https://cutshort.io/jobs/fullstack-developer-jobs",
        "https://cutshort.io/jobs/backend-developer-jobs",
    ]

    async def scrape_jobs(self) -> List[Job]:
        """Scrape jobs from Cutshort across startup directory endpoints."""
        jobs = []
        max_jobs = self.platform_config.get("max_jobs", 300)
        global_seen_urls = set()

        for target_url in self.platform_config.get("search_urls", self.TARGET_URLS):
            if len(jobs) >= max_jobs:
                break

            for page_num in range(1, self.max_pages + 1):
                parsed = urlparse(target_url)
                query = parse_qs(parsed.query)
                if parsed.path == "/profile/all-jobs":
                    query.update(
                        minexp=[settings.min_experience_years],
                        maxexp=[settings.max_experience_years],
                    )
                if page_num > 1:
                    query["page"] = [page_num]
                url = urlunparse(parsed._replace(query=urlencode(query, doseq=True)))
                try:
                    logger.info(f"[cutshort] Scraping page {page_num}: {url}")
                    await self.navigate(url, wait_until="domcontentloaded")
                    await self._random_delay(0.5)
                    target = urlparse(self.page.url)
                    redirect = parse_qs(target.query).get("redirect_url", [""])[0]
                    if target.path == "/" and redirect.startswith("/profile/"):
                        self.navigation_errors.append(
                            "Cutshort sign-in required: the jobs page redirected to Candidate login. "
                            "Sign in in regular Chrome from Platforms, then retry."
                        )
                        break

                    # Wait for job links
                    try:
                        await self.page.wait_for_selector(
                            'a[href*="/job/"]', timeout=12000
                        )
                    except Exception:
                        logger.warning(f"[cutshort] No job links found on {url}")
                        break

                    page_jobs = await self._extract_jobs_from_page(global_seen_urls)
                    if not page_jobs:
                        break

                    jobs.extend(page_jobs[: max_jobs - len(jobs)])
                    logger.info(
                        f"[cutshort] Found {len(page_jobs)} new jobs on {url} (Total so far: {len(jobs)})"
                    )

                    if len(jobs) >= max_jobs:
                        break

                except Exception as e:
                    logger.error(f"[cutshort] Error on {url}: {e}")
                    break

        return jobs

    async def _extract_jobs_from_page(
        self, seen_urls: Optional[set] = None
    ) -> List[Job]:
        """Extract job data from the current page."""
        raw_cards = await self.page.evaluate("""() => {
            const links = Array.from(document.querySelectorAll('a[href*="/job/"]'));
            const results = [];
            
            for (const link of links) {
                const title = link.innerText.trim();
                const url = link.href;
                if (!title || !url) continue;
                
                // Traverse up to find job card container
                let container = link.closest('[class~="sc-963106f5-1"], article, [data-job-id], [class*="jobCard"], [class*="JobCard"]');
                if (!container) {
                    container = link;
                    for (let i = 0; i < 5 && container.parentElement; i++) {
                        const parent = container.parentElement;
                        const urls = new Set(Array.from(parent.querySelectorAll('a[href*="/job/"]')).map(a => a.href));
                        if (urls.size > 1) break;
                        container = parent;
                    }
                }
                
                const lines = container.innerText.split('\\n').map(l => l.trim()).filter(Boolean);
                results.push({
                    title,
                    url,
                    lines,
                    company: container.querySelector('[class~="sc-963106f5-15"]')?.innerText.split('\\n')[1]?.trim(),
                    location: container.querySelector('[class~="sc-963106f5-29"]')?.innerText.trim(),
                    experience: Array.from(container.querySelectorAll('[class~="sc-963106f5-26"]')).map(e=>e.innerText.trim()).find(t=>/\\d\\s*(?:-\\s*\\d+\\s*)?yrs?\\b/.test(t)),
                    salary: Array.from(container.querySelectorAll('[class~="sc-963106f5-26"]')).map(e=>e.innerText.trim()).find(t=>/[₹$]/.test(t)),
                    skills: Array.from(container.querySelectorAll('[class~="sc-60b7a349-1"]')).map(e=>e.innerText.trim())
                });
            }
            return results;
        }""")

        jobs = []
        if seen_urls is None:
            seen_urls = set()

        for r in raw_cards:
            url = r.get("url", "")
            title = r.get("title", "")
            lines = r.get("lines", [])

            if not title or not url or url in seen_urls:
                continue
            seen_urls.add(url)

            company = "Startup"
            location = ""
            experience = ""
            salary = ""
            skills = []

            meta_idx = -1
            for idx, line in enumerate(lines):
                if line.startswith("at "):
                    company = line[3:].strip()
                elif "·" in line:
                    meta_idx = idx
                    parts = [p.strip() for p in line.split("·")]
                    if len(parts) >= 1:
                        location = parts[0]
                    for p in parts:
                        if (
                            "₹" in p
                            or "$" in p
                            or "lpa" in p.lower()
                            or "/ yr" in p.lower()
                        ):
                            salary = p
                        elif "year" in p.lower() or "yr" in p.lower():
                            experience = p

            if meta_idx != -1 and meta_idx + 1 < len(lines):
                for skill_line in lines[meta_idx + 1 :]:
                    low = skill_line.lower()
                    if low in [
                        "apply now",
                        "posted",
                        "candid answers",
                    ] or skill_line.startswith("+"):
                        continue
                    if len(skill_line) < 35 and skill_line not in skills:
                        skills.append(skill_line)

            external_id = ""
            match = re.search(r"/job/([a-zA-Z0-9_-]+)", url)
            if match:
                external_id = match.group(1)

            company = (r.get("company") or company).removeprefix("at ")
            location = r.get("location") or location
            experience = r.get("experience") or experience
            salary = r.get("salary") or salary
            skills = r.get("skills") or skills

            jobs.append(
                Job(
                    title=title,
                    company=company,
                    platform="cutshort",
                    url=url,
                    location=location,
                    salary=salary,
                    experience=experience,
                    skills=skills,
                    external_id=external_id,
                )
            )

        return jobs
