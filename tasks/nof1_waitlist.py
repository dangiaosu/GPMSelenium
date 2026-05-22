from __future__ import annotations

from pathlib import Path
from typing import Any

from selenium.common.exceptions import TimeoutException, WebDriverException
from selenium.webdriver.common.by import By
from selenium.webdriver.remote.webelement import WebElement
from selenium.webdriver.support import expected_conditions as expected
from selenium.webdriver.support.select import Select
from selenium.webdriver.support.ui import WebDriverWait

from gpm_selenium.contracts import TaskContext, TaskResult, fail, ok

TASK_NAME = "nof1_waitlist"
TASK_VERSION = "1.0.0"
TASK_DESCRIPTION = "Submit NOF1 waitlist form using Name, Email, Phone columns."
REQUIRED_COLUMNS = ["ProfileID", "ProfileName", "Name", "Email", "Phone"]
STATUS_SUCCESS = "SUCCESS"

WAITLIST_URL = "https://nof1.ai/waitlist"
SUCCESS_TEXT = "Successfully joined the waitlist!"
FIELD_XPATHS: dict[str, str] = {
    "Name": "//form[.//button[normalize-space()='JOIN']]//input[@placeholder='NAME']",
    "Email": "//form[.//button[normalize-space()='JOIN']]//input[@placeholder='EMAIL']",
    "Phone": "//form[.//button[normalize-space()='JOIN']]//input[@placeholder='PHONE']",
}
CONTACT_SELECT_XPATH = "//form[.//button[normalize-space()='JOIN']]//select"
SUBMIT_XPATH = "//form[.//button[normalize-space()='JOIN']]//button[@type='submit' and normalize-space()='JOIN']"


def run(context: TaskContext, row: dict[str, object]) -> TaskResult:
    current_block: str = "OPEN_BLOCK"
    try:
        current_block = "OPEN_BLOCK"
        context.open_new_tab(WAITLIST_URL)
        current_block = "FILL_FORM_BLOCK"
        fill_field(context, "Name", required_value(row, "Name"))
        fill_field(context, "Email", required_value(row, "Email"))
        fill_field(context, "Phone", required_value(row, "Phone"))
        current_block = "CONTACT_METHOD_BLOCK"
        select_contact_email(context)
        current_block = "SUBMIT_BLOCK"
        click_submit(context)
        current_block = "VERIFY_BLOCK"
        wait_success(context)
        return ok(STATUS_SUCCESS, {"url": WAITLIST_URL})
    except Exception as error:
        status: str = f"FAIL_AT_{current_block}: {type(error).__name__}: {error}"
        return fail(status, status, failure_data(context, current_block, {}))


def fill_field(context: TaskContext, column_name: str, value: str) -> None:
    xpath: str = FIELD_XPATHS[column_name]
    wait: WebDriverWait = context.node_wait()
    try:
        element: WebElement = wait.until(expected.visibility_of_element_located((By.XPATH, xpath)))
    except TimeoutException as error:
        raise RuntimeError(
            f"Could not find field; column_name={column_name}; xpath={xpath}; url={context.driver.current_url}"
        ) from error
    element.clear()
    element.send_keys(value)


def select_contact_email(context: TaskContext) -> None:
    wait: WebDriverWait = context.node_wait()
    try:
        element: WebElement = wait.until(expected.visibility_of_element_located((By.XPATH, CONTACT_SELECT_XPATH)))
    except TimeoutException as error:
        raise RuntimeError(f"Could not find contact dropdown; xpath={CONTACT_SELECT_XPATH}") from error
    Select(element).select_by_value("email")


def click_submit(context: TaskContext) -> None:
    wait: WebDriverWait = context.node_wait()
    try:
        button: WebElement = wait.until(expected.element_to_be_clickable((By.XPATH, SUBMIT_XPATH)))
    except TimeoutException as error:
        raise RuntimeError(f"Could not find submit button; xpath={SUBMIT_XPATH}") from error
    button.click()


def wait_success(context: TaskContext) -> None:
    wait: WebDriverWait = context.page_wait()
    try:
        wait.until(lambda _driver: SUCCESS_TEXT in context.page_text())
    except TimeoutException as error:
        raise RuntimeError(
            f"Submit did not reach success text; expected={SUCCESS_TEXT}; page_text={context.page_text()[:500]}"
        ) from error


def failure_data(context: TaskContext, block_name: str, extra_data: dict[str, object]) -> dict[str, object]:
    data: dict[str, object] = {
        "current_block": block_name,
        "url": context.driver.current_url,
        "page_text": context.page_text()[:500],
        **extra_data,
    }
    try:
        screenshot_path: Path | None = context.screenshot(f"error_{block_name}_{context.profile.profile_id}")
        if screenshot_path is not None:
            data["screenshot"] = str(screenshot_path)
    except WebDriverException as error:
        data["screenshot_error"] = f"{type(error).__name__}: {error}"
    try:
        html_path: Path | None = context.save_html(f"error_{block_name}_{context.profile.profile_id}")
        if html_path is not None:
            data["html"] = str(html_path)
    except (OSError, WebDriverException) as error:
        data["html_error"] = f"{type(error).__name__}: {error}"
    return data


def required_value(row: dict[str, object], column_name: str) -> str:
    raw_value: Any = row.get(column_name)
    value: str = "" if raw_value is None else str(raw_value).strip()
    if value == "":
        raise ValueError(f"Row missing required value; column_name={column_name}")
    return value
