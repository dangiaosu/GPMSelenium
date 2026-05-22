from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, TypeAlias, cast
from urllib.parse import urlencode

import requests
from requests import Response, Session
from selenium import webdriver
from selenium.common.exceptions import WebDriverException
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.remote.webdriver import WebDriver

JsonObject: TypeAlias = dict[str, Any]


class GpmApiError(RuntimeError):
    pass


@dataclass(frozen=True)
class WindowPosition:
    x: int
    y: int


@dataclass(frozen=True)
class WindowSize:
    width: int
    height: int


@dataclass(frozen=True)
class GpmWindowOptions:
    size: WindowSize
    position: WindowPosition
    scale: float
    addination_args: str | None


@dataclass(frozen=True)
class StartedProfile:
    profile_id: str
    remote_debugging_address: str
    driver_path: Path


@dataclass(frozen=True)
class GpmProfile:
    profile_id: str
    name: str
    group_id: str
    raw_proxy: str
    browser_type: str
    browser_version: str
    note: str
    created_at: str


@dataclass(frozen=True)
class GpmGroup:
    group_id: str
    name: str


class GpmClient:
    def __init__(self, base_url: str, session: Session, timeout_seconds: float, retries: int) -> None:
        self._base_url: str = base_url.rstrip("/")
        self._session: Session = session
        self._timeout_seconds: float = timeout_seconds
        self._retries: int = retries

    def start_profile(self, profile_id: str, window_options: GpmWindowOptions) -> StartedProfile:
        url: str = build_start_profile_url(self._base_url, profile_id, window_options)
        response_data: JsonObject = self._start_profile_with_open_profile_recovery(url, profile_id)
        data: Any = response_data.get("data")

        remote_debugging_address: Any = data.get("remote_debugging_address")
        driver_path: Any = data.get("driver_path")
        returned_profile_id: Any = data.get("profile_id")
        if not isinstance(remote_debugging_address, str) or remote_debugging_address == "":
            raise GpmApiError(
                f"GPM response missing remote_debugging_address; profile_id={profile_id}; response={response_data}"
            )
        if not isinstance(driver_path, str) or driver_path == "":
            raise GpmApiError(f"GPM response missing driver_path; profile_id={profile_id}; response={response_data}")

        normalized_profile_id: str = returned_profile_id if isinstance(returned_profile_id, str) else profile_id
        return StartedProfile(
            profile_id=normalized_profile_id,
            remote_debugging_address=remote_debugging_address,
            driver_path=Path(driver_path),
        )

    def close_profile(self, profile_id: str) -> None:
        url: str = f"{self._base_url}/api/v3/profiles/close/{profile_id}"
        response_data: JsonObject = self._get_json_with_retries(url, {"profile_id": profile_id})
        if not bool(response_data.get("success")):
            raise GpmApiError(f"GPM close profile failed; profile_id={profile_id}; response={response_data}")

    def _start_profile_with_open_profile_recovery(self, url: str, profile_id: str) -> JsonObject:
        first_response: JsonObject = self._get_json_with_retries(url, {"profile_id": profile_id})
        if start_profile_succeeded(first_response):
            return first_response
        if not start_profile_already_open(first_response):
            raise GpmApiError(f"GPM start profile failed; profile_id={profile_id}; response={first_response}")

        logging.warning(
            "gpm_profile_already_open_before_start",
            extra={"profile_id": profile_id, "response": first_response},
        )
        self.close_profile(profile_id)
        time.sleep(1.0)
        second_response: JsonObject = self._get_json_with_retries(url, {"profile_id": profile_id})
        if start_profile_succeeded(second_response):
            return second_response
        raise GpmApiError(f"GPM start profile failed after close retry; profile_id={profile_id}; response={second_response}")

    def list_profiles(self, page: int, per_page: int, search: str, sort: int, group_id: str | None) -> list[GpmProfile]:
        query_params: dict[str, str] = {
            "page": str(page),
            "per_page": str(per_page),
            "sort": str(sort),
        }
        if search.strip() != "":
            query_params["search"] = search.strip()
        if group_id is not None and group_id.strip() != "":
            query_params["group_id"] = group_id.strip()
        url: str = f"{self._base_url}/api/v3/profiles?{urlencode(query_params)}"
        response_data: JsonObject = self._get_json_with_retries(
            url,
            {
                "page": str(page),
                "per_page": str(per_page),
                "search": search,
                "sort": str(sort),
                "group_id": "" if group_id is None else group_id,
            },
        )
        data: Any = response_data.get("data")
        if not bool(response_data.get("success")) or not isinstance(data, list):
            raise GpmApiError(f"GPM list profiles failed; url={url}; response={response_data}")
        return [parse_profile(item) for item in data if isinstance(item, dict)]

    def list_groups(self) -> list[GpmGroup]:
        url: str = f"{self._base_url}/api/v3/groups"
        response_data: JsonObject = self._get_json_with_retries(url, {})
        data: Any = response_data.get("data")
        if not bool(response_data.get("success")) or not isinstance(data, list):
            raise GpmApiError(f"GPM list groups failed; url={url}; response={response_data}")
        return [parse_group(item) for item in data if isinstance(item, dict)]

    def _get_json_with_retries(self, url: str, request_context: Mapping[str, str]) -> JsonObject:
        last_error: Exception | None = None
        for attempt_number in range(1, self._retries + 1):
            try:
                response: Response = self._session.get(url, timeout=self._timeout_seconds)
                if response.status_code >= 400:
                    raise GpmApiError(
                        f"GPM request failed; url={url}; status_code={response.status_code}; response_body={response.text}"
                    )
                parsed_response: Any = response.json()
                if not isinstance(parsed_response, dict):
                    raise GpmApiError(f"GPM response was not a JSON object; url={url}; response_body={response.text}")
                return cast(JsonObject, parsed_response)
            except (requests.RequestException, ValueError, GpmApiError) as error:
                last_error = error
                logging.warning(
                    "gpm_request_attempt_failed",
                    extra={
                        "url": url,
                        "attempt_number": attempt_number,
                        "max_attempts": self._retries,
                        "request_context": dict(request_context),
                        "error_type": type(error).__name__,
                        "error": str(error),
                    },
                )
                if attempt_number < self._retries:
                    time.sleep(float(attempt_number))

        if last_error is None:
            raise GpmApiError(f"GPM request was not attempted; url={url}; request_context={dict(request_context)}")
        raise last_error


def parse_profile(raw_profile: Mapping[str, Any]) -> GpmProfile:
    raw_profile_id: Any = raw_profile.get("id")
    raw_name: Any = raw_profile.get("name")
    if not isinstance(raw_profile_id, str) or raw_profile_id.strip() == "":
        raise GpmApiError(f"GPM profile missing id; profile={dict(raw_profile)}")
    if not isinstance(raw_name, str):
        raw_name = ""
    return GpmProfile(
        profile_id=raw_profile_id.strip(),
        name=raw_name.strip(),
        group_id=string_value(raw_profile, "group_id"),
        raw_proxy=string_value(raw_profile, "raw_proxy"),
        browser_type=string_value(raw_profile, "browser_type"),
        browser_version=string_value(raw_profile, "browser_version"),
        note=string_value(raw_profile, "note"),
        created_at=string_value(raw_profile, "created_at"),
    )


def parse_group(raw_group: Mapping[str, Any]) -> GpmGroup:
    raw_group_id: Any = raw_group.get("id")
    raw_name: Any = raw_group.get("name")
    if raw_group_id is None:
        raise GpmApiError(f"GPM group missing id; group={dict(raw_group)}")
    group_id: str = str(raw_group_id).strip()
    if group_id == "":
        raise GpmApiError(f"GPM group id is empty; group={dict(raw_group)}")
    name: str = "" if raw_name is None else str(raw_name).strip()
    return GpmGroup(group_id=group_id, name=name if name != "" else f"Group {group_id}")


def string_value(raw_profile: Mapping[str, Any], key: str) -> str:
    raw_value: Any = raw_profile.get(key)
    if raw_value is None:
        return ""
    return str(raw_value).strip()


def start_profile_succeeded(response_data: JsonObject) -> bool:
    return bool(response_data.get("success")) and isinstance(response_data.get("data"), dict)


def start_profile_already_open(response_data: JsonObject) -> bool:
    message: Any = response_data.get("message")
    return isinstance(message, str) and message.strip().upper() == "ALREADY_OPEN"


def build_start_profile_url(base_url: str, profile_id: str, window_options: GpmWindowOptions) -> str:
    query_params: dict[str, str] = {
        "win_size": f"{window_options.size.width},{window_options.size.height}",
        "win_pos": f"{window_options.position.x},{window_options.position.y}",
        "win_scale": str(window_options.scale),
    }
    if window_options.addination_args is not None and window_options.addination_args.strip() != "":
        query_params["addination_args"] = window_options.addination_args.strip()
    return f"{base_url.rstrip('/')}/api/v3/profiles/start/{profile_id}?{urlencode(query_params)}"


def create_driver(started_profile: StartedProfile, attach_retries: int) -> WebDriver:
    if not started_profile.driver_path.exists():
        raise GpmApiError(
            f"GPM driver path does not exist; profile_id={started_profile.profile_id}; driver_path={started_profile.driver_path}"
        )

    last_error: WebDriverException | None = None
    for attempt_number in range(1, attach_retries + 1):
        try:
            options: Options = Options()
            options.add_experimental_option("debuggerAddress", started_profile.remote_debugging_address)
            service: Service = Service(executable_path=str(started_profile.driver_path))
            return webdriver.Chrome(service=service, options=options)
        except WebDriverException as error:
            last_error = error
            logging.warning(
                "webdriver_attach_attempt_failed",
                extra={
                    "profile_id": started_profile.profile_id,
                    "attempt_number": attempt_number,
                    "max_attempts": attach_retries,
                    "remote_debugging_address": started_profile.remote_debugging_address,
                    "driver_path": str(started_profile.driver_path),
                    "error_type": type(error).__name__,
                    "error": str(error),
                },
            )
            if attempt_number < attach_retries:
                time.sleep(float(attempt_number))

    if last_error is None:
        raise GpmApiError(f"WebDriver attach was not attempted; profile_id={started_profile.profile_id}")
    raise last_error


def close_driver(driver: WebDriver, logger: logging.Logger, profile_id: str) -> None:
    try:
        driver.quit()
    except WebDriverException as error:
        logger.warning(
            "driver_close_failed",
            extra={"profile_id": profile_id, "error_type": type(error).__name__, "error": str(error)},
        )
