from __future__ import annotations

import argparse
import json
import logging
import re
import sys
import threading
from dataclasses import dataclass
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, ClassVar, NoReturn, Sequence

import requests

PROJECT_ROOT: Path = Path(__file__).resolve().parents[1]
SRC_ROOT: Path = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from gpm_selenium.gpm import GpmClient, GpmGroup, GpmProfile, GpmWindowOptions, WindowPosition, WindowSize

JsonObject = dict[str, Any]


@dataclass(frozen=True)
class ScoutServerConfig:
    gpm_base_url: str
    host: str
    port: int
    output_dir: Path
    extension_dir: Path
    window_width: int
    window_height: int
    window_x: int
    window_y: int
    window_scale: float


@dataclass(frozen=True)
class StartedScoutProfile:
    profile_id: str
    profile_name: str
    remote_debugging_address: str
    driver_path: Path


class DumpRequestHandler(BaseHTTPRequestHandler):
    output_dir: ClassVar[Path] = PROJECT_ROOT / "artifacts"

    def do_OPTIONS(self) -> None:
        self.send_response(204)
        self.send_cors_headers()
        self.end_headers()

    def do_POST(self) -> None:
        if self.path != "/dump":
            self.write_json_response(404, {"ok": False, "error": f"Unsupported endpoint; path={self.path}"})
            return
        try:
            payload: JsonObject = read_json_payload(self)
            validate_dump_payload(payload)
            saved_path: Path = save_dump_payload(self.output_dir, payload)
            self.write_json_response(200, {"ok": True, "path": str(saved_path)})
            print(f"Flow saved successfully: {saved_path}")
            print("Hand this JSON file to the AI Wizard before generating a GPMSelenium task script.")
        except Exception as error:
            self.write_json_response(400, {"ok": False, "error": str(error)})

    def send_cors_headers(self) -> None:
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")

    def write_json_response(self, status_code: int, body: JsonObject) -> None:
        response_body: bytes = json.dumps(body, ensure_ascii=False, indent=2).encode("utf-8")
        self.send_response(status_code)
        self.send_cors_headers()
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(response_body)))
        self.end_headers()
        self.wfile.write(response_body)

    def log_message(self, format_string: str, *args: object) -> None:
        logging.info("http_request", extra={"client": self.client_address[0], "message": format_string % args})


def parse_args(arguments: Sequence[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Launch a mock GPM profile with the Record & Flow extension and receive dumps.")
    parser.add_argument("--gpm-url", dest="gpm_url", required=False)
    parser.add_argument("--host", dest="host", required=False)
    parser.add_argument("--port", dest="port", type=int, required=False)
    parser.add_argument("--output-dir", dest="output_dir", required=False)
    parser.add_argument("--extension-dir", dest="extension_dir", required=False)
    parser.add_argument("--window-width", dest="window_width", type=int, required=False)
    parser.add_argument("--window-height", dest="window_height", type=int, required=False)
    parser.add_argument("--window-scale", dest="window_scale", type=float, required=False)
    return parser.parse_args(arguments)


def build_config(namespace: argparse.Namespace) -> ScoutServerConfig:
    return ScoutServerConfig(
        gpm_base_url=string_or_default(namespace.gpm_url, "http://127.0.0.1:19995"),
        host=string_or_default(namespace.host, "127.0.0.1"),
        port=int(namespace.port if namespace.port is not None else 9999),
        output_dir=Path(string_or_default(namespace.output_dir, str(PROJECT_ROOT / "artifacts"))).resolve(),
        extension_dir=Path(string_or_default(namespace.extension_dir, str(PROJECT_ROOT / "extension_record_flow"))).resolve(),
        window_width=int(namespace.window_width if namespace.window_width is not None else 1280),
        window_height=int(namespace.window_height if namespace.window_height is not None else 900),
        window_x=0,
        window_y=0,
        window_scale=float(namespace.window_scale if namespace.window_scale is not None else 0.9),
    )


def string_or_default(value: Any, default_value: str) -> str:
    if value is None:
        return default_value
    text: str = str(value).strip()
    return text if text != "" else default_value


def main(arguments: Sequence[str]) -> NoReturn:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    config: ScoutServerConfig = build_config(parse_args(arguments))
    ensure_extension_dir(config.extension_dir)
    config.output_dir.mkdir(parents=True, exist_ok=True)
    DumpRequestHandler.output_dir = config.output_dir

    server: ThreadingHTTPServer = ThreadingHTTPServer((config.host, config.port), DumpRequestHandler)
    server_thread = threading.Thread(target=server.serve_forever, daemon=True)
    server_thread.start()
    print(f"Record & Flow dump server listening at http://{config.host}:{config.port}/dump")
    print("Use mock data only. Do not record real passwords, seed phrases, private keys, or production user data.")

    session = requests.Session()
    client = GpmClient(config.gpm_base_url, session, 30.0, 3)
    started_profile: StartedScoutProfile | None = None
    try:
        group_keyword: str = prompt_group_keyword()
        selected_group: GpmGroup = select_group(client.list_groups(), group_keyword)
        profiles: list[GpmProfile] = client.list_profiles(1, 500, "", 2, selected_group.group_id)
        selected_profile: GpmProfile = select_profile(profiles)
        started_profile = start_profile_for_scout(client, selected_profile, config)
        print_started_profile(started_profile)
        print("Open the Record & Flow extension popup in the launched GPM profile.")
        print("Press Ctrl+C here when the scouting session is done; the selected GPM profile will be closed.")
        while True:
            threading.Event().wait(3600.0)
    except KeyboardInterrupt:
        print("Stopping scout server...")
    finally:
        if started_profile is not None:
            close_profile(client, started_profile.profile_id)
        server.shutdown()
        server.server_close()
    raise SystemExit(0)


def ensure_extension_dir(extension_dir: Path) -> None:
    manifest_path: Path = extension_dir / "manifest.json"
    if not manifest_path.exists():
        raise FileNotFoundError(f"Record & Flow extension manifest not found; extension_dir={extension_dir}")


def prompt_group_keyword() -> str:
    raw_value: str = input("GPM group keyword [Mock]: ").strip()
    return raw_value if raw_value != "" else "Mock"


def select_group(groups: list[GpmGroup], keyword: str) -> GpmGroup:
    matches: list[GpmGroup] = [group for group in groups if keyword.lower() in group.name.lower()]
    if len(matches) == 0:
        available: str = ", ".join(group.name for group in groups[:20])
        raise ValueError(f"No GPM group matched keyword={keyword}; available_groups={available}")
    if len(matches) == 1:
        print(f"Selected group: {matches[0].name} ({matches[0].group_id})")
        return matches[0]
    print("Matched groups:")
    for index, group in enumerate(matches, start=1):
        print(f"{index}. {group.name} ({group.group_id})")
    selected_index: int = prompt_number("Select group number: ", len(matches))
    return matches[selected_index - 1]


def select_profile(profiles: list[GpmProfile]) -> GpmProfile:
    if len(profiles) == 0:
        raise ValueError("Selected GPM group has no profiles.")
    print("Available mock profiles:")
    for index, profile in enumerate(profiles, start=1):
        print(f"{index}. {profile.name} | {profile.profile_id} | {profile.browser_type} {profile.browser_version}")
    selected_index: int = prompt_number("Select profile number: ", len(profiles))
    return profiles[selected_index - 1]


def prompt_number(prompt: str, max_value: int) -> int:
    while True:
        raw_value: str = input(prompt).strip()
        try:
            selected_number: int = int(raw_value)
        except ValueError:
            print(f"Enter a number from 1 to {max_value}.")
            continue
        if 1 <= selected_number <= max_value:
            return selected_number
        print(f"Enter a number from 1 to {max_value}.")


def start_profile_for_scout(
    client: GpmClient,
    profile: GpmProfile,
    config: ScoutServerConfig,
) -> StartedScoutProfile:
    extension_arg: str = f"--load-extension={config.extension_dir}"
    window_options = GpmWindowOptions(
        size=WindowSize(width=config.window_width, height=config.window_height),
        position=WindowPosition(x=config.window_x, y=config.window_y),
        scale=config.window_scale,
        addination_args=extension_arg,
    )
    started_profile = client.start_profile(profile.profile_id, window_options)
    return StartedScoutProfile(
        profile_id=started_profile.profile_id,
        profile_name=profile.name,
        remote_debugging_address=started_profile.remote_debugging_address,
        driver_path=started_profile.driver_path,
    )


def print_started_profile(profile: StartedScoutProfile) -> None:
    print("GPM profile started for scout:")
    print(f"- Profile: {profile.profile_name} ({profile.profile_id})")
    print(f"- Remote debugging address: {profile.remote_debugging_address}")
    print(f"- Driver path: {profile.driver_path}")


def close_profile(client: GpmClient, profile_id: str) -> None:
    try:
        client.close_profile(profile_id)
        print(f"Closed GPM profile: {profile_id}")
    except Exception as error:
        logging.warning("gpm_close_profile_failed", extra={"profile_id": profile_id, "error": str(error)})


def read_json_payload(handler: BaseHTTPRequestHandler) -> JsonObject:
    raw_length: str | None = handler.headers.get("Content-Length")
    if raw_length is None:
        raise ValueError("Missing Content-Length header.")
    try:
        content_length: int = int(raw_length)
    except ValueError as error:
        raise ValueError(f"Invalid Content-Length header; value={raw_length}") from error
    if content_length <= 0:
        raise ValueError("Request body is empty.")
    if content_length > 25_000_000:
        raise ValueError(f"Request body is too large; bytes={content_length}")
    raw_body: bytes = handler.rfile.read(content_length)
    try:
        parsed_payload: Any = json.loads(raw_body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError(f"Request body is not valid JSON; error={error}") from error
    if not isinstance(parsed_payload, dict):
        raise ValueError("Dump payload must be a JSON object.")
    return parsed_payload


def validate_dump_payload(payload: JsonObject) -> None:
    metadata: Any = payload.get("metadata")
    if not isinstance(metadata, dict):
        raise ValueError("Dump payload missing metadata object.")
    task_name: Any = metadata.get("taskName")
    if not isinstance(task_name, str) or task_name.strip() == "":
        raise ValueError("Dump metadata missing taskName.")
    recorded_steps: Any = payload.get("recordedSteps")
    if not isinstance(recorded_steps, list):
        raise ValueError("Dump payload missing recordedSteps list.")
    unrolled_dom: Any = payload.get("unrolledDOM")
    if not isinstance(unrolled_dom, str):
        raise ValueError("Dump payload missing unrolledDOM string.")
    network_snapshot: Any = payload.get("networkSnapshot")
    if not isinstance(network_snapshot, list):
        raise ValueError("Dump payload missing networkSnapshot list.")


def save_dump_payload(output_dir: Path, payload: JsonObject) -> Path:
    metadata: dict[str, Any] = payload["metadata"]
    task_name: str = safe_filename(str(metadata["taskName"]))
    timestamp: str = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path: Path = output_dir / f"recorded_flow_{task_name}_{timestamp}.json"
    output_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return output_path


def safe_filename(value: str) -> str:
    cleaned: str = re.sub(r"[^a-zA-Z0-9_-]+", "_", value.strip()).strip("_")
    return cleaned if cleaned != "" else "recorded_task"


if __name__ == "__main__":
    main(sys.argv[1:])
