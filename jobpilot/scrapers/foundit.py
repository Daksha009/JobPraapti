"""
Foundit (formerly Monster India) job scraper.
Scrapes job listings from foundit.in using Playwright.
"""

import logging
import re
from typing import List
from urllib.parse import quote, urlencode

from .base import BaseScraper
from ..models import Job
from ..config import settings

logger = logging.getLogger(__name__)


class FounditScraper(BaseScraper):
    """Scraper for Foundit.in (Monster India) job listings."""

    platform_name = "foundit"

    def _build_search_url(self, query: str = "", page: int = 1) -> str:
        """Build Foundit search URL with filters."""
        base = self.platform_config.get("search_url", "https://www.foundit.in/search")
        roles = settings.search_queries
        locations = settings.user_locations

        search_query = query or (roles[0] if roles else "Software Developer")
        location = locations[0] if locations else "India"

        params = {
            "query": search_query,
            "locations": location,
            "experienceRanges": f"{settings.min_experience_years:g}~{settings.max_experience_years:g}",  # 0-2 years
            "sort": "1",  # Relevance
        }

        filters = self.platform_config.get("filters", {})
        if filters.get("job_freshness"):
            params["jobFreshness"] = filters["job_freshness"]

        # Current search uses a role slug and offsets, not the legacy /srp page.
        if base.rstrip("/").endswith(("/search", "/srp/results")):
            base = (
                "https://www.foundit.in/search/"
                + quote(re.sub(r"\s+", "-", search_query.strip().lower()), safe="-")
                + "-jobs"
            )
        params.update(start=(page - 1) * 20 + 1, limit=20)
        url = f"{base}?{urlencode(params, quote_via=quote)}"
        return url

    async def scrape_jobs(self) -> List[Job]:
        """Scrape jobs from Foundit across multiple search queries."""
        jobs = []
        roles = settings.search_queries
        max_jobs = self.platform_config.get("max_jobs", 50)

        for role in roles[
            : self.platform_config.get("max_queries", 3)
        ]:  # Limit to top 3 roles to avoid excessive scraping
            if len(jobs) >= max_jobs:
                break

            for page_num in range(1, self.max_pages + 1):
                if len(jobs) >= max_jobs:
                    break

                try:
                    url = self._build_search_url(query=role, page=page_num)
                    logger.info(f"[foundit] Scraping '{role}' page {page_num}: {url}")

                    await self.navigate(url, wait_until="domcontentloaded")
                    await self._random_delay(1.0)

                    # Dismiss cookie/notification banners
                    await self._dismiss_banners()

                    # Wait for job cards
                    try:
                        await self.page.wait_for_selector(
                            '.shadow-job-card:has(.jobCardTitle), [class*="card-apply-content"], '
                            '[class*="srpResultCardHeader"], .card-job-detail, '
                            "[data-job-id]",
                            timeout=15000,
                        )
                    except Exception:
                        logger.warning(
                            f"[foundit] No job cards found for '{role}' page {page_num}"
                        )
                        break

                    page_jobs = await self._extract_jobs_from_page()
                    if not page_jobs:
                        break

                    new_jobs = [
                        j for j in page_jobs if j.url not in {x.url for x in jobs}
                    ]
                    if not new_jobs:
                        break
                    jobs.extend(new_jobs[: max_jobs - len(jobs)])
                    logger.info(
                        f"[foundit] '{role}' page {page_num}: "
                        f"found {len(page_jobs)} jobs (total: {len(jobs)})"
                    )

                except Exception as e:
                    logger.error(
                        f"[foundit] Error scraping '{role}' page {page_num}: {e}"
                    )
                    break

        # Deduplicate by URL
        seen_urls = set()
        unique = []
        for j in jobs:
            if j.url not in seen_urls:
                seen_urls.add(j.url)
                unique.append(j)

        return unique

    async def _dismiss_banners(self):
        """Dismiss cookie consent and notification banners."""
        try:
            for selector in [
                "#onetrust-reject-all-handler",
            ]:
                btn = await self.page.query_selector(selector)
                if btn and await btn.is_visible():
                    await btn.click()
                    await self._random_delay(0.3)
        except Exception:
            pass

    async def _extract_jobs_from_page(self) -> List[Job]:
        """Extract job listings from the current Foundit search results page."""
        jobs = []

        # Foundit uses various card structures — try multiple selectors
        card_selectors = [
            ".shadow-job-card:has(.jobCardTitle)",
            '[class*="srpResultCardHeader"]',
            '[class*="jobCard"]',
            '[class*="card-apply-content"]',
            ".card-job-detail",
            "[data-job-id]",
        ]

        cards = []
        for selector in card_selectors:
            cards = await self.page.query_selector_all(selector)
            if cards:
                break

        # Fallback: use JavaScript to extract structured data from the page
        if not cards:
            return await self._extract_jobs_js()

        for card in cards:
            try:
                job = await self._parse_job_card(card)
                if job and job.title:
                    jobs.append(job)
            except Exception as e:
                logger.debug(f"[foundit] Error parsing card: {e}")
                continue

        return jobs

    async def _parse_job_card(self, card) -> Job:
        """Parse a Foundit job card into a Job object."""
        # Title
        title_el = await card.query_selector(
            '.jobCardTitle a, [class*="jobTitle"], [class*="job-title"], '
            '[class*="CardHeader"] a, h2 a, h3 a, a[title]'
        )
        title = ""
        if title_el:
            title = (await title_el.inner_text()).strip()
            if not title:
                title = (await title_el.get_attribute("title") or "").strip()

        if not title:
            text = await card.inner_text()
            lines = [l.strip() for l in text.split("\n") if l.strip()]
            title = lines[0] if lines else ""

        if not title:
            return None

        # Company
        company_el = await card.query_selector(
            '.jobCardCompany, [class*="companyName"], [class*="company-name"], '
            '[class*="Company"], [class*="jobCompany"]'
        )
        company = (await company_el.inner_text()).strip() if company_el else "Unknown"

        # URL
        link_el = await card.query_selector(
            'a[href*="/job/"], a[href*="/jobs/"], a[href*="job-detail"]'
        )
        url = ""
        if link_el:
            href = await link_el.get_attribute("href")
            if href:
                url = (
                    href if href.startswith("http") else f"https://www.foundit.in{href}"
                )
        if not url:
            return None

        # Location
        location_el = await card.query_selector(
            '[class*="location"], [class*="Location"], [class*="cardLocation"]'
        )
        location = (await location_el.inner_text()).strip() if location_el else ""

        # Experience
        exp_el = await card.query_selector(
            '.jobCardExperience, [class*="experience"], [class*="Experience"], [class*="expText"]'
        )
        experience = (await exp_el.inner_text()).strip() if exp_el else ""

        # Salary
        salary_el = await card.query_selector(
            '[class*="salary"], [class*="Salary"], [class*="salaryText"]'
        )
        salary = (await salary_el.inner_text()).strip() if salary_el else ""

        # Skills
        skill_els = await card.query_selector_all(
            '[class*="skill"], [class*="Skill"], [class*="tag"], [class*="chip"]'
        )
        skills = []
        for el in skill_els:
            text = (await el.inner_text()).strip()
            if text and text not in skills and len(text) < 50:
                skills.append(text)
        if not skills:
            # Current cards render skills beside a literal Skills: label.
            skills = await card.evaluate("""el => {
                const label = Array.from(el.querySelectorAll('p')).find(p => p.textContent.trim() === 'Skills:');
                const row = label?.nextElementSibling?.querySelector('p');
                return row ? Array.from(row.children).map(s => s.firstElementChild?.textContent.trim()).filter(Boolean) : [];
            }""")

        # External ID from URL
        external_id = ""
        if url:
            match = re.search(r"/job/(\d+)", url)
            if not match:
                match = re.search(r"[-/](\d{6,})", url)
            if match:
                external_id = match.group(1)

        # Posted date
        date_el = await card.query_selector(
            '[class*="posted"], [class*="Posted"], [class*="date"], [class*="Date"]'
        )
        posted_date = (await date_el.inner_text()).strip() if date_el else ""

        return Job(
            title=title,
            company=company,
            platform="foundit",
            url=url,
            location=location,
            salary=salary,
            experience=experience,
            skills=skills,
            external_id=external_id,
            posted_date=posted_date,
        )

    async def _extract_jobs_js(self) -> List[Job]:
        """Fallback: Extract job data using JavaScript evaluation."""
        try:
            raw_data = await self.page.evaluate("""() => {
                const results = [];
                
                // Try to find job cards by common patterns
                const anchors = Array.from(document.querySelectorAll('a[href*="/job/"]'));
                const seen = new Set();
                
                for (const anchor of anchors) {
                    const href = anchor.href;
                    if (seen.has(href)) continue;
                    seen.add(href);
                    
                    // Stop before a parent combines multiple job links.
                    let container = anchor;
                    for (let i = 0; i < 6 && container.parentElement; i++) {
                        const parent = container.parentElement;
                        const urls = new Set(Array.from(parent.querySelectorAll('a[href*="/job/"]')).map(a => a.href));
                        if (urls.size > 1) break;
                        container = parent;
                    }
                    
                    const text = container.innerText || '';
                    const lines = text.split('\\n').map(l => l.trim()).filter(Boolean);
                    const title = anchor.innerText.trim() || anchor.getAttribute('title') || '';
                    
                    if (title && href) {
                        results.push({
                            title: title,
                            url: href,
                            lines: lines,
                        });
                    }
                }
                return results;
            }""")

            jobs = []
            for r in raw_data:
                title = r.get("title", "")
                url_val = r.get("url", "")
                lines = r.get("lines", [])

                if not title or not url_val:
                    continue

                company = "Unknown"
                location = ""
                experience = ""
                salary = ""

                for line in lines:
                    if "yrs" in line.lower() or "year" in line.lower():
                        experience = line
                    elif "₹" in line or "lpa" in line.lower() or "lac" in line.lower():
                        salary = line
                    elif any(
                        city in line.lower()
                        for city in [
                            "bangalore",
                            "mumbai",
                            "delhi",
                            "hyderabad",
                            "pune",
                            "chennai",
                            "remote",
                            "india",
                        ]
                    ):
                        location = line

                external_id = ""
                match = re.search(r"/job/(\d+)", url_val)
                if match:
                    external_id = match.group(1)

                jobs.append(
                    Job(
                        title=title,
                        company=company,
                        platform="foundit",
                        url=url_val,
                        location=location,
                        salary=salary,
                        experience=experience,
                        external_id=external_id,
                    )
                )

            return jobs

        except Exception as e:
            logger.error(f"[foundit] JS extraction failed: {e}")
            return []
