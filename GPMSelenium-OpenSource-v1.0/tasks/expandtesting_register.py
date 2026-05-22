from __future__ import annotations

from pathlib import Path
from typing import Any

from selenium.common.exceptions import ElementClickInterceptedException, TimeoutException, WebDriverException
from selenium.webdriver.common.by import By
from selenium.webdriver.remote.webelement import WebElement
from selenium.webdriver.support import expected_conditions as expected
from selenium.webdriver.support.ui import WebDriverWait

from gpm_selenium.contracts import TaskContext, TaskResult, fail, ok

TASK_NAME = "expandtesting_register"
TASK_VERSION = "1.0.0"
TASK_DESCRIPTION = "Register a mock user on practice.expandtesting.com/register."
REQUIRED_COLUMNS = ["ProfileID", "ProfileName", "Username", "Password"]
STATUS_SUCCESS = "SUCCESS"

REGISTER_URL = "https://practice.expandtesting.com/register"
SUCCESS_URL_PART = "/login"
SUCCESS_TEXT = "Successfully registered, you can log in now."
ERROR_TEXTS: tuple[str, ...] = (
    "All fields are required.",
    "Passwords do not match.",
    "Username already exists.",
)


def run(context: TaskContext, row: dict[str, object]) -> TaskResult:
    username: str = required_value(row, "Username")
    password: str = required_value(row, "Password")
    current_block: str = "OPEN_BLOCK"
    try:
        current_block = "OPEN_BLOCK"
        context.open_new_tab(REGISTER_URL)
        current_block = "FILL_FORM_BLOCK"
        fill_input(context, "username", username)
        fill_input(context, "password", password)
        fill_input(context, "confirmPassword", password)
        current_block = "SUBMIT_BLOCK"
        click_register(context)
        current_block = "VERIFY_BLOCK"
        wait_registration_result(context)
        return ok(STATUS_SUCCESS, {"username": username, "url": context.driver.current_url})
    except Exception as error:
        status: str = f"FAIL_AT_{current_block}: {type(error).__name__}: {error}"
        return fail(status, status, failure_data(context, current_block, {"username": username}))


def fill_input(context: TaskContext, element_id: str, value: str) -> None:
    wait: WebDriverWait = context.node_wait()
    try:
        element: WebElement = wait.until(expected.visibility_of_element_located((By.ID, element_id)))
    except TimeoutException as error:
        raise RuntimeError(f"Could not find input; element_id={element_id}; url={context.driver.current_url}") from error
    element.clear()
    element.send_keys(value)


def click_register(context: TaskContext) -> None:
    wait: WebDriverWait = context.node_wait()
    locator: tuple[str, str] = (By.CSS_SELECTOR, "form#register button[type='submit']")
    try:
        button: WebElement = wait.until(expected.element_to_be_clickable(locator))
    except TimeoutException as error:
        raise RuntimeError(f"Could not find register button; locator={locator}; url={context.driver.current_url}") from error
    context.driver.execute_script("arguments[0].scrollIntoView({block: 'center', inline: 'nearest'});", button)
    try:
        button.click()
    except ElementClickInterceptedException:
        context.driver.execute_script("arguments[0].click();", button)
    request_submit_if_click_did_not_submit(context)


def request_submit_if_click_did_not_submit(context: TaskContext) -> None:
    wait: WebDriverWait = WebDriverWait(context.driver, 3)
    try:
        wait.until(lambda _driver: registration_succeeded(context) or registration_failed(context) or "/register" not in context.driver.current_url)
    except TimeoutException:
        context.driver.execute_script(
            "const form = document.querySelector('form#register');"
            "if (!form) { throw new Error('register form not found'); }"
            "form.requestSubmit();"
        )


def wait_registration_result(context: TaskContext) -> None:
    wait: WebDriverWait = context.page_wait()
    try:
        wait.until(lambda _driver: registration_succeeded(context) or registration_failed(context))
    except TimeoutException as error:
        raise RuntimeError(
            f"Register result did not appear; expected_success_text={SUCCESS_TEXT}; page_text={context.page_text()[:500]}"
        ) from error
    if registration_succeeded(context):
        return
    raise RuntimeError(f"Register failed; page_text={context.page_text()[:500]}")


def registration_succeeded(context: TaskContext) -> bool:
    return SUCCESS_URL_PART in context.driver.current_url and SUCCESS_TEXT in context.page_text()


def registration_failed(context: TaskContext) -> bool:
    page_text: str = context.page_text()
    return any(error_text in page_text for error_text in ERROR_TEXTS)


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
