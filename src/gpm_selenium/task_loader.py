from __future__ import annotations

import importlib.util
from dataclasses import dataclass
from pathlib import Path
from types import ModuleType
from typing import Any, Callable

from gpm_selenium.contracts import TaskContext, TaskResult

TaskRunCallable = Callable[[TaskContext, dict[str, object]], TaskResult]


class TaskLoadError(ValueError):
    pass


@dataclass(frozen=True)
class LoadedTask:
    module_path: Path
    name: str
    version: str
    description: str
    required_columns: list[str]
    arguments: list[dict[str, Any]]
    success_status: str
    run: TaskRunCallable


def load_task(module_path: Path) -> LoadedTask:
    if not module_path.exists():
        raise TaskLoadError(f"Task module does not exist; module_path={module_path}")
    module: ModuleType = import_module_from_path(module_path)
    name: str = read_required_string(module, "TASK_NAME", module_path)
    version: str = read_required_string(module, "TASK_VERSION", module_path)
    description: str = read_optional_string(module, "TASK_DESCRIPTION")
    success_status: str = read_optional_string(module, "STATUS_SUCCESS") or "OKIE"
    required_columns: list[str] = read_required_columns(module, module_path)
    arguments: list[dict[str, Any]] = read_task_arguments(module, module_path)
    if "ProfileID" not in required_columns:
        required_columns = ["ProfileID", *required_columns]
    run_attribute: Any = getattr(module, "run", None)
    if not callable(run_attribute):
        raise TaskLoadError(f"Task module must export callable run(context, row); module_path={module_path}")
    return LoadedTask(
        module_path=module_path,
        name=name,
        version=version,
        description=description,
        required_columns=required_columns,
        arguments=arguments,
        success_status=success_status,
        run=run_attribute,
    )


def import_module_from_path(module_path: Path) -> ModuleType:
    module_name: str = f"gpm_selenium_task_{abs(hash(str(module_path.resolve())))}"
    spec = importlib.util.spec_from_file_location(module_name, module_path)
    if spec is None or spec.loader is None:
        raise TaskLoadError(f"Could not create import spec for task module; module_path={module_path}")
    module: ModuleType = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def read_required_string(module: ModuleType, attribute_name: str, module_path: Path) -> str:
    raw_value: Any = getattr(module, attribute_name, None)
    if not isinstance(raw_value, str) or raw_value.strip() == "":
        raise TaskLoadError(f"Task module missing string {attribute_name}; module_path={module_path}")
    return raw_value.strip()


def read_optional_string(module: ModuleType, attribute_name: str) -> str:
    raw_value: Any = getattr(module, attribute_name, "")
    return raw_value.strip() if isinstance(raw_value, str) else ""


def read_required_columns(module: ModuleType, module_path: Path) -> list[str]:
    raw_value: Any = getattr(module, "REQUIRED_COLUMNS", None)
    if not isinstance(raw_value, list) or len(raw_value) == 0:
        raise TaskLoadError(f"Task module missing REQUIRED_COLUMNS list; module_path={module_path}")
    columns: list[str] = []
    for item in raw_value:
        if not isinstance(item, str) or item.strip() == "":
            raise TaskLoadError(f"Task module REQUIRED_COLUMNS must contain only strings; module_path={module_path}")
        columns.append(item.strip())
    return columns


def read_task_arguments(module: ModuleType, module_path: Path) -> list[dict[str, Any]]:
    raw_value: Any = getattr(module, "TASK_ARGUMENTS", [])
    if raw_value is None:
        return []
    if not isinstance(raw_value, list):
        raise TaskLoadError(f"Task module TASK_ARGUMENTS must be a list of dictionaries; module_path={module_path}")
    arguments: list[dict[str, Any]] = []
    for item in raw_value:
        if not isinstance(item, dict):
            raise TaskLoadError(f"Task module TASK_ARGUMENTS must contain only dictionaries; module_path={module_path}")
        raw_name: Any = item.get("name")
        raw_type: Any = item.get("type")
        if not isinstance(raw_name, str) or raw_name.strip() == "":
            raise TaskLoadError(f"Task argument missing string name; module_path={module_path}")
        if not isinstance(raw_type, str) or raw_type.strip() == "":
            raise TaskLoadError(f"Task argument missing string type; argument_name={raw_name}; module_path={module_path}")
        arguments.append(dict(item))
    return arguments
