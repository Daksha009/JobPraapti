# Validation notes

## Application reliability follow-up — 27 October 2026

Live regular-Chrome inspection established a concrete LinkedIn failure: its Next button contains nested spans, while the old exact-text CSS selector matched the smallest text element. Exact button/link lookups now use accessible names. The adapter targets the observed Easy Apply SDUI screen before generic dialogs, formats national phone numbers when a separate calling code is present, and uploads/verifies the profile resume through the observed file-chooser widget. The real form advanced from contact details to resume selection and then to screening (step 3 of 4). No Submit action was taken in this verification.

The final live screening check filled the saved answers but exposed another blocker: LinkedIn's custom text fields reject the current-CTC, expected-CTC and notice-period strings. Native HTML validity alone did not detect this. The filler now blurs text fields and checks visible, field-associated validation messages, saves rejected questions, and shows them in the job detail panel. A salary range is never silently converted into a single salary. This application remains in Review and is not counted as submitted.

After the user supplied single numeric CTC answers, the same regular-Chrome form advanced to final review. The optional company-follow checkbox is left unchecked unless explicitly answered otherwise. All visible fields resolved and the Submit control was found. Verification stopped before Submit, leaving the completed form available in Chrome; the job correctly remains in Review until a confirmed submission.

Screening now uses saved declarations and job-specific overrides. An opt-in local composer prepares supported narrative answers from skills shared by the resume and the actual job description, retaining the resume excerpt as evidence. Missing facts remain unresolved. The Opportunities detail panel supports preparing answers for manual questions, inspecting evidence, and saving overrides without changing application status. Incomplete application tabs remain open and the affected platform pauses.

LinkedIn and Wellfound descriptions can be extracted from bounded listing sections without collecting recommendation-card text. Known Glassdoor redirects to Indeed Smart Apply have a restricted handoff path; this has fixture coverage, not a new live submission confirmation. Unknown employer destinations, login checks, verification challenges and unsupported questions still require review.

All private captures, profile details and credentials remain outside publishable source. A working-file scan checked 123 publishable files against nine saved credential values and found no matches. No commit or push was performed.

Final verification: 163 Python tests and 11 frontend tests passed, along with the TypeScript/production build, Prettier, Ruff lint/format checks, dependency consistency and Git whitespace checks. The restarted dashboard, compiled assets and six data endpoints returned HTTP 200.

After the final optional-follow correction, all 28 application-answer regression tests passed, including its new opt-out case. The final live form reached Submit-ready review without unresolved fields. The dashboard was restarted with the final code and reopened in regular Chrome.

The latest live pipeline discovered 94 listings across Wellfound, Hirist, LinkedIn and Glassdoor, scored 32 new jobs, and recorded five new Hirist submissions with explicit site confirmations. There are now nine confirmed applications, all on Hirist. The other three platforms paused for review. Cutshort was still included in that run and reported sign-in required; it is now disabled in configuration to honor the requested skip.

## Local demo walkthrough

Start the app with `.venv/Scripts/python.exe -m jobpilot dashboard --port 5000`, then open `http://127.0.0.1:5000` in regular Chrome using the configured profile.

1. **Overview / Applications:** inspect real confirmed application counts, platforms and dates. The saved workspace has nine confirmed Hirist applications; review items are not counted as applications.
2. **Opportunities:** open a job to inspect its description, match score, application timeline and answers. Prepare a written answer from the job description and resume, inspect its evidence, and save job-specific corrections.
3. **My profile:** upload a resume, extract and edit skills, configure matching preferences and explicitly supplied screening facts.
4. **Platforms:** use the regular Chrome session and its existing site logins. Session expiry and Chrome debugging permission remain controlled by Chrome and the platforms.
5. **Automation:** select a platform and run a dry run to inspect discover/match/eligibility progress, or explicitly choose live application mode. Unsupported or rejected answers pause that platform for review; an actual site confirmation is required to count an application.

Cutshort remains skipped and Foundit disabled as requested. LinkedIn's tested form reached final review with no unresolved fields; Wellfound has employer-specific screening requirements, and Glassdoor's Indeed handoff has fixture coverage without a new confirmed live submission. This is a working local dashboard with bounded application automation, not a claim of unattended success on every employer form.

## Historical pre-push validation — 22 October 2026

## Passed

- Full Python and installed-Chrome regression suite: 136 tests.
- Frontend: 9 tests, TypeScript/production build, Prettier check.
- Ruff lint and formatting checks; Python dependency consistency; Git whitespace check.
- Regular-Chrome dashboard smoke test: Overview, Applications, Opportunities, Platforms, Automation and My profile all rendered. No page JavaScript errors or failed API responses. Mobile check found no document overflow.
- Local dashboard and checked API endpoints returned HTTP 200.
- Git working files, index and existing history checked for known stored credentials and personal values. The only match was the intentional public GitHub profile URL in README repository links. Private configuration, resumes, vault and application data are ignored.

## Corrections during this check

README now distinguishes available adapters from live-validated submission support, accurately describes offline keyword scoring and Windows vault requirements, and uses supported screening-answer configuration keys. Removed an MIT badge that linked to a missing LICENSE file; no license was selected or added. Updated environment-template guidance to describe session-based sign-in and configuration-file scraping settings.

## Remaining platform limitations

Hirist has four confirmed live applications from earlier tests. LinkedIn Easy Apply remains inconsistent and uncertain attempts stay in Review. Wellfound employer screening questions need explicit answers. Sampled Glassdoor jobs open Indeed Smart Apply for manual completion. Cutshort was skipped and Foundit remains disabled. This final pre-push check made no new job submissions.

The locally saved minimum match score is 10/100; personal profile settings are intentionally excluded from Git. New installations start with the example profile and configure their own preferences.

No commit or push was performed. Publish as a local assistant with these limitations, not as universally validated unattended application automation.
