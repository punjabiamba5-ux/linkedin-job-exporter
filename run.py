#!/usr/bin/env python3
import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def main():
    parser = argparse.ArgumentParser(description="Export manually signed-in LinkedIn jobs to Excel. No arguments opens the desktop app.")
    parser.add_argument("urls", nargs="*", help="One or more LinkedIn job URLs")
    parser.add_argument("--file", action="append", default=[], help="TXT/CSV file; repeat to import several files")
    parser.add_argument("--output", type=Path, default=ROOT / "exports" / "linkedin_jobs.xlsx")
    parser.add_argument("--profile", type=Path, default=ROOT / ".linkedin-profile")
    parser.add_argument("--browser", choices=["chromium", "chrome", "msedge"], default="chromium")
    parser.add_argument("--delay", type=float, default=3, help="Seconds between pages (minimum 1)")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--overwrite", action="store_true", help="Replace an existing workbook")
    mode.add_argument("--resume", action="store_true", help="Keep successful jobs from saved progress; retry incomplete jobs")
    parser.add_argument("--check", action="store_true", help="Validate inputs and output access without opening a browser")
    parser.add_argument("--gui", action="store_true", help="Open desktop window")
    args = parser.parse_args()
    if args.gui or not (args.urls or args.file or args.check or args.resume):
        from linkedin_exporter.gui import launch
        launch()
        return 0
    from linkedin_exporter.browser import export_jobs
    from linkedin_exporter.inputs import collect_urls
    from linkedin_exporter.workbook import validate_output
    try:
        urls = collect_urls("\n".join(args.urls), args.file)
        if not 1 <= args.delay <= 60:
            raise ValueError("--delay must be between 1 and 60 seconds.")
        if args.output.suffix.lower() != ".xlsx":
            raise ValueError("--output must end in .xlsx")
        if args.output.exists() and not (args.overwrite or args.resume or args.check):
            raise ValueError("Output already exists. Choose a new name or pass --overwrite.")
        args.output = validate_output(args.output)
        if args.resume:
            from linkedin_exporter.state import load_progress
            load_progress(args.output, urls)
        if args.check:
            print(f'Validated {len(urls)} unique job URLs. Output: {args.output}')
            return 0
        def ready(message):
            print(message.replace("click 'I am signed in — continue'", "press Enter here"))
            input()
        records = export_jobs(urls, args.output, args.profile, ready, delay=args.delay, channel=args.browser, resume=args.resume)
        print(f"Saved {len(records)}/{len(urls)} jobs to {args.output.resolve()}")
        return 0 if len(records) == len(urls) and all(row["status"] == "ok" for row in records) else 2
    except (ValueError, OSError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("Stopped. Completed jobs were saved to the workbook.", file=sys.stderr)
        return 130
    except Exception as exc:
        print(f"Error: {exc}\nRun setup_windows.bat if the browser is missing. Close Excel if the file is locked.", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
