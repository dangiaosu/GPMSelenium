from __future__ import annotations

import ctypes
import logging
import time
from ctypes import wintypes
from dataclasses import dataclass, replace
from pathlib import Path
from queue import Empty, Queue
from threading import Event, Thread
from typing import Any, Callable

import requests
from selenium.common.exceptions import WebDriverException
from selenium.webdriver.remote.webdriver import WebDriver

from gpm_selenium.contracts import ProfileContext, TaskContext, TaskResult
from gpm_selenium.excel import (
    ExcelDataError,
    ExcelRow,
    initialize_status_column,
    pending_rows,
    read_excel_rows,
    row_profile_id,
    row_profile_name,
    write_result_data,
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
class ScreenWorkArea:
    x: int
    y: int
    width: int
    height: int


@dataclass(frozen=True)
class WindowLayout:
    columns: int
    rows: int
    window_width: int
    window_height: int


@dataclass(frozen=True)
class RowRunResult:
    row: ExcelRow
    profile_id: str
    profile_name: str
    success: bool
    status: str
    error: str
    attempt_count: int
    data: dict[str, Any] | None


StatusWriter = Callable[[RowRunResult], None]


def default_runtime_config() -> RuntimeConfig:
    screen: ScreenWorkArea = detect_primary_screen_work_area()
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
        screen_width=screen.width,
        screen_height=screen.height,
        window_start_x=screen.x,
        window_start_y=screen.y,
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
        excel_path,
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
        excel_path,
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
    excel_path: Path | None,
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
        persisted_result: RowRunResult = persist_row_result(excel_path, status_writer, result)
        results.append(persisted_result)
        if persisted_result.success:
            success_count += 1
        else:
            failure_count += 1
        store.add_run_item(
            run_id,
            persisted_result.row.row_number,
            persisted_result.profile_id,
            persisted_result.profile_name,
            persisted_result.status,
            persisted_result.success,
            persisted_result.error,
        )
        callback(
            "row_finished",
            {
                "run_id": run_id,
                "row_number": persisted_result.row.row_number,
                "profile_id": persisted_result.profile_id,
                "profile_name": persisted_result.profile_name,
                "status": persisted_result.status,
                "success": persisted_result.success,
                "error": persisted_result.error,
                "success_count": success_count,
                "failure_count": failure_count,
                "completed_count": len(results),
                "total_count": len(queued_rows),
                "attempt_count": persisted_result.attempt_count,
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


def persist_row_result(
    excel_path: Path | None,
    status_writer: StatusWriter | None,
    result: RowRunResult,
) -> RowRunResult:
    if status_writer is None:
        return result
    try:
        if excel_path is not None and result.success and result.data is not None and len(result.data) > 0:
            write_result_data(excel_path, result.row.row_number, result.data)
        status_writer(result)
        return result
    except ExcelDataError as error:
        status: str = f"ExcelDataError: {error}"
        return replace(result, success=False, status=status, error=status)


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
    context: TaskContext | None = None
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
        context_config: dict[str, Any] = {
            **task_config,
            "page_timeout_seconds": config.page_timeout_seconds,
            "node_timeout_seconds": config.node_timeout_seconds,
        }
        context = TaskContext(
            driver=driver,
            profile=ProfileContext(profile_id=profile_id, profile_name=profile_name, row_number=row.row_number),
            logger=logger,
            config=context_config,
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
            data=task_result.data,
        )
    except RuntimeError as error:
        if context is None:
            status: str = build_failure_status(error)
            return RowRunResult(
                row=row,
                profile_id=profile_id,
                profile_name=profile_name,
                success=False,
                status=status,
                error=status,
                attempt_count=attempt_number,
                data=None,
            )
        business_error_message: str = str(error).strip() if str(error).strip() != "" else type(error).__name__
        logger.warning(
            "task_business_error",
            extra={
                "profile_id": profile_id,
                "profile_name": profile_name,
                "row_number": row.row_number,
                "attempt_number": attempt_number,
                "error_type": type(error).__name__,
                "error": business_error_message,
            },
        )
        callback(
            "business_error",
            {
                "run_id": run_id,
                "row_number": row.row_number,
                "profile_id": profile_id,
                "profile_name": profile_name,
                "attempt_number": attempt_number,
                "error": business_error_message,
            },
        )
        return RowRunResult(
            row=row,
            profile_id=profile_id,
            profile_name=profile_name,
            success=False,
            status="FAILED",
            error=business_error_message,
            attempt_count=attempt_number,
            data=business_error_data(context, error),
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
            data=None,
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
        data=None,
    )


def build_failure_status(error: Exception) -> str:
    message: str = str(error).strip()
    return type(error).__name__ if message == "" else f"{type(error).__name__}: {message}"


def business_error_data(context: TaskContext, error: RuntimeError) -> dict[str, Any]:
    data: dict[str, Any] = {
        "error_type": type(error).__name__,
        "error": str(error),
        "url": context.driver.current_url,
    }
    try:
        screenshot_path: Path | None = context.screenshot(f"business_error_{context.profile.profile_id}")
        if screenshot_path is not None:
            data["screenshot"] = str(screenshot_path)
    except WebDriverException as screenshot_error:
        data["screenshot_error"] = f"{type(screenshot_error).__name__}: {screenshot_error}"
    try:
        html_path: Path | None = context.save_html(f"business_error_{context.profile.profile_id}")
        if html_path is not None:
            data["html"] = str(html_path)
    except (OSError, WebDriverException) as html_error:
        data["html_error"] = f"{type(html_error).__name__}: {html_error}"
    return data


def build_window_options(config: RuntimeConfig, slot_number: int) -> GpmWindowOptions:
    layout: WindowLayout = calculate_window_layout(config)
    row_number: int = slot_number // layout.columns
    column_number: int = slot_number % layout.columns
    position: WindowPosition = WindowPosition(
        x=config.window_start_x + column_number * (layout.window_width + config.window_padding),
        y=config.window_start_y + row_number * (layout.window_height + config.window_padding),
    )
    size: WindowSize = WindowSize(width=layout.window_width, height=layout.window_height)
    addination_args: str | None = config.addination_args if config.addination_args.strip() != "" else None
    return GpmWindowOptions(size=size, position=position, scale=config.window_scale, addination_args=addination_args)


def calculate_window_columns(config: RuntimeConfig) -> int:
    return calculate_window_layout(config).columns


def calculate_window_layout(config: RuntimeConfig) -> WindowLayout:
    worker_count: int = max(1, config.max_workers)
    padding: int = max(0, config.window_padding)
    available_width: int = max(1, config.screen_width)
    available_height: int = max(1, config.screen_height)
    preferred_width: int = max(1, config.window_width)
    preferred_height: int = max(1, config.window_height)
    best_layout: WindowLayout | None = None
    best_score: tuple[int, int, int, int, int] | None = None
    for columns in range(1, worker_count + 1):
        rows: int = ceil_div(worker_count, columns)
        cell_width: int = (available_width - padding * (columns - 1)) // columns
        cell_height: int = (available_height - padding * (rows - 1)) // rows
        if cell_width <= 0 or cell_height <= 0:
            continue
        window_width: int = min(preferred_width, cell_width)
        window_height: int = min(preferred_height, cell_height)
        preferred_fit: int = 1 if window_width == preferred_width and window_height == preferred_height else 0
        area: int = window_width * window_height
        score: tuple[int, int, int, int, int] = (preferred_fit, area, -rows, columns, window_width)
        if best_score is None or score > best_score:
            best_score = score
            best_layout = WindowLayout(columns=columns, rows=rows, window_width=window_width, window_height=window_height)
    if best_layout is None:
        raise RuntimeError(
            "Unable to calculate GPM window layout; "
            f"screen_width={config.screen_width}; screen_height={config.screen_height}; "
            f"max_workers={config.max_workers}; window_padding={config.window_padding}"
        )
    return best_layout


def ceil_div(value: int, divisor: int) -> int:
    if divisor <= 0:
        raise ValueError(f"Divisor must be greater than zero; divisor={divisor}")
    return -(-value // divisor)


def detect_primary_screen_work_area() -> ScreenWorkArea:
    if not hasattr(ctypes, "windll"):
        raise RuntimeError("Primary screen work area detection requires Windows.")
    rect = wintypes.RECT()
    spi_getworkarea: int = 48
    result: int = ctypes.windll.user32.SystemParametersInfoW(spi_getworkarea, 0, ctypes.byref(rect), 0)
    if result == 0:
        raise RuntimeError("Windows SystemParametersInfoW failed while reading primary screen work area.")
    width: int = int(rect.right - rect.left)
    height: int = int(rect.bottom - rect.top)
    if width <= 0 or height <= 0:
        raise RuntimeError(
            "Windows primary screen work area is invalid; "
            f"left={rect.left}; top={rect.top}; right={rect.right}; bottom={rect.bottom}"
        )
    return ScreenWorkArea(x=int(rect.left), y=int(rect.top), width=width, height=height)


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
