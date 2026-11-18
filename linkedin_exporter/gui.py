"""A three-step desktop workflow. All Tk work stays on the main thread."""
import os
import queue
import subprocess
import sys
import threading
from datetime import datetime
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from .browser import export_jobs
from .inputs import collect_urls
from .state import load_progress, load_saved_batch, progress_path
from .workbook import validate_output

ROOT = Path(__file__).resolve().parents[1]


def result_message(records, total):
    complete = sum(row.get('status') == 'ok' for row in records)
    review = len(records) - complete
    remaining = total - len(records)
    closed = sum(row.get('application_status') == 'closed' for row in records)
    parts = [f'{len(records)} of {total} jobs saved', f'{complete} complete']
    if review:
        parts.append(f'{review} need review in Excel')
    if remaining:
        parts.append(f'{remaining} not attempted')
    if closed:
        parts.append(f'{closed} posting(s) no longer accepting applications; saved for reference')
    return '. '.join(parts) + '.'


class ExporterApp:
    def __init__(self, root, backend=None, project_dir=ROOT):
        self.root, self.backend, self.project_dir = root, backend or export_jobs, Path(project_dir)
        self.events = queue.Queue()
        self.signed_in, self.stop = threading.Event(), threading.Event()
        self.running = self.closing = False
        self.last_output = self.last_batch = None
        self.resume_anchor = None
        self.worker_thread = None
        self.poll_id = self.count_id = None
        self.files = []
        self.output = tk.StringVar(root, str(self.project_dir / 'exports' / f'LinkedIn_jobs_{datetime.now():%Y%m%d_%H%M%S}.xlsx'))
        self.channel = tk.StringVar(root, 'Chromium (recommended)')
        self.delay = tk.StringVar(root, '3')
        self.resume = tk.BooleanVar(root, False)
        self.status = tk.StringVar(root, 'Add job links above, then create your Excel file.')
        self.count_text = tk.StringVar(root, 'No job links added yet.')
        self.file_text = tk.StringVar(root, '')
        self.progress_text = tk.StringVar(root, '0 jobs saved')
        root.title('LinkedIn jobs to Excel')
        root.geometry(f'820x{min(760, max(580, root.winfo_screenheight() - 100))}')
        root.minsize(640, 540)
        style = ttk.Style(root)
        style.configure('Title.TLabel', font=('Segoe UI', 19, 'bold'))
        style.configure('Step.TLabelframe.Label', font=('Segoe UI', 11, 'bold'))
        style.configure('Primary.TButton', font=('Segoe UI', 11, 'bold'), padding=(14, 8))

        shell = ttk.Frame(root)
        shell.pack(fill='both', expand=True)
        self.canvas = tk.Canvas(shell, highlightthickness=0)
        scroll = ttk.Scrollbar(shell, orient='vertical', command=self.canvas.yview)
        self.canvas.configure(yscrollcommand=scroll.set)
        scroll.pack(side='right', fill='y')
        self.canvas.pack(side='left', fill='both', expand=True)
        self.body = ttk.Frame(self.canvas, padding=18)
        window = self.canvas.create_window((0, 0), window=self.body, anchor='nw')
        self.body.bind('<Configure>', lambda event: self.canvas.configure(scrollregion=self.canvas.bbox('all')))
        self.canvas.bind('<Configure>', lambda event: self.canvas.itemconfigure(window, width=event.width))
        root.bind('<MouseWheel>', self._wheel)
        ttk.Label(self.body, text='LinkedIn jobs to Excel', style='Title.TLabel').pack(anchor='w')
        ttk.Label(self.body, text='You provide: LinkedIn job links or a TXT/CSV list.\nYou get: an Excel file with full job descriptions and company details.', wraplength=720).pack(anchor='w', pady=(4, 14))

        step1 = ttk.LabelFrame(self.body, text='1. Add job links', style='Step.TLabelframe', padding=12)
        step1.pack(fill='x', pady=(0, 10))
        ttk.Label(step1, text='Paste one LinkedIn job link per line. No password is needed here.', wraplength=660).pack(anchor='w')
        self.urls_box = tk.Text(step1, height=5, wrap='word', font=('Segoe UI', 10), undo=True)
        self.urls_box.pack(fill='x', pady=8)
        self.urls_box.bind('<<Modified>>', self._edited)
        file_row = ttk.Frame(step1)
        file_row.pack(fill='x')
        self.import_button = ttk.Button(file_row, text='Import a TXT or CSV file…', command=self.choose_files)
        self.import_button.pack(side='left')
        self.clear_button = ttk.Button(file_row, text='Remove imported files', command=self.clear_files)
        self.clear_button.pack(side='left', padx=8)
        self.clear_button.pack_forget()
        ttk.Label(step1, textvariable=self.file_text, wraplength=660).pack(anchor='w', pady=(5, 0))
        ttk.Label(step1, textvariable=self.count_text).pack(anchor='w', pady=(4, 0))

        step2 = ttk.LabelFrame(self.body, text='2. Choose where to save', style='Step.TLabelframe', padding=12)
        step2.pack(fill='x', pady=(0, 10))
        self.output_entry = ttk.Entry(step2, textvariable=self.output)
        self.output_entry.pack(side='left', fill='x', expand=True)
        self.location_button = ttk.Button(step2, text='Choose location…', command=self.choose_output)
        self.location_button.pack(side='left', padx=(8, 0))

        step3 = ttk.LabelFrame(self.body, text='3. Create your Excel file', style='Step.TLabelframe', padding=12)
        step3.pack(fill='x', pady=(0, 10))
        ttk.Label(step3, text='A browser will open. Sign in to LinkedIn there, then return here to continue.', wraplength=660).pack(anchor='w')
        actions = ttk.Frame(step3)
        actions.pack(fill='x', pady=10)
        self.start_button = ttk.Button(actions, text='Create Excel file', style='Primary.TButton', command=self.start)
        self.start_button.pack(side='left')
        self.login_button = ttk.Button(actions, text='I am signed in — continue', style='Primary.TButton', command=self.continue_export)
        self.stop_button = ttk.Button(actions, text='Stop', command=self.cancel)
        self.progress_bar = ttk.Progressbar(step3, mode='determinate', maximum=1)
        self.progress_bar.pack(fill='x')
        ttk.Label(step3, textvariable=self.progress_text).pack(anchor='w', pady=(4, 0))
        ttk.Label(step3, textvariable=self.status, wraplength=660).pack(anchor='w', pady=(6, 0))
        self.result_frame = ttk.Frame(step3)
        self.result_title = ttk.Label(self.result_frame, text='Your Excel file is ready.', font=('Segoe UI', 11, 'bold'))
        self.result_title.pack(anchor='w', pady=(8, 5))
        self.result_path = ttk.Label(self.result_frame, wraplength=560)
        self.result_path.pack(anchor='w', pady=(0, 6))
        result_actions = ttk.Frame(self.result_frame)
        result_actions.pack(fill='x')
        self.open_button = ttk.Button(result_actions, text='Open Excel file', command=self.open_output)
        self.open_button.pack(side='left')
        self.folder_button = ttk.Button(result_actions, text='Show saved folder', command=self.open_folder)
        self.folder_button.pack(side='left', padx=8)
        self.retry_button = ttk.Button(step3, text='Retry unfinished jobs', command=self.retry)

        footer = ttk.Frame(self.body)
        footer.pack(fill='x')
        self.more_button = ttk.Button(footer, text='More options', command=self.toggle_more)
        self.more_button.pack(side='left')
        self.details_button = ttk.Button(footer, text='Show details', command=self.toggle_details)
        self.details_button.pack(side='left', padx=8)
        self.more_frame = ttk.LabelFrame(self.body, text='Optional settings', padding=12)
        row = ttk.Frame(self.more_frame)
        row.pack(fill='x')
        ttk.Label(row, text='Browser:').pack(side='left')
        self.browser_choice = ttk.Combobox(row, textvariable=self.channel, state='readonly', width=25,
            values=['Chromium (recommended)', 'Microsoft Edge', 'Google Chrome'])
        self.browser_choice.pack(side='left', padx=8)
        ttk.Label(row, text='Pause between pages:').pack(side='left')
        self.delay_box = ttk.Spinbox(row, from_=1, to=60, textvariable=self.delay, width=4)
        self.delay_box.pack(side='left', padx=5)
        ttk.Label(row, text='seconds').pack(side='left')
        self.resume_button = ttk.Checkbutton(self.more_frame, text='Continue the selected export instead of starting again', variable=self.resume)
        self.resume_button.pack(anchor='w', pady=8)
        advanced_actions = ttk.Frame(self.more_frame)
        advanced_actions.pack(fill='x')
        self.restore_button = ttk.Button(advanced_actions, text='Continue an earlier export…', command=self.restore)
        self.restore_button.pack(side='left')
        self.browser_button = ttk.Button(advanced_actions, text='Open sign-in browser only', command=lambda: self.start(sign_in_only=True))
        self.browser_button.pack(side='left', padx=8)
        self.details_frame = ttk.Frame(self.body)
        self.logs = tk.Text(self.details_frame, height=8, state='disabled', wrap='word', font=('Consolas', 9))
        self.logs.pack(side='left', fill='both', expand=True)
        log_scroll = ttk.Scrollbar(self.details_frame, command=self.logs.yview)
        log_scroll.pack(side='right', fill='y')
        self.logs.configure(yscrollcommand=log_scroll.set)
        self.input_controls = [self.import_button, self.clear_button, self.output_entry, self.location_button,
            self.browser_choice, self.delay_box, self.resume_button, self.restore_button, self.browser_button, self.more_button]
        self._update_count()
        root.protocol('WM_DELETE_WINDOW', self.close)
        self._poll()

    def _wheel(self, event):
        if not isinstance(event.widget, tk.Text) and event.delta:
            self.canvas.yview_scroll(-max(1, abs(event.delta) // 120) if event.delta > 0 else max(1, abs(event.delta) // 120), 'units')
            return 'break'

    def _edited(self, event=None):
        if self.urls_box.edit_modified():
            self.urls_box.edit_modified(False)
            if self.count_id:
                self.root.after_cancel(self.count_id)
            self.count_id = self.root.after(200, self._update_count)

    def _update_count(self):
        self.count_id = None
        text = self.urls_box.get('1.0', 'end').strip()
        try:
            urls = collect_urls(text, self.files)
            self.count_text.set(f'{len(urls)} unique job link(s) added. Duplicates are removed automatically.')
        except (ValueError, OSError):
            self.count_text.set('Some links need checking. Click Create Excel file for help.' if text or self.files else 'No job links added yet.')
        if not self.running:
            self.start_button.state(['!disabled'] if text or self.files else ['disabled'])

    def add_log(self, text):
        self.logs.configure(state='normal')
        self.logs.insert('end', text + '\n')
        self.logs.see('end')
        self.logs.configure(state='disabled')

    def choose_files(self):
        selected = filedialog.askopenfilenames(filetypes=[('Job link files', '*.txt *.csv')])
        if selected:
            self.files[:] = selected
            self.file_text.set('Imported: ' + ', '.join(Path(path).name for path in self.files))
            self.clear_button.pack(side='left', padx=8)
            self._update_count()

    def clear_files(self):
        self.files.clear()
        self.file_text.set('')
        self.clear_button.pack_forget()
        self._update_count()

    def choose_output(self):
        selected = filedialog.asksaveasfilename(defaultextension='.xlsx', initialfile=Path(self.output.get()).name,
                                               filetypes=[('Excel file', '*.xlsx')])
        if selected:
            self.output.set(selected)

    def toggle_more(self):
        if self.more_frame.winfo_manager():
            self.more_frame.pack_forget()
            self.more_button.configure(text='More options')
        else:
            self.more_frame.pack(fill='x', pady=8, before=self.details_frame) if self.details_frame.winfo_manager() else self.more_frame.pack(fill='x', pady=8)
            self.more_button.configure(text='Fewer options')

    def toggle_details(self):
        if self.details_frame.winfo_manager():
            self.details_frame.pack_forget()
            self.details_button.configure(text='Show details')
        else:
            self.details_frame.pack(fill='both', expand=True, pady=8)
            self.details_button.configure(text='Hide details')

    def restore(self):
        selected = filedialog.askopenfilename(filetypes=[('Saved exports', '*.xlsx *.progress.json')])
        if not selected:
            return
        target = Path(selected)
        if target.name.endswith('.progress.json'):
            target = target.with_name(target.name[:-len('.progress.json')] + '.xlsx')
        try:
            urls, records = load_saved_batch(target)
            self.files.clear()
            self.clear_files()
            self.urls_box.delete('1.0', 'end')
            self.urls_box.insert('1.0', '\n'.join(urls))
            self.output.set(str(target))
            self.resume.set(True)
            self.resume_anchor = (tuple(urls), target.resolve())
            self._update_count()
            self.status.set(f'Earlier export loaded: {len(records)} saved jobs. Click Create Excel file to continue.')
        except (ValueError, OSError) as exc:
            messagebox.showerror('Cannot continue that export', str(exc))

    def start(self, sign_in_only=False, retry=False):
        if self.running:
            return
        try:
            urls = [] if sign_in_only else collect_urls(self.urls_box.get('1.0', 'end'), self.files)
            target = Path(self.output.get()).expanduser().resolve()
            if not retry and self.resume_anchor and self.resume_anchor != (tuple(urls), target):
                self.resume.set(False)
                self.resume_anchor = None
            resume_batch = bool(urls and (self.resume.get() or retry))
            interval = float(self.delay.get())
            if not 1 <= interval <= 60:
                raise ValueError('The pause must be between 1 and 60 seconds. The recommended value is 3.')
            if urls:
                if resume_batch:
                    load_progress(target, urls)
                target = validate_output(target)
                if target.exists() and not resume_batch and not messagebox.askyesno('Replace this Excel file?', f'{target}\n\nReplace this file? Choose another location to keep it.'):
                    return
        except (ValueError, OSError) as exc:
            messagebox.showerror('Please check your links or save location', str(exc))
            return
        self.last_batch = (list(urls), target) if urls else None
        self.last_output = None
        self.result_frame.pack_forget()
        self.retry_button.pack_forget()
        self.running = True
        self.stop.clear()
        self.signed_in.clear()
        self.urls_box.configure(state='disabled')
        for control in self.input_controls + [self.start_button]:
            control.state(['disabled'])
        self.stop_button.pack(side='left', padx=8)
        self.stop_button.state(['!disabled'])
        self.progress_bar.configure(maximum=max(1, len(urls)), value=0)
        self.progress_text.set(f'0 of {len(urls)} jobs saved' if urls else 'Opening sign-in browser')
        self.status.set('Opening your browser…')
        browser = {'Microsoft Edge': 'msedge', 'Google Chrome': 'chrome'}.get(self.channel.get(), 'chromium')
        self.worker_thread = threading.Thread(target=self._worker, args=(urls, target, browser, interval, resume_batch), daemon=True)
        self.worker_thread.start()

    def _worker(self, urls, target, browser, interval, resume_batch):
        def ready(message):
            self.events.put(('login', message))
            while not self.signed_in.wait(0.1):
                if self.stop.is_set():
                    return
        try:
            records = self.backend(urls, target, self.project_dir / '.linkedin-profile', ready,
                log=lambda text: self.events.put(('log', text)), cancelled=self.stop.is_set, delay=interval,
                channel=browser, resume=resume_batch, progress=lambda *values: self.events.put(('progress', values)))
            self.events.put(('done', (records, target, len(urls))))
        except Exception as exc:
            self.events.put(('error', str(exc)))

    def continue_export(self):
        self.signed_in.set()
        self.login_button.pack_forget()
        self.status.set('Reading job and company pages. Your Excel file is saved as each job finishes.')

    def cancel(self):
        self.stop.set()
        self.stop_button.state(['disabled'])
        self.login_button.pack_forget()
        self.status.set('Stopping safely. Please wait for the current page to finish.')

    def retry(self):
        if self.last_batch:
            urls, target = self.last_batch
            self.files.clear()
            self.clear_files()
            self.urls_box.delete('1.0', 'end')
            self.urls_box.insert('1.0', '\n'.join(urls))
            self.output.set(str(target))
            self.start(retry=progress_path(target).exists())

    def _open(self, path):
        try:
            if not Path(path).exists():
                raise FileNotFoundError('The saved file or folder has been moved. Choose a new save location and export again.')
            if sys.platform == 'win32':
                os.startfile(str(path))
            else:
                subprocess.Popen(['open' if sys.platform == 'darwin' else 'xdg-open', str(path)])
        except OSError as exc:
            messagebox.showerror('Could not open the saved file', str(exc))

    def open_output(self):
        if self.last_output:
            self._open(self.last_output)

    def open_folder(self):
        if self.last_output:
            self._open(self.last_output.parent)

    def _idle(self):
        if self.worker_thread:
            self.worker_thread.join(timeout=0.5)
        self.running = False
        self.login_button.pack_forget()
        self.stop_button.pack_forget()
        self.urls_box.configure(state='normal')
        for control in self.input_controls:
            control.state(['!disabled'])
        self._update_count()

    def _poll(self):
        while not self.events.empty():
            kind, payload = self.events.get_nowait()
            if kind == 'log':
                self.add_log(payload)
            elif kind == 'progress':
                done, total, url, state = payload
                self.progress_bar.configure(maximum=max(1, total), value=done)
                self.progress_text.set(f'{done} of {total} jobs saved')
            elif kind == 'login':
                self.add_log(payload)
                if not self.stop.is_set():
                    self.login_button.pack(side='left', padx=8, before=self.stop_button)
                    self.status.set('Sign in to LinkedIn in the browser. Finish any verification yourself, then click “I am signed in — continue”.')
                    self.root.update_idletasks()
                    self.canvas.yview_moveto(1)
            else:
                self._idle()
                if kind == 'done':
                    records, target, total = payload
                    summary = result_message(records, total) if total else 'Sign-in browser closed. Your session is saved for the next export.'
                    self.status.set(summary)
                    self.add_log(summary)
                    if records:
                        self.last_output = Path(target)
                        self.result_title.configure(text='Your Excel file is ready.' if all(r.get('status') == 'ok' for r in records) else 'Your Excel file is saved. Some jobs need review.')
                        self.result_path.configure(text=str(target))
                        self.result_frame.pack(fill='x', pady=5)
                        self.add_log(f'Excel file: {target}')
                    if total and (len(records) < total or any(r.get('status') != 'ok' for r in records)):
                        self.retry_button.pack(anchor='w', pady=8)
                else:
                    self.status.set('The export could not finish. See details below, fix the issue, then retry.')
                    self.add_log(payload)
                    if not self.details_frame.winfo_manager():
                        self.toggle_details()
                    if self.last_batch:
                        self.retry_button.pack(anchor='w', pady=8)
                # Let Tk calculate the completed panel before revealing its actions.
                self.root.update_idletasks()
                self.canvas.yview_moveto(1)
                if self.closing:
                    self._close_now()
                    return
        self.poll_id = self.root.after(100, self._poll)

    def close(self):
        if self.running:
            self.closing = True
            self.cancel()
        else:
            self._close_now()

    def _close_now(self):
        for identifier in (self.poll_id, self.count_id):
            if identifier:
                self.root.after_cancel(identifier)
        self.root.destroy()


def launch():
    root = tk.Tk()
    ExporterApp(root)
    root.mainloop()
