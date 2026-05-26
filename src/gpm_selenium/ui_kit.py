from __future__ import annotations

HEADER_SIDE_WIDTH: int = 156


def run_status_display_text(status: str) -> str:
    normalized_status: str = status.strip().upper()
    status_labels: dict[str, str] = {
        "DONE_WITH_ERRORS": "Done + errors",
        "DONE": "Done",
        "STOPPED": "Stopped",
        "RUNNING": "Running",
        "STOPPING": "Stopping",
        "RETRYING": "Retrying",
        "ERROR": "Error",
        "IDLE": "Idle",
    }
    return status_labels.get(normalized_status, status.strip() if status.strip() != "" else "Idle")
