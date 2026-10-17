"""Hybrid LMS course navigator for an authorized QA/test environment.

Behavior:
- Prompts for the course URL and waits for manual sign-in.
- Detects visible Moodle-style activities and skips completed ones.
- Ordinary quizzes: selects choices 1,2,3,4 repeatedly (round robin),
  handles multiple pages, and submits.
- Module/final assessments: opens and pauses for manual completion.
"""

import logging
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from selenium import webdriver
from selenium.common.exceptions import (
    ElementClickInterceptedException, StaleElementReferenceException,
    TimeoutException, WebDriverException,
)
from selenium.webdriver.common.by import By
from selenium.webdriver.remote.webelement import WebElement
from selenium.webdriver.support.ui import WebDriverWait

AUTHORIZED_TEST_ENVIRONMENT = True
PAGE_TIMEOUT = 60
POST_LOGIN_WAIT = 5
CONTENT_WAIT = 7
BETWEEN_ITEMS_WAIT = 7

BASE = Path(__file__).resolve().parent
LOG_FILE = BASE / "Hybrid_Course_Navigator_Round_Robin.log"
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
    handlers=[logging.FileHandler(LOG_FILE, encoding="utf-8"), logging.StreamHandler()],
)
log = logging.getLogger("course-navigator")


@dataclass(frozen=True)
class Activity:
    title: str
    url: str
    completed: bool
    quiz: bool
    assessment: bool


def clean(value: Optional[str]) -> str:
    return " ".join((value or "").split()).strip()


def make_driver() -> webdriver.Edge:
    options = webdriver.EdgeOptions()
    options.add_argument("--start-maximized")
    options.add_argument("--disable-notifications")
    driver = webdriver.Edge(options=options)
    driver.set_page_load_timeout(PAGE_TIMEOUT)
    return driver


def wait_ready(driver: webdriver.Edge) -> None:
    WebDriverWait(driver, PAGE_TIMEOUT).until(
        lambda d: d.execute_script("return document.readyState") == "complete"
    )


def visible(elements):
    result = []
    for element in elements:
        try:
            if element.is_displayed() and element.is_enabled():
                result.append(element)
        except StaleElementReferenceException:
            pass
    return result


def click(driver: webdriver.Edge, element: WebElement) -> None:
    driver.execute_script("arguments[0].scrollIntoView({block:'center'});", element)
    time.sleep(0.3)
    try:
        element.click()
    except (ElementClickInterceptedException, WebDriverException):
        driver.execute_script("arguments[0].click();", element)


def label(element: WebElement) -> str:
    return clean(element.text or element.get_attribute("value") or
                 element.get_attribute("aria-label") or element.get_attribute("title"))


def find_button(driver: webdriver.Edge, names, timeout=10) -> Optional[WebElement]:
    wanted = [name.casefold() for name in names]
    def locate(d):
        candidates = d.find_elements(
            By.XPATH, "//button | //a | //input[@type='submit'] | //input[@type='button']"
        )
        for item in visible(candidates):
            if any(name in label(item).casefold() for name in wanted):
                return item
        return False
    try:
        return WebDriverWait(driver, timeout).until(locate)
    except TimeoutException:
        return None


def click_button(driver, names, timeout=10, required=False) -> bool:
    button = find_button(driver, names, timeout)
    if button is None:
        if required:
            raise TimeoutException(f"Button not found: {names}")
        return False
    click(driver, button)
    return True


def is_assessment(title: str) -> bool:
    value = clean(title).casefold()
    return any(marker in value for marker in (
        "module assessment", "final assessment", "module exam", "final exam"
    ))


def completion_state(link: WebElement) -> bool:
    try:
        container = link.find_element(
            By.XPATH,
            "./ancestor::*[contains(@class,'activity') or contains(@class,'courseindex-item')][1]",
        )
    except WebDriverException:
        container = link
    state = " ".join(filter(None, [
        clean(container.text), clean(container.get_attribute("class")),
        clean(container.get_attribute("aria-label")),
        clean(container.get_attribute("data-completionstate")),
        clean(container.get_attribute("data-completion-state")),
    ])).casefold()
    markers = ("done: view", "done: receive a grade", "completed", "passed",
               "completion_complete", "completion-complete")
    if any(marker in state for marker in markers):
        return True
    selectors = (
        ".completion_complete", ".completion-complete",
        "[data-completionstate='1']", "[data-completion-state='complete']",
        "[aria-label*='Completed' i]", "[aria-label*='Done' i]",
    )
    for selector in selectors:
        try:
            if visible(container.find_elements(By.CSS_SELECTOR, selector)):
                return True
        except WebDriverException:
            pass
    return False


def collect_activities(driver: webdriver.Edge):
    driver.switch_to.default_content()
    found, seen = [], set()
    selector = (".courseindex-item a[href], .activityinstance a[href], "
                ".activity a[href], a[href*='/mod/']")
    for link in visible(driver.find_elements(By.CSS_SELECTOR, selector)):
        try:
            title = label(link)
            url = clean(link.get_attribute("href"))
            if not title or not url or "/mod/" not in url.casefold():
                continue
            key = (title.casefold(), url)
            if key in seen:
                continue
            seen.add(key)
            assessment = is_assessment(title)
            quiz = assessment or "quiz" in title.casefold() or "/mod/quiz/" in url.casefold()
            found.append(Activity(title, url, completion_state(link), quiz, assessment))
        except StaleElementReferenceException:
            pass
    return found


def enter_question_frame(driver: webdriver.Edge) -> None:
    driver.switch_to.default_content()
    if visible(driver.find_elements(By.CSS_SELECTOR, "input[type='radio']")):
        return
    frames = driver.find_elements(By.TAG_NAME, "iframe")
    for index in range(len(frames)):
        driver.switch_to.default_content()
        current = driver.find_elements(By.TAG_NAME, "iframe")
        if index >= len(current):
            break
        try:
            driver.switch_to.frame(current[index])
            if visible(driver.find_elements(By.CSS_SELECTOR, "input[type='radio']")):
                return
        except WebDriverException:
            pass
    driver.switch_to.default_content()


def select_round_robin(driver: webdriver.Edge, next_index: int):
    """Select 1,2,3,4 repeatedly and return (selected_count, next_index)."""
    enter_question_frame(driver)
    containers = []
    for selector in (".que", ".question", "[data-region='question']", "fieldset"):
        candidates = []
        for item in visible(driver.find_elements(By.CSS_SELECTOR, selector)):
            if item.find_elements(By.CSS_SELECTOR, "input[type='radio']"):
                candidates.append(item)
        if candidates:
            containers = candidates
            break

    groups = []
    if containers:
        for container in containers:
            radios = visible(container.find_elements(By.CSS_SELECTOR, "input[type='radio']"))
            if radios:
                groups.append(radios)
    else:
        by_name = {}
        for radio in visible(driver.find_elements(By.CSS_SELECTOR, "input[type='radio']")):
            name = radio.get_attribute("name") or f"group-{len(by_name)}"
            by_name.setdefault(name, []).append(radio)
        groups = list(by_name.values())

    selected = 0
    for question_number, radios in enumerate(groups, 1):
        desired = next_index
        # Questions with fewer than four choices wrap within available choices.
        actual = desired % min(4, len(radios))
        click(driver, radios[actual])
        log.info("Question %d: selected option %d", question_number, actual + 1)
        selected += 1
        next_index = (next_index + 1) % 4

    driver.switch_to.default_content()
    return selected, next_index


def run_quiz(driver: webdriver.Edge, title: str) -> None:
    if click_button(driver, ["attempt quiz", "re-attempt quiz"], timeout=8):
        wait_ready(driver)
    if click_button(driver, ["continue attempt", "continue the last attempt", "return to attempt"], timeout=3):
        wait_ready(driver)

    total = 0
    next_index = 0
    page_number = 1
    while True:
        wait_ready(driver)
        count, next_index = select_round_robin(driver, next_index)
        if count == 0:
            raise RuntimeError(f"No single-choice questions found on page {page_number}")
        total += count
        driver.switch_to.default_content()

        next_button = find_button(driver, ["next page"], timeout=3)
        if next_button:
            click(driver, next_button)
            page_number += 1
            continue
        break

    click_button(driver, ["finish attempt"], timeout=10, required=True)
    wait_ready(driver)
    click_button(driver, ["submit all and finish"], timeout=15, required=True)
    time.sleep(1)
    # Confirm Moodle-style modal if present.
    for button in visible(driver.find_elements(By.CSS_SELECTOR, ".modal button, [role='dialog'] button")):
        if "submit all and finish" in label(button).casefold():
            click(driver, button)
            break
    wait_ready(driver)
    log.info("Submitted ordinary quiz '%s' with %d round-robin selections", title, total)


def main() -> None:
    if not AUTHORIZED_TEST_ENVIRONMENT:
        raise SystemExit("Enable only for an authorized QA/test environment.")
    url = input("Enter the authorized course URL: ").strip()
    if not url.lower().startswith(("http://", "https://")):
        raise SystemExit("Invalid URL")

    driver = make_driver()
    try:
        driver.get(url)
        wait_ready(driver)
        input("Complete login, open the course, expand the module, then press Enter...")
        time.sleep(POST_LOGIN_WAIT)
        return_url = driver.current_url
        activities = collect_activities(driver)
        if not activities:
            input("No activities detected. Press Enter to close...")
            return

        print("\nDetected activities:")
        for number, item in enumerate(activities, 1):
            kind = "ASSESSMENT" if item.assessment else "QUIZ" if item.quiz else "CONTENT"
            status = "SKIP-COMPLETED" if item.completed else "PENDING"
            print(f"{number:02d}. [{kind}] [{status}] {item.title}")

        pending = [item for item in activities if not item.completed]
        if not pending:
            input("Everything is completed. Press Enter to close...")
            return
        if input("Type START to continue: ").strip() != "START":
            return

        for position, item in enumerate(pending, 1):
            log.info("[%d/%d] Opening %s", position, len(pending), item.title)
            try:
                driver.switch_to.default_content()
                driver.get(item.url)
                wait_ready(driver)
                time.sleep(1)

                if item.assessment:
                    print("\n" + "=" * 72)
                    print(f"FINAL ASSESSMENT OPENED: {item.title}")
                    print("Complete and submit the assessment manually in Edge.")
                    print("The script will resume only after you return here.")
                    print("=" * 72)
                    input("After manual submission, press Enter to continue...")
                elif item.quiz:
                    run_quiz(driver, item.title)
                else:
                    time.sleep(CONTENT_WAIT)
            except Exception:
                log.exception("Failed activity: %s", item.title)

            driver.switch_to.default_content()
            driver.get(return_url)
            wait_ready(driver)
            if position < len(pending):
                time.sleep(BETWEEN_ITEMS_WAIT)

        input("Finished. Press Enter to close Edge...")
    finally:
        driver.quit()


if __name__ == "__main__":
    main()
