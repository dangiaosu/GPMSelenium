from __future__ import annotations

import json
import logging
import sys
import time
from pathlib import Path
from threading import Event

import requests

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
for import_path in (PROJECT_ROOT, SRC_ROOT):
    import_path_text: str = str(import_path)
    if import_path_text not in sys.path:
        sys.path.insert(0, import_path_text)

from gpm_selenium.contracts import ProfileContext, TaskContext
from gpm_selenium.gpm import GpmClient, GpmWindowOptions, WindowPosition, WindowSize, create_driver
from tasks.helpers.metamask_lib import find_metamask_extension_id, open_wallet_home, unlock_wallet_if_locked

GPM_BASE_URL = "http://127.0.0.1:19995"
MOCK_PROFILE_ID = "53236602-6685-4415-b686-3cf09647aac8"
MOCK_PROFILE_NAME = "mock-metamask"
MOCK_PASSWORD = "MockPassword123!"
SESSION_PATH = Path("artifacts") / "metamask_live_session.json"


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    logger: logging.Logger = logging.getLogger("metamask_live_scout")
    client = GpmClient(GPM_BASE_URL, requests.Session(), 30.0, 3)
    driver = None
    try:
        started_profile = client.start_profile(
            MOCK_PROFILE_ID,
            GpmWindowOptions(
                size=WindowSize(width=900, height=720),
                position=WindowPosition(x=0, y=0),
                scale=0.8,
                addination_args=None,
            ),
        )
        driver = create_driver(started_profile, 3)
        context = TaskContext(
            driver=driver,
            profile=ProfileContext(profile_id=MOCK_PROFILE_ID, profile_name=MOCK_PROFILE_NAME, row_number=2),
            logger=logger,
            config={"enable_debug_artifacts": False, "task_args": {"action": "Login Only"}},
            artifacts_dir=Path("artifacts"),
            timeout_seconds=45.0,
            node_timeout_seconds=15.0,
            stop_event=Event(),
        )
        extension_id: str = find_metamask_extension_id(context)
        open_wallet_home(context, extension_id)
        unlock_wallet_if_locked(context, MOCK_PASSWORD)
        write_session(started_profile.remote_debugging_address, extension_id)
        print("metamask_live_scout_ready")
        print(f"profile_id={MOCK_PROFILE_ID}")
        print(f"extension_id={extension_id}")
        print(f"remote_debugging_address={started_profile.remote_debugging_address}")
        print(f"session_path={SESSION_PATH.resolve()}")
        print("Keep this window open while scouting. Press Ctrl+C here to close the mock profile.")
        while True:
            time.sleep(1.0)
    except KeyboardInterrupt:
        print("metamask_live_scout_stopping")
    finally:
        if driver is not None:
            driver.quit()
        client.close_profile(MOCK_PROFILE_ID)
        print("mock_profile_closed")


def write_session(remote_debugging_address: str, extension_id: str) -> None:
    SESSION_PATH.parent.mkdir(parents=True, exist_ok=True)
    SESSION_PATH.write_text(
        json.dumps(
            {
                "profile_id": MOCK_PROFILE_ID,
                "remote_debugging_address": remote_debugging_address,
                "extension_id": extension_id,
            },
            indent=2,
        ),
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
