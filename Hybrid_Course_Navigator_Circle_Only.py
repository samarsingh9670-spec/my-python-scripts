"""Hybrid LMS course navigator for an authorized QA/test environment.

Enhancements:
- Re-scans the course after every activity so newly unlocked modules are discovered.
- Expands collapsed course-index/module sections before collecting activities.
- Automatically completes Moodle-style feedback forms by selecting a configurable score.
- Keeps module/final assessments manual.
- Ordinary quizzes retain 1,2,3,4 round-robin behavior.
"""
import logging
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from selenium import webdriver
from selenium.common.exceptions import (
    ElementClickInterceptedException,
    StaleElementReferenceException,
    TimeoutException,
    WebDriverException,
)
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import Select
from selenium.webdriver.remote.webelement import WebElement
from selenium.webdriver.support.ui import WebDriverWait

AUTHORIZED_TEST_ENVIRONMENT = True
PAGE_TIMEOUT = 60
POST_LOGIN_WAIT = 3
CONTENT_WAIT = 6
BETWEEN_ITEMS_WAIT = 5
FEEDBACK_SCORE = 5          # Uses option 5 when a 1-10 scale is available.
FEEDBACK_TEXT = "Good Content"
FEEDBACK_COUNTRY = "India"
MAX_DISCOVERY_ROUNDS = 250  # Supports long courses.
MAX_EMPTY_SCANS = 8       # Allow time for the LMS to unlock/render the next item.
EXCLUDED_ACTIVITY_TITLES = {"amigo walkthrough", "virtual labs", "announcements"}

BASE = Path(__file__).resolve().parent
LOG_FILE = BASE / "Hybrid_Course_Navigator_Enhanced.log"
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
    feedback: bool


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
    return clean(
        element.text
        or element.get_attribute("value")
        or element.get_attribute("aria-label")
        or element.get_attribute("title")
    )


def find_button(driver: webdriver.Edge, names, timeout=10) -> Optional[WebElement]:
    wanted = [name.casefold() for name in names]

    def locate(d):
        candidates = d.find_elements(
            By.XPATH,
            "//button | //a | //input[@type='submit'] | //input[@type='button']",
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
    return any(
        marker in value
        for marker in ("module assessment", "final assessment", "module exam", "final exam")
    )


def is_feedback(title: str, url: str) -> bool:
    value = f"{clean(title)} {clean(url)}".casefold()
    return "feedback" in value or "/mod/feedback/" in value


def completion_state(link: WebElement):
    """Return True for green tick, False for empty circle, or None for no marker.

    Only links with an explicit LMS completion marker are actionable. Links such
    as Join Live Class, headings, and informational links without a completion
    marker are ignored.
    """
    try:
        container = link.find_element(
            By.XPATH,
            "./ancestor::*[contains(@class,'activity') or "
            "contains(@class,'courseindex-item') or "
            "contains(@class,'course-index-item')][1]",
        )
    except WebDriverException:
        container = link

    def element_metadata(element: WebElement) -> str:
        return " ".join(
            filter(
                None,
                [
                    clean(element.get_attribute("class")),
                    clean(element.get_attribute("aria-label")),
                    clean(element.get_attribute("title")),
                    clean(element.get_attribute("data-completionstate")),
                    clean(element.get_attribute("data-completion-state")),
                    clean(element.get_attribute("data-icon")),
                ],
            )
        ).casefold()

    metadata = element_metadata(container)

    # Check explicit completion-state attributes before generic icon classes.
    completed_selectors = (
        ".completion_complete",
        ".completion-complete",
        "[data-completionstate='1']",
        "[data-completion-state='complete']",
        "[data-completion-state='completed']",
        "[aria-label*='Completed' i]",
        "[aria-label*='Done' i]",
        "[title*='Completed' i]",
        "[title*='Done' i]",
    )
    pending_selectors = (
        ".completion_incomplete",
        ".completion-incomplete",
        "[data-completionstate='0']",
        "[data-completion-state='incomplete']",
        "[data-completion-state='pending']",
        "[aria-label*='Not completed' i]",
        "[aria-label*='To do' i]",
        "[title*='Not completed' i]",
        "[title*='To do' i]",
    )

    for selector in completed_selectors:
        try:
            if container.find_elements(By.CSS_SELECTOR, selector):
                return True
        except WebDriverException:
            pass

    if any(
        marker in metadata
        for marker in (
            "completion_complete",
            "completion-complete",
            "completionstate 1",
            "completed",
            "done",
        )
    ):
        return True

    for selector in pending_selectors:
        try:
            if container.find_elements(By.CSS_SELECTOR, selector):
                return False
        except WebDriverException:
            pass

    if any(
        marker in metadata
        for marker in (
            "completion_incomplete",
            "completion-incomplete",
            "completionstate 0",
            "incomplete",
            "pending",
            "not completed",
            "to do",
        )
    ):
        return False

    # Detect visual completion icons used by alternate Moodle themes.
    try:
        icons = container.find_elements(
            By.CSS_SELECTOR,
            "i, svg, use, span[class*='icon'], [role='img'], [class*='completion']",
        )
        for icon in icons:
            icon_state = element_metadata(icon)

            if any(
                marker in icon_state
                for marker in (
                    "fa-check",
                    "check-circle",
                    "icon-check",
                    "circle-check",
                    "completion_complete",
                    "completion-complete",
                )
            ):
                return True

            if any(
                marker in icon_state
                for marker in (
                    "fa-circle-o",
                    "far fa-circle",
                    "circle-regular",
                    "icon-circle",
                    "completion_incomplete",
                    "completion-incomplete",
                )
            ):
                return False
    except WebDriverException:
        pass

    # No green tick and no empty completion circle means no completion task.
    return None


def expand_all_modules(driver: webdriver.Edge) -> None:
    """Expand collapsed course-index/module controls so later modules become discoverable."""
    driver.switch_to.default_content()
    for _ in range(4):
        collapsed = visible(
            driver.find_elements(
                By.CSS_SELECTOR,
                ".courseindex [aria-expanded='false'], "
                ".course-index [aria-expanded='false'], "
                "[data-region='course-index'] [aria-expanded='false'], "
                ".courseindex-section-title[aria-expanded='false']",
            )
        )
        if not collapsed:
            break
        clicked = 0
        for control in collapsed:
            try:
                click(driver, control)
                clicked += 1
                time.sleep(0.2)
            except (StaleElementReferenceException, WebDriverException):
                pass
        if clicked == 0:
            break


def collect_activities(driver: webdriver.Edge):
    """Collect actual course activities in course-menu order.

    The earlier broad selector searched every /mod/ link on the page, which also
    picked global/support links such as Amigo Walkthrough and Virtual Labs.
    """
    driver.switch_to.default_content()
    expand_all_modules(driver)

    roots = visible(
        driver.find_elements(
            By.CSS_SELECTOR,
            "[data-region='course-index'], .courseindex, .course-index, #courseindex",
        )
    )
    search_root = roots[0] if roots else driver

    selectors = (
        ".courseindex-item a[href*='/mod/'], "
        "li.activity a[href*='/mod/'], "
        ".activityinstance a[href*='/mod/']"
    )
    links = search_root.find_elements(By.CSS_SELECTOR, selectors)

    found, seen = [], set()
    for link in links:
        try:
            # Do not require is_displayed(): collapsed/unlocked module links still
            # need to be retained in the activity queue.
            title = label(link)
            url = clean(link.get_attribute("href"))
            normalized_title = title.casefold().strip(" :")
            if not title or not url or "/mod/" not in url.casefold():
                continue
            if normalized_title in EXCLUDED_ACTIVITY_TITLES:
                log.debug("Ignoring excluded non-course link: %s", title)
                continue
            key = url.split("#", 1)[0]
            if key in seen:
                continue
            seen.add(key)
            assessment = is_assessment(title)
            feedback = is_feedback(title, url)
            quiz = not feedback and (
                assessment or "quiz" in title.casefold() or "/mod/quiz/" in url.casefold()
            )
            state = completion_state(link)
            if state is None:
                log.debug("Ignoring link without completion marker: %s", title)
                continue
            found.append(Activity(title, url, state, quiz, assessment, feedback))
        except (StaleElementReferenceException, WebDriverException):
            pass
    return found


def enter_radio_frame(driver: webdriver.Edge) -> None:
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


def radio_groups(driver: webdriver.Edge):
    by_name = {}
    for radio in visible(driver.find_elements(By.CSS_SELECTOR, "input[type='radio']")):
        name = radio.get_attribute("name") or f"unnamed-{len(by_name)}"
        by_name.setdefault(name, []).append(radio)
    return list(by_name.values())


def select_round_robin(driver: webdriver.Edge, next_index: int):
    enter_radio_frame(driver)
    groups = radio_groups(driver)
    selected = 0
    for question_number, radios in enumerate(groups, 1):
        actual = next_index % min(4, len(radios))
        click(driver, radios[actual])
        log.info("Question %d: selected option %d", question_number, actual + 1)
        selected += 1
        next_index = (next_index + 1) % 4
    driver.switch_to.default_content()
    return selected, next_index


def run_quiz(driver: webdriver.Edge, title: str) -> None:
    if click_button(driver, ["attempt quiz", "re-attempt quiz"], timeout=8):
        wait_ready(driver)
    if click_button(
        driver,
        ["continue attempt", "continue the last attempt", "return to attempt"],
        timeout=3,
    ):
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
    for button in visible(
        driver.find_elements(By.CSS_SELECTOR, ".modal button, [role='dialog'] button")
    ):
        if "submit all and finish" in label(button).casefold():
            click(driver, button)
            break
    wait_ready(driver)
    log.info("Submitted ordinary quiz '%s' with %d selections", title, total)


def choose_feedback_option(radios, score: int) -> int:
    """Prefer the requested numeric value; otherwise safely use an available option."""
    for index, radio in enumerate(radios):
        candidate = clean(
            radio.get_attribute("value")
            or radio.get_attribute("aria-label")
            or radio.get_attribute("data-value")
        )
        if candidate == str(score):
            return index
    return min(max(score - 1, 0), len(radios) - 1)


def _fill_feedback_text_fields(driver: webdriver.Edge) -> int:
    """Fill all visible editable feedback text fields with the configured default."""
    count = 0
    selectors = (
        "textarea, "
        "input[type='text'], input[type='search'], input[type='email'], "
        "input:not([type])"
    )
    for field in visible(driver.find_elements(By.CSS_SELECTOR, selectors)):
        try:
            # Avoid overwriting fields that the LMS or user has already populated.
            if clean(field.get_attribute("value")):
                continue
            field.clear()
            field.send_keys(FEEDBACK_TEXT)
            count += 1
        except WebDriverException:
            pass
    return count


def _select_country(driver: webdriver.Edge) -> bool:
    """Select India from a native <select> or a custom accessible combobox."""
    # Native HTML select elements.
    for element in visible(driver.find_elements(By.TAG_NAME, "select")):
        try:
            options = [clean(o.text).casefold() for o in Select(element).options]
            if FEEDBACK_COUNTRY.casefold() in options:
                Select(element).select_by_visible_text(FEEDBACK_COUNTRY)
                return True
        except WebDriverException:
            pass

    # Custom dropdowns: prioritize a control associated with a Country label.
    xpaths = (
        "//*[contains(translate(normalize-space(.), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', "
        "'abcdefghijklmnopqrstuvwxyz'), 'country')]/following::*[@role='combobox'][1]",
        "//*[@role='combobox']",
        "//input[contains(translate(@aria-label, 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', "
        "'abcdefghijklmnopqrstuvwxyz'), 'country')]",
    )
    for xpath in xpaths:
        for combo in visible(driver.find_elements(By.XPATH, xpath)):
            try:
                click(driver, combo)
                time.sleep(0.5)

                # Search visible listbox options first.
                option_xpath = (
                    "//*[@role='option' and "
                    "translate(normalize-space(.), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', "
                    "'abcdefghijklmnopqrstuvwxyz')='india']"
                )
                india_options = visible(driver.find_elements(By.XPATH, option_xpath))
                if india_options:
                    click(driver, india_options[0])
                    return True

                # Searchable combobox fallback.
                combo.send_keys(FEEDBACK_COUNTRY)
                time.sleep(0.5)
                india_options = visible(driver.find_elements(By.XPATH, option_xpath))
                if india_options:
                    click(driver, india_options[0])
                else:
                    combo.send_keys(Keys.ENTER)
                return True
            except WebDriverException:
                try:
                    combo.send_keys(Keys.ESCAPE)
                except WebDriverException:
                    pass
    return False


def _find_feedback_submit(driver: webdriver.Edge) -> Optional[WebElement]:
    return find_button(
        driver,
        ["submit your answers", "submit answers", "submit feedback", "save changes", "submit"],
        timeout=5,
    )


def run_feedback(driver: webdriver.Edge, title: str) -> None:
    # Some feedback activities first show an "Answer the questions" landing page.
    if click_button(
        driver,
        ["answer the questions", "answer questions", "complete questionnaire", "start feedback"],
        timeout=8,
    ):
        wait_ready(driver)
        time.sleep(1)

    enter_radio_frame(driver)

    # Fill every visible rating group, regardless of whether there are 2, 5, or more.
    groups = radio_groups(driver)
    selected = 0
    for question_number, radios in enumerate(groups, 1):
        index = choose_feedback_option(radios, FEEDBACK_SCORE)
        click(driver, radios[index])
        log.info("Feedback rating %d: selected option %d", question_number, index + 1)
        selected += 1

    text_count = _fill_feedback_text_fields(driver)
    country_selected = _select_country(driver)
    log.info(
        "Feedback fields completed: ratings=%d, text=%d, country=%s",
        selected,
        text_count,
        FEEDBACK_COUNTRY if country_selected else "not present/not found",
    )

    # The submit button may be in the same iframe as the form or in the main document.
    submit_button = _find_feedback_submit(driver)
    if submit_button is None:
        driver.switch_to.default_content()
        submit_button = _find_feedback_submit(driver)
    if submit_button is None:
        raise TimeoutException("Feedback submit button was not found")

    click(driver, submit_button)
    time.sleep(1)
    driver.switch_to.default_content()

    # Handle an optional confirmation dialog.
    for button in visible(
        driver.find_elements(By.CSS_SELECTOR, ".modal button, [role='dialog'] button")
    ):
        button_text = label(button).casefold()
        if any(word in button_text for word in ("confirm", "continue", "submit")):
            click(driver, button)
            break

    wait_ready(driver)
    log.info(
        "Submitted feedback '%s' with %d ratings, %d text fields, country=%s",
        title,
        selected,
        text_count,
        FEEDBACK_COUNTRY if country_selected else "N/A",
    )


def mark_activity_done(driver: webdriver.Edge, title: str) -> bool:
    """Click a manual completion button when available, without reversing completion."""
    driver.switch_to.default_content()
    wait_ready(driver)
    time.sleep(2)

    try:
        body_text = clean(driver.find_element(By.TAG_NAME, "body").text).casefold()
    except WebDriverException:
        body_text = ""

    # Do not click anything if the LMS indicates that the activity is already complete.
    already_done_markers = (
        "mark as not done",
        "activity completed",
        "completed: view",
        "done: view",
    )
    if any(marker in body_text for marker in already_done_markers):
        log.info("Activity already marked done: %s", title)
        return True

    button = find_button(
        driver,
        ["mark as done", "mark complete", "complete activity"],
        timeout=8,
    )
    if button is None:
        log.info("No manual completion button found for '%s'", title)
        return False

    click(driver, button)
    time.sleep(1)

    # Handle an optional confirmation dialog.
    for dialog_button in visible(
        driver.find_elements(By.CSS_SELECTOR, ".modal button, [role='dialog'] button")
    ):
        text = label(dialog_button).casefold()
        if any(word in text for word in ("confirm", "continue", "mark as done")):
            click(driver, dialog_button)
            break

    time.sleep(2)
    log.info("Marked activity as done: %s", title)
    return True


def is_terminal_course_feedback(item: Activity) -> bool:
    """Course/faculty feedback belongs at the very end, after all modules."""
    title = clean(item.title).casefold()
    return item.feedback and (
        "student feedback for course" in title
        or "student feedback for faculty" in title
        or "course feedback for student" in title
        or "faculty feedback" in title
    )


def merge_new_items_before_terminal_feedback(queue, new_items):
    """Insert newly unlocked module work before final course/faculty feedback."""
    normal = [item for item in queue if not is_terminal_course_feedback(item)]
    terminal = [item for item in queue if is_terminal_course_feedback(item)]
    new_normal = [item for item in new_items if not is_terminal_course_feedback(item)]
    new_terminal = [item for item in new_items if is_terminal_course_feedback(item)]
    return normal + new_normal + terminal + new_terminal

def print_activities(activities) -> None:
    print("\nDetected activities:")
    for number, item in enumerate(activities, 1):
        if item.feedback:
            kind = "FEEDBACK"
        elif item.assessment:
            kind = "ASSESSMENT"
        elif item.quiz:
            kind = "QUIZ"
        else:
            kind = "CONTENT"
        status = "SKIP-COMPLETED" if item.completed else "PENDING"
        print(f"{number:02d}. [{kind}] [{status}] {item.title}")


def main() -> None:
    if not AUTHORIZED_TEST_ENVIRONMENT:
        raise SystemExit("Enable only for an authorized QA/test environment.")

    url = input("Enter the authorized course URL: ").strip()
    if not url.lower().startswith(("http://", "https://")):
        raise SystemExit("Invalid URL")

    driver = make_driver()
    processed = set()
    failed = set()
    try:
        driver.get(url)
        wait_ready(driver)
        input("Complete login, open the course, then press Enter...")
        time.sleep(POST_LOGIN_WAIT)
        course_url = driver.current_url

        initial = collect_activities(driver)
        if not initial:
            input("No activities detected. Press Enter to close...")
            return
        print_activities(initial)
        if input("Type START to continue: ").strip() != "START":
            return

        # Keep the initial pending list as a persistent queue. A temporary LMS/sidebar
        # rendering failure must never erase activities that were already discovered.
        initial_pending = [item for item in initial if not item.completed]
        queue = merge_new_items_before_terminal_feedback([], initial_pending)
        known_urls = {item.url for item in initial}
        empty_scans = 0

        for discovery_round in range(1, MAX_DISCOVERY_ROUNDS + 1):
            # Remove anything already handled, but retain every other previously
            # discovered item even if a later page scan returns only part of the menu.
            queue = [
                item for item in queue
                if item.url not in processed and item.url not in failed
            ]

            if not queue:
                driver.switch_to.default_content()
                driver.get(course_url)
                wait_ready(driver)
                time.sleep(3)

                rescanned = collect_activities(driver)
                new_items = []
                for candidate in rescanned:
                    if candidate.url not in known_urls:
                        known_urls.add(candidate.url)
                        if not candidate.completed:
                            new_items.append(candidate)

                if new_items:
                    queue = merge_new_items_before_terminal_feedback(queue, new_items)
                    empty_scans = 0
                    log.info("Discovered %d newly available activities", len(new_items))
                else:
                    empty_scans += 1
                    log.info(
                        "Queue empty; waiting for newly unlocked activities (%d/%d)",
                        empty_scans,
                        MAX_EMPTY_SCANS,
                    )
                    if empty_scans < MAX_EMPTY_SCANS:
                        time.sleep(4)
                        continue
                    log.info("No newly unlocked activities found after repeated checks")
                    break

            # Never run final course/faculty feedback while a newly unlocked module
            # may be available. Force a fresh course-menu scan first.
            if queue and is_terminal_course_feedback(queue[0]):
                driver.switch_to.default_content()
                driver.get(course_url)
                wait_ready(driver)
                time.sleep(4)
                expand_all_modules(driver)
                terminal_scan_items = []
                for candidate in collect_activities(driver):
                    if candidate.url not in known_urls:
                        known_urls.add(candidate.url)
                        if not candidate.completed:
                            terminal_scan_items.append(candidate)
                if terminal_scan_items:
                    queue = merge_new_items_before_terminal_feedback(queue, terminal_scan_items)
                    log.info(
                        "Deferred final feedback; inserted %d newly unlocked module activities",
                        len(terminal_scan_items),
                    )

            item = queue.pop(0)  # Module activities are prioritized before final feedback.
            log.info(
                "[Queue item %d] Next pending in course order: %s",
                discovery_round,
                item.title,
            )
            try:
                driver.switch_to.default_content()
                driver.get(item.url)
                wait_ready(driver)
                time.sleep(1)

                if item.feedback:
                    run_feedback(driver, item.title)
                elif item.assessment:
                    print("\n" + "=" * 72)
                    print(f"ASSESSMENT OPENED: {item.title}")
                    print("Complete and submit the assessment manually in Edge.")
                    print("The automation is paused. Return to this window only after submission.")
                    print("After Enter, the script will process feedback and the next unlocked module.")
                    print("=" * 72)
                    input("After manual submission, press Enter to continue...")
                elif item.quiz:
                    run_quiz(driver, item.title)
                else:
                    time.sleep(CONTENT_WAIT)
                    mark_activity_done(driver, item.title)

                processed.add(item.url)
            except Exception:
                failed.add(item.url)
                log.exception("Failed activity: %s", item.title)

            # Merge newly unlocked links without replacing or reordering the queue.
            try:
                driver.switch_to.default_content()
                driver.get(course_url)
                wait_ready(driver)
                time.sleep(2)
                discovered_now = []
                for candidate in collect_activities(driver):
                    if candidate.url not in known_urls:
                        known_urls.add(candidate.url)
                        if not candidate.completed:
                            discovered_now.append(candidate)
                            log.info("Added newly unlocked activity: %s", candidate.title)
                if discovered_now:
                    queue = merge_new_items_before_terminal_feedback(queue, discovered_now)
            except Exception:
                log.warning("Course re-scan failed; preserved %d queued activities", len(queue))

            time.sleep(BETWEEN_ITEMS_WAIT)
        else:
            log.warning("Stopped after MAX_DISCOVERY_ROUNDS=%d", MAX_DISCOVERY_ROUNDS)

        print(f"\nFinished. Processed: {len(processed)} | Failed: {len(failed)}")
        print(f"Log file: {LOG_FILE}")
        input("Press Enter to close Edge...")
    finally:
        driver.quit()


if __name__ == "__main__":
    main()
