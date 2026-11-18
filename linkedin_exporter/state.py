"""Local atomic progress snapshots. Contains exported data, never browser state."""
import json
import os
import tempfile
from pathlib import Path
from .inputs import normalize_job_url


def progress_path(output):
    return Path(output).with_suffix('.progress.json')


def save_progress(output, urls, records):
    target = progress_path(output)
    target.parent.mkdir(parents=True, exist_ok=True)
    descriptor, name = tempfile.mkstemp(prefix=target.name + '.', suffix='.tmp', dir=target.parent)
    temporary = Path(name)
    try:
        with os.fdopen(descriptor, 'w', encoding='utf-8') as stream:
            json.dump({'version': 1, 'job_urls': list(urls), 'records': records}, stream, ensure_ascii=False)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, target)
    finally:
        temporary.unlink(missing_ok=True)


def load_progress(output, urls):
    target = progress_path(output)
    try:
        data = json.loads(target.read_text(encoding='utf-8'))
        if data.get('version') != 1 or data.get('job_urls') != list(urls):
            raise ValueError('The saved batch does not match these URLs in this order.')
        records = data['records']
        if not isinstance(records, list):
            raise ValueError('Invalid records.')
        seen = set()
        for record in records:
            url = record['job_url']
            if url not in urls or url in seen or record.get('status') not in {'ok', 'partial', 'error', 'blocked'}:
                raise ValueError('Invalid or duplicate saved job.')
            seen.add(url)
            if record.get('status') == 'ok' and not all(isinstance(record.get(field), str) and record[field].strip()
                    for field in ('title', 'company_name', 'description', 'company_industry', 'company_size', 'company_about')):
                raise ValueError('A saved successful job is missing essential data.')
        return records
    except (OSError, ValueError, KeyError, TypeError, AttributeError) as exc:
        raise ValueError(f'Cannot resume from {target}: {exc}. Choose the original URL list or start a new export.') from exc


def load_saved_batch(output):
    """Restore the original inputs from a selected workbook's progress file."""
    target = progress_path(output)
    try:
        data = json.loads(target.read_text(encoding='utf-8'))
        urls = data['job_urls']
        if not isinstance(urls, list) or not urls or any(not isinstance(url, str) or normalize_job_url(url) != url for url in urls):
            raise ValueError('Invalid saved job links.')
        if len(set(urls)) != len(urls):
            raise ValueError('Duplicate saved job links.')
        return urls, load_progress(output, urls)
    except (OSError, ValueError, KeyError, TypeError, AttributeError) as exc:
        raise ValueError(f'Cannot open saved progress for {output}: {exc}') from exc
