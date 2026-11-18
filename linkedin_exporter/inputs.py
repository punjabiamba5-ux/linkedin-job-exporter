import csv
import re
from pathlib import Path
from urllib.parse import parse_qs, urlparse


def normalize_job_url(value: str) -> str:
    value = value.strip()
    parsed = urlparse(value)
    host = (parsed.hostname or "").lower()
    if parsed.scheme != "https" or not (host == "linkedin.com" or host.endswith(".linkedin.com")):
        raise ValueError(f"Expected an HTTPS LinkedIn job URL: {value}")
    if parsed.username is not None or parsed.password is not None or parsed.port not in (None, 443):
        raise ValueError("Job URLs must not contain credentials or a nonstandard port.")
    match = re.fullmatch(r"/jobs/view/(?:[^/]*-)?(\d+)/?", parsed.path)
    job_id = match.group(1) if match else None
    if not job_id and parsed.path.rstrip("/") in {"/jobs/search", "/jobs/search-results", "/jobs/collections/recommended"}:
        job_id = parse_qs(parsed.query).get("currentJobId", [""])[0]
    if not job_id or not job_id.isdigit():
        raise ValueError(f"Use a specific job link such as https://www.linkedin.com/jobs/view/1234567890/: {value}")
    return f"https://www.linkedin.com/jobs/view/{job_id}/"


def collect_urls(text: str = "", files=()) -> list[str]:
    values = [(line.strip(), f"Pasted URLs:{number}") for number, line in enumerate(text.splitlines(), 1)
              if line.strip() and not line.lstrip().startswith("#")]
    for filename in files:
        path = Path(filename)
        if path.suffix.lower() not in {'.txt', '.csv'}:
            raise ValueError(f"{path.name}: choose a TXT or CSV file.")
        try:
            content = path.read_text(encoding='utf-8-sig')
        except UnicodeError as exc:
            raise ValueError(f"{path.name}: save the file as UTF-8 text or CSV UTF-8, then retry.") from exc
        if path.suffix.lower() == ".csv":
            import io
            with io.StringIO(content, newline='') as stream:
                header = content.splitlines()[0] if content.splitlines() else ''
                try:
                    dialect = csv.Sniffer().sniff(header, delimiters=',;\t')
                except csv.Error:
                    dialect = csv.excel
                reader = csv.DictReader(stream, dialect=dialect, strict=True)
                headers = {name.strip().lower(): name for name in (reader.fieldnames or [])}
                column = next((headers[name] for name in ("job_url", "job url", "url", "job link") if name in headers), None)
                if column is None:
                    raise ValueError(f"{path.name}: CSV needs a job_url or url header.")
                try:
                    for row in reader:
                        value = (row.get(column) or '').strip()
                        if value:
                            values.append((value, f'{path.name}:{reader.line_num}'))
                except csv.Error as exc:
                    raise ValueError(f'{path.name}:{reader.line_num}: invalid CSV: {exc}') from exc
        else:
            values.extend((line.strip(), f'{path.name}:{number}') for number, line in enumerate(content.splitlines(), 1)
                          if line.strip() and not line.lstrip().startswith('#'))
    # Validate everything before opening a browser; preserve the user's order.
    result = []
    seen = set()
    for value, source in values:
        try:
            url = normalize_job_url(value)
        except ValueError as exc:
            raise ValueError(f'{source}: {exc}') from exc
        if url not in seen:
            seen.add(url)
            result.append(url)
    if not result:
        raise ValueError("Paste at least one job URL or choose a TXT/CSV file.")
    return result
