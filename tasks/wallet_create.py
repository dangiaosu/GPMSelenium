from __future__ import annotations

from typing import Any

from gpm_selenium.contracts import TaskContext, TaskResult, fail, ok
from tasks.helpers.metamask_lib import (
    confirm_seed_phrase,
    create_password,
    extract_wallet_addresses,
    failure_data,
    find_metamask_extension_id,
    finish_onboarding,
    open_onboarding,
    reveal_and_extract_seed,
    start_create_wallet,
    unlock_wallet_if_locked,
)

TASK_NAME = "wallet_create"
TASK_VERSION = "1.0.0"
TASK_DESCRIPTION = "Create a new MetaMask wallet and return the Secret Recovery Phrase."
REQUIRED_COLUMNS = ["ProfileID", "ProfileName", "Password"]
STATUS_SUCCESS = "SUCCESS"


def run(context: TaskContext, row: dict[str, object]) -> TaskResult:
    password: str = required_value(row, "Password")
    current_block: str = "FIND_EXTENSION_BLOCK"
    seed_words: list[str] = []
    addresses: dict[str, str] = {}
    try:
        current_block = "FIND_EXTENSION_BLOCK"
        extension_id: str = find_metamask_extension_id(context)
        current_block = "OPEN_ONBOARDING_BLOCK"
        open_onboarding(context, extension_id)
        current_block = "START_CREATE_BLOCK"
        start_create_wallet(context)
        current_block = "CREATE_PASSWORD_BLOCK"
        create_password(context, password)
        current_block = "SAVE_SEED_BLOCK"
        seed_words = reveal_and_extract_seed(context)
        current_block = "CONFIRM_SEED_BLOCK"
        confirm_seed_phrase(context, seed_words)
        current_block = "FINISH_ONBOARDING_BLOCK"
        finish_onboarding(context)
        current_block = "UNLOCK_EXTENSION_BLOCK"
        unlock_wallet_if_locked(context, password)
        current_block = "EXTRACT_ADDRESSES_BLOCK"
        addresses = extract_wallet_addresses(context)
        return ok("SUCCESS", {"SeedPhrase": " ".join(seed_words), **addresses})
    except Exception as error:
        status: str = f"FAIL_AT_{current_block}: {type(error).__name__}: {error}"
        data: dict[str, object] = {"SeedPhrase": " ".join(seed_words), **addresses}
        return fail(status, status, failure_data(context, current_block, data))


def required_value(row: dict[str, object], column_name: str) -> str:
    raw_value: Any = row.get(column_name)
    value: str = "" if raw_value is None else str(raw_value).strip()
    if value == "":
        raise ValueError(f"Row missing required value; column_name={column_name}")
    return value
