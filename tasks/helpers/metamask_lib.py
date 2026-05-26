from __future__ import annotations

import json
import re
from pathlib import Path
from threading import Lock
from typing import Any

from selenium.common.exceptions import JavascriptException, TimeoutException, WebDriverException
from selenium.webdriver.common.by import By
from selenium.webdriver.remote.webelement import WebElement
from selenium.webdriver.support import expected_conditions as expected

from gpm_selenium.contracts import TaskContext

METAMASK_EXTENSION_NAME = "MetaMask"
ONBOARDING_PATH = "home.html#/onboarding/welcome"
HOME_PATH = "home.html"
SEED_WORD_COUNT = 12
EVM_ADDRESS_PATTERN = re.compile(r"^0x[a-fA-F0-9]{40}$")
SOLANA_ADDRESS_PATTERN = re.compile(r"^[1-9A-HJ-NP-Za-km-z]{32,44}$")
PRIVATE_KEY_PATTERN = re.compile(r"^(?:0x)?[a-fA-F0-9]{64}$")
DASHBOARD_SELECTORS = [
    '[data-testid="network-group-with-copy-icon"]',
    '[data-testid="account-menu-icon"]',
    '[data-testid="wallet-overview"]',
    '[data-testid="account-overview"]',
    '[data-testid="eth-overview__primary-currency"]',
]
CLIPBOARD_LOCK = Lock()


class CdpClickableElement:
    def __init__(self, driver: Any, node_id: int) -> None:
        self._driver: Any = driver
        self._node_id: int = node_id

    def click(self) -> None:
        self._driver.execute_cdp_cmd("DOM.scrollIntoViewIfNeeded", {"nodeId": self._node_id})
        box_model: dict[str, Any] = self._driver.execute_cdp_cmd("DOM.getBoxModel", {"nodeId": self._node_id})
        content_box: list[float] = [float(value) for value in box_model["model"]["content"]]
        x_coordinates: list[float] = content_box[0::2]
        y_coordinates: list[float] = content_box[1::2]
        x_position: float = sum(x_coordinates) / len(x_coordinates)
        y_position: float = sum(y_coordinates) / len(y_coordinates)
        self._driver.execute_cdp_cmd(
            "Input.dispatchMouseEvent",
            {"type": "mousePressed", "x": x_position, "y": y_position, "button": "left", "clickCount": 1},
        )
        self._driver.execute_cdp_cmd(
            "Input.dispatchMouseEvent",
            {"type": "mouseReleased", "x": x_position, "y": y_position, "button": "left", "clickCount": 1},
        )


def find_metamask_extension_id(context: TaskContext) -> str:
    context.open_new_tab("chrome://extensions/")
    try:
        return str(context.node_wait().until(lambda driver: extension_id_from_extensions_page(driver, METAMASK_EXTENSION_NAME)))
    except TimeoutException as error:
        raise RuntimeError(f"Could not find MetaMask extension id; extension_name={METAMASK_EXTENSION_NAME}") from error


def extension_id_from_extensions_page(driver: Any, extension_name: str) -> str | bool:
    script: str = """
        const extensionName = arguments[0].toLowerCase();
        const manager = document.querySelector('extensions-manager');
        const managerRoot = manager && manager.shadowRoot;
        const itemList = managerRoot && managerRoot.querySelector('extensions-item-list');
        const itemListRoot = itemList && itemList.shadowRoot;
        const items = itemListRoot ? Array.from(itemListRoot.querySelectorAll('extensions-item')) : [];
        for (const item of items) {
            const root = item.shadowRoot;
            const nameNode = root && (root.querySelector('#name') || root.querySelector('.name'));
            const name = nameNode ? nameNode.textContent.trim().toLowerCase() : '';
            if (!name.includes(extensionName)) {
                continue;
            }
            const idFromAttribute = item.getAttribute('id') || '';
            if (idFromAttribute.trim()) {
                return idFromAttribute.trim();
            }
            const detailText = root ? root.textContent : '';
            const match = detailText.match(/[a-p]{32}/);
            return match ? match[0] : '';
        }
        return '';
    """
    try:
        extension_id: Any = driver.execute_script(script, extension_name)
    except JavascriptException:
        return False
    return extension_id if isinstance(extension_id, str) and extension_id.strip() != "" else False


def open_onboarding(context: TaskContext, extension_id: str) -> None:
    context.open_new_tab(f"chrome-extension://{extension_id}/{ONBOARDING_PATH}")
    context.page_wait().until(lambda _driver: "onboarding" in context.driver.current_url or page_has_text(context, "MetaMask"))


def open_wallet_home(context: TaskContext, extension_id: str) -> None:
    context.open_new_tab(f"chrome-extension://{extension_id}/{HOME_PATH}")
    context.page_wait().until(lambda _driver: wallet_dashboard_visible(context) or wallet_unlock_visible(context))


def start_create_wallet(context: TaskContext) -> None:
    create_button: CdpClickableElement = context.node_wait().until(
        lambda driver: cdp_clickable_by_selector(driver, 'button[data-testid="onboarding-create-wallet"]')
    )
    create_button.click()
    srp_button: CdpClickableElement = context.node_wait().until(
        lambda driver: cdp_clickable_by_selector(driver, 'button[data-testid="onboarding-create-with-srp-button"]')
    )
    srp_button.click()


def create_password(context: TaskContext, password: str) -> None:
    cdp_type_text(context, 'input[data-testid="create-password-new-input"]', password)
    cdp_type_text(context, 'input[data-testid="create-password-confirm-input"]', password)
    terms_checkbox: CdpClickableElement = context.node_wait().until(
        lambda driver: cdp_clickable_by_selector(driver, 'label[data-testid="create-password-terms"]')
    )
    terms_checkbox.click()
    submit_button: CdpClickableElement = context.node_wait().until(
        lambda driver: cdp_clickable_by_selector(driver, 'button[data-testid="create-password-submit"]:not([disabled])')
    )
    submit_button.click()


def reveal_and_extract_seed(context: TaskContext) -> list[str]:
    click_optional_cdp(
        context,
        [
            'button[data-testid="secure-wallet-recommended"]',
            'button[data-testid="recovery-phrase-reveal"]',
        ],
    )
    reveal_button: CdpClickableElement = context.node_wait().until(
        lambda driver: cdp_clickable_by_selector(driver, '[data-testid="recovery-phrase-reveal"]')
    )
    reveal_button.click()
    seed_words: list[str] = context.node_wait().until(
        lambda driver: seed_words_from_recovery_phrase_attribute(driver, '[data-testid="recovery-phrase-chips"]')
    )
    if len(seed_words) != SEED_WORD_COUNT:
        raise RuntimeError(f"Seed phrase extraction did not return 12 words; word_count={len(seed_words)}")
    continue_button: CdpClickableElement = context.node_wait().until(
        lambda driver: cdp_clickable_by_selector(driver, 'button[data-testid="recovery-phrase-continue"]:not([disabled])')
    )
    continue_button.click()
    return seed_words


def seed_words_from_recovery_phrase_attribute(driver: Any, selector: str) -> list[str] | bool:
    recovery_phrase: str | bool = cdp_attribute_by_selector(driver, selector, "data-recovery-phrase")
    if not isinstance(recovery_phrase, str) or recovery_phrase.strip() == "":
        return False
    result: list[str] = [word.strip().lower() for word in recovery_phrase.split(":")]
    if len(result) != SEED_WORD_COUNT:
        return False
    return result if all(word != "" for word in result) else False


def confirm_seed_phrase(context: TaskContext, seed_words: list[str]) -> None:
    empty_indexes: list[int] = context.node_wait().until(
        lambda driver: recovery_phrase_quiz_indexes(driver, '[data-testid="recovery-phrase-chips"]')
    )
    if len(empty_indexes) == 0:
        raise RuntimeError("Could not map empty seed confirmation inputs.")
    for seed_index in empty_indexes:
        if seed_index < 0 or seed_index >= len(seed_words):
            raise RuntimeError(f"Seed confirmation index out of range; seed_index={seed_index}")
        choice_button: CdpClickableElement = context.node_wait().until(
            lambda driver: cdp_clickable_by_selector(driver, f'button[data-testid="recovery-phrase-quiz-unanswered-{seed_index}"]')
        )
        choice_button.click()
    confirm_button: CdpClickableElement = context.node_wait().until(
        lambda driver: cdp_clickable_by_selector(driver, 'button[data-testid="recovery-phrase-confirm"]:not([disabled])')
    )
    confirm_button.click()


def recovery_phrase_quiz_indexes(driver: Any, selector: str) -> list[int] | bool:
    raw_quiz_words: str | bool = cdp_attribute_by_selector(driver, selector, "data-quiz-words")
    if not isinstance(raw_quiz_words, str) or raw_quiz_words.strip() == "":
        return False
    try:
        quiz_words: Any = json.loads(raw_quiz_words)
    except json.JSONDecodeError:
        return False
    if not isinstance(quiz_words, list) or len(quiz_words) == 0:
        return False
    indexes: list[int] = []
    for quiz_word in quiz_words:
        if not isinstance(quiz_word, dict):
            return False
        raw_index: Any = quiz_word.get("index")
        if not isinstance(raw_index, int):
            return False
        indexes.append(raw_index)
    return sorted(indexes)


def focus_seed_input(context: TaskContext, seed_index: int) -> None:
    script: str = """
        const seedIndex = arguments[0];
        const inputs = Array.from(document.querySelectorAll('input'))
            .filter(input => input.offsetParent !== null || input.getClientRects().length > 0)
            .filter(input => (input.type || 'text') !== 'password')
            .slice(0, 12);
        if (!inputs[seedIndex]) {
            return false;
        }
        inputs[seedIndex].focus();
        inputs[seedIndex].click();
        return true;
    """
    focused: Any = context.driver.execute_script(script, seed_index)
    if not bool(focused):
        raise RuntimeError(f"Could not focus seed confirmation input; seed_index={seed_index}")


def click_seed_word_choice(context: TaskContext, word: str) -> None:
    xpath: str = (
        "//button[translate(normalize-space(), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz')="
        f"'{word.lower()}']"
    )
    try:
        button: WebElement = context.node_wait().until(expected.element_to_be_clickable((By.XPATH, xpath)))
    except TimeoutException as error:
        raise RuntimeError(f"Could not find seed word choice button; word={word}") from error
    safe_click(context, button)


def finish_onboarding(context: TaskContext) -> None:
    button_selectors: list[str] = [
        'button[data-testid="confirm-srp-modal-button"]',
        'button[data-testid="metametrics-i-agree"]',
        'button[data-testid="onboarding-complete-done"]',
        'button[data-testid="pin-extension-next"]',
        'button[data-testid="pin-extension-done"]',
    ]
    for _ in range(12):
        if wallet_dashboard_visible(context):
            return
        if not click_optional_cdp(context, button_selectors):
            break
    if not wallet_dashboard_visible(context):
        raise RuntimeError(f"MetaMask dashboard did not appear; url={context.driver.current_url}")


def wallet_dashboard_visible(context: TaskContext) -> bool:
    if dashboard_ready_on_current_tab(context.driver):
        return True
    if switch_to_existing_metamask_dashboard(context):
        return True
    return False


def dashboard_ready_on_current_tab(driver: Any) -> bool:
    return any(cdp_selector_exists(driver, selector) for selector in DASHBOARD_SELECTORS)


def unlock_wallet_if_locked(context: TaskContext, password: str) -> None:
    if wallet_dashboard_visible(context):
        return
    context.node_wait().until(lambda _driver: wallet_dashboard_visible(context) or wallet_unlock_visible(context))
    if wallet_dashboard_visible(context):
        return
    if not wallet_unlock_visible(context):
        raise RuntimeError(f"MetaMask is neither unlocked nor on the unlock page; url={context.driver.current_url}")
    cdp_type_text(context, 'input[data-testid="unlock-password"]', password)
    submit_button: CdpClickableElement = context.node_wait().until(
        lambda driver: cdp_clickable_by_selector(driver, 'button[data-testid="unlock-submit"]:not([disabled])')
    )
    submit_button.click()
    context.node_wait().until(lambda _driver: wallet_dashboard_visible(context))


def extract_wallet_address(context: TaskContext) -> str:
    context.node_wait().until(lambda _driver: wallet_dashboard_visible(context))
    with CLIPBOARD_LOCK:
        copy_button: CdpClickableElement = context.node_wait().until(
            lambda driver: cdp_clickable_by_selector(driver, '[data-testid="network-group-with-copy-icon"]')
        )
        copy_button.click()
        address: str = context.node_wait().until(lambda driver: cdp_clipboard_text(driver))
    if not EVM_ADDRESS_PATTERN.match(address):
        raise RuntimeError(f"Clipboard did not contain a valid EVM address; clipboard_text={address}")
    return address


def extract_wallet_addresses(context: TaskContext) -> dict[str, str]:
    open_receiving_address_list(context)
    evm_address: str = copy_receiving_address_for_network(context, "Ethereum", EVM_ADDRESS_PATTERN)
    solana_address: str = copy_receiving_address_for_network(context, "Solana", SOLANA_ADDRESS_PATTERN)
    return {
        "Address": evm_address,
        "EvmAddress": evm_address,
        "SolanaAddress": solana_address,
    }


def login_existing_wallet_flow(context: TaskContext, password: str) -> dict[str, str]:
    unlock_wallet_if_locked(context, password)
    context.node_wait().until(lambda _driver: wallet_dashboard_visible(context))
    addresses: dict[str, str] = extract_wallet_addresses(context)
    return {**addresses, "WalletState": "Unlocked"}


def backup_existing_seed_phrase_flow(context: TaskContext, password: str) -> dict[str, str]:
    open_account_details(context)
    start_existing_seed_phrase_reveal(context)
    complete_seed_phrase_quiz(context)
    confirm_existing_seed_phrase_password(context, password)
    seed_words: list[str] = reveal_and_copy_existing_seed_phrase(context)
    return {
        "SeedPhrase": " ".join(seed_words),
        "WalletState": "ExistingWallet",
        "BackupMode": "RevealExistingSeedPhrase",
    }


def backup_ethereum_private_key_flow(context: TaskContext, password: str) -> dict[str, str]:
    open_account_details(context)
    open_private_key_reveal(context)
    confirm_private_key_password(context, password)
    private_key: str = copy_private_key_for_network(context, "Ethereum")
    return {
        "PrivateKey": private_key,
        "EthereumPrivateKey": private_key,
        "PrivateKeyNetwork": "Ethereum",
        "WalletState": "ExistingWallet",
        "BackupMode": "RevealEthereumPrivateKey",
    }


def open_account_details(context: TaskContext) -> None:
    if account_details_visible(context):
        return
    context.node_wait().until(lambda _driver: wallet_dashboard_visible(context))
    account_menu: CdpClickableElement = context.node_wait().until(
        lambda driver: cdp_clickable_by_selector(driver, 'button[data-testid="account-menu-icon"]')
    )
    account_menu.click()
    account_options: CdpClickableElement = context.node_wait().until(
        lambda driver: cdp_clickable_by_selector(driver, '[data-testid="multichain-account-cell-end-accessory"]')
    )
    account_options.click()
    account_details: CdpClickableElement = context.node_wait().until(
        lambda driver: cdp_clickable_by_selector(driver, '[data-testid="multichain-account-menu-item-accountDetails"]')
    )
    account_details.click()
    context.node_wait().until(lambda _driver: account_details_visible(context))


def account_details_visible(context: TaskContext) -> bool:
    return cdp_selector_exists(context.driver, 'button[data-testid="private-keys-action"]') and cdp_selector_exists(
        context.driver,
        '[data-testid="multichain-srp-backup"]',
    )


def start_existing_seed_phrase_reveal(context: TaskContext) -> None:
    reveal_entry: CdpClickableElement = context.node_wait().until(
        lambda driver: cdp_clickable_by_selector(driver, '[data-testid="multichain-srp-backup"]')
    )
    reveal_entry.click()
    context.node_wait().until(lambda driver: cdp_selector_exists(driver, '[data-testid="reveal-seed-page"]'))


def complete_seed_phrase_quiz(context: TaskContext) -> None:
    for _ in range(8):
        if cdp_selector_exists(context.driver, 'input[data-testid="input-password"]'):
            return
        started: bool = click_optional_cdp(context, ['button[data-testid="reveal-seed-quiz-get-started"]'])
        if started:
            continue
        answered: bool = click_optional_cdp(context, ['button[data-testid="srp-quiz-right-answer"]'])
        if answered:
            continue
        continued: bool = click_optional_cdp(context, ['button[data-testid="srp-quiz-continue"]'])
        if continued:
            continue
        break
    if not cdp_selector_exists(context.driver, 'input[data-testid="input-password"]'):
        raise RuntimeError(f"Could not complete seed phrase quiz; url={context.driver.current_url}")


def confirm_existing_seed_phrase_password(context: TaskContext, password: str) -> None:
    cdp_type_text(context, 'input[data-testid="input-password"]', password)
    continue_button: CdpClickableElement = context.node_wait().until(
        lambda driver: cdp_clickable_by_selector(driver, 'button[data-testid="reveal-seed-password-continue"]:not([disabled])')
    )
    continue_button.click()
    context.node_wait().until(lambda driver: cdp_selector_exists(driver, '[data-testid="recovery-phrase-reveal"]'))


def reveal_and_copy_existing_seed_phrase(context: TaskContext) -> list[str]:
    reveal_button: CdpClickableElement = context.node_wait().until(
        lambda driver: cdp_clickable_by_selector(driver, '[data-testid="recovery-phrase-reveal"]')
    )
    reveal_button.click()
    seed_words: list[str] = context.node_wait().until(lambda driver: existing_seed_phrase_words(driver))
    with CLIPBOARD_LOCK:
        copy_button: CdpClickableElement = context.node_wait().until(
            lambda driver: cdp_clickable_by_selector(driver, 'button[data-testid="reveal-seed-copy-button"]:not([disabled])')
        )
        copy_button.click()
    return validate_seed_words(seed_words)


def existing_seed_phrase_words(driver: Any) -> list[str] | bool:
    expression: str = r"""
        (() => Array.from(document.querySelectorAll('[data-testid^="recovery-phrase-chip-"]'))
            .map((node) => (node.innerText || node.textContent || '').replace(/^\s*\d+\.\s*/, '').trim().toLowerCase())
            .filter(Boolean))()
    """
    raw_words: Any = cdp_runtime_value(driver, expression)
    if not isinstance(raw_words, list):
        return False
    words: list[str] = [word for word in raw_words if isinstance(word, str) and word.strip() != ""]
    return validate_seed_words(words) if len(words) in {12, 24} else False


def validate_seed_words(seed_words: list[str]) -> list[str]:
    normalized_words: list[str] = [word.strip().lower() for word in seed_words]
    if len(normalized_words) not in {12, 24}:
        raise RuntimeError(f"Invalid seed word count; word_count={len(normalized_words)}")
    if any(word == "" for word in normalized_words):
        raise RuntimeError("Seed phrase contains blank words.")
    return normalized_words


def open_private_key_reveal(context: TaskContext) -> None:
    private_key_entry: CdpClickableElement = context.node_wait().until(
        lambda driver: cdp_clickable_by_selector(driver, 'button[data-testid="private-keys-action"]')
    )
    private_key_entry.click()
    context.node_wait().until(lambda driver: cdp_selector_exists(driver, 'input[data-testid="multichain-private-key-password-input"]'))


def confirm_private_key_password(context: TaskContext, password: str) -> None:
    cdp_type_text(context, 'input[data-testid="multichain-private-key-password-input"]', password)
    confirm_button: CdpClickableElement = context.node_wait().until(
        lambda driver: cdp_clickable_by_selector(driver, 'button[data-testid="confirm-button"]')
    )
    confirm_button.click()
    context.node_wait().until(lambda driver: private_key_rows_visible(driver))


def private_key_rows_visible(driver: Any) -> bool:
    return cdp_selector_exists(driver, '[data-testid="multichain-address-row"]') and not cdp_selector_exists(
        driver,
        'input[data-testid="multichain-private-key-password-input"]',
    )


def copy_private_key_for_network(context: TaskContext, network_name: str) -> str:
    with CLIPBOARD_LOCK:
        context.node_wait().until(lambda driver: cdp_click_copy_button_for_network(driver, network_name))
        private_key: str = context.node_wait().until(lambda driver: cdp_clipboard_text_matching(driver, PRIVATE_KEY_PATTERN))
    if not PRIVATE_KEY_PATTERN.match(private_key):
        raise RuntimeError(f"Clipboard did not contain a valid private key; network={network_name}")
    return private_key


def open_receiving_address_list(context: TaskContext) -> None:
    if receiving_address_list_visible(context.driver):
        return
    context.node_wait().until(lambda _driver: wallet_dashboard_visible(context))
    receive_button: CdpClickableElement = context.node_wait().until(
        lambda driver: cdp_clickable_by_selector(driver, 'button[data-testid="eth-overview-receive"]')
    )
    receive_button.click()
    context.node_wait().until(lambda driver: receiving_address_list_visible(driver))


def receiving_address_list_visible(driver: Any) -> bool:
    return cdp_selector_exists(driver, '[data-testid="multichain-address-rows-list"]')


def copy_receiving_address_for_network(context: TaskContext, network_name: str, pattern: re.Pattern[str]) -> str:
    with CLIPBOARD_LOCK:
        context.node_wait().until(lambda driver: cdp_click_copy_button_for_network(driver, network_name))
        address: str = context.node_wait().until(lambda driver: cdp_clipboard_text_matching(driver, pattern))
    if not pattern.match(address):
        raise RuntimeError(f"Clipboard did not contain a valid address; network={network_name}; clipboard_text={address}")
    return address


def switch_to_existing_metamask_dashboard(context: TaskContext) -> bool:
    current_handle: str = context.driver.current_window_handle
    for handle in context.driver.window_handles:
        context.driver.switch_to.window(handle)
        current_url: str = context.driver.current_url
        if "chrome-extension://" not in current_url:
            continue
        if "home.html" in current_url and "onboarding" not in current_url and "unlock" not in current_url:
            if not dashboard_ready_on_current_tab(context.driver):
                continue
            return True
    context.driver.switch_to.window(current_handle)
    return False


def wallet_unlock_visible(context: TaskContext) -> bool:
    if cdp_selector_exists(context.driver, 'input[data-testid="unlock-password"]'):
        return True
    return switch_to_existing_metamask_unlock(context)


def switch_to_existing_metamask_unlock(context: TaskContext) -> bool:
    current_handle: str = context.driver.current_window_handle
    for handle in context.driver.window_handles:
        context.driver.switch_to.window(handle)
        current_url: str = context.driver.current_url
        if "chrome-extension://" not in current_url:
            continue
        if "home.html" in current_url and "unlock" in current_url:
            if not cdp_selector_exists(context.driver, 'input[data-testid="unlock-password"]'):
                continue
            return True
    context.driver.switch_to.window(current_handle)
    return False


def fill_first_available(
    context: TaskContext,
    action_name: str,
    value: str,
    locators: list[tuple[str, str]],
    element_index: int,
) -> None:
    elements: list[WebElement] = context.node_wait().until(lambda _driver: visible_elements_for_locators(context, locators))
    if element_index >= len(elements):
        raise RuntimeError(f"Could not find input by index; action={action_name}; index={element_index}; count={len(elements)}")
    element: WebElement = elements[element_index]
    element.clear()
    element.send_keys(value)


def click_first_available(context: TaskContext, action_name: str, locators: list[tuple[str, str]]) -> None:
    for locator in locators:
        try:
            element: WebElement = context.node_wait().until(expected.element_to_be_clickable(locator))
            safe_click(context, element)
            return
        except TimeoutException:
            continue
    raise RuntimeError(f"Could not click action; action={action_name}; locators={locators}; url={context.driver.current_url}")


def cdp_clickable_by_selector(driver: Any, selector: str) -> CdpClickableElement | bool:
    try:
        driver.execute_cdp_cmd("DOM.enable", {})
        document = driver.execute_cdp_cmd("DOM.getDocument", {"depth": -1, "pierce": True})
        node_id: int = int(
            driver.execute_cdp_cmd(
                "DOM.querySelector",
                {"nodeId": document["root"]["nodeId"], "selector": selector},
            )["nodeId"]
        )
        if node_id == 0:
            return False
        return CdpClickableElement(driver=driver, node_id=node_id)
    except (KeyError, TypeError, ValueError, WebDriverException):
        return False


def cdp_selector_exists(driver: Any, selector: str) -> bool:
    try:
        driver.execute_cdp_cmd("DOM.enable", {})
        document = driver.execute_cdp_cmd("DOM.getDocument", {"depth": -1, "pierce": True})
        node_id: int = int(
            driver.execute_cdp_cmd(
                "DOM.querySelector",
                {"nodeId": document["root"]["nodeId"], "selector": selector},
            )["nodeId"]
        )
        return node_id != 0
    except (KeyError, TypeError, ValueError, WebDriverException):
        return False


def cdp_attribute_by_selector(driver: Any, selector: str, attribute_name: str) -> str | bool:
    try:
        driver.execute_cdp_cmd("DOM.enable", {})
        document = driver.execute_cdp_cmd("DOM.getDocument", {"depth": -1, "pierce": True})
        node_id: int = int(
            driver.execute_cdp_cmd(
                "DOM.querySelector",
                {"nodeId": document["root"]["nodeId"], "selector": selector},
            )["nodeId"]
        )
        if node_id == 0:
            return False
        response: dict[str, Any] = driver.execute_cdp_cmd("DOM.getAttributes", {"nodeId": node_id})
        attributes: Any = response.get("attributes")
        if not isinstance(attributes, list):
            return False
        for index in range(0, len(attributes), 2):
            name: Any = attributes[index]
            value: Any = attributes[index + 1] if index + 1 < len(attributes) else ""
            if name == attribute_name and isinstance(value, str):
                return value
        return False
    except (KeyError, TypeError, ValueError, WebDriverException):
        return False


def cdp_runtime_value(driver: Any, expression: str) -> Any:
    try:
        result: dict[str, Any] = driver.execute_cdp_cmd(
            "Runtime.evaluate",
            {
                "expression": expression,
                "awaitPromise": True,
                "returnByValue": True,
            },
        )
    except WebDriverException:
        return False
    raw_result: Any = result.get("result")
    if not isinstance(raw_result, dict):
        return False
    return raw_result.get("value")


def cdp_click_copy_button_for_network(driver: Any, network_name: str) -> bool:
    expression: str = """
        (() => {
            const networkName = %s;
            const rows = Array.from(document.querySelectorAll('[data-testid="multichain-address-row"]'));
            for (const row of rows) {
                const nameNode = row.querySelector('[data-testid="multichain-address-row-network-name"]');
                const name = nameNode ? nameNode.textContent.trim() : '';
                if (name !== networkName) {
                    continue;
                }
                const button = row.querySelector('[data-testid="multichain-address-row-copy-button"]');
                if (!button) {
                    return false;
                }
                button.click();
                return true;
            }
            return false;
        })()
    """ % json.dumps(network_name)
    try:
        result: dict[str, Any] = driver.execute_cdp_cmd(
            "Runtime.evaluate",
            {
                "expression": expression,
                "awaitPromise": False,
                "returnByValue": True,
            },
        )
    except WebDriverException:
        return False
    raw_result: Any = result.get("result")
    if not isinstance(raw_result, dict):
        return False
    return raw_result.get("value") is True


def cdp_clipboard_text(driver: Any) -> str | bool:
    try:
        result: dict[str, Any] = driver.execute_cdp_cmd(
            "Runtime.evaluate",
            {
                "expression": "navigator.clipboard && navigator.clipboard.readText ? navigator.clipboard.readText() : ''",
                "awaitPromise": True,
                "returnByValue": True,
            },
        )
    except WebDriverException:
        return False
    raw_result: Any = result.get("result")
    if not isinstance(raw_result, dict):
        return False
    value: Any = raw_result.get("value")
    if not isinstance(value, str):
        return False
    address: str = value.strip()
    return address if EVM_ADDRESS_PATTERN.match(address) else False


def cdp_clipboard_text_matching(driver: Any, pattern: re.Pattern[str]) -> str | bool:
    try:
        result: dict[str, Any] = driver.execute_cdp_cmd(
            "Runtime.evaluate",
            {
                "expression": "navigator.clipboard && navigator.clipboard.readText ? navigator.clipboard.readText() : ''",
                "awaitPromise": True,
                "returnByValue": True,
            },
        )
    except WebDriverException:
        return False
    raw_result: Any = result.get("result")
    if not isinstance(raw_result, dict):
        return False
    value: Any = raw_result.get("value")
    if not isinstance(value, str):
        return False
    address: str = value.strip()
    return address if pattern.match(address) else False


def cdp_type_text(context: TaskContext, selector: str, value: str) -> None:
    target: CdpClickableElement = context.node_wait().until(lambda driver: cdp_clickable_by_selector(driver, selector))
    target.click()
    clear_active_input(context.driver)
    context.driver.execute_cdp_cmd("Input.insertText", {"text": value})


def clear_active_input(driver: Any) -> None:
    driver.execute_cdp_cmd("Input.dispatchKeyEvent", {"type": "keyDown", "key": "Control", "code": "ControlLeft", "windowsVirtualKeyCode": 17})
    driver.execute_cdp_cmd(
        "Input.dispatchKeyEvent",
        {"type": "keyDown", "key": "a", "code": "KeyA", "windowsVirtualKeyCode": 65, "modifiers": 2},
    )
    driver.execute_cdp_cmd(
        "Input.dispatchKeyEvent",
        {"type": "keyUp", "key": "a", "code": "KeyA", "windowsVirtualKeyCode": 65, "modifiers": 2},
    )
    driver.execute_cdp_cmd("Input.dispatchKeyEvent", {"type": "keyUp", "key": "Control", "code": "ControlLeft", "windowsVirtualKeyCode": 17})
    driver.execute_cdp_cmd("Input.dispatchKeyEvent", {"type": "keyDown", "key": "Backspace", "code": "Backspace", "windowsVirtualKeyCode": 8})
    driver.execute_cdp_cmd("Input.dispatchKeyEvent", {"type": "keyUp", "key": "Backspace", "code": "Backspace", "windowsVirtualKeyCode": 8})


def click_optional(context: TaskContext, action_name: str, locators: list[tuple[str, str]]) -> bool:
    for locator in locators:
        try:
            element: WebElement = context.node_wait().until(expected.element_to_be_clickable(locator))
            safe_click(context, element)
            return True
        except TimeoutException:
            continue
    return False


def click_optional_cdp(context: TaskContext, selectors: list[str]) -> bool:
    for selector in selectors:
        element: CdpClickableElement | bool = cdp_clickable_by_selector(context.driver, selector)
        if isinstance(element, CdpClickableElement):
            element.click()
            return True
    return False


def visible_elements_for_locators(context: TaskContext, locators: list[tuple[str, str]]) -> list[WebElement] | bool:
    for locator in locators:
        elements: list[WebElement] = [
            element for element in context.driver.find_elements(*locator) if element.is_displayed() and element.is_enabled()
        ]
        if len(elements) > 0:
            return elements
    return False


def safe_click(context: TaskContext, element: WebElement) -> None:
    try:
        element.click()
    except WebDriverException:
        context.driver.execute_script("arguments[0].click();", element)


def page_has_text(context: TaskContext, text: str) -> bool:
    return text.lower() in context.page_text().lower()


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
