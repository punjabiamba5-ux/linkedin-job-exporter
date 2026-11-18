"""Excel output with safe strings and lossless long-text continuation rows."""
import os
import re
import tempfile
from pathlib import Path

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

JOB_COLUMNS = [
    "job_url", "title", "company_name", "location", "posted", "salary", "job_type",
    "seniority", "workplace_type", "job_function", "job_industries", "description",
    "company_url", "company_industry", "company_size", "company_headquarters",
    "company_website", "company_about", "company_founded", "company_specialties",
    "primary_details", "job_insights", "scraped_at_utc", "status", "notes",
    "description_expanded", "missing_fields", "application_status",
]
COMPANY_COLUMNS = ["job_url", "company_url", "company_name", "company_industry", "company_size",
                   "company_headquarters", "company_website", "company_about", "company_founded",
                   "company_specialties", "company_tagline", "company_details", "status", "notes"]
INVALID_XML = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f]")


def validate_output(target):
    """Check the chosen destination before spending time opening LinkedIn."""
    target = Path(target).expanduser().resolve()
    if target.suffix.lower() != '.xlsx':
        raise ValueError('Choose an output file ending in .xlsx.')
    if target.is_dir():
        raise ValueError('The Excel filename is a folder. Choose a file inside a writable folder.')
    target.parent.mkdir(parents=True, exist_ok=True)
    try:
        if target.exists():
            # Open without writing/truncating to detect Excel's Windows file lock.
            with target.open('r+b'):
                pass
        with tempfile.TemporaryFile(dir=target.parent):
            pass
    except PermissionError as exc:
        raise PermissionError(f'Cannot write {target}. Close it in Excel or choose another folder.') from exc
    return target


def safe_text(value):
    return INVALID_XML.sub("", '' if value is None else str(value))


def chunks(value):
    # Excel's limit is 32767 UTF-16 code units, not Python Unicode characters.
    data = safe_text(value).encode("utf-16-le")
    while data:
        end = min(len(data), 60000)
        if 0xD800 <= int.from_bytes(data[end - 2:end], "little") <= 0xDBFF:
            end -= 2
        yield data[:end].decode("utf-16-le")
        data = data[end:]


def append_text(sheet, values):
    row = sheet.max_row + 1
    for col, value in enumerate(values, 1):
        cell = sheet.cell(row, col, next(chunks(value), ""))
        # Force text: a scraped string starting with '=' must never become a formula.
        cell.data_type = "s"
        cell.alignment = Alignment(vertical="top", wrap_text=True)


def write_workbook(records, target):
    target = Path(target)
    target.parent.mkdir(parents=True, exist_ok=True)
    book = Workbook()
    book.remove(book.active)
    sheets = {}
    specs = {"Jobs": JOB_COLUMNS, "Companies": COMPANY_COLUMNS,
             "Descriptions": ["job_url", "title", "part", "description"],
             "Page text": ["job_url", "source_url", "page_type", "part", "text"],
             "Long fields": ["job_url", "field", "part", "text"]}
    for name, columns in specs.items():
        sheet = book.create_sheet(name)
        sheet.append(columns)
        sheets[name] = sheet
    for record in records:
        for name, columns in (("Jobs", JOB_COLUMNS), ("Companies", COMPANY_COLUMNS)):
            values = []
            requested = ['title', 'company_name', 'location', 'posted', 'salary', 'job_type', 'seniority',
                         'workplace_type', 'description', 'company_url', 'company_industry', 'company_size',
                         'company_headquarters', 'company_website', 'company_about', 'company_founded', 'company_specialties']
            for key in columns:
                if key == 'description_expanded':
                    values.append({True: 'yes', False: 'no', None: 'unknown'}.get(record.get(key), 'unknown'))
                elif key == 'missing_fields':
                    values.append(', '.join(field for field in requested if not record.get(field)))
                elif key == 'application_status':
                    values.append(record.get(key, 'unknown'))
                else:
                    values.append(record.get(key, ''))
            append_text(sheets[name], values)
        for part, text in enumerate(chunks(record.get("description", "")), 1):
            append_text(sheets["Descriptions"], [record["job_url"], record.get("title", ""), str(part), text])
        for kind, source in (("job", record["job_url"]), ("company", record.get("company_url", ""))):
            for part, text in enumerate(chunks(record.get(f"raw_{kind}_text", "")), 1):
                append_text(sheets["Page text"], [record["job_url"], source, kind, str(part), text])
        for key in dict.fromkeys(JOB_COLUMNS + COMPANY_COLUMNS):
            parts = list(chunks(record.get(key, "")))
            if len(parts) > 1:
                for part, text in enumerate(parts, 1):
                    append_text(sheets["Long fields"], [record["job_url"], key, str(part), text])
    for sheet in sheets.values():
        sheet.freeze_panes = "B2"
        sheet.auto_filter.ref = sheet.dimensions
        sheet.row_dimensions[1].height = 28
        for cell in sheet[1]:
            cell.font = Font(bold=True, color="FFFFFF")
            cell.fill = PatternFill("solid", fgColor="0A66C2")
        for idx, name in enumerate(specs[sheet.title], 1):
            sheet.column_dimensions[get_column_letter(idx)].width = 65 if name in {"description", "text", "company_about", "notes"} else 28
        for row in range(2, sheet.max_row + 1):
            sheet.row_dimensions[row].height = 72
            for col, key in enumerate(specs[sheet.title], 1):
                cell = sheet.cell(row, col)
                if key in {'job_url', 'company_url'} and re.match(r'^https://www\.linkedin\.com/(?:jobs/view/\d+/|company/[^/]+/about/)$', str(cell.value or '')):
                    cell.hyperlink = cell.value
                    cell.font = Font(color='0563C1', underline='single')
                if key == 'status':
                    color = {'ok': 'E2F0D9', 'partial': 'FFF2CC', 'error': 'FCE4D6', 'blocked': 'E4DFEC'}.get(cell.value)
                    if color:
                        cell.fill = PatternFill('solid', fgColor=color)
                if key == 'application_status' and cell.value == 'closed':
                    cell.fill = PatternFill('solid', fgColor='FCE4D6')
    # Replace atomically so interruption never leaves a half-written workbook.
    temp = target.with_name(target.name + ".tmp")
    try:
        book.save(temp)
        os.replace(temp, target)
    finally:
        temp.unlink(missing_ok=True)
