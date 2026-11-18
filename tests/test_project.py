import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from openpyxl import load_workbook
from playwright.sync_api import BrowserType, sync_playwright

from linkedin_exporter.browser import AccessBlocked, check_access, company_record, export_jobs, job_record, read_page
from linkedin_exporter.inputs import collect_urls, normalize_job_url
from linkedin_exporter.workbook import write_workbook

JOB = '''<html><body><main>
<div class="job-details-jobs-unified-top-card">
<div class="job-details-jobs-unified-top-card__job-title"><h1>Python Engineer</h1></div>
<div class="job-details-jobs-unified-top-card__company-name"><a href="/company/example/">Example Ltd</a></div>
<div class="job-details-jobs-unified-top-card__primary-description-container"><span class="tvm__text--low-emphasis">London, England</span> · 2 days ago</div>
<div class="job-details-jobs-unified-top-card__job-insight">£60,000/yr - £80,000/yr · Full-time · Hybrid · Mid-Senior level</div>
</div>
<div id="job-details">Build Python systems.</div>
<button class="jobs-description__footer-button" onclick="document.getElementById('job-details').innerText+=' Full expanded description.';this.remove()">Show more</button>
<span style="display:none">This hidden content must not be exported.</span>
</main></body></html>'''
COMPANY = '''<html><body><main><h1>Example Ltd</h1>
<p class="org-about-us-organization-description__text">We build useful software.</p>
<dl><dt>Website</dt><dd><a href="https://example.com">https://example.com</a></dd>
<dt>Industry</dt><dd>Software Development</dd>
<dt>Company size</dt><dd>51-200 employees</dd><dd>80 associated members</dd>
<dt>Headquarters</dt><dd>London</dd><dt>Founded</dt><dd>2017</dd>
<dt>Specialties</dt><dd>Python, data</dd></dl></main></body></html>'''


class InputTests(unittest.TestCase):
    def test_normalization_duplicates_and_files(self):
        with tempfile.TemporaryDirectory() as folder:
            csv = Path(folder) / "urls.csv"
            csv.write_text('\ufeffjob_url,notes\nhttps://uk.linkedin.com/jobs/view/python-engineer-123/?trackingId=x,example\n', encoding="utf-8")
            self.assertEqual(collect_urls("https://www.linkedin.com/jobs/view/123/\n# skip", [csv]), ["https://www.linkedin.com/jobs/view/123/"])
        self.assertEqual(normalize_job_url("https://www.linkedin.com/jobs/search/?currentJobId=987"), "https://www.linkedin.com/jobs/view/987/")
        self.assertEqual(normalize_job_url("https://www.linkedin.com/jobs/search-results/?currentJobId=987&keywords=AI"), "https://www.linkedin.com/jobs/view/987/")

    def test_reject_foreign_hosts_and_search_without_selected_job(self):
        for value in ("https://linkedin.com.evil.com/jobs/view/123/", "https://www.linkedin.com/jobs/search/", "http://linkedin.com/jobs/view/123/"):
            with self.assertRaises(ValueError):
                normalize_job_url(value)


class WorkbookTests(unittest.TestCase):
    def test_long_unicode_text_and_formula_safety(self):
        with tempfile.TemporaryDirectory() as folder:
            output = Path(folder) / "test.xlsx"
            description = "😀" * 18000 + "\nFinal paragraph."
            write_workbook([dict(job_url="https://www.linkedin.com/jobs/view/123/", title="=1+1",
                                 description=description, company_about="=HYPERLINK(\"bad\")",
                                 raw_job_text="Text\x00with control", status="ok")], output)
            book = load_workbook(output)
            self.assertEqual(book["Jobs"]["A1"].value, "job_url")
            self.assertEqual(book["Jobs"]["B2"].data_type, "s")
            self.assertEqual(book["Jobs"]["B2"].value, "=1+1")
            parts = [row[3] for row in book["Descriptions"].iter_rows(min_row=2, values_only=True)]
            self.assertEqual("".join(parts), description)
            self.assertEqual(book["Page text"]["E2"].value, "Textwith control")
            self.assertGreater(book["Long fields"].max_row, 2)
            book.close()


class BrowserTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.playwright = sync_playwright().start()
        options = {"headless": True}
        if os.environ.get("TEST_BROWSER_EXECUTABLE"):
            options["executable_path"] = os.environ["TEST_BROWSER_EXECUTABLE"]
        cls.browser = cls.playwright.chromium.launch(**options)

    @classmethod
    def tearDownClass(cls):
        cls.browser.close()
        cls.playwright.stop()

    def test_visible_job_company_and_expansion(self):
        page = self.browser.new_page()
        page.route("**/jobs/view/123/", lambda route: route.fulfill(body=JOB, content_type="text/html"))
        page.route("**/company/example/about/", lambda route: route.fulfill(body=COMPANY, content_type="text/html"))
        record = job_record("https://www.linkedin.com/jobs/view/123/", read_page(page, "https://www.linkedin.com/jobs/view/123/", "job"))
        self.assertEqual(record["title"], "Python Engineer")
        self.assertEqual(record["company_name"], "Example Ltd")
        self.assertEqual(record["location"], "London, England")
        self.assertEqual(record["posted"], "2 days ago")
        self.assertEqual(record["job_type"], "Full-time")
        self.assertEqual(record["workplace_type"], "Hybrid")
        self.assertIn("Full expanded description.", record["description"])
        self.assertNotIn("hidden content", record["raw_job_text"])
        info = company_record(read_page(page, record["company_url"], "company"))
        self.assertEqual(info["company_industry"], "Software Development")
        self.assertIn("51-200 employees", info["company_size"])
        self.assertEqual(info["company_headquarters"], "London")
        page.close()

    def test_checkpoint_is_not_silently_scraped(self):
        page = self.browser.new_page()
        page.route("**/*", lambda route: route.fulfill(body="<h1>Verification</h1>", content_type="text/html"))
        page.goto("https://www.linkedin.com/checkpoint/challenge/")
        with self.assertRaises(AccessBlocked):
            check_access(page)
        page.close()

    def test_closed_posting_is_flagged_and_apply_is_never_clicked(self):
        page = self.browser.new_page()
        active = JOB.replace('<div class="job-details-jobs-unified-top-card">', '<div class="job-details-jobs-unified-top-card"><button onclick="window.applied=true">Apply</button>')
        page.route('**/*', lambda r: r.fulfill(body=active, content_type='text/html'))
        data = read_page(page, 'https://www.linkedin.com/jobs/view/123/', 'job')
        self.assertEqual(job_record('https://www.linkedin.com/jobs/view/123/', data)['application_status'], 'accepting applications')
        self.assertFalse(page.evaluate('!!window.applied'))
        page.unroute('**/*')
        closed = active.replace('Python Engineer</h1>', 'Python Engineer</h1><p>No longer accepting applications</p>')
        page.route('**/*', lambda r: r.fulfill(body=closed, content_type='text/html'))
        data = read_page(page, 'https://www.linkedin.com/jobs/view/123/', 'job')
        self.assertEqual(data['application_status'], 'closed')
        self.assertFalse(page.evaluate('!!window.applied'))
        page.close()

    def test_normal_description_is_not_a_rate_limit_screen(self):
        page = self.browser.new_page()
        page.route('**/*', lambda r: r.fulfill(body=JOB.replace('Build Python systems.', 'Handle too many requests errors and verify you are human flows.'), content_type='text/html'))
        response = page.goto('https://www.linkedin.com/jobs/view/123/')
        check_access(page, response)
        page.evaluate("document.body.insertAdjacentHTML('beforeend', '<div role=alert>Too many requests</div>')")
        with self.assertRaises(AccessBlocked):
            check_access(page)
        page.unroute('**/*')
        page.route('**/*', lambda r: r.fulfill(body='<h1>Too many requests</h1>', status=429, content_type='text/html'))
        response = page.goto('https://www.linkedin.com/login')
        with self.assertRaisesRegex(AccessBlocked, 'HTTP 429'):
            check_access(page, response)
        page.close()

    def test_unexpanded_legacy_description_is_reported(self):
        page = self.browser.new_page()
        page.route('**/*', lambda r: r.fulfill(body=JOB.replace('onclick=', 'data-unused='), content_type='text/html'))
        data = read_page(page, 'https://www.linkedin.com/jobs/view/123/', 'job')
        self.assertFalse(data['description_expanded'])
        self.assertIn('Build Python', data['description'])
        page.close()

    def test_current_signed_in_layout_and_scoped_labels(self):
        job = '''<main><section aria-label="Primary content"><div data-testid="lazy-column">
        <div><a href="/company/example/life/"><p>Example Ltd</p></a>
        <div><p><a href="/jobs/view/123/">AI Engineer</a></p></div><p><span>Noida, Uttar Pradesh, India</span> · 1 week ago · 100 applicants</p>
        <a href="/jobs/view/123/">Hybrid</a><a href="/jobs/view/123/">Full-time</a>
        <a href="/jobs/view/123/">₹2M/yr - ₹3M/yr</a></div>
        <div componentkey="JobDetails_AboutTheJob_123"><h2>About the job</h2>
        <span data-testid="expandable-text-box">Build AI systems.<button data-testid="expandable-text-button"
        onclick="this.parentElement.innerText='Build AI systems. Final expanded paragraph.'">… more</button></span></div>
        </div></section><aside><h1>Unrelated recommendation</h1></aside></main>'''
        company = '''<main><div componentkey="pages.topCard.123"><h2>Example Ltd</h2><p>Useful AI</p></div>
        <section><h2>Overview</h2><p>We build useful AI.</p>
        <div><div><p>Industry</p></div><div><p>Software Development</p></div></div>
        <div><div><p>Company size</p></div><div><p>51-200 employees</p></div><div><p>82 associated members</p></div></div>
        <div><div><p>Headquarters</p></div><div><p>Noida</p></div></div></section>
        <aside><p>Industry</p><p>Retail</p></aside></main>'''
        page = self.browser.new_page()
        page.route('**/jobs/view/123/', lambda r: r.fulfill(body=job, content_type='text/html; charset=utf-8'))
        page.route('**/company/example/about/', lambda r: r.fulfill(body=company, content_type='text/html; charset=utf-8'))
        record = job_record('https://www.linkedin.com/jobs/view/123/', read_page(page, 'https://www.linkedin.com/jobs/view/123/', 'job'))
        self.assertEqual(record['title'], 'AI Engineer')
        self.assertEqual(record['location'], 'Noida, Uttar Pradesh, India')
        self.assertEqual(record['posted'], '1 week ago')
        self.assertEqual(record['job_type'], 'Full-time')
        self.assertEqual(record['workplace_type'], 'Hybrid')
        self.assertEqual(record['salary'], '₹2M/yr - ₹3M/yr')
        self.assertTrue(record['description_expanded'])
        self.assertEqual(record['description'], 'Build AI systems. Final expanded paragraph.')
        info = company_record(read_page(page, record['company_url'], 'company'))
        self.assertEqual(info['company_industry'], 'Software Development')
        self.assertEqual(info['company_size'], '51-200 employees\n82 associated members')
        self.assertEqual(info['company_about'], 'We build useful AI.')
        self.assertEqual(info['company_headquarters'], 'Noida')
        page.close()

    def test_description_control_added_after_initial_layout(self):
        page = self.browser.new_page()
        html = '''<main><div data-testid="lazy-column"><div><a href="/company/example/"><p>Example</p></a><p>AI Engineer</p></div>
        <div componentkey="JobDetails_AboutTheJob_123"><span data-testid="expandable-text-box" id="text" style="display:block;position:relative">First paragraph.<br><br>Second paragraph.<br><br>Final paragraph.</span></div></div></main>
        <script>setTimeout(() => { const box=document.getElementById('text');box.style.maxHeight='30px';box.style.overflow='hidden';
        const button=document.createElement('button');button.dataset.testid='expandable-text-button';button.innerText='… more';button.style.position='absolute';button.style.bottom='0';
        button.onclick=()=>{box.style.maxHeight='none';button.remove()};box.append(button); },300);</script>'''
        page.route('**/jobs/view/123/', lambda r: r.fulfill(body=html, content_type='text/html; charset=utf-8'))
        data = read_page(page, 'https://www.linkedin.com/jobs/view/123/', 'job')
        self.assertTrue(data['description_expanded'])
        self.assertTrue(data['description'].endswith('Final paragraph.'))
        page.close()


class PipelineTests(unittest.TestCase):
    def test_pipeline_partial_error_cache_and_checkpoint(self):
        original_launch = BrowserType.launch_persistent_context
        requests = []

        def launch(browser_type, **kwargs):
            kwargs["headless"] = True
            if os.environ.get("TEST_BROWSER_EXECUTABLE"):
                kwargs["executable_path"] = os.environ["TEST_BROWSER_EXECUTABLE"]
            context = original_launch(browser_type, **kwargs)
            def route_request(route):
                url = route.request.url
                requests.append(url)
                if "/company/incomplete/" in url:
                    body, status = COMPANY.replace('<dt>Company size</dt><dd>51-200 employees</dd><dd>80 associated members</dd>', ''), 200
                elif "/company/" in url:
                    body, status = COMPANY, 200
                elif "/view/3/" in url:
                    body, status = JOB.replace('/company/example/', '/company/incomplete/'), 200
                elif "/view/4/" in url:
                    body, status = "<h1>Page unavailable</h1>", 404
                elif "/view/5/" in url:
                    body, status = "<h1>Too many requests</h1>", 429
                elif "/view/" in url:
                    body, status = JOB, 200
                else:
                    body, status = "<h1>Mock login</h1>", 200
                route.fulfill(body=body, status=status, content_type="text/html")
            context.route("**/*", route_request)
            return context

        with tempfile.TemporaryDirectory() as folder, patch.object(BrowserType, "launch_persistent_context", launch):
            target = Path(folder) / "jobs.xlsx"
            records = export_jobs([f"https://www.linkedin.com/jobs/view/{i}/" for i in range(1, 7)],
                                  target, Path(folder) / "profile", lambda message: None, log=lambda message: None, delay=0)
            self.assertEqual([r["status"] for r in records], ["ok", "ok", "partial", "error", "blocked"])
            self.assertIn("company_size", records[2]["notes"])
            self.assertEqual(sum("/company/example/" in url for url in requests), 1)
            self.assertFalse(any("/view/6/" in url for url in requests))
            book = load_workbook(target)
            self.assertEqual(book["Jobs"].max_row, 6)
            self.assertEqual(book["Companies"]["D2"].value, "Software Development")
            book.close()


if __name__ == "__main__":
    unittest.main()
