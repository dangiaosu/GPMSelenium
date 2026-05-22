from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from gpm_selenium.excel import ExcelRow, pending_rows, read_excel_rows
from gpm_selenium.gpm import GpmProfile

PROFILE_COLUMNS: set[str] = {"ProfileID", "ProfileName"}


class ProfileRowError(ValueError):
    pass


@dataclass(frozen=True)
class ProfileRowsPreview:
    selected_profiles: int
    matched_excel_rows: int
    pending_rows: int
    skipped_rows: int
    missing_data_columns: list[str]


def build_rows_from_profiles(
    profiles: list[GpmProfile],
    required_columns: list[str],
    excel_path: Path | None,
) -> list[ExcelRow]:
    if len(profiles) == 0:
        raise ProfileRowError("Select at least one GPM profile before starting a profile-based run.")
    if excel_path is None:
        ensure_profile_only_columns(required_columns)
        return [profile_to_row(index + 1, profile, "", {}) for index, profile in enumerate(profiles)]

    excel_rows: list[ExcelRow] = read_excel_rows(excel_path, required_columns)
    rows_by_profile_id: dict[str, ExcelRow] = {
        row.values.get("ProfileID", "").strip(): row for row in excel_rows if row.values.get("ProfileID", "").strip() != ""
    }
    rows_by_profile_name: dict[str, ExcelRow] = {
        row.values.get("ProfileName", "").strip(): row
        for row in excel_rows
        if row.values.get("ProfileName", "").strip() != ""
    }

    built_rows: list[ExcelRow] = []
    for index, profile in enumerate(profiles):
        matched_row: ExcelRow | None = rows_by_profile_id.get(profile.profile_id)
        if matched_row is None and profile.name != "":
            matched_row = rows_by_profile_name.get(profile.name)
        if matched_row is None:
            ensure_profile_only_columns(required_columns)
            built_rows.append(profile_to_row(0, profile, "", {}))
        else:
            built_rows.append(profile_to_row(matched_row.row_number, profile, matched_row.status, matched_row.values))
    return built_rows


def preview_rows_from_profiles(
    profiles: list[GpmProfile],
    required_columns: list[str],
    excel_path: Path | None,
) -> ProfileRowsPreview:
    rows: list[ExcelRow] = build_rows_from_profiles(profiles, required_columns, excel_path)
    matched_excel_rows: int = len([row for row in rows if row.row_number > 0 and excel_path is not None])
    queued_rows: list[ExcelRow] = pending_rows(rows)
    missing_data_columns: list[str] = [
        column_name for column_name in required_columns if column_name not in PROFILE_COLUMNS and excel_path is None
    ]
    return ProfileRowsPreview(
        selected_profiles=len(profiles),
        matched_excel_rows=matched_excel_rows,
        pending_rows=len(queued_rows),
        skipped_rows=len(rows) - len(queued_rows),
        missing_data_columns=missing_data_columns,
    )


def ensure_profile_only_columns(required_columns: list[str]) -> None:
    missing_data_columns: list[str] = [column_name for column_name in required_columns if column_name not in PROFILE_COLUMNS]
    if len(missing_data_columns) > 0:
        raise ProfileRowError(
            "Excel data is required for this task; missing task columns from selected profiles only: "
            f"{missing_data_columns}"
        )


def profile_to_row(row_number: int, profile: GpmProfile, status: str, values: dict[str, str]) -> ExcelRow:
    merged_values: dict[str, str] = dict(values)
    merged_values["ProfileID"] = profile.profile_id
    merged_values["ProfileName"] = profile.name
    return ExcelRow(row_number=row_number, values=merged_values, status=status)
