import json
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

from playwright.sync_api import TimeoutError as BrowserTimeout, sync_playwright

from .workbook import write_workbook
from .state import load_progress, progress_path, save_progress

EXTRACT = Path(__file__).with_name("extract.js").read_text(encoding="utf-8")


class AccessBlocked(RuntimeError):
    pass


def company_about_url(value):
    parsed = urlparse(value)
    if parsed.scheme != "https" or not ((parsed.hostname or "") == "linkedin.com" or (parsed.hostname or "").endswith(".linkedin.com")):
        return ""
    match = re.match(r"^/company/([^/]+)/?", parsed.path)
    return f"https://www.linkedin.com/company/{match.group(1)}/about/" if match else ""


def check_access(page, response=None):
    if response and response.status in {401, 403, 429, 999}:
        raise AccessBlocked(f"LinkedIn limited access (HTTP {response.status}). Export stopped; try again later.")
    path = urlparse(page.url).path.lower()
    if any(part in path for part in ("/login", "/checkpoint", "/authwall", "/uas/login", "/challenge")):
        raise AccessBlocked("LinkedIn requires sign-in or verification. Complete it manually in the browser, then rerun the export.")
    if page.locator('input[name="session_password"]:visible, iframe[src*="captcha"]:visible, #captcha-internal:visible').count():
        raise AccessBlocked("A login or verification screen is visible. Complete it manually and rerun.")
    body = page.locator("body").inner_text(timeout=5000).lower()
    content = page.locator('#job-details, .jobs-description__content, .description__text, [componentkey^="JobDetails_AboutTheJob_"], h2:text-is("Overview")')
    has_content = any(element.is_visible() for element in content.all()[:3])
    phrases = ("let’s do a quick security check", "let's do a quick security check", "verify you are human", "too many requests")
    gate_text = '\n'.join(element.inner_text().lower() for element in page.locator('[role="dialog"], [role="alert"], h1').all()
                          if element.is_visible())
    if any(phrase in gate_text for phrase in phrases) or (not has_content and any(phrase in body for phrase in phrases)):
        raise AccessBlocked("LinkedIn displayed a verification or rate-limit screen. Export stopped.")


def read_page(page, url, kind):
    response = page.goto(url, wait_until="domcontentloaded", timeout=45000)
    check_access(page, response)
    if response and response.status >= 400:
        raise RuntimeError(f"Page returned HTTP {response.status}; the listing may have expired.")
    selector = ('[componentkey^="JobDetails_AboutTheJob_"] [data-testid="expandable-text-box"], #job-details, .jobs-description__content, .description__text' if kind == "job"
                else 'h2:text-is("Overview"), main dt, .org-about-us-organization-description__text, .org-page-details__definition-text')
    try:
        page.locator(selector).first.wait_for(state="visible", timeout=15000)
    except BrowserTimeout:
        pass  # Read what is present and explicitly flag missing fields.
    check_access(page)
    # SDUI adds truncation controls after its first layout/hydration pass.
    # A description can already have all its DOM text while still being clipped.
    if kind == "job" and page.locator('[componentkey^="JobDetails_AboutTheJob_"]').count():
        page.wait_for_timeout(1000)
        modern_button = page.locator('[componentkey^="JobDetails_AboutTheJob_"] [data-testid="expandable-text-button"]').first
        for attempt in range(3):
            check_access(page)
            if modern_button.count() and modern_button.is_visible() and "more" in modern_button.inner_text().lower():
                try:
                    modern_button.click(timeout=4000)
                except BrowserTimeout:
                    pass  # Preserve readable text; expansion is verified below.
            page.wait_for_timeout(700)
            expanded = page.evaluate('''() => {
              const box = document.querySelector('[componentkey^="JobDetails_AboutTheJob_"] [data-testid="expandable-text-box"]');
              if (!box) return false;
              const button = box.querySelector('[data-testid="expandable-text-button"]');
              const more = button && button.getClientRects().length && /more/i.test(button.innerText);
              return !more && !(box.clientHeight > 0 && box.scrollHeight > box.clientHeight + 2);
            }''')
            if expanded:
                break
    # Expand only description/About controls; never click Apply, Follow, or messaging.
    expansion_failed = False
    for selector in (
        '.jobs-description__footer-button',
        '.description__text button.show-more-less-html__button',
        '.org-about-us-organization-description button',
    ):
        button = page.locator(selector).first
        if button.count() and button.is_visible():
            label = (button.inner_text() + " " + (button.get_attribute("aria-label") or "")).lower()
            if any(word in label for word in ("show more", "see more", "read more")) or re.fullmatch(r"[\s.…]*more\s*", label):
                try:
                    button.click(timeout=4000)
                    page.wait_for_timeout(350)
                except BrowserTimeout:
                    expansion_failed = True
    # Trigger lazy rendered content within a finite scroll budget.
    page.evaluate("window.scrollBy(0, 700)")
    page.wait_for_timeout(500)
    check_access(page)
    data = page.evaluate(EXTRACT)
    if expansion_failed and kind == 'job':
        data['description_expanded'] = False
    return data


def job_record(url, data):
    criteria = data.get("criteria", {})
    insights = "\n".join(data.get("insight_items", [])) or data.get("job_insights", "")
    result = {key: data.get(key, "") for key in ("title", "company_name", "location", "posted", "salary", "description", "primary_details")}
    result.update(job_url=url, company_url=company_about_url(data.get("company_url", "")),
                  raw_job_text=data.get("raw_text", ""), job_insights=insights,
                  job_type=criteria.get("employment type", ""), seniority=criteria.get("seniority level", ""),
                  job_function=criteria.get("job function", ""), job_industries=criteria.get("industries", ""))
    result["description_expanded"] = data.get("description_expanded")
    result['application_status'] = data.get('application_status', 'unknown')
    # Match explicit labels only. Leave ambiguous or translated labels in raw text.
    for field, pattern in {
        "job_type": r"\b(Full-time|Part-time|Contract|Temporary|Internship|Volunteer|Other)\b",
        "workplace_type": r"\b(On-site|Hybrid|Remote)\b",
        "seniority": r"\b(Internship|Entry level|Associate|Mid-Senior level|Director|Executive)\b",
    }.items():
        match = re.search(pattern, insights, re.I)
        if match and not result.get(field):
            result[field] = match.group(1)
    if not result["posted"]:
        match = re.search(r"(?:Reposted\s+)?(?:\d+\s+(?:minute|hour|day|week|month)s?\s+ago|Just now|Today|Yesterday)", result["primary_details"], re.I)
        if match:
            result["posted"] = match.group(0)
    if not result["salary"]:
        # Preserve the entire insight containing currency rather than guessing a range.
        result["salary"] = "\n".join(line for line in data.get("insight_items", []) if re.search(r"[$€£₹¥]|\b(?:USD|GBP|EUR|INR|CAD|AUD)\b", line))
    return result


def company_record(data):
    definitions = data.get("definitions", {})
    result = {"company_" + field: definitions.get(label, "") for field, label in {
        "industry": "industry", "size": "company size", "headquarters": "headquarters",
        "website": "website", "founded": "founded", "specialties": "specialties",
    }.items()}
    result.update(company_about=data.get("company_about", ""),
                  company_tagline=data.get("company_tagline", ""), raw_company_text=data.get("raw_text", ""),
                  company_details=json.dumps(definitions, ensure_ascii=False))
    return result


def wait_between_pages(seconds, cancelled):
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        if cancelled():
            return False
        time.sleep(min(0.1, max(0, end - time.monotonic())))
    return not cancelled()


def export_jobs(urls, output, profile, ready, log=print, cancelled=lambda: False, delay=3.0, channel="chromium", executable=None,
                resume=False, progress=lambda done, total, url, status: None):
    """Callbacks keep both the CLI and desktop UI independent of browser internals."""
    urls = list(urls)
    records, cache = (load_progress(output, urls) if resume else []), {}
    by_url = {record['job_url']: record for record in records}
    complete = {record['job_url'] for record in records if record.get('status') == 'ok'}
    finished = set(complete)
    progress(len(complete), len(urls), '', 'ready')
    if resume:
        log(f'Resuming: {len(complete)} successful jobs will be kept; incomplete jobs will be retried.')
        if complete == set(urls):
            write_workbook(records, output)
            log('Restored workbook from saved progress. No browser requests were needed.')
            return records
    profile = Path(profile).expanduser().resolve()
    profile.mkdir(parents=True, exist_ok=True)
    try:
        profile.chmod(0o700)
    except OSError:
        pass
    with sync_playwright() as playwright:
        options = dict(user_data_dir=str(profile), headless=False, viewport={"width": 1440, "height": 1000})
        if executable:
            options["executable_path"] = executable
        elif channel != "chromium":
            options["channel"] = channel
        context = playwright.chromium.launch_persistent_context(**options)
        try:
            page = context.pages[0] if context.pages else context.new_page()
            page.goto("https://www.linkedin.com/login", wait_until="domcontentloaded", timeout=45000)
            ready("Sign in to LinkedIn in the opened browser. Complete any verification, then click 'I am signed in — continue'. For best field matching, use LinkedIn in English.")
            if cancelled():
                return records
            for index, url in enumerate(urls, 1):
                if url in complete:
                    continue
                if cancelled():
                    log("Stopped. Previously completed rows are saved.")
                    break
                record = {"job_url": url, "status": "error", "scraped_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds")}
                notes, blocked = [], False
                log(f"[{index}/{len(urls)}] Reading {url}")
                try:
                    record.update(job_record(url, read_page(page, url, "job")))
                    if not all(record.get(key) for key in ('title', 'company_name', 'description')):
                        notes.append("Job title, employer or description missing; page may be unavailable or use an unsupported layout.")
                    if record.get("description_expanded") is False:
                        notes.append("Job description remains collapsed; full description could not be verified.")
                    company = record.get("company_url")
                    if company:
                        if company in cache:
                            record.update(cache[company])
                        else:
                            if cancelled():
                                raise RuntimeError("Stopped before company extraction.")
                            if not wait_between_pages(delay, cancelled):
                                raise RuntimeError('Stopped before company extraction.')
                            try:
                                info = company_record(read_page(page, company, "company"))
                                record.update(info)
                                if all(info.get(key) for key in ("company_industry", "company_size", "company_about")):
                                    cache[company] = info
                            except AccessBlocked:
                                raise
                            except Exception as exc:
                                notes.append(f"Company page failed: {exc}")
                    else:
                        notes.append("No visible company page link found.")
                    missing = [key for key in ("company_industry", "company_size", "company_about") if not record.get(key)]
                    if missing:
                        notes.append("Company fields unavailable: " + ", ".join(missing))
                    record["status"] = "partial" if notes else "ok"
                    if record.get('application_status') == 'closed':
                        notes.append('This posting is no longer accepting applications; exported for reference.')
                except AccessBlocked as exc:
                    record["status"] = "blocked"
                    notes.append(str(exc))
                    blocked = True
                except Exception as exc:
                    record["status"] = "partial" if record.get("description") else "error"
                    notes.append(str(exc))
                record["notes"] = " | ".join(notes)
                by_url[url] = record
                records = [by_url[value] for value in urls if value in by_url]
                # Persist the attempted row before Excel replacement. If Excel
                # becomes locked mid-run, resume can restore this exact row.
                save_progress(output, urls, records)
                try:
                    write_workbook(records, output)
                except OSError as exc:
                    raise OSError(f'Excel could not be saved: {exc}. Completed data is safe in {progress_path(output)}. Close Excel, then resume this batch.') from exc
                finished.add(url)
                progress(len(finished), len(urls), url, record['status'])
                log(f"Saved: {record['status']}" + (f" — {record['notes']}" if notes else ""))
                if blocked:
                    log(f"Stopped after {index} of {len(urls)} jobs. Remaining jobs were not attempted.")
                    break
                if index < len(urls) and not cancelled():
                    wait_between_pages(delay, cancelled)
        finally:
            context.close()
    return records
