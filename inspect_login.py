from playwright.sync_api import sync_playwright

SITE_URL = "https://sjf-catalog-bice.vercel.app/"

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_page()
    page.goto(SITE_URL, wait_until="networkidle", timeout=60000)

    print("Title:", page.title())
    print("URL:", page.url)

    print("\nVisible page text:")
    print(page.locator("body").inner_text(timeout=10000))

    print("\nInput elements:")
    inputs = page.locator("input")
    for i in range(inputs.count()):
        input_el = inputs.nth(i)
        print({
            "index": i,
            "type": input_el.get_attribute("type"),
            "name": input_el.get_attribute("name"),
            "id": input_el.get_attribute("id"),
            "placeholder": input_el.get_attribute("placeholder"),
            "aria-label": input_el.get_attribute("aria-label"),
            "autocomplete": input_el.get_attribute("autocomplete"),
        })

    print("\nTextarea elements:")
    textareas = page.locator("textarea")
    for i in range(textareas.count()):
        textarea_el = textareas.nth(i)
        print({
            "index": i,
            "name": textarea_el.get_attribute("name"),
            "id": textarea_el.get_attribute("id"),
            "placeholder": textarea_el.get_attribute("placeholder"),
            "aria-label": textarea_el.get_attribute("aria-label"),
        })

    print("\nButton elements:")
    buttons = page.locator("button")
    for i in range(buttons.count()):
        button_el = buttons.nth(i)
        print({
            "index": i,
            "text": button_el.inner_text(),
            "type": button_el.get_attribute("type"),
            "name": button_el.get_attribute("name"),
            "id": button_el.get_attribute("id"),
            "aria-label": button_el.get_attribute("aria-label"),
        })

    browser.close()
