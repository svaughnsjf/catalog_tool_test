import os
from pathlib import Path
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError

SITE_URL = "https://sjf-catalog-bice.vercel.app/"
ENV_FILE = Path(".env.local")
AUTH_FILE = "auth_state.json"
SCREENSHOT_DIR = Path("screenshots")


def load_env_file(path: Path):
    if not path.exists():
        raise FileNotFoundError(
            f"Missing {path}. Create it with CATALOG_EMAIL and CATALOG_PASSWORD."
        )

    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ[key.strip()] = value.strip()


def main():
    load_env_file(ENV_FILE)

    email = os.environ.get("CATALOG_EMAIL")
    password = os.environ.get("CATALOG_PASSWORD")

    if not email or not password:
        raise ValueError("CATALOG_EMAIL and CATALOG_PASSWORD must be set in .env.local")

    SCREENSHOT_DIR.mkdir(exist_ok=True)

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context()
        page = context.new_page()

        print("Opening site...")
        page.goto(SITE_URL, wait_until="networkidle", timeout=60000)

        print("Initial title:", page.title())
        print("Initial URL:", page.url)

        print("Filling login form...")
        page.locator('input[type="email"]').fill(email)
        page.locator('input[type="password"]').fill(password)

        print("Submitting login...")
        page.get_by_role("button", name="Access Audit Dashboard").click()

        try:
            page.wait_for_load_state("networkidle", timeout=60000)
        except PlaywrightTimeoutError:
            print("Network idle timeout after login; continuing with current page state.")

        page.wait_for_timeout(3000)

        print("After login title:", page.title())
        print("After login URL:", page.url)

        body_text = page.locator("body").inner_text(timeout=10000)
        print("\nVisible page text sample:")
        print(body_text[:3000])

        screenshot_path = SCREENSHOT_DIR / "after_login.png"
        page.screenshot(path=str(screenshot_path), full_page=True)
        print(f"\nSaved screenshot: {screenshot_path}")

        context.storage_state(path=AUTH_FILE)
        print(f"Saved auth state: {AUTH_FILE}")

        browser.close()


if __name__ == "__main__":
    main()
