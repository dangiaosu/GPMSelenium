from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from threading import Event
from typing import Any

from selenium.webdriver.remote.webdriver import WebDriver
from selenium.webdriver.support.ui import WebDriverWait


@dataclass(frozen=True)
class TaskResult:
    success: bool
    status: str
    data: dict[str, Any] | None
    error: str | None


@dataclass(frozen=True)
class ProfileContext:
    profile_id: str
    profile_name: str
    row_number: int


@dataclass(frozen=True)
class TaskContext:
    driver: WebDriver
    profile: ProfileContext
    logger: logging.Logger
    config: dict[str, Any]
    artifacts_dir: Path
    timeout_seconds: float
    node_timeout_seconds: float
    stop_event: Event

    def wait_ready(self) -> None:
        self.page_wait().until(lambda active_driver: active_driver.execute_script("return document.readyState") == "complete")

    def page_wait(self) -> WebDriverWait:
        return WebDriverWait(self.driver, self.timeout_seconds)

    def node_wait(self) -> WebDriverWait:
        return WebDriverWait(self.driver, self.node_timeout_seconds)

    def open_new_tab(self, url: str) -> None:
        self.driver.switch_to.new_window("tab")
        self.driver.get(url)
        self.wait_ready()

    def page_text(self) -> str:
        raw_text: Any = self.driver.execute_script("return document.body ? document.body.innerText : ''")
        return raw_text if isinstance(raw_text, str) else ""

    def html_source(self) -> str:
        return self.driver.page_source

    def screenshot(self, name: str) -> Path | None:
        if not bool(self.config.get("enable_debug_artifacts", False)):
            return None
        safe_name: str = "".join(character if character.isalnum() or character in "-_" else "_" for character in name)
        path: Path = self.artifacts_dir / f"{safe_name}.png"
        self.artifacts_dir.mkdir(parents=True, exist_ok=True)
        self.driver.save_screenshot(str(path))
        return path

    def save_html(self, name: str) -> Path | None:
        if not bool(self.config.get("enable_debug_artifacts", False)):
            return None
        safe_name: str = "".join(character if character.isalnum() or character in "-_" else "_" for character in name)
        path: Path = self.artifacts_dir / f"{safe_name}.html"
        self.artifacts_dir.mkdir(parents=True, exist_ok=True)
        path.write_text(self.html_source(), encoding="utf-8", errors="replace")
        return path

    def stop_requested(self) -> bool:
        return self.stop_event.is_set()


def ok(status: str, data: dict[str, Any] | None) -> TaskResult:
    return TaskResult(success=True, status=status, data=data, error=None)


def fail(status: str, error: str, data: dict[str, Any] | None) -> TaskResult:
    return TaskResult(success=False, status=status, data=data, error=error)
