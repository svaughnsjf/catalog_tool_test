import os
import time
from datetime import datetime
from pathlib import Path

import pandas as pd
from dotenv import load_dotenv
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError


# ============================================================
# Configuration
# ============================================================

SITE_URL = "https://sjf-catalog-bice.vercel.app/"

AUTH_FILE = Path("auth_state.json")
ENV_FILE = Path(".env.local")
QUESTIONS_FILE = Path("questions.txt")
RESULTS_FILE = Path("results.csv")
SCREENSHOT_DIR = Path("screenshots")

# Catalog option values from the page's <select>
CATALOG_2025_2026_UNDERGRAD = "4c5af1e3-90b9-533e-8cf3-88590a9fcf4e"
CATALOG_2025_2026_GRAD = "8fc6a38b-a206-5928-a663-4e3f194fcd96"
CATALOG_2024_2025_UNDERGRAD = "0dc88cf4-f168-5df0-af31-558fda8f9f69"
CATALOG_2024_2025_GRAD = "252176fe-c43c-50dd-8fbd-3b1690b5b031"
CATALOG_2023_2024_UNDERGRAD = "5915aecf-83b4-5467-a2da-c559e3b43603"
CATALOG_2023_2024_GRAD = "e604e850-70a5-5b55-9c3f-662e7cd3d50c"
CATALOG_2022_2023_UNDERGRAD = "e58045e1-1b81-57de-b2e2-44a218d626b8"
CATALOG_2022_2023_GRAD = "022ed67b-ed7f-560f-934f-d7d70b25a4f3"

DEFAULT_CATALOG_VALUE = CATALOG_2025_2026_UNDERGRAD

# Increase for broad analytical questions
QUESTION_TIMEOUT_MS = 300000  # 5 minutes

# How long the assistant response text must stop changing before we treat it as complete
ANSWER_STABLE_SECONDS = 5

# Run headless on server. Set to False if you want to watch the browser.
HEADLESS = True


# ============================================================
# Utility functions
# ============================================================

def load_credentials():
    """
    Loads credentials from .env.local if present.

    Expected .env.local format:
        CATALOG_EMAIL=your_email
        CATALOG_PASSWORD=your_password
    """
    if ENV_FILE.exists():
        load_dotenv(ENV_FILE)

    return (
        os.environ.get("CATALOG_EMAIL"),
        os.environ.get("CATALOG_PASSWORD")
    )


def read_questions():
    """
    Reads questions from questions.txt.
    Assumes one question per non-blank line.
    """
    if not QUESTIONS_FILE.exists():
        raise FileNotFoundError(
            f"Missing {QUESTIONS_FILE}. Please create it with one question per line."
        )

    with open(QUESTIONS_FILE, "r", encoding="utf-8") as f:
        questions = [line.strip() for line in f if line.strip()]

    if not questions:
        raise ValueError(f"{QUESTIONS_FILE} exists but contains no questions.")

    return questions


def save_results(results):
    """
    Saves current results to CSV.
    Called after each question so progress is preserved if the run is interrupted.
    """
    pd.DataFrame(results).to_csv(RESULTS_FILE, index=False)


def save_screenshot(page, filename):
    """
    Saves a full-page screenshot and returns the screenshot path as a string.
    """
    SCREENSHOT_DIR.mkdir(exist_ok=True)
    path = SCREENSHOT_DIR / filename
    page.screenshot(path=str(path), full_page=True)
    return str(path)


# ============================================================
# Authentication and navigation
# ============================================================

def perform_login(page, context, email, password):
    """
    Performs fresh login and saves auth_state.json.
    """
    print("Performing fresh login...")

    page.goto(f"{SITE_URL.rstrip('/')}/login", wait_until="networkidle", timeout=60000)

    page.locator('input[type="email"]').wait_for(state="visible", timeout=15000)
    page.locator('input[type="email"]').fill(email)
    page.locator('input[type="password"]').fill(password)

    page.get_by_role("button", name="Access Audit Dashboard").click()

    try:
        page.wait_for_load_state("networkidle", timeout=60000)
    except PlaywrightTimeoutError:
        print("Network idle timeout after login; continuing with current page state.")

    page.wait_for_timeout(2000)

    if "/login" in page.url:
        body_text = page.locator("body").inner_text(timeout=10000)
        raise RuntimeError(
            "Login appears to have failed; still on /login.\n\n"
            f"Visible page text sample:\n{body_text[:2000]}"
        )

    context.storage_state(path=str(AUTH_FILE))
    print(f"Saved auth state to {AUTH_FILE}")


def ensure_authenticated(page, context):
    """
    Opens the site using existing storage state.
    If redirected to /login, uses credentials from .env.local.
    """
    page.goto(SITE_URL, wait_until="networkidle", timeout=60000)

    if "/login" not in page.url:
        print("Authenticated session is valid.")
        return

    print("Stored auth session missing or expired.")

    email, password = load_credentials()
    if not email or not password:
        raise ValueError(
            "Session expired and no credentials found.\n"
            "Create .env.local with CATALOG_EMAIL and CATALOG_PASSWORD."
        )

    perform_login(page, context, email, password)


def open_ai_assistant(page):
    """
    Opens the AI Catalog Assistant from the left sidebar.
    """
    print("Navigating to AI Catalog Assistant...")

    selectors = [
        "button:has-text('AI Catalog Assistant')",
        "text=AI Catalog Assistant"
    ]

    last_error = None

    for selector in selectors:
        try:
            page.locator(selector).first.click(timeout=15000)
            page.wait_for_timeout(1500)
            return
        except Exception as e:
            last_error = e

    raise RuntimeError(
        f"Could not open AI Catalog Assistant. Last error: {last_error}"
    )


def select_catalog_version(page, catalog_value=DEFAULT_CATALOG_VALUE):
    """
    Selects the active catalog version.
    """
    dropdown = page.locator("select").first
    dropdown.wait_for(state="visible", timeout=10000)

    current_val = dropdown.input_value()

    if current_val != catalog_value:
        print(f"Selecting catalog version value: {catalog_value}")
        dropdown.select_option(value=catalog_value)
        page.wait_for_timeout(1000)
    else:
        print("Catalog version already selected.")


def start_new_chat(page):
    """
    Starts a new chat before each question to avoid contamination from prior answers.
    """
    new_chat_btn = page.locator("button[title='Start a new chat'], button:has-text('New Chat')")

    try:
        new_chat_btn.first.wait_for(state="visible", timeout=5000)
        new_chat_btn.first.click()
        page.wait_for_timeout(1000)
        print("  --> Started new chat.")
    except PlaywrightTimeoutError:
        print("  --> New Chat button not found or not visible; continuing.")


# ============================================================
# Question submission and answer capture
# ============================================================

def wait_for_ask_button_enabled(page, timeout=3000):
    """
    Waits for the Ask Assistant button to become enabled.

    Steve observed that this usually happens less than one second after typing.
    Timeout is intentionally short so genuine UI problems surface quickly.
    """
    page.wait_for_function(
        """() => {
            const buttons = [...document.querySelectorAll("button[type='submit']")];
            const askButton = buttons.find(b => b.innerText.includes("Ask Assistant"));
            return askButton && !askButton.disabled;
        }""",
        timeout=timeout
    )


def fill_question_and_get_submit_button(page, question_text):
    """
    Fills the question textarea and waits for the Ask Assistant button to light up.
    """
    textarea = page.locator("textarea[placeholder*='Ask about academic policies']")
    textarea.wait_for(state="visible", timeout=10000)
    textarea.click()
    textarea.fill(question_text)

    submit_btn = page.locator("button[type='submit']:has-text('Ask Assistant')")
    submit_btn.wait_for(state="visible", timeout=10000)

    try:
        wait_for_ask_button_enabled(page, timeout=3000)
    except PlaywrightTimeoutError:
        # One fallback: simulate one harmless key event by appending/removing a space.
        # This can help React-controlled components notice the input value.
        print("  --> Ask button did not enable quickly; nudging textarea input event.")
        textarea.press("End")
        textarea.type(" ")
        textarea.press("Backspace")

        wait_for_ask_button_enabled(page, timeout=3000)

    return submit_btn


def get_markdown_messages(page):
    """
    Returns all markdown-content texts currently on the page.
    """
    try:
        return page.locator(".markdown-content").all_inner_texts()
    except Exception:
        return []


def wait_for_assistant_answer(page, question_text, before_count, start_time, timeout_ms):
    """
    Waits for the assistant answer.

    Observed message pattern:
        .markdown-content[0] = welcome message
        .markdown-content[1] = user question
        .markdown-content[2] = assistant answer

    For each question after New Chat, we expect at least two new markdown-content
    blocks after submission: the echoed user question and the assistant response.

    This function watches the latest markdown-content block and returns it once
    it has stopped changing for ANSWER_STABLE_SECONDS.
    """
    deadline = time.time() + (timeout_ms / 1000)

    latest_answer = ""
    last_answer_text = ""
    stable_since = None

    while time.time() < deadline:
        page.wait_for_timeout(1000)

        markdown_texts = get_markdown_messages(page)
        current_count = len(markdown_texts)

        if current_count > before_count:
            candidate = markdown_texts[-1].strip()

            # Avoid returning the user's own echoed question as the answer.
            if candidate and candidate.strip() != question_text.strip():
                latest_answer = candidate

                if latest_answer != last_answer_text:
                    last_answer_text = latest_answer
                    stable_since = time.time()
                    print(
                        f"  --> Assistant response detected; length {len(latest_answer)} chars",
                        flush=True
                    )
                else:
                    stable_for = time.time() - stable_since if stable_since else 0

                    if stable_for >= ANSWER_STABLE_SECONDS:
                        elapsed_time = round(time.time() - start_time, 2)
                        return latest_answer, elapsed_time

        # Secondary rescue:
        # If we have at least two new markdown blocks, the last is likely the answer.
        # We still prefer the stable-text return above, but keep latest_answer populated.
        if current_count >= before_count + 2:
            candidate = markdown_texts[-1].strip()
            if candidate and candidate.strip() != question_text.strip():
                latest_answer = candidate

    # Final rescue before marking timeout:
    final_texts = get_markdown_messages(page)

    if len(final_texts) >= before_count + 2:
        candidate = final_texts[-1].strip()
        if candidate and candidate.strip() != question_text.strip():
            elapsed_time = round(time.time() - start_time, 2)
            print("  --> Returning final detected answer despite timeout boundary.")
            return candidate, elapsed_time

    final_combined = "\n\n---MESSAGE---\n\n".join(final_texts)

    raise PlaywrightTimeoutError(
        "Timed out waiting for assistant response to complete.\n\n"
        f"Initial markdown count: {before_count}\n"
        f"Final markdown count: {len(final_texts)}\n"
        f"Final markdown text sample:\n{final_combined[:3000]}"
    )


def ask_question_and_get_answer(page, question_text, timeout_ms=QUESTION_TIMEOUT_MS):
    """
    Starts a clean chat, selects the catalog, submits one question,
    and returns the assistant answer plus elapsed time.
    """
    start_new_chat(page)
    select_catalog_version(page)

    submit_btn = fill_question_and_get_submit_button(page, question_text)

    before_texts = get_markdown_messages(page)
    before_count = len(before_texts)

    print(f"  --> Markdown messages before submit: {before_count}")
    print("  --> Clicking Ask Assistant...")

    start_time = time.time()
    submit_btn.click()

    answer, elapsed_time = wait_for_assistant_answer(
        page=page,
        question_text=question_text,
        before_count=before_count,
        start_time=start_time,
        timeout_ms=timeout_ms
    )

    return answer, elapsed_time


# ============================================================
# Main test runner
# ============================================================

def run_test_suite():
    SCREENSHOT_DIR.mkdir(exist_ok=True)

    questions = read_questions()
    print(f"Loaded {len(questions)} test questions from {QUESTIONS_FILE}")

    results = []

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=HEADLESS)

        if AUTH_FILE.exists():
            print(f"Using saved auth state from {AUTH_FILE}")
            context = browser.new_context(storage_state=str(AUTH_FILE))
        else:
            print("No saved auth state found; creating fresh browser context.")
            context = browser.new_context()

        page = context.new_page()

        try:
            ensure_authenticated(page, context)
            open_ai_assistant(page)

            for idx, question_text in enumerate(questions, start=1):
                print()
                print(f"[{idx}/{len(questions)}] Running Question: {question_text[:80]}...")

                record = {
                    "question_num": idx,
                    "question": question_text,
                    "answer": "",
                    "response_time_sec": None,
                    "status": "pending",
                    "error": "",
                    "timestamp": datetime.now().isoformat(),
                    "screenshot": ""
                }

                try:
                    answer, duration = ask_question_and_get_answer(
                        page,
                        question_text,
                        timeout_ms=QUESTION_TIMEOUT_MS
                    )

                    record["answer"] = answer
                    record["response_time_sec"] = duration
                    record["status"] = "success"

                    print(f"  --> SUCCESS in {duration}s")

                except PlaywrightTimeoutError as e:
                    screenshot_path = save_screenshot(page, f"timeout_q{idx}.png")

                    record["status"] = "timeout"
                    record["error"] = str(e)
                    record["screenshot"] = screenshot_path

                    print(f"  --> TIMEOUT on question {idx}")
                    print(f"  --> Screenshot saved to {screenshot_path}")

                except Exception as e:
                    screenshot_path = save_screenshot(page, f"error_q{idx}.png")

                    record["status"] = "failed"
                    record["error"] = str(e)
                    record["screenshot"] = screenshot_path

                    print(f"  --> FAILED on question {idx}: {e}")
                    print(f"  --> Screenshot saved to {screenshot_path}")

                results.append(record)
                save_results(results)

        finally:
            browser.close()

    print()
    print(f"Audit test suite completed. Results saved to: {RESULTS_FILE}")


if __name__ == "__main__":
    run_test_suite()
