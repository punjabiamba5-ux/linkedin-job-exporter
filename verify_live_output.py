"""Opt-in comparison of an exported workbook with authenticated rendered pages.

Run only after a manual sign-in and with the exporter's browser closed.
Reads job/company pages, expands descriptions, and never handles credentials.
"""
import json
import re
import time
import argparse
from pathlib import Path

from openpyxl import load_workbook
from playwright.sync_api import sync_playwright
from linkedin_exporter.browser import check_access

ROOT = Path(__file__).resolve().parent
OUTPUT = ROOT / 'exports' / 'delhi_ncr_live.xlsx'


def normalize(text):
    return re.sub(r'\s+', ' ', text or '').strip()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--workbook', type=Path, default=OUTPUT)
    args = parser.parse_args()
    output = args.workbook.expanduser().resolve()
    book = load_workbook(output)
    values = list(book['Jobs'].values)
    records = [dict(zip(values[0], row)) for row in values[1:]]
    descriptions = {}
    for url, title, part, text in book['Descriptions'].iter_rows(min_row=2, values_only=True):
        descriptions[url] = descriptions.get(url, '') + (text or '')
    report = {'workbook': str(output), 'source': 'authenticated live rendered LinkedIn pages', 'jobs': []}
    prefix = '' if output == OUTPUT else output.stem + '_'
    assert all(sheet.cell(1, 1).value == 'job_url' for sheet in book)
    assert len(records) == 3
    assert all(cell.data_type != 'f' for sheet in book for row in sheet for cell in row)
    with sync_playwright() as pw:
        context = pw.chromium.launch_persistent_context(str(ROOT / '.linkedin-profile'), headless=False,
                                                       viewport={'width': 1440, 'height': 1000})
        page = context.pages[0] if context.pages else context.new_page()
        try:
            for index, record in enumerate(records, 1):
                print(f'Checking live job {index}: {record["job_url"]}', flush=True)
                response = page.goto(record['job_url'], wait_until='domcontentloaded', timeout=45000)
                check_access(page, response)
                section = page.locator('[componentkey^="JobDetails_AboutTheJob_"]')
                section.wait_for(state='visible', timeout=20000)
                page.wait_for_timeout(1500)
                button = section.locator('[data-testid="expandable-text-button"]')
                for _ in range(3):
                    if button.count() and button.is_visible() and 'more' in button.inner_text().lower():
                        button.click(timeout=4000)
                    page.wait_for_timeout(700)
                    if not button.count() or not button.is_visible() or 'less' in button.inner_text().lower():
                        break
                check_access(page)
                description = section.locator('[data-testid="expandable-text-box"]')
                visible_description = description.inner_text().strip()
                if button.count() and button.is_visible():
                    label = button.inner_text().strip()
                    if label and visible_description.endswith(label):
                        visible_description = visible_description[:-len(label)].strip()
                expanded = (not button.count() or not button.is_visible() or 'less' in button.inner_text().lower()) and description.evaluate('(e) => !(e.clientHeight > 0 && e.scrollHeight > e.clientHeight + 2)')
                # Compare every stored description part to the independently read
                # expanded section, including its final paragraph.
                checks = {'status_ok': record['status'] == 'ok', 'description_expanded': expanded,
                          'description_complete': normalize(descriptions[record['job_url']]) == normalize(visible_description),
                          'title_matches_page_title': normalize(record['title']) == normalize(page.title().split(' | ')[0])}
                body = page.locator('body').inner_text()
                if 'application_status' in record:
                    closed = 'no longer accepting applications' in body.lower()
                    checks['closed_posting_flag'] = (record['application_status'] == 'closed') if closed else record['application_status'] != 'closed'
                for field in ('title', 'company_name', 'location', 'posted', 'salary', 'job_type', 'workplace_type'):
                    if record.get(field):
                        checks[field] = normalize(record[field]) in normalize(body)
                page.screenshot(path=str(ROOT / 'exports' / f'{prefix}live_{index}_job.png'))
                description.screenshot(path=str(ROOT / 'exports' / f'{prefix}live_{index}_description.png'))
                time.sleep(3)
                response = page.goto(record['company_url'], wait_until='domcontentloaded', timeout=45000)
                check_access(page, response)
                heading = page.get_by_role('heading', name='Overview', exact=True)
                heading.wait_for(state='visible', timeout=20000)
                overview = heading.locator('..')
                for _ in range(8):
                    if overview.locator('p').filter(has_text=re.compile(r'^Industry$')).count():
                        break
                    overview = overview.locator('..')
                paragraphs = overview.locator('p').all_inner_texts()
                expected = {}
                labels = {'Website', 'Phone', 'Industry', 'Company size', 'Headquarters', 'Founded', 'Type', 'Specialties', 'Verified page'}
                for label, field in [('Industry', 'company_industry'), ('Company size', 'company_size'),
                                     ('Headquarters', 'company_headquarters'), ('Website', 'company_website'),
                                     ('Founded', 'company_founded'), ('Specialties', 'company_specialties')]:
                    if label in paragraphs:
                        start = paragraphs.index(label) + 1
                        parts = []
                        for text in paragraphs[start:]:
                            if text.strip() in labels:
                                break
                            if text.strip():
                                parts.append(text.strip())
                        expected[field] = '\n'.join(parts)
                        checks[field] = normalize(record.get(field)) == normalize(expected[field])
                    else:
                        checks[field] = not record.get(field)
                checks['company_about'] = normalize(record.get('company_about')) == normalize(paragraphs[0])
                check_access(page)
                page.screenshot(path=str(ROOT / 'exports' / f'{prefix}live_{index}_company.png'), full_page=True)
                result = {'job_url': record['job_url'], 'title': record['title'], 'company': record['company_name'],
                          'checks': checks, 'description_characters': len(descriptions[record['job_url']]),
                          'description_final_text': visible_description[-180:],
                          'visible_company_fields': expected,
                          'unavailable_fields': [field for field in ('salary', 'seniority', 'job_function', 'job_industries',
                               'company_founded', 'company_specialties') if not record.get(field)]}
                report['jobs'].append(result)
                target = ROOT / 'exports' / f'{prefix}live_verification.json'
                target.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
                print(json.dumps(result, ensure_ascii=True), flush=True)
                if not all(checks.values()):
                    raise AssertionError('Live comparison failed; see live_verification.json')
                if index < len(records):
                    time.sleep(3)
        finally:
            context.close()
            book.close()
    print('PASS: all three jobs and company About pages match the workbook.', flush=True)


if __name__ == '__main__':
    main()
