# Three-round test and improvement report

Historical report. The later whole-app simplified-interface testing and final
closed-posting fix are documented in ACCEPTANCE_TESTS.md (40 tests passed).

The existing project was tested, improved, and retested in three successive rounds. All changes are local. No credentials or browser session data were exported or packaged.

| Round | Findings and changes | Verification |
| --- | --- | --- |
| 1 — Input and destination validation | Missing CSV cells could raise an AttributeError; Excel-style semicolon files were unsupported; errors lacked source rows; output problems appeared too late. Added comma/semicolon/tab CSV support, blank-cell handling, file/row errors, UTF-8 guidance, unsupported-file/credential-URL rejection, and non-destructive destination preflight. | 12 tests passed in 17.888 seconds. |
| 2 — Recovery and extraction reliability | A failed Excel replacement lost the latest attempted row; interrupted jobs needed manual rebuilding; delay was uninterruptible; ordinary job text could trigger rate-limit detection; legacy expansion failure was not recorded. Added atomic progress snapshots, explicit resume/retry without duplicates, recovery without network when already complete, interruptible delay, scoped access checks, and partial status for collapsed descriptions. | 17 tests passed in 16.389 seconds. Simulated an Excel sharing failure and restored the row from progress with browser access forbidden by the test. |
| 3 — Desktop workflow and results | Added validation preview, progress counts, resume control, timestamped suggested filenames, clear-files and open-folder actions, disabled mutable inputs during runs, and protection against stale result buttons. Excel gained clickable source URLs, status colors, expansion flags and missing-field details. Added CLI no-input/dry-check cases. | Final suite: 23 tests passed. Includes real Tk event loops with a local mocked backend; GUI scenarios run in isolated processes to avoid Tcl interpreter cleanup on another thread. |

## Final live checks

The improved exporter used the session signed into manually by the user. It exported:

| Job | Employer | Location | Result |
| --- | --- | --- | --- |
| AI Engineer – FinTech | SYTalent | Gurugram, Haryana, India | ok |
| Artificial Intelligence Engineer | Grey Chain AI | New Delhi, Delhi, India | ok |
| AI Developer | TekSalt Solutions | Noida, Uttar Pradesh, India | ok |

Deliverable: `exports/delhi_ncr_improved.xlsx`. A sibling `delhi_ncr_improved.progress.json` supports recovery and resume. The previous verified workbook was preserved.

`verify_live_output.py --workbook exports/delhi_ncr_improved.xlsx` passed fresh-page comparisons for all three jobs. It checked full expanded descriptions (including final paragraphs), titles, employer, location, posting time, available salary, employment/workplace types, and company industry, size, headquarters, website, About, founded year and specialties. Job URL remains first in all five sheets and no scraped value became a formula.

Company size and industry remained distinct: SYTalent = Human Resources Services / 11–50 employees; Grey Chain AI and TekSalt = IT Services and IT Consulting / 51–200 employees. Associated-member counts are retained alongside the company-size range. Description lengths were 1,367, 3,373 and 2,719 characters.

Completed-batch `--resume` restored all three successful rows without browser requests. The actual Tkinter Start → Continue → Save flow also passed against one live job using a temporary workbook, exercising the worker, queue, output and restored control states.

Evidence: `exports/delhi_ncr_improved_live_verification.json` and associated browser screenshots. Automated local checks: `python -m unittest discover -s tests -v`. Historical initial Windows evidence remains in `WINDOWS_TEST_RESULTS.txt`.

## Limits and deferred additions

- This verifies a three-job sample and the listed failure paths; it does not establish support for every LinkedIn layout. Access restrictions still stop the batch.
- Explicit seniority was unavailable. Salary was visible for Grey Chain only; missing data remains blank and is listed in `missing_fields`.
- Native Windows click geometry and screenshot capture were unavailable. GUI callback/state tests passed and Playwright browser screenshots were inspected; a full native mouse/keyboard and visual-accessibility audit remains unavailable.
- General search-result crawling, automated applications, messaging, following, CAPTCHA handling, and parallel scraping were not added.
- Resume requires the original ordered URL list and matching progress snapshot; it does not import arbitrary historic workbooks. Successful cached rows are intentionally retained, so choose a fresh export when updated posting data is required.
- The five-sheet workbook retains full text but only shows a preview in fixed-height rows. Use the formula bar or expand row height to read long text in Excel.

## Distribution and privacy

`package_project.py` builds `../linkedin-job-exporter-improved.zip` from an explicit source allowlist and includes `SHA256SUMS.txt`. It excludes `.linkedin-profile/`, `.venv/`, `exports/`, actual workbooks, progress snapshots and screenshot diagnostics. The included `examples/sample_output.xlsx` is the original clearly fictional example. The installed workspace keeps the user's profile local; copying the source ZIP to another folder requires setup and a new manual sign-in.
