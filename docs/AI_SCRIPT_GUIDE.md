# GPMSelenium AI Script Guide

This guide is written for AI IDE agents that generate GPMSelenium task modules.

## Role

Act as a junior automation developer reporting to the senior dev lead. Follow `contracts.py` exactly. Do not invent external systems, do not bypass the runtime, and do not mix platform responsibilities into task scripts.

## Responsibility Boundary

GPMSelenium owns platform behavior:

- Start and close GPMLogin profiles.
- Attach Selenium to the started browser.
- Run bounded worker queues.
- Retry failed rows.
- Read/write Excel status and extracted task data.
- Save run history and logs.

Task scripts own page behavior only:

- Open the target page in a new tab.
- Read row values already supplied by the runtime.
- Interact with DOM or verified in-profile network calls.
- Extract result data into dictionaries.
- Return `TaskResult` through `ok(...)` or `fail(...)`.

Task scripts must never import `pandas`, `openpyxl`, or `csv`. Task scripts must never read or write Excel files. Task scripts must not start or close GPM profiles.

## Required Contract

Every task module must export:

```python
TASK_NAME = "target_task_name"
TASK_VERSION = "1.0.0"
TASK_DESCRIPTION = "Short description of the workflow."
REQUIRED_COLUMNS = ["ProfileID", "ProfileName", "Email"]
STATUS_SUCCESS = "SUCCESS"
```

Every task module must export:

```python
def run(context: TaskContext, row: dict[str, object]) -> TaskResult:
    ...
```

Return `ok("SUCCESS", extracted_data_dict)` only after the page confirms success. Return `fail("FAIL_AT_<BLOCK>", error, partial_data_dict)` when a block fails. The runtime treats both legacy `OKIE` and new `SUCCESS` as completed statuses during reruns.

## Block Flow

Structure scripts like a block-based workflow. Maintain a `current_block` variable:

```python
current_block = "OPEN_BLOCK"
current_block = "LOGIN_FORM_BLOCK"
current_block = "SUBMIT_BLOCK"
current_block = "VERIFY_BLOCK"
```

Each block should have:

- Entry condition.
- Exit condition.
- Stable selectors or verified network request.
- Step-level retry plan.
- Fatal status such as `FAIL_AT_LOGIN_FORM_BLOCK`.

Before writing a new flow, outline the block flow and network strategy. Generate code only after the senior lead approves the approach.

## Network-First Strategy

During scouting, inspect XHR/fetch traffic before choosing UI automation. Prefer direct API calls only when the request is stable and fully understood:

- Method and URL.
- Required cookies, CSRF token, bearer token, JWT, headers, and body.
- Success and error response shapes.
- Whether the request is signed, encrypted, captcha-gated, or bound to dynamic browser state.

Do not guess payloads. If a request cannot be reproduced reliably with mock data, use Selenium UI automation.

## Timeout And Retry Rules

Use:

- `context.node_wait()` for selectors, inputs, buttons, dropdowns, modals, and small UI steps.
- `context.page_wait()` for full page load, redirect, or final submit result.

Do not use `time.sleep()` except for explicit humanization or unavoidable animation settling.

Step-level retry pattern:

```text
try original node action
if node not found/clickable:
  check interruptive modals
  check bot protection/captcha/OTP
  retry original node action
if still failing:
  return FAIL_AT_<BLOCK>
```

Selector failures should fail at node timeout, not page timeout.

## Core-Gated Debug Artifacts

Debug artifact enforcement lives in `TaskContext`, not in task scripts. `context.screenshot(...)` and `context.save_html(...)` read `context.config["enable_debug_artifacts"]` internally.

Task scripts may attempt to capture artifacts in failure handling. If the GUI checkbox is disabled, the core returns `None` immediately and does not create directories or files.

```python
screenshot_path = context.screenshot(f"error_{current_block}_{context.profile.profile_id}")
html_path = context.save_html(f"error_{current_block}_{context.profile.profile_id}")
```

## BrowserOS Scouting

BrowserOS is only for research with mock data. Never paste real Excel names, emails, phones, credentials, profile IDs, or tokens into BrowserOS.

When asked to scout, work interactively:

1. Inspect DOM and XHR/fetch network activity.
2. Report stable selectors, API endpoints, tokens, and blockers.
3. Pause and ask the senior lead to choose UI clicks vs API requests when both are possible.
4. Write code for one block only after approval.

Scout report format:

```text
Target URL:
Mock data:
Block flow:
Network strategy:
Stable selectors:
Success condition:
Failure conditions:
Blockers:
Recommended next step:
```

## Selector Strategy

Avoid absolute XPath and generated hash selectors.

Prefer:

- `data-testid`, `data-cy`, `aria-label`, `name`, and stable IDs.
- Scoped CSS selectors under a stable parent.
- Relative XPath anchored to stable text or form structure.

Every selector failure must include selector, block name, and current URL in the error message.

## Recommended Skeleton

```python
from __future__ import annotations

from pathlib import Path
from typing import Any

from selenium.common.exceptions import TimeoutException, WebDriverException
from selenium.webdriver.common.by import By
from selenium.webdriver.remote.webelement import WebElement
from selenium.webdriver.support import expected_conditions as expected

from gpm_selenium.contracts import TaskContext, TaskResult, fail, ok

TASK_NAME = "example_task"
TASK_VERSION = "1.0.0"
TASK_DESCRIPTION = "Automates example.com with mock-safe selectors discovered by BrowserOS."
REQUIRED_COLUMNS = ["ProfileID", "ProfileName", "Email"]
STATUS_SUCCESS = "SUCCESS"

TARGET_URL = "https://example.com/form"
SUCCESS_TEXT = "Success"


def run(context: TaskContext, row: dict[str, object]) -> TaskResult:
    email: str = required_value(row, "Email")
    current_block: str = "OPEN_BLOCK"
    try:
        current_block = "OPEN_BLOCK"
        context.open_new_tab(TARGET_URL)
        current_block = "FILL_FORM_BLOCK"
        fill_email(context, email)
        current_block = "SUBMIT_BLOCK"
        submit(context)
        current_block = "VERIFY_BLOCK"
        wait_success(context)
        return ok(STATUS_SUCCESS, {"email": email, "url": context.driver.current_url})
    except Exception as error:
        status: str = f"FAIL_AT_{current_block}: {type(error).__name__}: {error}"
        return fail(status, status, failure_data(context, current_block, {"email": email}))


def fill_email(context: TaskContext, email: str) -> None:
    locator: tuple[str, str] = (By.CSS_SELECTOR, "input[type='email']")
    try:
        element: WebElement = context.node_wait().until(expected.visibility_of_element_located(locator))
    except TimeoutException as error:
        raise RuntimeError(f"Could not find email input; block=FILL_FORM_BLOCK; locator={locator}; url={context.driver.current_url}") from error
    element.clear()
    element.send_keys(email)


def submit(context: TaskContext) -> None:
    locator: tuple[str, str] = (By.CSS_SELECTOR, "button[type='submit']")
    try:
        button: WebElement = context.node_wait().until(expected.element_to_be_clickable(locator))
    except TimeoutException as error:
        raise RuntimeError(f"Could not find submit button; block=SUBMIT_BLOCK; locator={locator}; url={context.driver.current_url}") from error
    button.click()


def wait_success(context: TaskContext) -> None:
    try:
        context.page_wait().until(lambda _driver: SUCCESS_TEXT in context.page_text())
    except TimeoutException as error:
        raise RuntimeError(f"Success text did not appear; block=VERIFY_BLOCK; expected={SUCCESS_TEXT}; page_text={context.page_text()[:500]}") from error


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
```

## Handoff Checklist

- Contract loads in the Scripts tab.
- Required columns match the input source.
- Success returns `SUCCESS` and extracted data dictionary.
- Failure returns `FAIL_AT_<BLOCK>` and partial data dictionary.
- No task-level Excel imports or writes.
- Debug artifacts are gated by `TaskContext`, not by task-side `if` checks.
- Selector failures use `context.node_wait()`.
- Result waits use `context.page_wait()`.
