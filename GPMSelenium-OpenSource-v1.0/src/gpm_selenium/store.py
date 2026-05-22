from __future__ import annotations

import json
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class RegisteredTask:
    id: int
    name: str
    version: str
    module_path: str
    description: str
    required_columns: list[str]


class PlatformStore:
    def __init__(self, db_path: Path) -> None:
        self._db_path: Path = db_path
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def register_task(
        self,
        name: str,
        version: str,
        module_path: Path,
        description: str,
        required_columns: list[str],
    ) -> int:
        with self._connection() as connection:
            cursor = connection.execute(
                """
                insert into tasks(name, version, module_path, description, required_columns, enabled)
                values (?, ?, ?, ?, ?, 1)
                on conflict(name, version) do update set
                    module_path = excluded.module_path,
                    description = excluded.description,
                    required_columns = excluded.required_columns,
                    enabled = 1
                """,
                (name, version, str(module_path), description, json.dumps(required_columns)),
            )
            row = connection.execute(
                "select id from tasks where name = ? and version = ?",
                (name, version),
            ).fetchone()
            return int(row["id"]) if row is not None else int(cursor.lastrowid)

    def list_tasks(self) -> list[RegisteredTask]:
        with self._connection() as connection:
            rows = connection.execute(
                "select id, name, version, module_path, description, required_columns from tasks where enabled = 1 order by name"
            ).fetchall()
        return [self._registered_task_from_row(row) for row in rows]

    def get_task(self, task_id: int) -> RegisteredTask:
        with self._connection() as connection:
            row = connection.execute(
                "select id, name, version, module_path, description, required_columns from tasks where id = ?",
                (task_id,),
            ).fetchone()
        if row is None:
            raise ValueError(f"Task not found; task_id={task_id}")
        return self._registered_task_from_row(row)

    def create_run(self, task_id: int, excel_path: str | Path, config: dict[str, Any]) -> int:
        with self._connection() as connection:
            cursor = connection.execute(
                "insert into runs(task_id, excel_path, started_at, status, config_json) values (?, ?, datetime('now'), ?, ?)",
                (task_id, str(excel_path), "RUNNING", json.dumps(config)),
            )
            return int(cursor.lastrowid)

    def finish_run(self, run_id: int, status: str, success_count: int, failure_count: int) -> None:
        with self._connection() as connection:
            connection.execute(
                """
                update runs
                set finished_at = datetime('now'), status = ?, success_count = ?, failure_count = ?
                where id = ?
                """,
                (status, success_count, failure_count, run_id),
            )

    def add_run_item(
        self,
        run_id: int,
        row_number: int,
        profile_id: str,
        profile_name: str,
        status: str,
        success: bool,
        error: str,
    ) -> None:
        with self._connection() as connection:
            connection.execute(
                """
                insert into run_items(run_id, row_number, profile_id, profile_name, status, success, error, finished_at)
                values (?, ?, ?, ?, ?, ?, ?, datetime('now'))
                """,
                (run_id, row_number, profile_id, profile_name, status, 1 if success else 0, error),
            )

    def list_runs(self) -> list[dict[str, Any]]:
        with self._connection() as connection:
            rows = connection.execute(
                """
                select runs.id, tasks.name as task_name, tasks.version, runs.excel_path, runs.started_at,
                       runs.finished_at, runs.status, runs.success_count, runs.failure_count
                from runs
                join tasks on tasks.id = runs.task_id
                order by runs.id desc
                limit 100
                """
            ).fetchall()
        return [dict(row) for row in rows]

    def log(self, run_id: int | None, level: str, message: str, context: dict[str, Any]) -> None:
        with self._connection() as connection:
            connection.execute(
                "insert into logs(run_id, created_at, level, message, context_json) values (?, datetime('now'), ?, ?, ?)",
                (run_id, level, message, json.dumps(context)),
            )

    def _initialize(self) -> None:
        with self._connection() as connection:
            connection.executescript(
                """
                create table if not exists tasks (
                    id integer primary key autoincrement,
                    name text not null,
                    version text not null,
                    module_path text not null,
                    description text not null,
                    required_columns text not null,
                    enabled integer not null,
                    unique(name, version)
                );

                create table if not exists runs (
                    id integer primary key autoincrement,
                    task_id integer not null,
                    excel_path text not null,
                    started_at text not null,
                    finished_at text,
                    status text not null,
                    success_count integer not null default 0,
                    failure_count integer not null default 0,
                    config_json text not null,
                    foreign key(task_id) references tasks(id)
                );

                create table if not exists run_items (
                    id integer primary key autoincrement,
                    run_id integer not null,
                    row_number integer not null,
                    profile_id text not null,
                    profile_name text not null,
                    status text not null,
                    success integer not null,
                    error text not null,
                    finished_at text not null,
                    foreign key(run_id) references runs(id)
                );

                create table if not exists logs (
                    id integer primary key autoincrement,
                    run_id integer,
                    created_at text not null,
                    level text not null,
                    message text not null,
                    context_json text not null,
                    foreign key(run_id) references runs(id)
                );
                """
            )

    @contextmanager
    def _connection(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self._db_path)
        connection.row_factory = sqlite3.Row
        try:
            yield connection
            connection.commit()
        finally:
            connection.close()

    def _registered_task_from_row(self, row: sqlite3.Row) -> RegisteredTask:
        required_columns: list[str] = json.loads(str(row["required_columns"]))
        return RegisteredTask(
            id=int(row["id"]),
            name=str(row["name"]),
            version=str(row["version"]),
            module_path=str(row["module_path"]),
            description=str(row["description"]),
            required_columns=required_columns,
        )
