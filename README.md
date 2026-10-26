# JobPraapti

[![Tests](https://github.com/Daksha009/JobPraapti/actions/workflows/tests.yml/badge.svg)](https://github.com/Daksha009/JobPraapti/actions/workflows/tests.yml)
[![Python 3.11 | 3.12](https://img.shields.io/badge/python-3.11%20%7C%203.12-blue.svg)](https://www.python.org/)
[![React 19](https://img.shields.io/badge/frontend-React%2019%20%2B%20TypeScript-61dafb.svg)](https://react.dev/)

A local-first, privacy-respecting automation workspace for job discovery, AI candidate matching, and smart application submission across **LinkedIn, Wellfound, Hirist, Cutshort, Glassdoor, and Foundit**.

---

## Architecture at a Glance

```
                         ┌───────────────────────────────────────────────┐
                         │               JobPraapti Core                 │
                         ├───────────────────────┬───────────────────────┤
                         │    Web Dashboard      │       CLI Engine      │
                         │ (React 19 + Waitress) │   (Click + Asyncio)   │
                         └───────────┬───────────┴───────────┬───────────┘
                                     │                       │
           ┌─────────────────────────┼───────────────────────┼─────────────────────────┐
           ▼                         ▼                       ▼                         ▼
   ┌───────────────┐         ┌───────────────┐       ┌───────────────┐         ┌───────────────┐
   │ Job Scrapers  │         │   AI Matcher  │       │ Auto-Applier  │         │ Local Storage │
   ├───────────────┤         ├───────────────┤       ├───────────────┤         ├───────────────┤
   │ • LinkedIn    │         │ • Gemini Flash│       │ • Easy Apply  │         │ • SQLite DB   │
   │ • Wellfound   │ ──────▶ │ • Heuristic   │ ────▶ │ • Form Fill   │ ──────▶ │ • DPAPI Vault │
   │ • Hirist      │         │   Fallback    │       │ • Review Flow │         │ • Chrome Sess │
   │ • Cutshort    │         └───────────────┘       └───────┬───────┘         └───────────────┘
   │ • Glassdoor   │                                         │
   │ • Foundit     │                                         ▼
   └───────────────┘                        [ Installed Google Chrome Profile ]
```

---

## Key Highlights

- **Local Credential Storage**: Passwords and API keys are stored with Windows DPAPI encryption (`data/credentials.dpapi`). Resumes, session cookies, personal YAML profiles, and SQLite databases are excluded by `.gitignore`; audit tracked files and history before sharing.
- **Native Chrome Session Reuse**: Connects to your installed Google Chrome via remote debugging. Uses your active, logged-in sessions without extracting cookies to plain disk or requesting your passwords.
- **Dry-Run by Default**: Never submits an application unexpectedly. The `--live` flag and deliberate dashboard confirmation are strictly required to click final submit buttons.
- **AI-Powered & Offline Matching**: Scores job descriptions against your resume using Gemini Flash with automatic fallback to deterministic role-keyword and skill-overlap scoring.
- **Human-in-the-Loop Review Queue**: Ambiguous questions, complex ATS redirects, and unexpected screening fields halt the application and route it to an explicit review queue instead of hallucinating answers.
- **Concurrency & Quota Controls**: Enforces per-platform daily limits (resetting at 00:00 UTC) with file locks and atomic database claims. Uncertain attempts remain in Review to prevent automatic retries.

---

## Platform Adapters

| Platform | Discovery Method | Application Support | Login & Session Method | Default Status |
| :--- | :--- | :--- | :--- | :--- |
| **LinkedIn** | Keyword & location search, experience filters | Multi-step Easy Apply modal forms | Chrome session / Interactive | **Enabled** |
| **Wellfound** | Role & location feed with pagination | Supported one-click application dialogs | Chrome session / Interactive | **Enabled** |
| **Hirist** | Category browsing & search queries | Direct one-click application flows | Chrome session / Interactive | **Enabled** |
| **Cutshort** | Search URLs & category scraping | Native candidate application workflows | Chrome session / Interactive | *Disabled (temporarily skipped)* |
| **Glassdoor** | Role & location search | Supported Easy Apply dialogs | Chrome session / Interactive | **Enabled** |
| **Foundit** | Role queries, freshness & experience filters | Quick Apply dialogs | Chrome session / Interactive | *Disabled (toggle in config)* |

### Live validation status (27 October 2026)

Adapter availability does not guarantee unattended submission for every employer form.

- **Hirist:** nine real submissions confirmed, including five from the latest live pipeline.
- **LinkedIn:** discovery and matching work. Regular-Chrome verification reached contact → profile-resume upload → screening → final review with no unresolved fields, after correcting nested button lookups and using user-confirmed numeric screening answers. The Submit control was verified without clicking it; no live submission confirmation was established.
- **Wellfound:** discovery works; unavailable listings are recognized and employer-specific screening questions require saved answers.
- **Glassdoor:** discovery works; sampled applications handed off to Indeed Smart Apply for manual completion.
- **Cutshort:** the latest pipeline reported sign-in required; now disabled to honor the requested skip.
- **Foundit:** disabled and not live-validated.

The minimum match score is configurable in My profile (`preferences.min_match_score`, 0–100). It is a relevance score, not a literal percentage of resume keywords. Lowering it broadens the candidate queue; it does not bypass required answers or confirm an application.

---

## Quick Start

### Option A: Windows 1-Click Launch (Recommended)

1. **First-time setup**:
   Double-click `Setup-JobPraapti.cmd`. This creates your Python virtual environment and installs all dependencies.
2. **Start the application**:
   Double-click `Start-JobPraapti.cmd`.
3. Open [http://127.0.0.1:5000](http://127.0.0.1:5000) in your browser.

> [!NOTE]
> Ensure Google Chrome is installed. In a Chrome version that provides the setting, enable **Allow remote debugging** under `chrome://inspect/#remote-debugging` so JobPraapti can interact with your existing sessions upon prompt approval.

---

### Option B: Manual Setup (CLI)

Windows is required for the encrypted credential vault. Browser and isolated test helpers also support other operating systems; the full credential-storage workflow is not cross-platform.

```powershell
# 1. Clone repository and enter directory
git clone https://github.com/Daksha009/JobPraapti.git
cd JobPraapti

# 2. Create and activate virtual environment
python -m venv .venv
# Windows:
.\.venv\Scripts\Activate.ps1
# Linux/macOS:
# source .venv/bin/activate

# 3. Install dependencies in editable mode
python -m pip install -e ".[dev]"

# 4. Initialize configuration templates
python -m jobpilot init

# 5. Verify local environment and browser connection
python -m jobpilot doctor
```

---

## Configuration

JobPraapti keeps all user-specific data strictly decoupled from source code:

| File | Purpose |
| :--- | :--- |
| **`.env`** | Runtime variables and optional plaintext fallback credentials (prefer the dashboard vault): `DASHBOARD_PORT`, `JOBPILOT_TIMEZONE`, `GEMINI_MODEL`. |
| **`config/profile.yaml`** | Personal contact info, target roles, experience range, skills, and screening answers. |
| **`config/platforms.yaml`** | Enabled platforms, daily attempt limits, search URLs, delays, and selector overrides. |
| **`config/resume.pdf`** | Local candidate resume used for skill parsing and application attachment. |
| **`data/credentials.dpapi`** | Encrypted credential vault generated on-demand (passwords, Gemini API key). |

### 1. Screening Answers (`config/profile.yaml`)

JobPraapti answers screening questions deterministically without inventing data. Supply answers in `config/profile.yaml`:

```yaml
personal:
  full_name: "Your Name"
  email: "your.email@example.com"
  phone: "+91-9876543210"
  location: "Bangalore, India"

preferences:
  roles:
    - "Software Engineer"
    - "Full Stack Developer"
  min_experience_years: 1
  max_experience_years: 3

application_defaults:
  years_of_experience: 2
  notice_period: "30 days"
  current_ctc: "12 LPA"
  expected_ctc: "18 LPA"
  answers:
    "How many years of Python experience do you have?": 2
    "Are you comfortable working in a hybrid environment?": true
    "Do you require visa sponsorship?": false
```

For written questions, enable **Prepare written answers using my resume and the job description** in My profile (`application_defaults.compose_narrative_answers: true`). Supported interest/background questions use skills present in both the resume and the job description, with a supporting resume excerpt. This runs locally and does not require an AI API. Missing evidence, factual declarations, salary amounts, and consent are never invented.

Open a job in Opportunities to view **Application answers**, inspect resume evidence, paste a manual screening question, or save a job-specific answer. Job-specific answers take priority over the general profile. Saving an answer does not resubmit the job. Verify uncertain submissions on the platform before shortlisting them again; use **Mark as applied** only after the platform confirms a manual completion.

The worker leaves incomplete forms open in regular Chrome and pauses that platform when review is needed. Known Glassdoor redirects to Indeed Smart Apply have a dedicated handoff path; unsupported destinations and verification screens still require manual completion. Adapter fixtures passing does not establish live support for every employer's form.

### 2. Platform Overrides (`config/platforms.yaml`)

If a job portal updates their DOM, you can override CSS selectors without touching Python code:

```yaml
platforms:
  linkedin:
    enabled: true
    daily_limit: 20
    application:
      apply_selectors:
        - 'button[aria-label*="Easy Apply"]'
      submit_selectors:
        - 'button[aria-label*="Submit application"]'
```

---

## CLI Reference

The `jobpilot` CLI provides full programmatic control over all pipeline stages:

```powershell
# Run diagnostics
python -m jobpilot doctor

# Discover and rank listings without applying
python -m jobpilot run-daily --no-apply

# Run the complete pipeline in dry-run mode (safe inspection)
python -m jobpilot run-daily --dry-run

# Run live application for a single platform up to a daily limit
python -m jobpilot apply -p linkedin --live --limit 5

# Full automated daily run across all enabled platforms
python -m jobpilot run-daily --live --limit 20

# Start background scheduler (e.g., daily at 09:00 AM)
python -m jobpilot schedule --time 09:00 --timezone Asia/Kolkata --live

# Interactive sign-in to save a platform session
python -m jobpilot login -p wellfound

# Inspect review queue and manually record an application decision
python -m jobpilot jobs --status review
python -m jobpilot review 142 --status applied

# Extract skills from a resume without modifying profile
python -m jobpilot parse-resume --pdf config/resume.pdf

# Launch the Web Dashboard server
python -m jobpilot dashboard --port 5000
```

---

## Job Lifecycle & Queue States

```
                 [Scraped]
                     │
                     ▼
                 ┌───────┐
                 │  new  │
                 └───┬───┘
                     │  (Score & Filter)
                     ▼
          ┌──────────────────────┐
          │ matched / shortlisted│
          └──────────┬───────────┘
                     │  (Select Candidate)
                     ▼
          ┌──────────────────────┐
          │       applying       │ ──(Process Interrupted)──▶ [ jobpilot recover ]
          └──────────┬───────────┘                                    │
                     │                                                ▼
       ┌─────────────┴─────────────┐                           ┌──────────────┐
       │ (Confirmed)               │ (Question/Flow Ambiguous) │    review    │
       ▼                           ▼                           └──────────────┘
  ┌─────────┐                ┌───────────┐
  │ applied │                │  review   │
  └─────────┘                └───────────┘
```

- **`new`**: Crawled and stored; waiting to be scored.
- **`matched` / `shortlisted`**: Scored or manually shortlisted; the current score, experience and title filters are checked when an apply run starts.
- **`applying`**: Locked atomically by active worker to prevent duplicate submission.
- **`applied`**: Confirmed submission recorded with timestamp and platform feedback.
- **`review`**: Encountered unfamiliar screening questions or complex redirect flows.
- **`expired`**: Listing flagged as closed by the job portal.

---

## Testing & Quality Assurance

Both the Python backend and React frontend maintain strict automated CI validation:

```powershell
# 1. Run Python unit & integration tests
python -m pytest -q

# 2. Run Python linting and formatting checks
python -m ruff check jobpilot tests
python -m ruff format --check jobpilot tests

# 3. Test frontend components & types
cd frontend
pnpm test
pnpm format:check
pnpm build
```

---

## Safe Sharing & Distribution

To create a sanitized zip package safe for distribution (excluding all personal profiles, credentials, databases, and logs):

```powershell
python tools/package_source.py
```
This writes `dist/jobpraapti-source.zip` using an explicit allowlist.

---

## Disclaimer

JobPraapti is a local productivity tool designed to assist candidates with their own job search workflows. It is the user's responsibility to review application details before submission, comply with the terms of service of each respective job portal, and adhere to reasonable scraping and application limits.
