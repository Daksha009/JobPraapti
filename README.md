# JobPraapti — your private job search workspace

**Windows quick start:** double-click `Start-JobPraapti.cmd`. The website opens at [localhost](http://127.0.0.1:5000). Keep the launcher window open while using it. On a fresh computer, install Python 3.11+ and run `Setup-JobPraapti.cmd` first. The release includes the compiled frontend; Node is needed only to edit the website.

The new website uses **React, TypeScript, GSAP, Flask/Waitress and SQLite**. It includes application totals and activity charts, date/platform/search filters, CSV export, job details and review actions, a profile editor, PDF resume uploads, encrypted credential entry, interactive platform sign-in, background workflows, cancellation and persistent run history. Fonts and scripts are served locally.

1. In **My profile**, review your details, preferences, resume and screening answers.
2. In **Platforms**, **Sign in** opens regular Chrome and reuses existing logins. Complete any OTP there. Enable **Allow remote debugging** at `chrome://inspect/#remote-debugging` in Chrome 144+, then select **Verify sign-in** and allow Chrome's connection prompt. Workers never retry your password.
3. In **Automation**, start a dry run, inspect matches and review items, then deliberately select live mode when ready to apply.

**New:** Keep me signed in is always on for regular Chrome, with per-platform and all-platform sign-out controls. Resume uploads automatically extract skills and job-search keywords locally; both remain editable in My profile. For an existing resume, use **Extract from saved resume**. The custom J/arrow logo and favicon identify JobPraapti throughout the website. The `jobpilot` Python command and previous launcher filenames remain compatible.

The five active platforms are Wellfound, Hirist, Cutshort, LinkedIn and Glassdoor. Foundit is disabled. [Website operation, privacy and development](docs/WEBSITE.md) describes the new interface and its limits.

A configurable Python job discovery, matching and application assistant for **Cutshort, Wellfound, Hirist, LinkedIn, Foundit and Glassdoor**.

The pipeline discovers listings, removes duplicates, ranks them against your profile, processes supported application forms and stores outcomes in SQLite. A CLI, local dashboard and daily scheduler use the same services. Personal details belong in configuration files; adding a new user requires no Python edits.

**Verification status:** automated tests exercise synthetic listings and application forms in the device's installed Google Chrome, including a complete discovery → matching → submission → duplicate-prevention cycle. Authenticated live applications on these six sites have **not** been verified in this revision. Site selectors, account access and employer-specific forms vary. This is an application assistant with an explicit review queue, not a guarantee that every listing can be submitted unattended.

## Setup

Requires Python 3.11 or newer and an existing Google Chrome installation. From the extracted project directory:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
python -m jobpilot init
python -m jobpilot install-browser
```

On macOS/Linux, activate with `source .venv/bin/activate`. Install without `[dev]` if you do not need tests. `pip install -r requirements.txt` is also supported from the project root. Keep the source checkout: installation is editable.

Configure these files:

| File | What to set |
| --- | --- |
| Website → Platforms | Write-only credential forms; saves passwords/API key using Windows account-bound encryption |
| `.env` | Non-secret options such as model, port and timezone; environment credentials remain a CLI compatibility fallback |
| `config/profile.yaml` | Personal details, roles, skills, locations, experience range, application answers |
| `config/platforms.yaml` | Enabled platforms, page limits, daily limits, filters and optional UI selector overrides |
| `config/resume.pdf` | Your resume, or an explicit `resume.path` in your profile |

`init` copies the examples only when a destination does not exist. Existing personal files are preserved. Paths resolve against the project root, regardless of your terminal's current directory. `JOBPILOT_HOME` can select a different configuration/data directory; set it before starting the process. The `install-browser` compatibility command now **checks for installed Google Chrome**; it does not download Chrome for Testing or Chromium. If Chrome is installed elsewhere, set `JOBPILOT_CHROME_PATH` in `.env` to its executable. There is no silent browser fallback.

The launcher opens the website in regular Google Chrome. Sign-in tabs and automation reuse that profile's native sessions. Enable Chrome's permission-based remote debugging and approve its connection prompt before running automation. JobPraapti does not copy cookies, retry passwords, or launch a replacement profile. Workers close only their own tabs. Existing `data/chrome-workspace` data is preserved but unused. See the website guide for selecting a regular Chrome profile.

The Automation screen now includes live stage cards, elapsed time, current work, actual counters, a platform-filtered event stream and complete timeline downloads. The overview adds interactive CSS 3D artwork with reduced-motion support. Every page carries Daksh's footer credit.

```powershell
python -m jobpilot doctor
python -m jobpilot login -p linkedin
```

Repeat login for each enabled platform. A visible browser lets you complete SSO, OTP, CAPTCHA or 2FA. Credentials are prefilled on supported login pages; a simple email/password form can also be used automatically. Multi-stage and SSO logins may require the interactive command even with credentials configured. Login is accepted only when an authenticated UI indicator is visible. A saved profile directory alone is not proof of authentication.

Foundit remains disabled in the supplied configuration; set `enabled: true` to use it. Existing enabled settings for the other platforms are retained.

## Run the pipeline

```powershell
# Discover, score and inspect Apply controls. Does not click Apply or upload files.
python -m jobpilot run-daily --dry-run

# Discover and score only
python -m jobpilot run-daily --no-apply

# Submit eligible jobs on one platform, up to its remaining daily quota
python -m jobpilot run-daily -p linkedin --live --limit 5

# Submit on all enabled platforms
python -m jobpilot run-daily --live --limit 20

# Daily schedule; this process must remain running
python -m jobpilot schedule --time 09:00 --timezone Asia/Kolkata --live

python -m jobpilot dashboard
```

The dashboard is available at `http://127.0.0.1:5000`. **Dry run** is selected by default. To submit, choose **Live applications** and explicitly confirm that your profile and answers are ready. CLI `apply`, `run-daily` and `schedule` also default to dry run unless `--live` is specified. Dry-run discovery/matching **does** update listings and scores; its application stage does not change application status or history. It verifies the entry control only, not all later form steps.

CLI results are JSON. Invalid input and pipeline/platform failures return nonzero exit codes. Jobs requiring manual review are normal reported outcomes, not successful submissions.

## Profile answers and review

Known contact fields use your personal profile. General experience, notice period, CTC and introduction fields use `application_defaults`. Skill-specific experience, legal/work-authorization questions, choices, consent and other screening answers must be explicitly supplied. The engine does not choose Yes, the first option, or invented experience.

```yaml
application_defaults:
  years_of_experience: 2
  intro_message: "Your own truthful introduction."
  answers:
    # Examples only: replace these with your own answers and exact question labels.
    "How many years of Python experience do you have?": 2
    "Do you require visa sponsorship?": true
    "I consent to the processing of my application": true
```

Question matching ignores capitalization and punctuation, but does not guess based on partial wording. Unknown questions, including optional fields and default selected choices, pause the application for review. An explicit empty string can leave an optional text field blank. Native input/select/radio/checkbox fields and labelled resume uploads are supported. Custom widgets, external ATS redirects, extra application tabs and ambiguous flows are sent to review.

| Status | Meaning |
| --- | --- |
| `new` | Discovered; not yet scored |
| `matched` / `shortlisted` | Eligible for selection if score and experience filters pass |
| `applying` | Atomically reserved by an application run; may indicate an interrupted process |
| `applied` | Explicit site confirmation, an already-applied indicator, or a recorded manual decision |
| `review` | Unknown question, verification, unsupported flow, or uncertain submission |
| `expired` | Explicit closed-listing indication |

Only matched/shortlisted jobs are selected automatically. The configured score threshold also applies to shortlisted jobs. The experience filter uses overlapping ranges; unspecified experience is allowed. Excluded title keywords are respected. Salary and location preferences inform search/AI matching, but are not strict hard filters; offline matching uses role and skill overlap.

```powershell
python -m jobpilot jobs --status review
python -m jobpilot jobs --status applying
# After an interrupted browser has stopped:
python -m jobpilot recover 123
# Inspect the listing on the platform before requeuing an uncertain submission:
python -m jobpilot review 123 --status applied
python -m jobpilot review 124 --status shortlisted
python -m jobpilot apply -p linkedin --live --limit 1
```

Application history appears in the job detail modal. Optional review screenshots are saved under `data/review/`. The browser is closed at the end of the run; review does not keep a filled form open. A retry reloads the listing. Interrupted jobs are never automatically resubmitted.

Daily quotas count **attempts**, including attempts that need review, across process restarts. Quotas reset at 00:00 UTC; the scheduler timezone independently controls when a run starts. `--limit` caps the selected platform's daily attempt budget for that invocation, bounded by its configured `daily_limit`. For example, if five attempts were already made today, another run with `--limit 5` has no remaining slots. Database claims and per-platform browser locks prevent concurrent duplicate submissions. They cannot make a remote website and a local database one atomic transaction, so ambiguous results require review.

## Matching and resume extraction

Gemini is optional. Without `GEMINI_API_KEY`, matching runs offline; API errors also fall back to role/skill scoring. `GEMINI_MODEL` selects the model. A configured key enables sending profile/job data to Gemini. Resume extraction sends resume text only when AI extraction is enabled.

```powershell
python -m jobpilot parse-resume --no-ai
python -m jobpilot match --limit 200
python -m jobpilot jobs --min-score 70
python -m jobpilot stats
```

Resume extraction is an explicit utility: review its output and put the relevant skills/summary into your profile. It does not silently overwrite your profile. Put a reviewed cover letter in My profile; generated text is not automatically inserted into application forms. The older dashboard remains available at `/legacy` for compatibility.

## Platform behavior and maintenance

| Platform | Discovery | Application scope |
| --- | --- | --- |
| Cutshort | Configurable category/search URLs | Same-site application and candidate portal flow |
| Wellfound | Configured search URL and scrolling | Supported application dialogs |
| Hirist | Configurable categories and pagination | Supported same-site forms / confirmed one-click applications |
| LinkedIn | Keyword/location search with configurable experience and Easy Apply filter | Easy Apply dialogs, including multiple steps |
| Foundit | Role queries, experience and freshness filters | Supported Quick Apply forms |
| Glassdoor | Role/location search | Supported Easy Apply forms; external sites go to review |

These are implemented adapters, not current live-site certifications. For a changed page, inspect the browser with `--no-headless` and update its selectors. You can override adapter selectors without editing Python:

```yaml
platforms:
  linkedin:
    enabled: true
    daily_limit: 10
    application:
      # Example: verify selectors against the actual logged-in page first.
      apply_selectors:
        - 'button[aria-label*="Easy Apply"]'
```

Other override keys are `auth_selectors`, `form_selectors`, `next_selectors`, `submit_selectors`, `success_selectors` and `already_selectors`. Success selectors must match actual submission evidence. `form_selectors` must scope controls to the application form. Broad selectors can cause incorrect actions.

Cutshort's `search_urls` and Hirist's `categories` can replace the supplied engineering categories. Wellfound uses `search_url`; LinkedIn currently uses the first configured role/location. Foundit and Glassdoor use up to `max_queries` roles (default three) and the first location. Set these deliberately for your search. Empty extraction is reported as unsuccessful/uncertain because it can mean no jobs, expired login, or a changed page.

See [architecture and adding a platform](docs/ARCHITECTURE.md) and [review findings](docs/REVIEW.md).

## Tests

```powershell
python -m pip install -e ".[dev]"
python -m jobpilot install-browser
python -m pytest -q
python -m ruff check jobpilot tests
python -m ruff format --check jobpilot tests
```

Tests isolate the database/profile, remove credential variables and fulfil browser requests with local synthetic pages. They make no real applications or paid model calls. CI repeats these checks. Browser fixtures verify code behavior, not the current DOM of a third-party site.

For frontend changes, run `pnpm install --frozen-lockfile`, `pnpm build`, `pnpm test` and `pnpm format:check` from `frontend/` before Python browser tests. Build output is served from `jobpilot/dashboard/web/`.

To make a shareable source copy, run `python tools/package_source.py`. This creates `dist/jobpraapti-source.zip` from an explicit file allowlist, including examples and tests while excluding personal profiles, credentials, resumes, data and browser sessions.

## Local data

`.env`, `config/profile.yaml`, PDFs, SQLite data, browser sessions and screenshots are excluded by `.gitignore`. Never distribute those files with a source copy. Sessions and screenshots can contain account access or personal details. The dashboard binds to localhost, disables Flask debug mode, rejects foreign hosts/origins and requires a per-process request token for mutations. It is a single-user local tool, not a public multi-user service.

The Windows credential vault is `data/credentials.dpapi`. Only the same Windows account can decrypt it. The website never returns saved passwords or API keys to browser clients. Existing plaintext secret entries were removed from this installation's `.env`. Profile details, resumes, databases and Chrome sessions are separate personal data; they are not all encrypted by the credential vault. Do not share or publicly sync the working directory. Use the sanitized source ZIP when sharing.
