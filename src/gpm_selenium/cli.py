from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path
from threading import Event
from typing import Any, NoReturn, Sequence

from gpm_selenium.excel import preview_excel
from gpm_selenium.runner import RuntimeConfig, default_runtime_config, run_task_batch
from gpm_selenium.store import PlatformStore
from gpm_selenium.task_loader import LoadedTask, load_task


def parse_args(arguments: Sequence[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="gpm-selenium", description="Run AI-code Selenium tasks on GPMLogin profiles.")
    parser.add_argument("--task-path", required=True, help="Path to Python task module.")
    parser.add_argument("--excel-path", required=True, help="Path to Excel input/output file.")
    parser.add_argument("--db-path", default="gpm_selenium.sqlite3", help="SQLite platform database path.")
    parser.add_argument("--max-workers", type=int, default=3, help="Number of GPM profiles to run at once.")
    parser.add_argument("--window-width", type=int, default=800)
    parser.add_argument("--window-height", type=int, default=600)
    parser.add_argument("--window-scale", type=float, default=0.8)
    parser.add_argument("--node-timeout-seconds", type=float, default=8.0, help="Fail a selector/node step after this many seconds.")
    parser.add_argument("--retry-count", type=int, default=0, help="Retry failed rows this many times before writing status.")
    parser.add_argument("--enable-debug-artifacts", action="store_true", help="Save task screenshots/HTML on failure.")
    return parser.parse_args(arguments)


def main(arguments: Sequence[str] | None = None) -> NoReturn:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    namespace = parse_args(arguments if arguments is not None else sys.argv[1:])
    task: LoadedTask = load_task(Path(namespace.task_path))
    excel_path = Path(namespace.excel_path)
    preview = preview_excel(excel_path, task.required_columns)
    if len(preview.missing_columns) > 0:
        raise SystemExit(f"Missing Excel columns: {preview.missing_columns}")
    config: RuntimeConfig = default_runtime_config()
    config = RuntimeConfig(
        gpm_base_url=config.gpm_base_url,
        request_retries=config.request_retries,
        request_timeout_seconds=config.request_timeout_seconds,
        page_timeout_seconds=config.page_timeout_seconds,
        node_timeout_seconds=float(namespace.node_timeout_seconds),
        max_workers=int(namespace.max_workers),
        delay_between_profiles_seconds=config.delay_between_profiles_seconds,
        window_width=int(namespace.window_width),
        window_height=int(namespace.window_height),
        window_scale=float(namespace.window_scale),
        screen_width=config.screen_width,
        screen_height=config.screen_height,
        window_start_x=config.window_start_x,
        window_start_y=config.window_start_y,
        window_padding=config.window_padding,
        addination_args=config.addination_args,
        attach_retries=config.attach_retries,
        retry_count=int(namespace.retry_count),
    )
    store = PlatformStore(Path(namespace.db_path))
    task_id = store.register_task(
        task.name,
        task.version,
        task.module_path,
        task.description,
        task.required_columns,
        task.arguments,
    )
    task_config: dict[str, Any] = {"enable_debug_artifacts": bool(namespace.enable_debug_artifacts)}
    run_task_batch(store, task_id, task, excel_path, config, task_config, print_event, Event())
    raise SystemExit(0)


def print_event(event_name: str, payload: dict[str, object]) -> None:
    message: str = f"{event_name}: {payload}\n"
    sys.stdout.buffer.write(message.encode("utf-8", errors="replace"))
    sys.stdout.flush()
