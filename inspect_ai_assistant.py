from pathlib import Path
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError

SITE_URL = "https://sjf-catalog-bice.vercel.app/"
AUTH_FILE = "auth_state.json"
SCREENSHOT_DIR = Path("screenshots")


def print_elements(page, selector, label, include_text=True, limit=100):
    print(f"\n{label}:")
    elements = page.locator(selector)
    count = elements.count()
    print(f"Count: {count}")

    for i in range(min(count, limit)):
        el = elements.nth(i)
        try:
            tag = el.evaluate("node => node.tagName.toLowerCase()")
        except Exception:
            tag = None

        data = {
            "index": i,
            "tag": tag,
            "type": el.get_attribute("type"),
            "name": el.get_attribute("name"),
            "id": el.get_attribute("id"),
            "class": el.get_attribute("class"),
            "placeholder": el.get_attribute("placeholder"),
            "aria-label": el.get_attribute("aria-label"),
            "role": el.get_attribute("role"),
            "value": el.get_attribute("value"),
            "href": el.get_attribute("href"),
        }

        if include_text:
            try:
                text = el.inner_text(timeout=1000)
                data["text"] = text[:300]
            except Exception:
                data["text"] = None

        print(data)


def click_ai_catalog_assistant(page):
    print("Clicking AI Catalog Assistant...")

    selectors = [
        lambda: page.get_by_role("button", name="AI Catalog Assistant"),
        lambda: page.locator("button:has-text('AI Catalog Assistant')"),
        lambda: page.locator("text=AI Catalog Assistant"),
    ]

    last_error = None

    for selector_factory in selectors:
        try:
            target = selector_factory()
            target.first.click(timeout=10000)
            return
        except Exception as e:
            last_error = e

    raise RuntimeError(f"Could not click AI Catalog Assistant. Last error: {last_error}")


def main():
    if not Path(AUTH_FILE).exists():
        raise FileNotFoundError(
            f"Missing {AUTH_FILE}. Run login_probe.py first."
        )

    SCREENSHOT_DIR.mkdir(exist_ok=True)

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(storage_state=AUTH_FILE)
        page = context.new_page()

        print("Opening authenticated site...")
        page.goto(SITE_URL, wait_until="networkidle", timeout=60000)

        print("Before click title:", page.title())
        print("Before click URL:", page.url)

        click_ai_catalog_assistant(page)

        try:
            page.wait_for_load_state("networkidle", timeout=60000)
        except PlaywrightTimeoutError:
            print("Network idle timeout after clicking AI Catalog Assistant; continuing.")

        page.wait_for_timeout(3000)

        print("\nAfter click title:", page.title())
        print("After click URL:", page.url)

        print("\nVisible page text sample:")
        body_text = page.locator("body").inner_text(timeout=10000)
        print(body_text[:5000])

        print_elements(page, "button", "Button elements")
        print_elements(page, "input", "Input elements", include_text=False)
        print_elements(page, "textarea", "Textarea elements", include_text=False)
        print_elements(page, "select", "Select elements")
        print_elements(page, "[contenteditable='true']", "Contenteditable elements")
        print_elements(page, "[role='textbox']", "Role=textbox elements")
        print_elements(page, "form", "Form elements")
        print_elements(page, "div", "Div elements", include_text=True, limit=50)

        screenshot_path = SCREENSHOT_DIR / "ai_assistant_page.png"
        page.screenshot(path=str(screenshot_path), full_page=True)
        print(f"\nSaved screenshot: {screenshot_path}")

        browser.close()


if __name__ == "__main__":
    main()
