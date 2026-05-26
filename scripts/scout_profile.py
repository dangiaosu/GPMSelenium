from __future__ import annotations

import code
from pathlib import Path
from typing import Any

import requests
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.remote.webdriver import WebDriver

GPM_BASE_URL = "http://127.0.0.1:19995"
PROFILE_ID = "53236602-6685-4415-b686-3cf09647aac8"


def main() -> None:
    started_profile: dict[str, str] = start_gpm_profile(PROFILE_ID)
    driver: WebDriver = attach_driver(started_profile)
    print("Attached to GPM profile.")
    print(f"ProfileID: {PROFILE_ID}")
    print(f"Remote debugging: {started_profile['remote_debugging_address']}")
    print("Driver is available as variable: driver")
    print("This script intentionally does not call driver.quit() or GPM close.")
    code.interact(local={"driver": driver, "profile": started_profile})


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


if __name__ == "__main__":
    main()
