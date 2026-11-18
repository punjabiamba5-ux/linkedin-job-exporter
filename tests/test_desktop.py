"""Complete GUI scenarios in isolated real Tk event loops. No live requests."""
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from openpyxl import load_workbook

from linkedin_exporter import gui
from linkedin_exporter.state import save_progress
from linkedin_exporter.workbook import write_workbook

URL = 'https://www.linkedin.com/jobs/view/123/'
RECORD = dict(job_url=URL, title='AI Engineer', company_name='Example', description='Full description.',
              company_industry='Software Development', company_size='11-50 employees', company_about='We build AI.', status='ok')


class DesktopTests(unittest.TestCase):
    def exercise(self, scenario):
        project = Path(__file__).resolve().parents[1]
        result = subprocess.run([sys.executable, '-X', 'utf8', __file__, '--scenario', scenario], cwd=project,
            env=dict(os.environ, PYTHONPATH=str(project)), capture_output=True, text=True, encoding='utf-8', timeout=25)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn('PASS', result.stdout)

    def _exercise(self, scenario):
        errors, calls = [], []
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / 'jobs.xlsx'
            source = Path(directory) / 'links.csv'
            source.write_text('job_url\n' + URL + '\n' + URL + '\n', encoding='utf-8')

            def backend(urls, output, profile, ready, **options):
                calls.append((list(urls), options['resume']))
                ready('Mock browser: sign in manually')
                if options['cancelled']() or not urls:
                    return []
                if scenario == 'worker_error' and len(calls) == 1:
                    raise OSError('Disk unavailable')
                row = dict(RECORD)
                if scenario == 'retry_partial' and len(calls) == 1:
                    row['status'] = 'partial'
                    row['notes'] = 'Company field missing'
                save_progress(output, urls, [row])
                write_workbook([row], output)
                options['progress'](1, len(urls), URL, row['status'])
                return [row]

            root = gui.tk.Tk()
            app = gui.ExporterApp(root, backend=backend, project_dir=Path(directory))
            stage, done = 0, False
            app.output.set(str(target))

            def finish():
                nonlocal done
                done = True
                app.close()

            def tick():
                nonlocal stage
                try:
                    if stage == 0:
                        self.assertFalse(app.more_frame.winfo_manager())
                        self.assertFalse(app.details_frame.winfo_manager())
                        self.assertFalse(app.login_button.winfo_manager())
                        self.assertTrue(app.start_button.instate(['disabled']))
                        if scenario == 'small_result':
                            root.geometry('640x540')
                            root.update_idletasks()
                        if scenario == 'layout':
                            root.geometry('640x540')
                            root.update_idletasks()
                            self.assertGreater(app.canvas.bbox('all')[3], 540)
                            self.assertTrue(app.start_button.winfo_manager())
                            app.toggle_more()
                            self.assertTrue(app.more_frame.winfo_manager())
                            app.toggle_more()
                            self.assertFalse(app.more_frame.winfo_manager())
                            finish()
                            return
                        if scenario in ('restore', 'restore_edit'):
                            save_progress(target, [URL], [dict(RECORD, status='partial')])
                            with patch.object(gui.filedialog, 'askopenfilename', return_value=str(target.with_suffix('.progress.json'))):
                                app.restore_button.invoke()
                            self.assertTrue(app.resume.get())
                            self.assertEqual(app.urls_box.get('1.0', 'end').strip(), URL)
                            if scenario == 'restore_edit':
                                app.output.set(str(Path(directory) / 'new.xlsx'))
                        elif scenario == 'import':
                            with patch.object(gui.filedialog, 'askopenfilenames', return_value=[str(source)]):
                                app.import_button.invoke()
                            self.assertIn('1 unique', app.count_text.get())
                            self.assertTrue(app.clear_button.winfo_manager())
                        else:
                            app.urls_box.insert('1.0', 'bad link' if scenario == 'invalid_input' else URL + '\n' + URL)
                            app._update_count()
                        if scenario == 'invalid_input':
                            app.start_button.invoke()
                            self.assertTrue(errors and 'Pasted URLs:1' in errors[0])
                            errors.clear()
                            self.assertFalse(calls)
                            self.assertFalse(app.running)
                            finish()
                            return
                        if scenario == 'invalid_resume':
                            app.resume.set(True)
                        if scenario == 'overwrite_decline':
                            target.write_bytes(b'keep this workbook')
                            with patch.object(gui.messagebox, 'askyesno', return_value=False):
                                app.start_button.invoke()
                            self.assertFalse(calls)
                            self.assertFalse(app.running)
                            self.assertEqual(target.read_bytes(), b'keep this workbook')
                            finish()
                            return
                        if scenario == 'directory_output':
                            target.mkdir()
                            with patch.object(gui.messagebox, 'askyesno') as confirm:
                                app.start_button.invoke()
                            confirm.assert_not_called()
                            self.assertTrue(errors and 'folder' in errors[0])
                            errors.clear()
                            self.assertFalse(calls)
                            finish()
                            return
                        if scenario == 'locked_output':
                            with patch.object(gui, 'validate_output', side_effect=PermissionError('Close Excel first')):
                                app.start_button.invoke()
                            self.assertTrue(errors and 'Close Excel' in errors[0])
                            errors.clear()
                            self.assertFalse(calls)
                            finish()
                            return
                        app.start_button.invoke()
                        if scenario == 'invalid_resume':
                            self.assertTrue(errors and 'Cannot resume' in errors[0])
                            errors.clear()
                            self.assertFalse(calls)
                            finish()
                            return
                        self.assertTrue(app.running)
                        self.assertEqual(str(app.urls_box.cget('state')), 'disabled')
                        self.assertTrue(app.import_button.instate(['disabled']))
                        stage = 1
                    elif stage in (1, 3) and app.login_button.winfo_manager():
                        if scenario == 'small_result':
                            root.update_idletasks()
                            self.assertGreaterEqual(app.login_button.winfo_rooty(), app.canvas.winfo_rooty())
                            self.assertLessEqual(app.login_button.winfo_rooty() + app.login_button.winfo_height(),
                                                 app.canvas.winfo_rooty() + app.canvas.winfo_height())
                        if scenario in ('stop_login', 'close_running'):
                            app.close() if scenario == 'close_running' else app.stop_button.invoke()
                            if scenario == 'close_running':
                                return
                        else:
                            app.login_button.invoke()
                        stage += 1
                    elif stage in (2, 4) and not app.running:
                        self.assertEqual(str(app.urls_box.cget('state')), 'normal')
                        self.assertFalse(app.login_button.winfo_manager())
                        if scenario == 'stop_login':
                            self.assertFalse(target.exists())
                            self.assertFalse(app.result_frame.winfo_manager())
                            finish()
                            return
                        if scenario in ('worker_error', 'retry_partial') and stage == 2:
                            self.assertTrue(app.retry_button.winfo_manager())
                            if scenario == 'worker_error':
                                self.assertIn('Disk unavailable', app.logs.get('1.0', 'end'))
                                self.assertTrue(app.details_frame.winfo_manager())
                            app.retry_button.invoke()
                            stage = 3
                        elif scenario == 'sign_in_only' and stage == 2:
                            self.assertTrue(app.result_frame.winfo_manager())
                            app.start(sign_in_only=True)
                            self.assertFalse(app.result_frame.winfo_manager())
                            stage = 3
                        elif scenario == 'sign_in_only' and stage == 4:
                            self.assertIsNone(app.last_output)
                            self.assertFalse(app.result_frame.winfo_manager())
                            finish()
                            return
                        else:
                            self.assertTrue(app.result_frame.winfo_manager())
                            self.assertEqual(app.last_output, Path(directory) / 'new.xlsx' if scenario == 'restore_edit' else target)
                            self.assertEqual(float(app.progress_bar.cget('value')), 1)
                            if scenario == 'small_result':
                                root.update_idletasks()
                                self.assertGreaterEqual(app.open_button.winfo_rooty(), app.canvas.winfo_rooty())
                                self.assertLessEqual(app.open_button.winfo_rooty() + app.open_button.winfo_height(),
                                                     app.canvas.winfo_rooty() + app.canvas.winfo_height())
                            book = load_workbook(app.last_output)
                            self.assertEqual(book['Jobs']['B2'].value, RECORD['title'])
                            book.close()
                            if scenario == 'retry_partial':
                                self.assertEqual(calls, [([URL], False), ([URL], True)])
                            if scenario == 'restore':
                                self.assertEqual(calls, [([URL], True)])
                            if scenario == 'restore_edit':
                                self.assertEqual(calls, [([URL], False)])
                                self.assertFalse(app.resume.get())
                            if scenario == 'import':
                                app.clear_button.invoke()
                                self.assertFalse(app.files)
                            if scenario == 'open_missing':
                                app.last_output = Path(directory) / 'moved.xlsx'
                                app.open_button.invoke()
                                self.assertTrue(errors and 'moved' in errors[0])
                                errors.clear()
                            finish()
                            return
                    root.after(80, tick)
                except Exception as exc:
                    errors.append(repr(exc))
                    app._close_now()

            def timeout():
                errors.append('GUI scenario timed out')
                app._close_now()
            root.after(15000, timeout)
            root.after(150, tick)
            with patch.object(gui.messagebox, 'showerror', lambda title, message: errors.append(message)):
                root.mainloop()
            self.assertFalse(errors, repr(errors))
            self.assertTrue(done or scenario == 'close_running')

    def test_complete_export_and_progress(self): self.exercise('success')
    def test_import_deduplication_and_removal(self): self.exercise('import')
    def test_invalid_input_stays_editable(self): self.exercise('invalid_input')
    def test_output_failure_before_browser(self): self.exercise('locked_output')
    def test_resume_requires_snapshot(self): self.exercise('invalid_resume')
    def test_restore_loads_original_inputs(self): self.exercise('restore')
    def test_retry_partial_reuses_batch_without_duplicate(self): self.exercise('retry_partial')
    def test_worker_error_exposes_recovery(self): self.exercise('worker_error')
    def test_stop_at_login(self): self.exercise('stop_login')
    def test_close_waits_for_worker(self): self.exercise('close_running')
    def test_sign_in_only_does_not_offer_stale_result(self): self.exercise('sign_in_only')
    def test_moved_file_open_reports_actionable_error(self): self.exercise('open_missing')
    def test_small_window_scrolls_and_advanced_is_hidden(self): self.exercise('layout')
    def test_declined_overwrite_preserves_existing_file(self): self.exercise('overwrite_decline')
    def test_directory_is_not_offered_as_a_file_to_replace(self): self.exercise('directory_output')
    def test_saved_result_is_visible_in_small_window(self): self.exercise('small_result')
    def test_changed_restored_destination_starts_new_export(self): self.exercise('restore_edit')


if __name__ == '__main__':
    if len(sys.argv) == 3 and sys.argv[1] == '--scenario':
        DesktopTests()._exercise(sys.argv[2])
        print('PASS: ' + sys.argv[2])
    else:
        unittest.main()
