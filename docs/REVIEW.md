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


## Application pipeline review (2026-10-20)

The reported live run stopped before submission: Hirist and LinkedIn failed stale login checks, while the other platforms had no candidates passing the saved filters. Hirist now recognizes its current profile-avatar test ID on /jobfeed; the shared authentication check waits for member navigation to hydrate and rejects login/checkpoint redirects. Existing LinkedIn navigation support is retained.

Application selection now reports scored/shortlisted totals and mutually exclusive score, experience and title exclusions, without lowering the user's preferences. The final Apply event preserves selected/processed counts and reports the actual login blocker. The dashboard aggregates totals across platforms and renders per-platform application outcomes, including historical run errors. Per-run attempt limits are separated from the persistent platform daily quota, so a one-job run does not incorrectly consume the entire permitted day after a previous attempt.

Validation: 106 Python/installed-Chrome tests and 8 frontend tests passed, followed by 5 application-readiness tests including the additional daily-quota regression. Production frontend rebuilt; local server started. Live submission testing requires the user's native Chrome connection approval and is tracked separately from these fixture tests.

Follow-up validation on the same date: 19 affected Python/browser tests and 9 frontend tests passed after the final changes. Cumulative progress now retains known candidate counts when older terminal errors contain zero counters, without rewriting saved events. The reported historical run correctly exposes five Hirist candidates plus one LinkedIn candidate. Connection failures have an explicit browser-approval blocker, and the activity stream explains the native Chrome permission step. Desktop and 390-pixel mobile checks reported no page errors or horizontal overflow. Ruff checks and the production build passed.

Live evidence: regular Chrome Profile 2 authenticated Hirist successfully, and a dry run on the highest-ranked eligible Sciative Solutions Python/Django/Flask listing found its Apply control without clicks or uploads. Two subsequent one-job live runs through the dashboard timed out before Chrome granted their new connection requests; both retained zero processed jobs and made no application attempts. This verifies session recognition and preflight only, not real submission or employer form completion. No real application was submitted in these tests.

### Live confirmation follow-up (2026-10-20)

After a new Chrome connection was approved, the one-job live run submitted the Sciative Solutions Python/Django/Flask application. Hirist displayed “Your application has been submitted successfully!” in the saved post-click screenshot. The adapter did not yet recognize that exact wording and conservatively recorded review. Added an anchored, Hirist-specific confirmation selector. All 27 application/browser tests passed, including new coverage for this one-click confirmation, a negative sentence and a confirmation already present before any click.

The confirmed application and its run were reconciled locally from the saved evidence without another application click. The recorded time uses the original screenshot/review event (06:38:52 UTC, 12:08:52 IST); original logs and a private pre-correction snapshot remain available. Dashboard verification showed one confirmed Hirist application and zero jobs awaiting review. This is evidence for that specific Hirist flow, not universal submission support across other platforms or employer forms.

A second one-job live run then applied to Bridgehorn's Software Engineer listing using the corrected adapter. It returned one explicit confirmation, zero review outcomes and a completed run automatically; no record reconciliation was needed. Both jobs are terminally applied and excluded from the normal candidate queue. Live testing stopped after these two confirmed Hirist applications.

## Cross-platform workflow validation (2026-10-20–21)

The requested all-platform run discovered 94 listings across Wellfound, Hirist and Glassdoor, inserted 10 new eligible records, scored all 10, and confirmed one further Hirist submission. Cutshort redirected to its signed-out homepage; the user subsequently requested that it be skipped. Foundit remained disabled. A previously saved LinkedIn listing had expired; its screenshot explicitly showed “No longer accepting applications.” Its local status was corrected to expired with the original run events retained and no submission click.

Live inspection identified and corrected LinkedIn's current title/company/location selectors and repeated-page handling; Wellfound's recommendation-card container and member navigation; Glassdoor's member controls; and LinkedIn's expired-listing wording. Cutshort's signed-out redirect now reports a specific sign-in requirement. Gemini returned service errors, so matching now falls back for the remainder of that matcher instance after one service failure rather than waiting through the same failure for each job. A new matcher retries the service; malformed JSON alone does not disable subsequent requests.

Retesting verified four newly discovered LinkedIn jobs were scored and correctly held below the saved 50-point threshold. Wellfound's retest extracted three cards with company/location metadata, inserted and scored one new job, and also correctly skipped submission below the threshold. Regular-Chrome authentication was positively verified for Wellfound, Glassdoor and LinkedIn. Read-only application preflight found Apply controls on Wellfound and LinkedIn without clicking, uploading or submitting. Glassdoor's sampled listing did not expose a recognized Easy Apply control. These results do not establish live submission support for those three platforms; only Hirist has confirmed live submissions so far.

Final automated validation at this point: 123 Python/installed-Chrome tests passed, plus 9 frontend tests. The dashboard reports three confirmed applications in total, all Hirist, and zero jobs awaiting review. The application's private data directory retains detailed run results and screenshots; these are excluded from the source archive.

Glassdoor follow-up: live inspection showed a `button[data-test="easyApply"]` on the sampled listing. Added that current selector and a shared bounded wait for application controls to render, while checking verification, existing confirmation and expired states before any click. The corrected Glassdoor adapter passed a live dry run: Apply found, zero clicks/uploads/submissions. Wellfound and LinkedIn also passed live read-only preflight. Their actual submissions remain untested because the saved score threshold excluded the available candidates.

The final application regression suite passed all 30 tests after the rendering-wait change, including delayed Apply controls and delayed expired notices. Ruff checks passed. The earlier complete 123-test suite and 9 frontend tests remain the broader validation baseline.


## Lower score threshold and application follow-up (2026-10-22)

The user's saved minimum score was changed through the profile API from 50 to 10. This is the application's 0–100 relevance score, not a literal percentage of resume keywords. The existing queue changed from 6 eligible records to 155 before the new tests (Wellfound 6, Hirist 52, LinkedIn 74, Glassdoor 23). Existing title, experience, daily quota and duplicate-application checks remain active. Cutshort had no queued candidates and Foundit stayed disabled.

A one-job-per-platform live run confirmed a fourth Hirist application overall. Wellfound's selected listing was unavailable; a later read-only check established the exact expired notice, which is now recognized. Its review status was corrected to expired with an audit snapshot. LinkedIn showed an informational pre-apply reminder; support is restricted to that exact screen and same-platform continuation links. Follow-up testing reached an unsubmitted contact form. Glassdoor opened Indeed Smart Apply in a separate tab and was correctly left for manual completion; the result now includes the destination host without query parameters. A second Wellfound listing reached employer-specific screening questions that require explicit answers.

Application transitions now wait up to 10 seconds for a form, confirmation, known informational step, verification block or child tab. Native HTML dialogs are supported. Input labels wrapped around controls are read even when a site's `for` attribute is broken. Hidden native radio/checkbox controls with visible labels are no longer silently ignored. These changes preserve explicit confirmation before recording a submission and do not retry uncertain submissions.

Validation for the final changes: 48 application/browser regression tests passed and Ruff passed. The final LinkedIn retest advanced to the resume page (2/4) but stopped with no recognized next/submit control; it remains in review and is not a confirmed submission. Further inspection showed native dialog content can render after the dialog itself and identified a missing phone-country answer. The worker now waits for form controls; calling-code selection uses the saved international phone only when a unique option matches. Thirteen targeted regression rechecks passed after these changes. The last live retest did not expose a supported application form or confirmation and remains in review; LinkedIn is not established as reliable unattended submission. Four confirmed Hirist applications remain the only established live successes.
