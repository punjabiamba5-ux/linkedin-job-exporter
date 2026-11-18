import tempfile
import unittest
import time
import contextlib
import io
import sys
from pathlib import Path
from unittest.mock import patch

from openpyxl import load_workbook

from linkedin_exporter.inputs import collect_urls, normalize_job_url
from linkedin_exporter.workbook import safe_text, validate_output, write_workbook
from linkedin_exporter.browser import export_jobs, wait_between_pages
from linkedin_exporter.state import load_progress, load_saved_batch, progress_path, save_progress

URL = 'https://www.linkedin.com/jobs/view/123/'


class ValidationTests(unittest.TestCase):
    def test_csv_missing_cell_and_semicolon_dialect(self):
        with tempfile.TemporaryDirectory() as folder:
            source = Path(folder) / 'jobs.csv'
            source.write_text('notes,job_url\nempty\nvalid,' + URL + '\n', encoding='utf-8')
            self.assertEqual(collect_urls(files=[source]), [URL])
            source.write_text('\ufeffnotes;job_url\n"contains, comma";' + URL + '\n', encoding='utf-8')
            self.assertEqual(collect_urls(files=[source]), [URL])

    def test_source_line_and_encoding_errors_are_actionable(self):
        with tempfile.TemporaryDirectory() as folder:
            source = Path(folder) / 'my_jobs.txt'
            source.write_text('# skip\n' + URL + '\nhttps://example.com/jobs/4\n', encoding='utf-8')
            with self.assertRaisesRegex(ValueError, 'my_jobs.txt:3'):
                collect_urls(files=[source])
            source.write_bytes(b'\xff\xfeinvalid')
            with self.assertRaisesRegex(ValueError, 'UTF-8'):
                collect_urls(files=[source])

    def test_unsupported_files_and_credential_urls_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            source = Path(folder) / 'jobs.xlsx'
            source.write_text(URL, encoding='utf-8')
            with self.assertRaisesRegex(ValueError, 'TXT or CSV'):
                collect_urls(files=[source])
        for value in ('https://user:secret@www.linkedin.com/jobs/view/123/',
                      'https://www.linkedin.com:123/jobs/view/123/'):
            with self.subTest(value=value), self.assertRaises(ValueError):
                normalize_job_url(value)

    def test_output_directory_and_existing_file_are_safe(self):
        with tempfile.TemporaryDirectory() as folder:
            target = Path(folder) / 'jobs.xlsx'
            target.mkdir()
            with self.assertRaisesRegex(ValueError, 'folder'):
                validate_output(target)
            other = Path(folder) / 'keep.xlsx'
            other.write_bytes(b'existing file')
            self.assertEqual(validate_output(other), other.resolve())
            self.assertEqual(other.read_bytes(), b'existing file')
            self.assertEqual(list(Path(folder).glob('*.tmp')), [])


JOB_DATA = {'title': 'AI Engineer', 'company_name': 'Example', 'company_url': 'https://www.linkedin.com/company/example/',
            'description': 'Build useful AI.'}
COMPANY_DATA = {'company_about': 'We build AI.', 'definitions': {'industry': 'Software Development', 'company size': '11-50 employees'}}


class RecoveryTests(unittest.TestCase):
    def test_saved_batch_rejects_corrupt_success_and_unsafe_links(self):
        with tempfile.TemporaryDirectory() as folder:
            target = Path(folder) / 'jobs.xlsx'
            save_progress(target, [URL], [{'job_url': URL, 'status': 'ok'}])
            with self.assertRaisesRegex(ValueError, 'missing essential data'):
                load_saved_batch(target)
            save_progress(target, ['https://example.com/'], [])
            with self.assertRaisesRegex(ValueError, 'saved progress'):
                load_saved_batch(target)

    def test_blocked_resume_stops_and_keeps_unattempted_urls(self):
        from linkedin_exporter.browser import AccessBlocked
        with tempfile.TemporaryDirectory() as folder:
            target = Path(folder) / 'jobs.xlsx'
            urls = [URL, URL.replace('123', '456')]
            with patch('linkedin_exporter.browser.sync_playwright'), patch('linkedin_exporter.browser.read_page', side_effect=AccessBlocked('HTTP 429')) as reader:
                first = export_jobs(urls, target, Path(folder) / 'profile', lambda m: None, delay=0, log=lambda m: None)
            self.assertEqual(reader.call_count, 1)
            self.assertEqual([r['status'] for r in first], ['blocked'])
            self.assertEqual(load_saved_batch(target)[0], urls)
            with patch('linkedin_exporter.browser.sync_playwright'), patch('linkedin_exporter.browser.read_page', side_effect=AccessBlocked('HTTP 429')) as reader:
                again = export_jobs(urls, target, Path(folder) / 'profile', lambda m: None, delay=0, resume=True, log=lambda m: None)
            self.assertEqual(reader.call_count, 1)
            self.assertEqual(len(again), 1)

    def test_cancel_before_company_preserves_partial_row(self):
        cancelled = False
        def read(*args):
            nonlocal cancelled
            cancelled = True
            return JOB_DATA
        with tempfile.TemporaryDirectory() as folder:
            target = Path(folder) / 'jobs.xlsx'
            with patch('linkedin_exporter.browser.sync_playwright'), patch('linkedin_exporter.browser.read_page', side_effect=read) as reader:
                result = export_jobs([URL], target, Path(folder) / 'profile', lambda m: None, delay=0,
                                     cancelled=lambda: cancelled, log=lambda m: None)
            self.assertEqual(reader.call_count, 1)
            self.assertEqual(result[0]['status'], 'partial')
            self.assertEqual(load_progress(target, [URL])[0]['description'], JOB_DATA['description'])

    def test_failed_excel_save_is_recoverable_without_network(self):
        with tempfile.TemporaryDirectory() as folder:
            target = Path(folder) / 'jobs.xlsx'
            with patch('linkedin_exporter.browser.sync_playwright'), patch('linkedin_exporter.browser.read_page', side_effect=[JOB_DATA, COMPANY_DATA]), \
                    patch('linkedin_exporter.browser.write_workbook', side_effect=PermissionError('locked by Excel')):
                with self.assertRaisesRegex(OSError, 'Completed data is safe'):
                    export_jobs([URL], target, Path(folder) / 'profile', lambda m: None, delay=0, log=lambda m: None)
            self.assertTrue(progress_path(target).exists())
            self.assertEqual(load_progress(target, [URL])[0]['status'], 'ok')
            with patch('linkedin_exporter.browser.sync_playwright', side_effect=AssertionError('Must not access LinkedIn')):
                recovered = export_jobs([URL], target, Path(folder) / 'profile', lambda m: None, resume=True, log=lambda m: None)
            self.assertEqual(len(recovered), 1)
            book = load_workbook(target)
            self.assertEqual(book['Jobs']['B2'].value, 'AI Engineer')
            book.close()

    def test_resume_retries_incomplete_jobs_without_duplicate_rows(self):
        with tempfile.TemporaryDirectory() as folder:
            target = Path(folder) / 'jobs.xlsx'
            urls = [URL, URL.replace('123', '456')]
            bad_job = dict(JOB_DATA, description='')
            with patch('linkedin_exporter.browser.sync_playwright'), patch('linkedin_exporter.browser.read_page',
                    side_effect=[JOB_DATA, COMPANY_DATA, bad_job]):
                initial = export_jobs(urls, target, Path(folder) / 'profile', lambda m: None, delay=0, log=lambda m: None)
            self.assertEqual([r['status'] for r in initial], ['ok', 'partial'])
            updates = []
            with patch('linkedin_exporter.browser.sync_playwright'), patch('linkedin_exporter.browser.read_page',
                    side_effect=[JOB_DATA, COMPANY_DATA]) as reader:
                result = export_jobs(urls, target, Path(folder) / 'profile', lambda m: None, delay=0, resume=True,
                                     progress=lambda *args: updates.append(args), log=lambda m: None)
            self.assertEqual(reader.call_args_list[0].args[1], urls[1])
            self.assertEqual([r['status'] for r in result], ['ok', 'ok'])
            self.assertEqual([r['job_url'] for r in result], urls)
            self.assertEqual([u[0] for u in updates], [1, 2])
            with self.assertRaisesRegex(ValueError, 'does not match'):
                load_progress(target, list(reversed(urls)))

    def test_stop_interrupts_long_delay(self):
        started = time.monotonic()
        self.assertFalse(wait_between_pages(30, lambda: True))
        self.assertLess(time.monotonic() - started, 0.5)


class ResultsTests(unittest.TestCase):
    def test_closed_posting_is_explained_in_the_desktop_summary(self):
        from linkedin_exporter.gui import result_message
        message = result_message([dict(JOB_DATA, job_url=URL, status='ok', application_status='closed')], 1)
        self.assertIn('no longer accepting applications', message)
        self.assertIn('1 complete', message)

    def test_results_have_sources_expansion_and_missing_field_details(self):
        self.assertEqual(safe_text(0), '0')
        self.assertEqual(safe_text(False), 'False')
        with tempfile.TemporaryDirectory() as folder:
            target = Path(folder) / 'result.xlsx'
            write_workbook([dict(JOB_DATA, job_url=URL, status='partial', description_expanded=False)], target)
            book = load_workbook(target)
            sheet = book['Jobs']
            columns = {cell.value: cell.column for cell in sheet[1]}
            self.assertEqual(sheet['A2'].hyperlink.target, URL)
            self.assertEqual(sheet.cell(2, columns['description_expanded']).value, 'no')
            self.assertIn('salary', sheet.cell(2, columns['missing_fields']).value)
            self.assertNotIn('title,', sheet.cell(2, columns['missing_fields']).value)
            self.assertEqual(sheet.cell(2, columns['status']).fill.fgColor.rgb[-6:], 'FFF2CC')
            self.assertEqual(sheet.cell(2, columns['title']).value, 'AI Engineer')
            book.close()


class CommandLineTests(unittest.TestCase):
    def test_check_with_no_input_reports_error_instead_of_opening_gui(self):
        import run
        stderr = io.StringIO()
        with patch.object(sys, 'argv', ['run.py', '--check']), patch('linkedin_exporter.gui.launch') as launch, \
                contextlib.redirect_stderr(stderr):
            self.assertEqual(run.main(), 1)
        launch.assert_not_called()
        self.assertIn('at least one job URL', stderr.getvalue())

    def test_check_deduplicates_and_does_not_open_browser_or_write_workbook(self):
        import run
        with tempfile.TemporaryDirectory() as folder:
            target = Path(folder) / 'jobs.xlsx'
            output = io.StringIO()
            with patch.object(sys, 'argv', ['run.py', URL, URL, '--check', '--output', str(target)]), \
                    patch('linkedin_exporter.browser.export_jobs') as exporter, contextlib.redirect_stdout(output):
                self.assertEqual(run.main(), 0)
            exporter.assert_not_called()
            self.assertFalse(target.exists())
            self.assertIn('1 unique job URLs', output.getvalue())


if __name__ == '__main__':
    unittest.main()
