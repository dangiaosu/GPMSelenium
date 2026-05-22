from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from pathlib import Path
from queue import Empty, Queue
from threading import Event, Thread
from typing import Any, Callable

import requests
from selenium.webdriver.remote.webdriver import WebDriver

from gpm_selenium.contracts import ProfileContext, TaskContext, TaskResult
from gpm_selenium.excel import (
    ExcelRow,
    initialize_status_column,
    pending_rows,
    read_excel_rows,
    row_profile_id,
    row_profile_name,
    write_status,
)
from gpm_selenium.gpm import (
    GpmClient,
    GpmWindowOptions,
    WindowPosition,
    WindowSize,
    close_driver,
    create_driver,
)
from gpm_selenium.store import PlatformStore
from gpm_selenium.task_loader import LoadedTask

RunnerCallback = Callable[[str, dict[str, Any]], None]


@dataclass(frozen=True)
class RuntimeConfig:
    gpm_base_url: str
    request_retries: int
    request_timeout_seconds: float
    page_timeout_seconds: float
    node_timeout_seconds: float
    max_workers: int
    delay_between_profiles_seconds: float
    window_width: int
    window_height: int
    window_scale: float
    screen_width: int
    screen_height: int
    window_start_x: int
    window_start_y: int
    window_padding: int
    addination_args: str
    attach_retries: int
    retry_count: int


@dataclass(frozen=True)
class RowRunResult:
    row: ExcelRow
    profile_id: str
    profile_name: str
    success: bool
    status: str
    error: str
    attempt_count: int


StatusWriter = Callable[[RowRunResult], None]


def default_runtime_config() -> RuntimeConfig:
    return RuntimeConfig(
        gpm_base_url="http://127.0.0.1:19995",
        request_retries=3,
        request_timeout_seconds=30.0,
        page_timeout_seconds=60.0,
        node_timeout_seconds=8.0,
        max_workers=3,
        delay_between_profiles_seconds=2.0,
        window_width=800,
        window_height=600,
        window_scale=0.8,
        screen_width=1920,
        screen_height=1080,
        window_start_x=0,
        window_start_y=0,
        window_padding=10,
        addination_args="",
        attach_retries=3,
        retry_count=0,
    )


def run_task_batch(
    store: PlatformStore,
    task_id: int,
    task: LoadedTask,
    excel_path: Path,
    config: RuntimeConfig,
    task_config: dict[str, Any],
    callback: RunnerCallback,
    stop_event: Event,
) -> list[RowRunResult]:
    initialize_status_column(excel_path)
    excel_rows: list[ExcelRow] = read_excel_rows(excel_path, task.required_columns)
    queued_rows: list[ExcelRow] = pending_rows(excel_rows)
    return run_prepared_rows(
        store,
        task_id,
        task,
        str(excel_path),
        queued_rows,
        build_excel_status_writer(excel_path),
        config,
        task_config,
        callback,
        stop_event,
    )


def run_selected_profiles_batch(
    store: PlatformStore,
    task_id: int,
    task: LoadedTask,
    source_label: str,
    rows: list[ExcelRow],
    excel_path: Path | None,
    config: RuntimeConfig,
    task_config: dict[str, Any],
    callback: RunnerCallback,
    stop_event: Event,
) -> list[RowRunResult]:
    status_writer: StatusWriter | None = None
    if excel_path is not None:
        initialize_status_column(excel_path)
        status_writer = build_excel_status_writer(excel_path)
    queued_rows: list[ExcelRow] = pending_rows(rows)
    return run_prepared_rows(
        store,
        task_id,
        task,
        source_label,
        queued_rows,
        status_writer,
        config,
        task_config,
        callback,
        stop_event,
    )


def run_prepared_rows(
    store: PlatformStore,
    task_id: int,
    task: LoadedTask,
    source_label: str,
    queued_rows: list[ExcelRow],
    status_writer: StatusWriter | None,
    config: RuntimeConfig,
    task_config: dict[str, Any],
    callback: RunnerCallback,
    stop_event: Event,
) -> list[RowRunResult]:
    run_id: int = store.create_run(task_id, source_label, runtime_config_to_dict(config))
    callback("run_started", {"run_id": run_id, "pending_rows": len(queued_rows)})

    if len(queued_rows) == 0:
        store.finish_run(run_id, "DONE", 0, 0)
        callback("run_finished", {"run_id": run_id, "success_count": 0, "failure_count": 0})
        return []

    result_queue: Queue[RowRunResult] = Queue()
    work_queue: Queue[ExcelRow] = build_work_queue(queued_rows)
    worker_count: int = min(config.max_workers, len(queued_rows))
    logger: logging.Logger = logging.getLogger("gpm_selenium")

    workers: list[Thread] = [
        Thread(
            target=queue_worker,
            args=(worker_number + 1, work_queue, result_queue, task, config, task_config, logger, run_id, callback, stop_event),
            daemon=True,
        )
        for worker_number in range(worker_count)
    ]
    for worker in workers:
        worker.start()

    results: list[RowRunResult] = []
    success_count: int = 0
    failure_count: int = 0
    while any(worker.is_alive() for worker in workers) or not result_queue.empty():
        try:
            result: RowRunResult = result_queue.get(timeout=0.2)
        except Empty:
            continue
        results.append(result)
        if result.success:
            success_count += 1
        else:
            failure_count += 1
        if status_writer is not None:
            status_writer(result)
        store.add_run_item(
            run_id,
            result.row.row_number,
            result.profile_id,
            result.profile_name,
            result.status,
            result.success,
            result.error,
        )
        callback(
            "row_finished",
            {
                "run_id": run_id,
                "row_number": result.row.row_number,
                "profile_id": result.profile_id,
                "profile_name": result.profile_name,
                "status": result.status,
                "success": result.success,
                "success_count": success_count,
                "failure_count": failure_count,
                "completed_count": len(results),
                "total_count": len(queued_rows),
                "attempt_count": result.attempt_count,
            },
        )

    for worker in workers:
        worker.join()

    if stop_event.is_set():
        final_status: str = "STOPPED"
    else:
        final_status = "DONE" if failure_count == 0 else "DONE_WITH_ERRORS"
    store.finish_run(run_id, final_status, success_count, failure_count)
    callback(
        "run_finished",
        {
            "run_id": run_id,
            "success_count": success_count,
            "failure_count": failure_count,
            "processed_count": len(results),
            "total_count": len(queued_rows),
            "status": final_status,
        },
    )
    return results


def build_excel_status_writer(excel_path: Path) -> StatusWriter:
    def write_excel_status(result: RowRunResult) -> None:
        if result.row.row_number > 0:
            write_status(excel_path, result.row.row_number, result.status)

    return write_excel_status


def build_work_queue(rows: list[ExcelRow]) -> Queue[ExcelRow]:
    work_queue: Queue[ExcelRow] = Queue()
    for row in rows:
        work_queue.put(row)
    return work_queue


def queue_worker(
    worker_number: int,
    work_queue: Queue[ExcelRow],
    result_queue: Queue[RowRunResult],
    task: LoadedTask,
    config: RuntimeConfig,
    task_config: dict[str, Any],
    logger: logging.Logger,
    run_id: int,
    callback: RunnerCallback,
    stop_event: Event,
) -> None:
    while True:
        if stop_event.is_set():
            return
        try:
            row: ExcelRow = work_queue.get_nowait()
        except Empty:
            return
        try:
            result: RowRunResult = process_row(worker_number, row, task, config, task_config, logger, run_id, callback, stop_event)
            result_queue.put(result)
            if not stop_event.is_set():
                time.sleep(config.delay_between_profiles_seconds)
        finally:
            work_queue.task_done()


def process_row(
    worker_number: int,
    row: ExcelRow,
    task: LoadedTask,
    config: RuntimeConfig,
    task_config: dict[str, Any],
    logger: logging.Logger,
    run_id: int,
    callback: RunnerCallback,
    stop_event: Event,
) -> RowRunResult:
    max_attempts: int = config.retry_count + 1
    result: RowRunResult = stopped_row_result(row, 0) if stop_event.is_set() else process_row_attempt(
        worker_number,
        row,
        task,
        config,
        task_config,
        logger,
        run_id,
        stop_event,
        1,
        callback,
    )
    attempt_number: int = 1
    while not result.success and attempt_number < max_attempts and not stop_event.is_set():
        attempt_number += 1
        callback(
            "row_retry",
            {
                "run_id": run_id,
                "row_number": row.row_number,
                "profile_id": result.profile_id,
                "profile_name": result.profile_name,
                "next_attempt": attempt_number,
                "max_attempts": max_attempts,
                "previous_status": result.status,
            },
        )
        time.sleep(config.delay_between_profiles_seconds)
        result = process_row_attempt(
            worker_number,
            row,
            task,
            config,
            task_config,
            logger,
            run_id,
            stop_event,
            attempt_number,
            callback,
        )
    return result


def process_row_attempt(
    worker_number: int,
    row: ExcelRow,
    task: LoadedTask,
    config: RuntimeConfig,
    task_config: dict[str, Any],
    logger: logging.Logger,
    run_id: int,
    stop_event: Event,
    attempt_number: int,
    callback: RunnerCallback,
) -> RowRunResult:
    profile_id: str = row_profile_id(row)
    profile_name: str = row_profile_name(row)
    if stop_event.is_set():
        return stopped_row_result(row, attempt_number)
    session = requests.Session()
    client: GpmClient = GpmClient(config.gpm_base_url, session, config.request_timeout_seconds, config.request_retries)
    driver: WebDriver | None = None
    profile_started: bool = False
    try:
        window_options: GpmWindowOptions = build_window_options(config, worker_number - 1)
        started_profile = client.start_profile(profile_id, window_options)
        profile_started = True
        callback(
            "profile_started",
            {
                "run_id": run_id,
                "row_number": row.row_number,
                "profile_id": profile_id,
                "profile_name": profile_name,
                "attempt_number": attempt_number,
                "worker_number": worker_number,
            },
        )
        driver = create_driver(started_profile, config.attach_retries)
        context: TaskContext = TaskContext(
            driver=driver,
            profile=ProfileContext(profile_id=profile_id, profile_name=profile_name, row_number=row.row_number),
            logger=logger,
            config=task_config,
            artifacts_dir=Path("artifacts") / f"run_{run_id}" / f"row_{row.row_number}",
            timeout_seconds=config.page_timeout_seconds,
            node_timeout_seconds=config.node_timeout_seconds,
            stop_event=stop_event,
        )
        task_result: TaskResult = task.run(context, dict(row.values))
        return RowRunResult(
            row=row,
            profile_id=profile_id,
            profile_name=profile_name,
            success=task_result.success,
            status=task_result.status,
            error=task_result.error or "",
            attempt_count=attempt_number,
        )
    except Exception as error:
        status: str = build_failure_status(error)
        return RowRunResult(
            row=row,
            profile_id=profile_id,
            profile_name=profile_name,
            success=False,
            status=status,
            error=status,
            attempt_count=attempt_number,
        )
    finally:
        if driver is not None:
            close_driver(driver, logger, profile_id)
        if profile_started:
            try:
                client.close_profile(profile_id)
            except Exception as error:
                logger.warning(
                    "gpm_profile_close_failed",
                    extra={"profile_id": profile_id, "error_type": type(error).__name__, "error": str(error)},
                )
            finally:
                callback(
                    "profile_finished",
                    {
                        "run_id": run_id,
                        "row_number": row.row_number,
                        "profile_id": profile_id,
                        "profile_name": profile_name,
                        "attempt_number": attempt_number,
                        "worker_number": worker_number,
                    },
                )


def stopped_row_result(row: ExcelRow, attempt_count: int) -> RowRunResult:
    profile_id: str = row.values.get("ProfileID", "")
    profile_name: str = row.values.get("ProfileName", f"Row {row.row_number}")
    status: str = "STOPPED: Run was stopped before this row started."
    return RowRunResult(
        row=row,
        profile_id=profile_id,
        profile_name=profile_name,
        success=False,
        status=status,
        error=status,
        attempt_count=attempt_count,
    )


def build_failure_status(error: Exception) -> str:
    message: str = str(error).strip()
    return type(error).__name__ if message == "" else f"{type(error).__name__}: {message}"


def build_window_options(config: RuntimeConfig, slot_number: int) -> GpmWindowOptions:
    columns: int = calculate_window_columns(config)
    row_number: int = slot_number // columns
    column_number: int = slot_number % columns
    position: WindowPosition = WindowPosition(
        x=config.window_start_x + column_number * (config.window_width + config.window_padding),
        y=config.window_start_y + row_number * (config.window_height + config.window_padding),
    )
    size: WindowSize = WindowSize(width=config.window_width, height=config.window_height)
    addination_args: str | None = config.addination_args if config.addination_args.strip() != "" else None
    return GpmWindowOptions(size=size, position=position, scale=config.window_scale, addination_args=addination_args)


def calculate_window_columns(config: RuntimeConfig) -> int:
    available_width: int = max(1, config.screen_width - config.window_start_x)
    window_track_width: int = max(1, config.window_width + config.window_padding)
    return max(1, available_width // window_track_width)


def runtime_config_to_dict(config: RuntimeConfig) -> dict[str, Any]:
    return {
        "gpm_base_url": config.gpm_base_url,
        "request_retries": config.request_retries,
        "request_timeout_seconds": config.request_timeout_seconds,
        "page_timeout_seconds": config.page_timeout_seconds,
        "node_timeout_seconds": config.node_timeout_seconds,
        "max_workers": config.max_workers,
        "delay_between_profiles_seconds": config.delay_between_profiles_seconds,
        "window_width": config.window_width,
        "window_height": config.window_height,
        "window_scale": config.window_scale,
        "screen_width": config.screen_width,
        "screen_height": config.screen_height,
        "window_start_x": config.window_start_x,
        "window_start_y": config.window_start_y,
        "window_padding": config.window_padding,
        "addination_args": config.addination_args,
        "attach_retries": config.attach_retries,
        "retry_count": config.retry_count,
    }
