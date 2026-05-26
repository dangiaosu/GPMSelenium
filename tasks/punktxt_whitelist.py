from __future__ import annotations

from pathlib import Path
from typing import Any

from selenium.common.exceptions import ElementClickInterceptedException, TimeoutException, WebDriverException
from selenium.webdriver.common.by import By
from selenium.webdriver.remote.webelement import WebElement
from selenium.webdriver.support import expected_conditions as expected
from selenium.webdriver.support.ui import WebDriverWait

from gpm_selenium.contracts import TaskContext, TaskResult, fail, ok

TASK_NAME = "punktxt_whitelist"
TASK_VERSION = "1.0.0"
TASK_DESCRIPTION = "Reserve a punk.txt whitelist spot using an ETH address from Excel."
REQUIRED_COLUMNS = ["ProfileID", "ProfileName", "ETH Address"]
STATUS_SUCCESS = "SUCCESS"

TARGET_URL = "https://www.punktxt.xyz/"
ADDRESS_COLUMN = "ETH Address"
LOCAL_STORAGE_KEY = "punk_txt_reservation"
ADDRESS_INPUT_SELECTOR = "input[placeholder], input[type='text']"
TURNSTILE_TOKEN_SELECTOR = 'input[name="cf-turnstile-response"]'
RESERVE_BUTTON_XPATH = "//button[contains(translate(normalize-space(.), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'reserve spot')]"
RESERVE_BUTTON_SELECTOR = "button"
SUCCESS_TEXTS: tuple[str, ...] = ("SPOT RESERVED", "RESERVED", "ALREADY ON THE LIST")
RESERVE_READY_TIMEOUT_SECONDS = 30.0


def run(context: TaskContext, row: dict[str, object]) -> TaskResult:
    eth_address: str = required_value(row, ADDRESS_COLUMN)
    current_block: str = "OPEN_BLOCK"
    try:
        current_block = "OPEN_BLOCK"
        open_target_in_current_tab(context)
        current_block = "CHECK_EXISTING_RESERVATION_BLOCK"
        existing_result: TaskResult | None = existing_reservation_result(context, eth_address)
        if existing_result is not None:
            return existing_result
        current_block = "FILL_ADDRESS_BLOCK"
        fill_eth_address(context, eth_address)
        current_block = "SUBMIT_RESERVE_BLOCK"
        click_reserve_when_ready(context)
        current_block = "VERIFY_RESULT_BLOCK"
        reservation_data: dict[str, object] = wait_reservation_result(context, eth_address)
        return ok(STATUS_SUCCESS, reservation_data)
    except Exception as error:
        status: str = f"FAIL_AT_{current_block}: {type(error).__name__}: {error}"
        return fail(status, status, failure_data(context, current_block, {"EthAddress": eth_address}))


def existing_reservation_result(context: TaskContext, eth_address: str) -> TaskResult | None:
    reservation: dict[str, str] | None = read_existing_reservation(context)
    if reservation is None:
        return None
    reserved_address: str = reservation.get("address", "").strip()
    if same_address(reserved_address, eth_address):
        return ok(
            STATUS_SUCCESS,
            {
                "EthAddress": normalize_address(reserved_address),
                "ReservationState": "AlreadyReservedInProfile",
                "CreatedAt": reservation.get("createdAt", ""),
            },
        )
    raise RuntimeError(
        "Profile already contains a different punk.txt reservation; "
        f"reserved_address={reserved_address}; expected_address={eth_address}"
    )


def open_target_in_current_tab(context: TaskContext) -> None:
    open_blank_tab(context)
    context.driver.get(TARGET_URL)
    context.wait_ready()


def open_blank_tab(context: TaskContext) -> None:
    existing_handles: set[str] = set(context.driver.window_handles)
    context.driver.execute_script("window.open('about:blank', '_blank');")
    context.page_wait(timeout=10.0).until(lambda driver: len(driver.window_handles) > len(existing_handles))
    new_handles: list[str] = [handle for handle in context.driver.window_handles if handle not in existing_handles]
    if len(new_handles) == 0:
        raise RuntimeError("Could not open a new active tab for punktxt.")
    context.driver.switch_to.window(new_handles[-1])


def fill_eth_address(context: TaskContext, eth_address: str) -> None:
    wait: WebDriverWait = context.node_wait()
    try:
        element: WebElement = wait.until(expected.visibility_of_element_located((By.CSS_SELECTOR, ADDRESS_INPUT_SELECTOR)))
    except TimeoutException as error:
        raise RuntimeError(f"Could not find ETH address input; selector={ADDRESS_INPUT_SELECTOR}; url={context.driver.current_url}") from error
    element.click()
    element.clear()
    element.send_keys(eth_address)
    dispatch_react_input_events(context, eth_address)
    context.node_wait().until(lambda _driver: address_is_valid(context))


def dispatch_react_input_events(context: TaskContext, eth_address: str) -> None:
    context.driver.execute_script(
        """
        const input = document.querySelector(arguments[1]);
        const value = arguments[0];
        if (!input) {
          return;
        }
        if (input.value !== value) {
          input.value = value;
        }
        input.dispatchEvent(new Event('input', { bubbles: true }));
        input.dispatchEvent(new Event('change', { bubbles: true }));
        """,
        eth_address,
        ADDRESS_INPUT_SELECTOR,
    )


def click_reserve_when_ready(context: TaskContext) -> None:
    ready_button: WebElement | bool = reserve_button_ready(context)
    if isinstance(ready_button, WebElement):
        click_button(context, ready_button)
        return
    button: WebElement = context.node_wait(timeout=RESERVE_READY_TIMEOUT_SECONDS).until(lambda _driver: reserve_button_ready(context))
    if isinstance(button, WebElement):
        click_button(context, button)
        return
    raise RuntimeError(
        "Reserve button did not become enabled; "
        f"turnstile_token_length={len(turnstile_token(context))}; page_text={context.page_text()[:500]}"
    )


def reserve_button(context: TaskContext) -> WebElement:
    try:
        return context.node_wait().until(expected.presence_of_element_located((By.XPATH, RESERVE_BUTTON_XPATH)))
    except TimeoutException as error:
        raise RuntimeError(f"Could not find reserve button; xpath={RESERVE_BUTTON_XPATH}; url={context.driver.current_url}") from error


def reserve_button_ready(context: TaskContext) -> WebElement | bool:
    button: WebElement | None = current_reserve_button(context)
    if button is None:
        return False
    if button.is_enabled() and not button_disabled(button):
        return button
    return False


def current_reserve_button(context: TaskContext) -> WebElement | None:
    buttons: list[WebElement] = context.driver.find_elements(By.CSS_SELECTOR, RESERVE_BUTTON_SELECTOR)
    for button in buttons:
        text: str = button.text.strip().lower()
        if "reserve spot" in text:
            return button
    return None


def click_button(context: TaskContext, button: WebElement) -> None:
    context.driver.execute_script("arguments[0].scrollIntoView({block: 'center', inline: 'nearest'});", button)
    try:
        button.click()
    except ElementClickInterceptedException:
        context.driver.execute_script("arguments[0].click();", button)


def wait_reservation_result(context: TaskContext, eth_address: str) -> dict[str, object]:
    try:
        context.page_wait(timeout=30.0).until(lambda _driver: reservation_result_visible(context))
    except TimeoutException as error:
        raise RuntimeError(f"Reservation result did not appear; page_text={context.page_text()[:500]}") from error
    reservation: dict[str, str] | None = read_existing_reservation(context)
    data: dict[str, object] = {
        "EthAddress": normalize_address(eth_address),
        "ReservationState": reservation_state(context),
        "Url": context.driver.current_url,
    }
    if reservation is not None:
        data["CreatedAt"] = reservation.get("createdAt", "")
        data["ReservedAddress"] = normalize_address(reservation.get("address", ""))
    return data


def reservation_result_visible(context: TaskContext) -> bool:
    page_text: str = context.page_text().upper()
    if any(success_text in page_text for success_text in SUCCESS_TEXTS):
        return True
    reservation: dict[str, str] | None = read_existing_reservation(context)
    return reservation is not None


def reservation_state(context: TaskContext) -> str:
    page_text: str = context.page_text().upper()
    if "ALREADY ON THE LIST" in page_text:
        return "AlreadyOnList"
    if "SPOT RESERVED" in page_text or "RESERVED" in page_text:
        return "Reserved"
    return "ReservedByLocalStorage"


def address_is_valid(context: TaskContext) -> bool:
    page_text: str = context.page_text().upper()
    return "VALID" in page_text or "ADDRESS READY" in page_text


def turnstile_token(context: TaskContext) -> str:
    raw_value: Any = context.driver.execute_script(
        "const input = document.querySelector(arguments[0]); return input ? input.value : '';",
        TURNSTILE_TOKEN_SELECTOR,
    )
    return raw_value.strip() if isinstance(raw_value, str) else ""


def read_existing_reservation(context: TaskContext) -> dict[str, str] | None:
    raw_value: Any = context.driver.execute_script("return localStorage.getItem(arguments[0]) || '';", LOCAL_STORAGE_KEY)
    if not isinstance(raw_value, str) or raw_value.strip() == "":
        return None
    parsed_value: Any = context.driver.execute_script(
        """
        try {
          const parsed = JSON.parse(arguments[0]);
          return {
            address: typeof parsed.address === 'string' ? parsed.address : '',
            createdAt: typeof parsed.createdAt === 'string' ? parsed.createdAt : ''
          };
        } catch (_error) {
          return null;
        }
        """,
        raw_value,
    )
    if not isinstance(parsed_value, dict):
        return None
    return {
        "address": str(parsed_value.get("address", "")).strip(),
        "createdAt": str(parsed_value.get("createdAt", "")).strip(),
    }


def button_disabled(button: WebElement) -> bool:
    disabled_attribute: str | None = button.get_attribute("disabled")
    aria_disabled: str | None = button.get_attribute("aria-disabled")
    return disabled_attribute is not None or aria_disabled == "true"


def same_address(left_address: str, right_address: str) -> bool:
    return normalize_address(left_address) == normalize_address(right_address)


def normalize_address(eth_address: str) -> str:
    return eth_address.strip().lower()


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
