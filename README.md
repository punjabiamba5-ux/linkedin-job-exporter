# LinkedIn Jobs → Excel

A Windows desktop application and Python command line script for exporting specific LinkedIn job postings and their linked company About pages. Paste job links or import TXT/CSV files. Sign in yourself in the opened browser, then export to Excel. No API key is required.

**Simple desktop flow:** **1. Add job links → 2. Choose where to save → 3. Create your Excel file.** Browser and recovery settings stay under **More options**. See [QUICK_START.md](QUICK_START.md) for the nontechnical guide and [ACCEPTANCE_TESTS.md](ACCEPTANCE_TESTS.md) for the latest whole-app test evidence.

## Start on Windows

1. Install **Python 3.11 or newer** from https://www.python.org/downloads/windows/. Include the Python launcher and Tcl/Tk (both included in a standard installation).
2. Extract this entire ZIP into a folder you can write to, such as `Documents\LinkedInJobExporter`. Do not run the scripts inside the ZIP.
3. Double-click **`setup_windows.bat`** once. This installs the Python dependencies and Playwright Chromium; it requires internet access. Wait for “Setup complete”.
4. Double-click **`start_windows.bat`**.
5. In **1. Add job links**, paste one specific job URL per line, or click **Import a TXT or CSV file…**. Example: `https://www.linkedin.com/jobs/view/1234567890/` (replace the ID with a real job ID). The screen counts unique links automatically.
6. In **2. Choose where to save**, keep the suggested filename or click **Choose location…**. Then click **Create Excel file** in step 3.
7. Sign in to LinkedIn directly in the browser window that opens. Complete any verification yourself. Set LinkedIn's interface to **English** for the best structured field matching.
8. Return to the app and click **I am signed in — continue**.
9. Watch the saved-job progress. A result panel appears when a workbook is saved. Click **Open Excel file** or **Show saved folder**. **Retry unfinished jobs** appears only when needed.

Under **More options**, Microsoft Edge and Google Chrome can also be selected if installed. This uses a separate browser profile, so your usual browser login is not automatically available. Do not open multiple exporter instances using the same profile.

Under **More options**, click **Open sign-in browser only** to sign in and browse without entering job URLs. Copy specific job links there. Clicking **I am signed in — continue** in this mode closes the browser without creating a workbook; the browser profile is retained for your next export. The continue button appears only while a browser is waiting for you.

Windows setup also supports an existing `.venv`, Python on PATH, and a Python 3.11 installation under `%USERPROFILE%\.local\bin` when the `py` launcher is unavailable.

## Input formats

- Paste one job URL per line. Duplicate job IDs are removed, preserving order.
- TXT: one URL per line; blank lines and lines beginning with `#` are ignored.
- CSV: include a `job_url` column. Headers `url`, `job url`, and `job link` also work. Comma, semicolon and tab delimiters are detected from the header. Additional columns and empty URL cells are ignored. UTF-8 and UTF-8 with BOM are supported. Invalid entries identify their file and row; unsupported file types and encodings produce an actionable error.
- A LinkedIn search link with a specific `currentJobId` can be normalized to that single job. General search result crawling, pagination, and discovering new jobs are not implemented.
- Sample inputs are in `examples/`; their job IDs are placeholders.
- `examples/sample_output.xlsx` demonstrates the Excel layout using clearly labeled fictional data.

## Excel output

**The first column in every sheet is `job_url`.**

| Sheet | Content |
| --- | --- |
| Jobs | One row per attempted job, with all mapped job and company fields |
| Companies | Company information associated with each attempted job |
| Descriptions | Full job description; very long descriptions use numbered continuation rows |
| Page text | Rendered main-page text collected from each job and company About page, in numbered parts |
| Long fields | Full continuation parts for fields that exceed one Excel cell |

Job fields: URL, title, employer, location, displayed posting time, salary when shown, employment type, seniority when explicit, workplace type, job function, job industries, description, primary job details, job insights, extraction timestamp, status and notes.

The Jobs sheet also includes `description_expanded` (`yes`, `no`, or `unknown`), `missing_fields`, and `application_status`. Application status is `closed`, `accepting applications`, or `unknown`, based only on the visible posting. A closed posting can be extracted successfully for reference: extraction status `ok` does not mean the job is open. The app summary and row notes flag closed postings. A missing optional field does not by itself make a row partial. Source URLs are clickable, and status cells are color coded.

Company fields: LinkedIn About URL, employer name, industry, size, headquarters, displayed website text, About description, founded year, specialties, tagline, and additional definition-list details as JSON. Company pages shared by several jobs are reused during a run when the essential company fields are available.

Posting time is preserved as displayed (for example “2 days ago”); no exact date is invented. Salary insight text is preserved without guessing currencies or ranges. Unavailable optional fields stay blank. No text-generation service is used to fill missing information.

Excel supports only 32,767 UTF-16 units in a cell. Main-sheet values are capped at 30,000 units; complete long values are preserved in **Long fields**, **Descriptions**, or **Page text**. Exported strings are stored as text, so content beginning with `=` cannot execute as an Excel formula.

## Status and stopping

- `ok`: title, employer, description, company industry, size and About text were extracted without an error, and no recognized description control remains collapsed. Other optional fields can still be blank.
- `partial`: essential fields were unavailable or the company page failed. See `notes` and **Page text**.
- `error`: job extraction failed. The failed URL remains in Excel with a reason.
- `blocked`: LinkedIn displayed a recognized login/verification checkpoint or access limit. The export stops; later URLs are not attempted.

The workbook is saved after each attempted job. **Stop** interrupts the delay between pages immediately and finishes the current browser operation before preserving completed rows. An operation may take around a minute if a page times out. Completed records remain saved if a later page fails. Input controls are disabled during an export so the displayed batch cannot change underneath the running work. Close the workbook in Excel while exporting so Windows can replace it.

To resume an earlier run, open **More options → Continue an earlier export…** and choose the workbook or its matching progress file. The app restores the original links and filename for you; click **Create Excel file**. To retry the current run, use **Retry unfinished jobs**. Successful rows are kept, while partial, error, blocked and unattempted jobs are retried once. Existing successful rows are not duplicated. Resuming still requires authorized access; checkpoints and limits stop it normally. If the batch is already successful, the workbook is restored without browser requests. Corrupt snapshots that claim success without essential data are rejected.

Each attempt is first saved atomically to a sibling progress file: `batch.xlsx` uses `batch.progress.json`. Keep this file next to the workbook. If Excel becomes locked after a run starts, the latest attempted row is still in that progress file. Close Excel and resume to recover it. A new export with overwrite starts a new batch; resume never silently merges a different URL list. Old workbooks created before progress snapshots were introduced cannot be resumed without their snapshot; export their URLs to a new filename instead.

## What “visible information” means

This project reads rendered page elements in the browser, expands recognized description controls, and performs a limited scroll. It maps common English LinkedIn job/company layouts and preserves rendered main-page text as a fallback. It does not enumerate every company tab, expand every nested section, capture images, or access hidden/internal LinkedIn APIs. A company's company-size figure can include both an employee range and an associated-member count; these are preserved as displayed.

LinkedIn changes its UI and can restrict browser automation. Signing in does not guarantee extraction succeeds. Use only access you are authorized to use and follow applicable LinkedIn terms. There is no CAPTCHA bypass, stealth browser modification, proxy rotation, or automatic verification handling. If access is limited, the project stops and records the issue. Complete verification manually and rerun later as appropriate.

## Local sign-in storage

Your credentials are entered directly on LinkedIn, never into the exporter. The browser stores session cookies and local storage in `.linkedin-profile/` beside the project. Treat that directory as sensitive: do not share it, commit it, or include it in support ZIPs. To clear the saved login, close the app/browser and delete `.linkedin-profile/`.

No cookies, passwords, or full HTML snapshots are written into Excel or progress snapshots. Both contain the exported page text, which may include account-visible or personalized content. Treat progress files like the workbook and review before sharing. The app has no analytics or remote data upload feature. The source ZIP builder uses an allowlist and excludes profiles, virtual environments, exports and progress files.

## Command line

After Windows setup, open a terminal in the project folder:

```bat
.venv\Scripts\python.exe run.py "https://www.linkedin.com/jobs/view/1234567890/" --output exports\jobs.xlsx
.venv\Scripts\python.exe run.py --file examples\jobs.txt --output exports\batch.xlsx
.venv\Scripts\python.exe run.py --file my_jobs.csv --browser msedge --delay 5 --output exports\batch.xlsx --overwrite
.venv\Scripts\python.exe run.py --file my_jobs.csv --output exports\batch.xlsx --check
.venv\Scripts\python.exe run.py --file my_jobs.csv --output exports\batch.xlsx --resume
```

You still sign in manually and press Enter in the terminal to continue. `--check` validates input and destination access without opening a browser or writing a workbook. `--resume` and `--overwrite` are mutually exclusive. Exit codes: `0` = all attempted and status `ok` (or a successful check); `2` = partial/error/blocked results or incomplete batch; `1` = setup/input/output failure; `130` = interrupted.

For macOS/Linux, create a virtual environment, install requirements and the browser, then run the CLI. The desktop UI additionally requires Tk; Linux may need browser system libraries.

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python -m playwright install chromium
.venv/bin/python run.py --file my_jobs.txt --output exports/jobs.xlsx
```

## Troubleshooting

- **Python not found:** setup accepts the Python launcher, Python on PATH, or `%USERPROFILE%\.local\bin\python3.11.exe`. Install Python 3.11+ with Tcl/Tk if none is available, then rerun setup.
- **Missing browser:** rerun setup, or select installed Edge/Chrome in the app.
- **Profile in use:** close the exporter's browser and other exporter instances. Use a different `--profile` directory for separate CLI instances.
- **Permission denied saving Excel:** close the workbook in Excel and choose a writable folder.
- **Blank fields:** verify the page is accessible, use English, check **Page text**, and inspect selectors in `linkedin_exporter/extract.js` if LinkedIn changed its layout. The app does not claim complete extraction when essential fields are missing.
- **Sign-in/checkpoint/limit:** finish sign-in or verification manually. Rerun the affected URLs once access is available. The program does not retry a blocked batch automatically.

## Validation and maintenance

Tests cover URL/file validation, description expansion, rendered text extraction, company data, checkpoint handling, company caching, saved partial batches, Excel formula safety and lossless long Unicode descriptions.

```bat
.venv\Scripts\python.exe -m unittest discover -s tests -v
```

The original six local mock tests passed on Linux. The first Windows/live update passed eight tests. The subsequent **three improvement rounds passed 12, 17 and 23 automated tests**, respectively. The final suite includes local browser fixtures, input/output failures, recovery and deduplication, CLI dry checks, and isolated real Tkinter event loops with a mocked backend. These automated tests never sign in to LinkedIn. See `QA_REPORT.md` for findings and evidence.

The latest simplified-interface acceptance passes supersede those historical counts: **33, 36, then 40 tests passed**. They exercise the entire desktop flow, failed output, overwrite refusal, moved files, import/removal, restored inputs, retry, cancellation, close-while-running and small-window scrolling. The final browser screenshot review revealed a closed posting; the exporter now flags it explicitly without clicking Apply. The actual simplified GUI exported three live jobs to `exports/delhi_ncr_final.xlsx` (the earlier `delhi_ncr_simple_ui.xlsx` is preserved). One posting is closed and retained for reference; the other two show Apply controls. Setup was also rerun successfully. Native Windows screenshot capture still times out, so native visual/mouse coverage is explicitly limited. The prepared GitHub Actions workflow runs local tests only and has not run on GitHub yet.

A manually authenticated **live Windows batch exported three jobs**: SYTalent (Gurugram), Grey Chain AI (New Delhi), and TekSalt Solutions (Noida). The original workbook is `exports/delhi_ncr_live.xlsx`; the final improved version is `exports/delhi_ncr_improved.xlsx`. All three rows have status `ok`. Independent fresh browser reads matched the titles, available job metadata, fully expanded descriptions, company About text, industry, size, headquarters, website, founding year, and specialties. The description lengths were 1,367, 3,373, and 2,719 characters. Grey Chain displayed a salary; the other two did not. Explicit seniority, job function, and job industries were unavailable and remain blank.

The real Tkinter Start → Continue → Save flow also passed a live single-job test using a temporary workbook. This exercised widget callbacks, the worker thread, event queue, completion counts, and restored button states. Native Windows screenshot capture failed, so native mouse/keyboard interaction and desktop appearance were not fully verified. Browser screenshots were captured successfully through Playwright. See `WINDOWS_TEST_RESULTS.txt` for the distinction between live and mock checks.

Selectors now support both legacy pages and the current signed-in component layout. LinkedIn can still change its UI or restrict access. General search-result crawling is not implemented; collect specific URLs in the browser. Selected-job URLs from both `/jobs/search/` and `/jobs/search-results/` are accepted.

Optional local diagnostics (require your saved manual sign-in and all other exporter browsers closed): `verify_live_output.py --workbook exports/delhi_ncr_improved.xlsx` compares the three-job deliverable to fresh visible pages; `verify_desktop.py` exercises one live export through Tkinter into a temporary workbook; `live_review.py` supports interactive page inspection. These scripts do not run with the automated test suite. Diagnostics and screenshots stay under ignored `exports/`; review personalized page captures before sharing. `package_project.py` builds a source-only ZIP with a SHA-256 file manifest.

Source references: [Playwright authentication](https://playwright.dev/python/docs/auth), [persistent browser contexts](https://playwright.dev/python/docs/api/class-browsertype#browser-type-launch-persistent-context), [openpyxl](https://openpyxl.readthedocs.io/).
