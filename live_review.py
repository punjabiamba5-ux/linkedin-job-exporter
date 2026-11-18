"""Local interactive live-test helper. Never reads cookies or credential fields."""
import json
from pathlib import Path
from playwright.sync_api import sync_playwright
from linkedin_exporter.browser import check_access, read_page, EXTRACT

ROOT = Path(__file__).resolve().parent

def main():
    with sync_playwright() as pw:
        context = pw.chromium.launch_persistent_context(
            str(ROOT / '.linkedin-profile'), headless=False,
            viewport={'width': 1440, 'height': 1000})
        page = context.pages[0] if context.pages else context.new_page()
        print('READY', flush=True)
        try:
            while True:
                try:
                    command = json.loads(input())
                    action = command['action']
                    if action == 'close':
                        break
                    if action == 'goto':
                        response = page.goto(command['url'], wait_until='domcontentloaded', timeout=45000)
                        page.wait_for_timeout(3000)
                        check_access(page, response)
                    elif action == 'select_job':
                        page.get_by_role('button', name=command['name'], exact=True).click(timeout=10000)
                        page.wait_for_timeout(2500)
                        check_access(page)
                    elif action == 'extract':
                        data = read_page(page, command['url'], command['kind'])
                        print(json.dumps(data, ensure_ascii=True), flush=True)
                        continue
                    elif action == 'screenshot':
                        path = ROOT / 'exports' / command['filename']
                        path.parent.mkdir(exist_ok=True)
                        page.screenshot(path=str(path), full_page=True)
                        print(str(path), flush=True)
                        continue
                    elif action != 'inspect':
                        raise ValueError('Unknown action')
                    data = page.evaluate('''() => {
                        const main = document.body;
                        const visible = e => !!e.getClientRects().length;
                        return {url: location.href, title: document.title,
                          text: main.innerText,
                          links: [...main.querySelectorAll('a[href]')].filter(visible).map(e=>({text:e.innerText,href:e.href})),
                          buttons: [...main.querySelectorAll('button')].filter(visible).map(e=>({text:e.innerText,label:e.getAttribute('aria-label')})),
                          headings: [...main.querySelectorAll('h1,h2,h3')].filter(visible).map(e=>({text:e.innerText,tag:e.tagName,cls:e.className})),
                          definitions: [...main.querySelectorAll('dt,dd')].filter(visible).map(e=>({tag:e.tagName,text:e.innerText,cls:e.className})),
                          sections: [...main.querySelectorAll('h1,h2,h3')].filter(visible).map(e=>({heading:e.innerText,html:(e.closest('section') || e.parentElement.parentElement.parentElement).outerHTML.slice(0,40000)})),
                          landmarks: [...main.querySelectorAll('[data-testid], [componentkey]')].filter(visible).map(e=>({tag:e.tagName,testid:e.getAttribute('data-testid'),key:e.getAttribute('componentkey'),text:(e.innerText || "").slice(0,200)})),
                          jobLinks: [...main.querySelectorAll('a[href*=\"/jobs/view/\"]')].filter(visible).slice(0,3).map(e=>e.parentElement.parentElement.parentElement.outerHTML.slice(0,30000))};
                    }''')
                    if command.get('save'):
                        target = ROOT / 'exports' / command['save']
                        target.parent.mkdir(exist_ok=True)
                        target.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')
                        print(json.dumps({'saved':str(target),'url':page.url}), flush=True)
                    else:
                        print(json.dumps(data, ensure_ascii=True), flush=True)
                except EOFError:
                    break
                except Exception as exc:
                    print(json.dumps({'error':str(exc)}, ensure_ascii=True), flush=True)
        finally:
            context.close()

if __name__ == '__main__':
    main()

