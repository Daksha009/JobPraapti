# Private website

## Start and stop

On this Windows installation, run `Start-JobPraapti.cmd`. It opens the workspace in the device's installed Google Chrome. It reuses an existing JobPraapti server if one is already listening, otherwise starts Waitress on `127.0.0.1:5000`. Ctrl+C in the launcher stops it. `DASHBOARD_PORT` in `.env` selects another port. The CLI equivalent is `python -m jobpilot dashboard`.

The server is intentionally reachable only on this computer. It rejects non-loopback Host headers and cross-origin mutations, uses a random CSRF token, blocks framing, and disables caching for personal API responses. Do not put it behind a public tunnel. It has no multi-user authentication model.

For a new user, extract the sanitized source ZIP, install Python 3.11+ and Google Chrome, run `Setup-JobPraapti.cmd`, then `Start-JobPraapti.cmd`. Enter details in My profile and credentials in Platforms. No source-code edits are needed. The Windows vault feature is not available on macOS/Linux; CLI environment credentials remain supported there.

Sign-in, automation, and automated browser tests use the installed Chrome executable. On this device it is `C:\Program Files\Google\Chrome\Application\chrome.exe`. `JOBPILOT_CHROME_PATH` can select a nonstandard installation. The existing `install-browser` command only checks availability, and nothing falls back to Chrome for Testing.

JobPraapti opens sign-in pages in **regular Chrome**, including the selected local profile. It no longer launches `data/chrome-workspace`. Existing tabs and cookies stay in Chrome; no profile or cookie copying is performed. The old isolated directory is left untouched but is no longer used.

1. In regular Chrome 144 or newer, open `chrome://inspect/#remote-debugging` and enable **Allow remote debugging**.
2. In Platforms, use **Sign in** to open each platform normally. Finish login, SSO or OTP there before connecting automation. If already signed in, the jobs page reuses that session.
3. Select **Verify sign-in** and allow Chrome's native connection prompt. The worker checks positive authenticated evidence without entering or submitting passwords.
4. Start your run. All platforms in one web run share one connection, so JobPraapti does not request permission separately for every platform. Chrome can ask again for a new connection; browser permission is separate from platform login.

The connection is discovered from Chrome's `DevToolsActivePort` metadata and uses its exact loopback WebSocket endpoint. The app fails with setup guidance if unavailable; it never launches an isolated fallback browser or changes Chrome's security settings. This uses [Chrome's permission-based existing-session connection](https://developer.chrome.com/blog/chrome-devtools-mcp-debug-your-browser-session). Only each worker's own tab is closed after completion or cancellation. The browser and existing user tabs stay open. Closing Chrome during a run interrupts its browser work.

For users with several Chrome profiles, `data/browser-preferences.json` can select `{"profile_directory": "Profile 2"}` (or `Default`, `Profile 1`, etc.; use the last directory in `chrome://version` > Profile Path). This local file contains no passwords. Without it, Chrome chooses its normal active/last-used profile. Use the same profile for sign-in and enabling remote debugging. The dashboard may stay in another browser: its Sign in buttons still open regular Chrome through the local service.

## Remembered sign-ins

**Keep me signed in** is always on for regular Chrome. JobPraapti never clears its sessions on startup, after a run or after a browser restart; persistence follows the site's cookie lifetime and your Chrome settings. It cannot prevent expiry, revocation, or security verification by a platform. Clearing browsing data, using Incognito, or disabling persistent cookies can remove a login. Worker authentication only checks existing sessions; it does not retry saved passwords.

**Sign out here** explicitly clears the selected platform's cookies/storage and closes that platform's tabs in your regular Chrome profile. **Sign out of all** applies this to every registered job platform. Both ask for confirmation explaining that normal browsing in that profile is affected. Other platforms, the dashboard and other devices are unaffected; shared SSO-provider accounts are not signed out. After an explicit sign-out, use Sign in and Verify sign-in to reconnect. Legacy session-saving opt-out settings never clear the regular browser on startup. Session controls are unavailable during an active web run.

## Resume-driven skills and searches

Upload a PDF in **My profile**, or choose **Extract from saved resume** for an existing file. Extraction happens locally with pdfplumber and the maintained skill vocabulary, without sending the PDF to an AI service. Recognized skills and up to eight initial search keywords are merged into saved preferences without removing manual entries. Edit **Your skills** and **Job search keywords**, or toggle extracted skill chips; choose **Save profile** after edits. Changes take effect on future runs and do not silently rescore previous jobs.

Keywords augment role queries on LinkedIn, Glassdoor and Foundit (when enabled). Platforms using feeds or configured category URLs rank extracted listings by keyword relevance before their result limit. All platforms use the saved skills for matching. Platform page/query limits still apply, so put the most useful keywords first. Uploads accept valid PDFs up to 5 MB and 30 pages. Scanned PDFs without selectable text report that manual skills or a text-based PDF are needed; OCR is not included. The parser can miss unfamiliar terminology, so the editable fields remain authoritative.

The product is now **JobPraapti**, with a custom J/upward-arrow SVG mark and favicon. Use `Start-JobPraapti.cmd` and `Setup-JobPraapti.cmd`; legacy launcher filenames, the Python package `jobpilot`, environment keys, data paths and API tokens remain compatible.

## Screens

- **Overview:** confirmed application totals, local-day activity, jobs discovered, shortlist/review counts, platform summaries and latest applications. Empty data stays empty; demo jobs are never inserted into the personal database.
- **Applications:** search, platform and inclusive local-date filters, pagination and CSV download. CSV exports all filtered rows, not only the displayed page. Dangerous spreadsheet formula prefixes are escaped.
- **Opportunities:** filtered roles, job descriptions, scores, shortlisting and review decisions. Mark as applied requires a deliberate confirmation. It records a manual confirmation time, not a fabricated historical submission time. Repeated confirmations preserve the first timestamp. Recover interrupted applying jobs only after their worker/browser has stopped, and check the site before retrying.
- **Platforms:** write-only credential entry, saved-state indicators, connection checks and visible browser sign-in. Foundit stays disabled. Session folders alone do not imply authentication. OTP, SSO, CAPTCHA and multi-step sign-in need user interaction.
- **My profile:** personal information, roles/skills/locations, score/experience preferences, resume PDF upload, reviewed messages and exact screening answers. Changes save atomically and are blocked during an active web run. The upload endpoint validates a readable PDF and limits it to 5 MB.
- **Automation:** discover → match → apply, individual stages, connection checks, dry/live mode, per-platform attempt caps and stop. The live panel shows elapsed time, stage states, current platform/job, discovery and application counters, matching fallback messages, item progress when a total is known, and a timestamped activity stream. Filter events by platform or download the complete timeline. The latest 200 events are displayed; aggregate counters retain earlier events. Progress uses actual events rather than an estimated percentage or ETA. Older runs retain their results but have no retroactive activity stream. One web run executes at a time. Restarted unfinished runs are marked interrupted; applying jobs require review before any retry. Runs continue only while the local Python server is running. The existing CLI scheduler is available for daily runs.

## Dates and counts

New application events use UTC. The website defaults to `Asia/Kolkata`; set `JOBPILOT_TIMEZONE` in `.env` to an IANA timezone and restart to change it. Calendar filters and daily charts use that timezone. Older timestamp strings without an offset are interpreted as UTC, matching SQLite's event log. If an imported historical record has no timestamp, it is labelled “Date not recorded” and omitted from dated charts/filters. Totals include only jobs currently marked applied. Export includes UTC time and local date.

## Credential handling

Platform passwords, emails and the Gemini API key are encrypted using Windows DPAPI in `data/credentials.dpapi`; they are never embedded in frontend bundles. Encryption is tied to the account that starts the server. Start with your normal Windows account, not a different service account. Credential fields are always blank when opened. Blank fields preserve saved values. `Vault.update` accepts an empty value for explicit deletion via local maintenance code; do not put secrets in shell arguments.

Personal profile details and resume files are intentionally editable/readable by the local application. Browser profiles and screenshots also contain sensitive data, and are not covered by the credential vault. Keep the working directory private, including any OneDrive sync settings. Share only the allowlisted source archive. DPAPI protects stored secrets, not secrets pasted into a conversation or software already running as your Windows user. Rotate previously shared credentials and replace them through Platforms.

With a Gemini key configured, matching sends relevant profile and job content to Google's API. The UI assets themselves make no CDN or analytics requests. The connection check lists available models; it does not generate content or submit applications.

## Verification on 2026-10-13

The original local profile and resume passed configuration validation, and Chromium was installed. Google's live model-list endpoint accepted the supplied key and listed the configured model. All five enabled job platforms returned `action_required`: an authenticated session could not yet be verified. No real applications were submitted. Cutshort and Glassdoor have email-only credentials supplied; use their interactive sign-in flow.

Subsequent user-run workflows discovered Wellfound roles and correctly rejected duplicate listings on repeat runs. Gemini content generation returned HTTP 503, so matching used the existing offline fallback; successful key validation does not guarantee model availability. Browser execution was then changed, at the user's request, to installed Google Chrome for all automation and tests.

A subsequent discovery run through the website found a Hirist role after applying the original preferences. Cutshort returned no listing links; LinkedIn returned HTTP 999 and Glassdoor HTTP 403. Wellfound exposed a navigation-link parsing bug: `/jobs/signup` was collected as a role. The parser now requires an actual numeric listing identifier on Wellfound's domain, with a regression test. The erroneous signup record was removed. These blocked/empty results require sign-in or site-specific follow-up; the application does not bypass verification or access blocks.

Automated tests use isolated synthetic profiles and sites. They cover all adapters, duplicate prevention, application lifecycle, truthful form answers, CSRF/host controls, the vault round trip, filtering, local date boundaries, CSV export, background cancellation, live-mode confirmation and the compiled React interface at desktop/mobile sizes. They are not a claim that current employer-specific forms have all been verified on live accounts. Complete sign-in, inspect a dry run, and verify real-site selectors for any unsupported flow.

## Development

```powershell
# Backend
python -m pip install -e ".[dev]"
python -m jobpilot install-browser

# Frontend (Node 24, pnpm 11.25.0)
cd frontend
pnpm install --frozen-lockfile
pnpm build
pnpm test
pnpm format:check
cd ..
python -m pytest -q
python -m ruff check jobpilot tests tools
python -m ruff format --check jobpilot tests tools
```

React views are separated by responsibility in `frontend/src/`. `lib.ts` contains API and formatting helpers; shared dialogs/tables live in `components.tsx`. Vite writes assets to `jobpilot/dashboard/web/`, served by Flask. `web_api.py` exposes the new routes, `analytics.py` calculates reports, `connections.py` manages account verification, `runner.py` persists and executes operations, and `vault.py` isolates Windows encryption. The existing registry and pipeline remain the sole automation entry points. New registry entries automatically appear in platform lists and the credential allowlist; add a scraper, application adapter and platform config as described in ARCHITECTURE.md.

The visual direction draws on the expressive typography and motion of GSAP and the composed component layouts of ThreeUI/21st.dev. Tasteskills.dev could not be loaded during reference research. Artwork is CSS/SVG and motion uses GSAP with reduced-motion support. Fonts are bundled locally.

### Latest LinkedIn session verification

After manual sign-in in regular Chrome Profile 2, two independent connections both verified LinkedIn authentication without password entry. The adapter supports both legacy navigation and the newer React member navigation, including delayed hydration. No applications were submitted in this verification. Other platforms still require individual authentication checks.
