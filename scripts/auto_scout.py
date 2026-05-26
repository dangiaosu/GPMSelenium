from __future__ import annotations

from pathlib import Path
from typing import Any

import requests
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.remote.webdriver import WebDriver
from selenium.webdriver.support.ui import WebDriverWait

GPM_BASE_URL = "http://127.0.0.1:19995"
PROFILE_ID = "53236602-6685-4415-b686-3cf09647aac8"
ARTIFACT_PATH = Path("artifacts") / "dom_snapshot_step_1.html"
METAMASK_EXTENSION_NAME = "MetaMask"


def main() -> None:
    started_profile: dict[str, str] = start_gpm_profile(PROFILE_ID)
    driver: WebDriver = attach_driver(started_profile)
    extension_id: str = find_metamask_extension_id(driver)
    driver.switch_to.new_window("tab")
    driver.get(f"chrome-extension://{extension_id}/home.html#/onboarding/welcome")
    WebDriverWait(driver, 30).until(lambda active_driver: active_driver.execute_script("return document.readyState") == "complete")
    WebDriverWait(driver, 30).until(lambda active_driver: active_driver.execute_script("return document.body ? document.body.innerText.length : 0") > 0)
    ARTIFACT_PATH.parent.mkdir(parents=True, exist_ok=True)
    ARTIFACT_PATH.write_text(driver.page_source, encoding="utf-8", errors="replace")
    print(f"extension_id={extension_id}")
    print(f"dom_snapshot={ARTIFACT_PATH.resolve()}")


def start_gpm_profile(profile_id: str) -> dict[str, str]:
    url: str = f"{GPM_BASE_URL}/api/v3/profiles/start/{profile_id}"
    response = requests.get(url, timeout=30)
    response.raise_for_status()
    response_data: Any = response.json()
    if not isinstance(response_data, dict) or not bool(response_data.get("success")):
        raise RuntimeError(f"GPM start profile failed; url={url}; response={response_data}")
    data: Any = response_data.get("data")
    if not isinstance(data, dict):
        raise RuntimeError(f"GPM start response missing data object; url={url}; response={response_data}")
    remote_debugging_address: Any = data.get("remote_debugging_address")
    driver_path: Any = data.get("driver_path")
    if not isinstance(remote_debugging_address, str) or remote_debugging_address.strip() == "":
        raise RuntimeError(f"GPM response missing remote_debugging_address; response={response_data}")
    if not isinstance(driver_path, str) or driver_path.strip() == "":
        raise RuntimeError(f"GPM response missing driver_path; response={response_data}")
    return {
        "remote_debugging_address": remote_debugging_address.strip(),
        "driver_path": driver_path.strip(),
    }


def attach_driver(started_profile: dict[str, str]) -> WebDriver:
    options = Options()
    options.add_experimental_option("debuggerAddress", started_profile["remote_debugging_address"])
    service = Service(str(Path(started_profile["driver_path"])))
    return webdriver.Chrome(service=service, options=options)


def find_metamask_extension_id(driver: WebDriver) -> str:
    driver.switch_to.new_window("tab")
    driver.get("chrome://extensions/")
    WebDriverWait(driver, 30).until(lambda active_driver: active_driver.execute_script("return document.readyState") == "complete")
    extension_id: str | bool = WebDriverWait(driver, 30).until(
        lambda active_driver: extension_id_from_extensions_page(active_driver, METAMASK_EXTENSION_NAME)
    )
    if not isinstance(extension_id, str) or extension_id.strip() == "":
        raise RuntimeError(f"Could not find extension id; extension_name={METAMASK_EXTENSION_NAME}")
    return extension_id.strip()


def extension_id_from_extensions_page(driver: WebDriver, extension_name: str) -> str | bool:
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
    extension_id: Any = driver.execute_script(script, extension_name)
    return extension_id if isinstance(extension_id, str) and extension_id.strip() != "" else False


if __name__ == "__main__":
    main()
