# Turn LinkedIn job links into an Excel file

## Open the app

The first time, double-click `setup_windows.bat` and wait for “Setup complete”. Then double-click `start_windows.bat`.

## What you provide

Open a job on LinkedIn and copy its link. You can use one job or a list of jobs. You do not enter your LinkedIn password into this app.

## Three steps

1. **Add job links.** Paste one link per line. Or choose **Import a TXT or CSV file…**. Repeated links are counted only once. A TXT file has one link per line; a CSV file needs a `job_url` column.
2. **Choose where to save.** Keep the suggested Excel filename, or click **Choose location…** to choose a folder and name.
3. **Create your Excel file.** Click the large button. In the browser that opens, sign in to LinkedIn yourself and finish any verification. Return to the app and click **I am signed in — continue** when that button appears.

When finished, click **Open Excel file**. **Show saved folder** opens the folder containing it.
The saved file's full location appears above these buttons. On a small screen, the app scrolls to the sign-in and result buttons automatically.

## What you receive

An Excel workbook with the job link as the first column. It includes job title, employer, location, posting time, pay when shown, employment/workplace type, full job description, and company information such as industry, size, website and About text.

The **Jobs** sheet gives one row per attempted job. **Companies** contains company details. **Descriptions** preserves full job descriptions, including long ones. **Page text** and **Long fields** keep supporting text. A blank field means the information was not available; it is not guessed.

Check **application_status** before considering a job: `closed` means LinkedIn says it is no longer accepting applications. Closed jobs can still be saved for your records. The extraction status `ok` means the data was read successfully; it does not mean a vacancy is open.

## If something goes wrong

- Fix a bad link or file row identified by the error, then try again.
- Close the workbook in Excel before creating or updating it.
- If some jobs need review, open Excel and read their status and notes. **Retry unfinished jobs** tries those jobs again while keeping successful ones.
- To continue a run after closing the app, choose **More options → Continue an earlier export…**. Select the earlier Excel file, or its matching `.progress.json` file if Excel could not be saved. The app restores the links for you.
- If you change those restored links or choose a different save location, the next export starts a new batch automatically.
- If LinkedIn asks for sign-in or verification, finish it yourself in the browser. If access is limited, stop and try later. The app does not bypass these restrictions.
- **Show details** opens the log when you need help. **More options** contains browser selection and other optional settings; you do not need to change them for a normal export.

Keep `.linkedin-profile/` private. It contains your saved browser session. The source ZIP does not include it or your exported workbooks.
