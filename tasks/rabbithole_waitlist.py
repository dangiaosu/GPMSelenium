"""
Rabbithole Waitlist Task - GPMSelenium compatible script
Joins Rabbithole.gg waitlist with provided email.
"""

import time
from pathlib import Path
from typing import Any

from selenium.common.exceptions import TimeoutException, WebDriverException
from selenium.webdriver.common.by import By
from selenium.webdriver.remote.webelement import WebElement
from selenium.webdriver.support import expected_conditions as expected
from selenium.webdriver.support.ui import WebDriverWait

from gpm_selenium.contracts import TaskContext, TaskResult, ok, fail

TASK_NAME = "rabbithole_waitlist"
TASK_VERSION = "1.0.0"
TASK_DESCRIPTION = "Join Rabbithole.gg waitlist with email from Excel row"
REQUIRED_COLUMNS = ["ProfileID", "ProfileName", "Email"]
STATUS_SUCCESS = "SUCCESS"

WAITLIST_URL = "https://www.rabbithole.gg/"

# CSS selector for email input (supports placeholder or type attribute)
EMAIL_INPUT_CSS = 'input[placeholder*="Email" i], input[placeholder*="email" i], input[type="email"]'


def run(context: TaskContext, row: dict[str, object]) -> TaskResult:
    """
    Task to submit email to Rabbithole.gg waitlist.
    
    Expected columns:
        - ProfileID: str - GPM Profile ID
        - ProfileName: str - GPM Profile Name  
        - Email: str - Email to submit to waitlist
    """
    current_block: str = "VALIDATE_BLOCK"
    
    try:
        # Get required values
        email: str = required_value(row, "Email")
        profile_id: str = str(row.get("ProfileID", ""))
        profile_name: str = str(row.get("ProfileName", ""))
        
        # Validate email format
        current_block = "VALIDATE_BLOCK"
        if "@" not in email or "." not in email:
            raise ValueError(f"Invalid email format: {email}")
        
        # Open page in new tab
        current_block = "OPEN_BLOCK"
        context.open_new_tab(WAITLIST_URL)
        
        # Find and fill email input
        current_block = "FILL_EMAIL_BLOCK"
        fill_email_input(context, email)
        
        # Click submit button
        current_block = "SUBMIT_BLOCK"
        click_join_waitlist(context)
        
        # Wait for submission to complete - dùng explicit wait thay vì sleep
        current_block = "WAIT_BLOCK"
        wait_for_result(context, timeout=10)
        
        # Verify result
        current_block = "VERIFY_BLOCK"
        success, message = verify_submission(context)
        
        if success:
            return ok(STATUS_SUCCESS, {
                "url": context.driver.current_url,
                "email": email,
                "message": message
            })
        else:
            # Thêm debug: log page text để biết tại sao fail
            page_text = context.page_text()[:500]
            context.logger.warning(f"Verification failed. Page text: {page_text}")
            raise RuntimeError(f"Submission failed: {message}")
            
    except Exception as error:
        status: str = f"FAIL_AT_{current_block}: {type(error).__name__}: {error}"
        return fail(status, status, failure_data(context, current_block, {}))


def fill_email_input(context: TaskContext, email: str) -> None:
    """Find and fill the email input on the page."""
    wait: WebDriverWait = context.node_wait(20)
    driver = context.driver
    
    # Try CSS selector first
    try:
        element: WebElement = wait.until(
            expected.visibility_of_element_located((By.CSS_SELECTOR, EMAIL_INPUT_CSS))
        )
    except TimeoutException:
        raise RuntimeError(f"Could not find email input with selector: {EMAIL_INPUT_CSS}")
    
    element.clear()
    element.send_keys(email)


def click_join_waitlist(context: TaskContext) -> None:
    """Click the Join Waitlist button."""
    wait: WebDriverWait = context.node_wait(20)
    driver = context.driver
    
    # Try to find button by text using XPath (case-insensitive)
    try:
        button: WebElement = wait.until(
            expected.element_to_be_clickable((
                By.XPATH, 
                '//button[contains(translate(text(), "ABCDEFGHIJKLMNOPQRSTUVWXYZ", "abcdefghijklmnopqrstuvwxyz"), "join waitlist")]'
            ))
        )
        button.click()
        return
    except TimeoutException:
        pass
    
    # Fallback: find button by partial text match
    buttons = driver.find_elements(By.TAG_NAME, 'button')
    for btn in buttons:
        btn_text: str = btn.text.lower()
        if 'join' in btn_text and 'waitlist' in btn_text:
            if btn.is_displayed():
                btn.click()
                return
    
    # Last resort: press Enter on email input
    try:
        email_input = driver.find_element(By.CSS_SELECTOR, EMAIL_INPUT_CSS)
        email_input.send_keys('\n')
    except WebDriverException as e:
        raise RuntimeError(f"Could not find or click Join Waitlist button: {e}")


def wait_for_result(context: TaskContext, timeout: int = 10) -> None:
    """Wait for page to update after submission using explicit wait."""
    driver = context.driver
    wait: WebDriverWait = WebDriverWait(driver, timeout)
    
    # Wait until either success text appears OR email input is cleared
    def check_result(driver):
        page_text = driver.execute_script("return document.body ? document.body.innerText : ''").lower()
        
        # Check success indicators
        success_keywords = ["you're on the list", "you are on the list", "success", "joined", "thank you"]
        for kw in success_keywords:
            if kw in page_text:
                return True
        
        # Check if email input was cleared
        try:
            inputs = driver.find_elements(By.CSS_SELECTOR, EMAIL_INPUT_CSS)
            for inp in inputs:
                value = inp.get_attribute('value') or ''
                if inp.is_displayed() and value == '':
                    return True
        except:
            pass
        
        return False
    
    try:
        wait.until(check_result)
    except TimeoutException:
        # Không raise lỗi ở đây, để verify_submission xử lý
        pass


def verify_submission(context: TaskContext) -> tuple[bool, str]:
    """
    Verify that submission was successful.
    Returns (success: bool, message: str)
    """
    driver = context.driver
    page_text: str = context.page_text()
    page_text_lower = page_text.lower()
    current_url: str = driver.current_url
    
    # Primary success check: "You're on the list"
    # Dùng cả 2 cách kiểm tra: với dấu ' thường và smart quote
    if "you're on the list" in page_text_lower:
        return True, "Successfully joined waitlist - You're on the list"
    
    if "on the list" in page_text_lower:
        return True, "On waitlist confirmed"
    
    # Kiểm tra các indicators khác
    other_indicators = ["success", "joined", "thank you", "welcome", "congratulations"]
    for indicator in other_indicators:
        if indicator in page_text_lower:
            return True, f"Success detected: {indicator}"
    
    # Check if email input was cleared (another success signal)
    try:
        email_inputs = driver.find_elements(By.CSS_SELECTOR, EMAIL_INPUT_CSS)
        for inp in email_inputs:
            value = inp.get_attribute('value') or ''
            if value == '' and inp.is_displayed():
                return True, "Email input cleared - successful submission"
    except:
        pass
    
    # Check for error messages
    error_indicators = ["invalid email", "enter a valid email", "something went wrong"]
    for indicator in error_indicators:
        if indicator in page_text_lower:
            return False, f"Error detected: {indicator}"
    
    # Check if redirected to app login (success scenario)
    if 'app.rabbithole.gg' in current_url.lower():
        return True, "Redirected to app - successful submission"
    
    # Debug: return actual page text for troubleshooting
    preview = page_text.replace('\n', ' ')[:300]
    return False, f"Could not determine submission status. Page preview: {preview}"


def failure_data(context: TaskContext, block_name: str, extra_data: dict[str, object]) -> dict[str, object]:
    """Collect debug data on failure."""
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
    except WebDriverException as err:
        data["screenshot_error"] = str(err)
    
    try:
        html_path: Path | None = context.save_html(f"error_{block_name}_{context.profile.profile_id}")
        if html_path is not None:
            data["html"] = str(html_path)
    except (OSError, WebDriverException) as err:
        data["html_error"] = str(err)
    
    return data


def required_value(row: dict[str, object], column_name: str) -> str:
    """Get and validate required column value."""
    raw_value: Any = row.get(column_name)
    value: str = "" if raw_value is None else str(raw_value).strip()
    if value == "":
        raise ValueError(f"Row missing required value; column_name={column_name}")
    return value
