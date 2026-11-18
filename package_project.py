"""Build a source-only distribution using an explicit allowlist."""
import hashlib
from pathlib import Path
from zipfile import ZipFile, ZIP_DEFLATED

ROOT = Path(__file__).resolve().parent
TARGET = ROOT.parent / 'linkedin-job-exporter-improved.zip'


def main():
    files = [ROOT / name for name in (
        '.gitignore', 'README.md', 'TEST_RESULTS.txt', 'WINDOWS_TEST_RESULTS.txt',
        'QA_REPORT.md', 'ACCEPTANCE_TESTS.md', 'QUICK_START.md', '.github/workflows/tests.yml', 'requirements.txt', 'setup_windows.bat', 'start_windows.bat',
        'run.py', 'live_review.py', 'verify_live_output.py', 'verify_desktop.py', 'package_project.py')]
    files += list((ROOT / 'linkedin_exporter').glob('*.py'))
    files += [ROOT / 'linkedin_exporter' / 'extract.js']
    files += list((ROOT / 'tests').glob('test_*.py'))
    files += [ROOT / 'examples' / name for name in ('jobs.csv', 'jobs.txt', 'sample_output.xlsx')]
    manifest = []
    with ZipFile(TARGET, 'w', compression=ZIP_DEFLATED) as archive:
        for source in sorted(set(files)):
            relative = source.relative_to(ROOT)
            assert not any(part in {'.git', '.venv', '.linkedin-profile', 'exports', '__pycache__'} for part in relative.parts)
            assert source.resolve().is_relative_to(ROOT)
            data = source.read_bytes()
            name = 'linkedin-job-exporter/' + relative.as_posix()
            archive.writestr(name, data)
            manifest.append(f'{hashlib.sha256(data).hexdigest()}  {relative.as_posix()}')
        archive.writestr('linkedin-job-exporter/SHA256SUMS.txt', '\n'.join(manifest) + '\n')
    with ZipFile(TARGET) as archive:
        assert archive.testzip() is None
        assert not any(part in {'.linkedin-profile', '.venv', 'exports', '__pycache__'}
                       for name in archive.namelist() for part in Path(name).parts)
        print(f'Created {TARGET} ({len(archive.namelist())} files). Private profiles and exports excluded.')


if __name__ == '__main__':
    main()
