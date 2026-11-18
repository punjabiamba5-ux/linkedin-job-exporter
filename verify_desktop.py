"""Opt-in live acceptance test through the actual desktop controls.

Requires a session already signed into manually. No credentials are entered.
Defaults to a temporary single-job workbook; --file and --output test a batch.
"""
import argparse
import tempfile
from pathlib import Path

from openpyxl import load_workbook
from linkedin_exporter.gui import ExporterApp, tk
from linkedin_exporter.inputs import collect_urls


def run_test(urls, target, resume=False):
    root = tk.Tk()
    app = ExporterApp(root)
    app.output.set(str(target))
    app.urls_box.insert('1.0', '\n'.join(urls))
    app.resume.set(resume)
    app._update_count()
    result = {'continued': False}
    started = False

    def inspect():
        nonlocal started
        if not started:
            app.start_button.invoke()
            started = True
        if app.login_button.winfo_manager():
            # Continue only uses the browser session the user saved manually.
            # The exporter itself still checks login, CAPTCHA and access limits.
            app.login_button.invoke()
            result['continued'] = True
        if started and not app.running:
            result['log'] = app.logs.get('1.0', 'end').strip()
            result['output'] = app.last_output
            result['progress'] = float(app.progress_bar.cget('value'))
            result['ready'] = not app.start_button.instate(['disabled'])
            app.close()
        else:
            root.after(100, inspect)

    def timeout():
        result['error'] = 'Live desktop acceptance test timed out.'
        app.close()
    root.after(240000, timeout)
    root.after(500, inspect)
    root.mainloop()
    print(result.get('log', ''), flush=True)
    if result.get('error'):
        raise RuntimeError(result['error'])
    if result.get('output') != target:
        raise AssertionError('The desktop did not produce the requested workbook. See its export log.')
    book = load_workbook(target)
    try:
        values = list(book['Jobs'].values)
        rows = [dict(zip(values[0], row)) for row in values[1:]]
        print('LIVE_DESKTOP_ROWS', [(row['title'], row['status'], row['notes']) for row in rows], flush=True)
        assert len(rows) == len(urls)
        assert all(row['status'] == 'ok' for row in rows), 'Live access/extraction incomplete; see row notes.'
        assert result['ready'] and result['progress'] == len(urls)
    finally:
        book.close()
    print('PASS: desktop controls → browser → job/company extraction → saved Excel → ready state.', flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--file', type=Path)
    parser.add_argument('--output', type=Path)
    parser.add_argument('--resume', action='store_true')
    args = parser.parse_args()
    urls = collect_urls(files=[args.file]) if args.file else ['https://www.linkedin.com/jobs/view/4484925897/']
    if args.output:
        target = args.output.resolve()
        if target.exists() and not args.resume:
            raise ValueError('Choose a new output filename, or --resume. This test never confirms an overwrite.')
        run_test(urls, target, args.resume)
    else:
        with tempfile.TemporaryDirectory(prefix='linkedin-desktop-acceptance-') as directory:
            run_test(urls, Path(directory) / 'desktop.xlsx', args.resume)


if __name__ == '__main__':
    main()
