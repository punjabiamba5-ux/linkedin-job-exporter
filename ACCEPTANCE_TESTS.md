# Whole-app acceptance testing and simplified UI

## Fresh three-pass recheck (14 November 2026, India time)

After the renewed test request, the unchanged baseline passed 40 tests in 38.024 seconds. A new real-Tk 640×540 scenario then reproduced a usability failure: the result button ended below the visible viewport (bottom 792 versus viewport bottom 632). The app now scrolls to the sign-in controls and completed result, and displays the full saved filename beside the open-file actions.

The second pass added regression coverage for that issue and for changing a restored export's destination. A restored batch previously kept its resume setting and rejected a different output with a snapshot error. Changing the restored URLs or destination now resets that inherited resume setting before validation; explicit manual resume still validates the snapshot. All 42 tests passed in 47.299 seconds.

The final complete pass also verified visibility of the sign-in button in the small window: all 42 tests passed in 50.995 seconds. These are actual Tk geometry and callback checks, not native screenshot validation. A fresh live desktop export produced `exports/delhi_ncr_recheck.xlsx`, with three extraction-success rows and the closed SYTalent posting clearly flagged. Existing outputs were preserved. The remaining observations and earlier historical passes below continue to apply.

Independent live comparison of that new workbook passed for all three jobs and company About pages, including full expanded descriptions (1,367 / 3,373 / 2,719 characters), available job metadata, industry, size, About text and closure flags. Evidence: `exports/delhi_ncr_recheck_live_verification.json` and the matching browser screenshots. Fields absent from LinkedIn remain unavailable, including seniority for these examples and salary for two of them. The connected GitHub account was rechecked; its accessible repository list remains empty and the proposed repository still returns 404. Upload has not occurred.

The source ZIP was extracted into a clean temporary folder: checksums and privacy exclusions passed, and all 42 tests passed there in 43.669 seconds. Only this report changed afterward; the final archive was rebuilt with integrity and privacy checks. Profiles and real exports are excluded.

This report records the follow-up to the earlier QA_REPORT.md. Three new complete test passes were run, with fixes checked before the next pass. No claim is made that every possible LinkedIn layout or failure is covered.

| Pass | What was tested and fixed | Result |
| --- | --- | --- |
| 1 | Rebuilt the desktop around three numbered steps. The default screen explains inputs and outputs, counts duplicate links, hides optional browser/recovery controls, and shows Continue and result actions only at the correct time. Full GUI scenarios cover successful output, import/removal, invalid input, locked destinations, missing snapshots, restore, partial retry, worker failure, cancellation, closing during login, stale results, moved output and small-window scrolling. | 33 tests passed in 35.891 s. |
| 2 | Exercised damaged snapshots, cancelled company extraction and repeated access blocks. Rejected saved “ok” rows lacking essential fields and unsafe saved URLs. Found and fixed an overwrite-prompt ordering problem for a folder named `.xlsx`; added refusal-preserves-original and folder-rejection cases for the final pass. | 36-test pass completed in 34.763 s; overwrite regression cases included in pass 3. Actual three-job desktop/browser/Excel flow passed. |
| 3 | Reran the entire expanded suite after those fixes. An additional browser screenshot review found a closed posting that lacked an explicit application-status field. Added the field, summary/row warning, and no-Apply-click regression; reran the complete suite and actual desktop export. Checked Windows setup and distribution privacy. | Initially 38 tests passed; after the closed-posting fix, all 40 tests passed in 51.724 s. No test failures remain in the tested scope. |

## Actual live acceptance

Command: `.venv\Scripts\python.exe -X utf8 verify_desktop.py --file exports/live_test_urls.txt --output exports/delhi_ncr_final.xlsx`

This ran the real desktop's Create → Continue → browser extraction → Excel → ready flow using the user's previously authenticated local profile. It did not enter credentials or solve verification. The resulting workbook contains:

| Job | Employer | Location | Status |
| --- | --- | --- | --- |
| AI Engineer – FinTech | SYTalent | Gurugram | ok; application_status=closed (retained for reference) |
| Artificial Intelligence Engineer | Grey Chain AI | New Delhi | ok; Apply control visible |
| AI Developer | TekSalt Solutions | Noida | ok; Apply control visible |

Command: `.venv\Scripts\python.exe -X utf8 verify_live_output.py --workbook exports/delhi_ncr_final.xlsx`

Independent fresh reads passed against the refreshed `delhi_ncr_final.xlsx`, including the new closure flag for each job. They matched full expanded descriptions, titles, available job metadata, company About text, industry, size, headquarters, website, founding year and specialties for all three jobs. Descriptions were 1,367, 3,373 and 2,719 characters. Salary was shown only for Grey Chain; explicit seniority was not shown. Missing information remains blank. Evidence is in `exports/delhi_ncr_final_live_verification.json` and its browser screenshots. The earlier completed-batch desktop resume check also restored all three rows without opening a browser.

The real `setup_windows.bat` completed successfully on Windows with the installed venv and browser. `start_windows.bat` remains the normal entry point.

## Usability changes

The default screen asks only for job links and the Excel save location. It states what the user will receive. The continue button is hidden until a browser needs confirmation; open-file actions appear only after a saved result. Optional controls are collapsed. Import counts update automatically. Recovery can restore the original links from a selected earlier export instead of requiring the user to reconstruct them. Closing an active app now stops safely and closes after the worker finishes, without asking the user to close it a second time. Open-file failures show an actionable error rather than crashing a callback. The content scrolls at small window sizes.

## GitHub readiness and blocker

The connected account is `punjabiamba5-ux`. Account/profile lookup succeeds, but both accessible-repository and owned-repository lists are empty. Looking up `punjabiamba5-ux/linkedin-job-exporter` returns GitHub API 404. The connector can write files and commits to an accessible repository but does not expose a repository-creation tool. Local noninteractive credential lookup was unavailable and was stopped; no credentials were printed, saved or shared.

Source upload is prepared, including a Windows GitHub Actions test workflow. The hosted workflow has not run because there is no accessible destination repository yet. No successful GitHub upload is claimed. An existing repository URL with connector access, or a newly created repository made accessible to the connector, is needed to finish publication. The source ZIP excludes profiles, progress, installed dependencies, real outputs and screenshot diagnostics.

## Verification limits

Native Windows capture failed twice with `FrameArrived timed out` / `window capture timed out`. GUI tests use real Tk event loops and widget callbacks; they are not evidence of successful native mouse/keyboard or screenshot-based visual testing. Playwright browser screenshots and independent field comparisons succeeded. A human usability/accessibility study was not performed. Future LinkedIn changes or restrictions can still require another fix or manual sign-in.
