# Review and corrections

Reviewed the six scrapers/appliers, configuration, models, SQLite persistence, AI helpers, CLI, scheduler and dashboard. The supplied folder had no Git repository metadata, so changes were made directly in the workspace.

| Finding in the original implementation | Correction |
| --- | --- |
| Several appliers treated a click, closed dialog or external redirect as a successful application | Shared typed outcomes; success requires an explicit confirmation; uncertain results go to review |
| Cutshort's dry run could reach application clicks before checking the flag | All adapters stop before the first application click in dry run |
| LinkedIn selected Yes or the first dropdown option and used generic experience values | Exact profile answers; unknown questions/default choices stop the flow |
| Introduction messages contained hardcoded candidate technologies | User-supplied introduction and cover-letter text only |
| Application loops were copied six times | One shared lifecycle/form engine and thin platform UI adapters |
| Per-run limits were described as daily limits; simultaneous runs could duplicate work | Transactional attempt quotas and job claims, persistent across restarts; browser profile locks |
| Application selection included unscored jobs, ignored shortlists in some flows and applied disabled platforms via some entry points | Matched/shortlisted eligibility and enabled-platform selection shared across entry points |
| Scrapers started fresh sessions while login/appliers saved profiles in relative directories | A common home-relative persistent browser profile for discovery and application |
| Login success was inferred from missing login buttons | Positive authenticated UI evidence required |
| `JobMatcher` raised when no API key existed despite documented offline fallback | Offline scoring works without credentials; async current SDK wrapper and configurable model |
| Experience filtering hardcoded junior title exclusions and mishandled lower bounds / months / open-ended requirements | Profile-driven range overlap, months and Unicode-dash parsing; title exclusions stay configurable |
| Cutshort crawled ancestors far enough to mix adjacent cards' metadata | Card-scoped parsing and a regression test using two different companies |
| Foundit used job type as freshness, and several search filters ignored configured experience | Corrected query inputs; configurable categories/search URLs and bounded query counts |
| Scrape errors/empty pages could look like a successful zero-result run | Navigation errors and uncertain empty extraction are visible in reports |
| Database sort/update column names were interpolated without validation | Allowlisted identifiers, validated pagination/statuses/scores, canonical URLs and external-ID deduplication |
| Updating match scores could reset a terminal application status | Scoring preserves status unless it was new |
| Dashboard accepted cross-origin mutations, ran with debug enabled, and allowed arbitrary statuses | Local host/origin checks, request token, validated inputs, debug off and guarded status transitions |
| Dashboard read an obsolete apply response shape and referred only to Cutshort | Aggregated per-platform results, review counts and explicit dry-run control |
| Personal profile/resume files were not ignored | Ignore rules and a source-only sharing procedure |
| Website sign-in and automation used different Chrome profiles | Dashboard, normal sign-in tabs and worker tabs now share one persistent Chrome workspace; unrelated browsers show a switch button |
| Multiple browser tabs were mistaken for application popups | Only tabs opened by the worker page trigger application review |
| Background runs exposed only a generic message and final JSON | Persisted stage/job events, cumulative counters, live timeline, platform filters and complete event download |
| Successful dry-run checks were marked as failed runs because they did not submit | Expected dry-run/already-applied/expired outcomes no longer flag failure |

## Validation

Current local validation result (2026-10-14): **90 Python/browser tests passed** on Python 3.12 / Windows using installed **Google Chrome**, plus **6 frontend tests**. Production React/TypeScript build, Ruff lint/format, frontend formatting and dependency checks passed. A subsequent keyword-priority refinement passed all seven resume/session tests. The shareable source ZIP is checked against local saved secrets in memory and excludes personal configuration, resumes, databases and browser sessions. The earlier CLI source archive was also extracted and smoke-tested with `--help`, `init` and `stats`. The CI workflow is provided but has not been executed on GitHub in this workspace.

Saved-session tests cover a real Chrome process restart, retained session cookies, unchanged expiry, expired-cookie rejection, per-platform cookie/storage clearing, preservation of unrelated tabs, and preventing automatic re-login after explicit sign-out. Resume tests cover valid and invalid PDFs, scanned/empty text, alias deduplication, token boundaries, preserved manual skills, editable keywords reaching search URLs, and the full upload/edit/save browser flow. The supplied one-page resume was parsed locally: 27 recognized skills and eight recommended search keywords, with existing manual skills preserved and a private backup made before the update. No resume content was sent to an external extraction service.

The browser resolver selects the device's installed Google Chrome executable for every application session and browser fixture. The setup command checks that executable instead of installing a testing browser; missing Chrome fails clearly. The dashboard launcher opens a shared JobPraapti Chrome workspace, separate from the everyday Chrome profile. Tests cover executable selection, no-fallback behavior, actual Chrome version, shared cookies across worker reconnects, preserved user tabs, progress persistence through completion/cancellation and counters beyond the visible event limit. Live local inspection confirmed that the Chrome workspace recognizes its browser marker and renders all five same-browser sign-in links. Read-only live checks still require interactive authentication on all five job sites; Gemini's model-list check succeeds.

The test suite includes SQLite concurrency and quota tests, configuration/CLI validation, dashboard request validation, browser fixtures for all six listing extractors and application adapters, multi-step forms, unknown answers, missing confirmation, and a complete synthetic pipeline with a second duplicate run. Runtime dependency consistency and Python lint/format checks are also run.

No real applications were submitted during development. Live account authentication, SSO provider behavior, platform-specific DOM compatibility and arbitrary employer ATS flows remain outside the fixture test evidence. Review/blocked outcomes for those cases are intentional and visible; the project does not claim universal unattended application support.

The Gemini integration follows Google's [SDK migration documentation](https://ai.google.dev/gemini-api/docs/migrate) and [Python SDK async usage](https://googleapis.github.io/python-genai/). API failures fall back to local matching; a configured model is still subject to availability for your account.


## Regular Chrome sign-in update (2026-10-14)

Replaced the isolated workspace launch with regular Chrome and its native permission-based endpoint. Login opens a normal tab in the user's selected profile (Profile 2 for this local installation). Worker authentication only verifies existing sessions and never resubmits stored credentials. Per-run pooling avoids separate permission prompts for each platform; denial fails the remaining checks without repeating prompts. Native sessions are never cleared on startup, including when an old isolated-workspace preference had remembering disabled. Explicit scoped sign-out remains available with confirmation covering normal browsing in that profile. Legacy connection results are not misrepresented as verified regular-Chrome sessions.

Installed Chrome 155.0.8059.40 accepted a real connection. Live read-only checks reached all five enabled platforms, but none returned a positive authenticated indicator yet; manual sign-in or verification is still needed. No real applications were submitted. The production frontend and local server were rebuilt/reloaded. Automated regression checks cover normal launch arguments, selected profile routing, local-only metadata parsing, absence of password retries, shared connections, denial handling, native-session preservation and the revised UI.

Final validation for this update: 98 Python/installed-Chrome tests and 6 frontend tests passed; Python and frontend formatting checks passed. A direct Chrome version-page check confirmed automation uses the requested Profile 2. The release contains 114 allowlisted files, with no findings against 9 known credential values. First manual platform login/session reuse remains pending user completion.

LinkedIn follow-up: after the user completed sign-in in regular Chrome Profile 2, live inspection showed the new React member navigation no longer uses the legacy global-nav selectors. The adapter now accepts the member messaging/notifications navigation pair and waits up to 10 seconds for hydration, while rejecting login/checkpoint redirects. Two separate real connections both verified authenticated status without entering credentials or submitting applications. All 19 affected session/browser tests passed, including four new LinkedIn navigation regressions. Other platforms still require independent sign-in verification.
