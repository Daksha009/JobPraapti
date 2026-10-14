# Architecture and extension guide

`registry.py` maps a platform name to import paths for its scraper and applier. The CLI, dashboard and scheduler discover platforms from this registry. Credentials follow `<PLATFORM>_EMAIL` / `<PLATFORM>_PASSWORD`; no settings property is required for a new platform.

```text
CLI / Flask / scheduler
          |
      pipeline.py
          |
  scraper -> SQLite -> matcher -> applier -> SQLite application history
     |                              |
     +-------- BrowserSession ------+
```

- `config.py`: home-relative paths, environment, YAML and validation.
- `browser.py`: resolves installed Google Chrome and enforces cross-process per-platform operation locks. `workspace_browser.py` opens normal Chrome tabs and discovers the regular browser's permission-based loopback CDP endpoint. Each `BrowserSession` attaches to this context, creates one worker tab, and disconnects without closing user tabs. The HTTP-only workspace marker lets the dashboard distinguish connected Chrome from unrelated browsers. Tests use the same executable resolver with isolated temporary profiles.
- `scrapers/base.py`: lifecycle, read-navigation retries, filtering and persistence.
- `applier/base.py`: session authentication, selection, quota claims, bounded form steps and verified outcomes.
- `applier/forms.py`: deterministic field labels and explicit answers; unsupported inputs become review items.
- `database.py`: SQLite transactions, deduplication, status updates, quotas and audit history.
- `ai/client.py`: optional asynchronous Gemini access with request timeout.
- `pipeline.py`: reusable orchestration. Submission errors are not retried automatically.
- `progress.py`: context-local structured event sink; scraper, matcher and applier emit curated progress without scraping logs. The web runner persists events in `web_run_events`, returns cumulative snapshots per stage/platform, and exposes a complete event download. React polls while visible; `RunProgress.tsx` displays stages, actual counts and filtered history.
- `sessions.py`: scoped platform storage clearing on explicit sign-out and reconnection tracking. It never clears regular Chrome sessions on worker startup. Native Chrome stores sessions; this module never exports tokens to application files or API responses.
- `resume_insights.py`: bounded local PDF extraction, normalized skill names, stable deduplication and editable keyword suggestions. It reuses the existing parser vocabulary. Profile writes use one atomic helper; uploads and re-extraction preserve manual skills. `Settings.search_queries` integrates keyword/role combinations into supported adapters while the base scraper ranks feed listings.

## Add a platform

1. Create `jobpilot/scrapers/example.py` with a `BaseScraper` subclass. Set `platform_name = "example"`; implement `scrape_jobs()` returning `Job` objects. Use `await self.navigate(url, wait_until="domcontentloaded")`, preserve canonical URLs/external IDs, and respect `max_pages`/`max_jobs`. Do not return fabricated listing URLs.
2. Create `jobpilot/applier/example_applier.py` with a `BaseApplier` subclass. Set `platform_name`, `HOME_URL`, `LOGIN_URL`, `allowed_domains`, positive authenticated selectors, application selectors and explicit success selectors. Scope form selectors narrowly. Override `apply_to_job()` only for a site flow the shared engine cannot express; return an `ApplicationResult` and retain dry-run and confirmation behavior.
3. Register the pair once in `registry.py`:

```python
register_platform(PlatformSpec(
    "example",
    "jobpilot.scrapers.example:ExampleScraper",
    "jobpilot.applier.example_applier:ExampleApplier",
))
```

4. Add a `platforms.example` mapping in `config/platforms.yaml` with `enabled`, `daily_limit`, page limits and delays. Add credential placeholders to `.env.example` if email/password login is supported.
5. Add synthetic card/form fixtures. Test extraction, zero-click dry run, positive login evidence, unknown questions, confirmed success, missing confirmation and duplicate prevention. Validate the live authenticated flow separately before relying on unattended submissions.

No separate CLI choice lists, dashboard platform lists or scheduler switches need to be changed. The legacy `Platform` enum is retained for compatibility; new adapters use registry names and do not require an enum entry.

## Submission invariants

The database reserves a matched/shortlisted job and attempt slot in one `BEGIN IMMEDIATE` transaction. A confirmed result atomically updates status and appends an audit event. An exception after a click is uncertain, even if the browser did not show confirmation. Such jobs remain in review; an interrupted process leaves applying status. No time-based recovery automatically requeues them.

A per-platform browser-operation lock spans authentication and the application loop. Scrapers share that lock. Another operation for the same platform receives a busy result; all platforms reuse the shared browser context. Workers attach to regular Chrome through its user-approved endpoint; no separate browser is launched. A context-local connection pool shares one connection across all platforms in a web run and disconnects without closing Chrome. Recovery requires the operation lock, so an active run cannot be reclaimed. Application popup detection checks the opener page and ignores unrelated user tabs.

Database compatibility is additive: the existing tables and columns remain valid. New application-log actions track attempt quotas. Previous applied jobs remain applied, but historical false-success entries cannot be corrected without checking the sites. Historical attempts from older versions may lack logs and cannot be retroactively counted toward the new quota.

## Limits

The React API dispatches one background web worker and persists run state; legacy synchronous API routes remain for compatibility. This is not a distributed queue. The scheduler runs one cycle at a time in its own long-lived process. One configuration home is one user's data boundary; use separate homes for separate users. Windows credentials use DPAPI. Hosted multi-user account management is not included.
