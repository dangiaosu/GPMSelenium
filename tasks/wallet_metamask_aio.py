from __future__ import annotations

from typing import Any

from gpm_selenium.contracts import TaskContext, TaskResult, fail, ok
from tasks.helpers.metamask_lib import (
    backup_ethereum_private_key_flow,
    backup_existing_seed_phrase_flow,
    confirm_seed_phrase,
    create_password,
    extract_wallet_addresses,
    failure_data,
    find_metamask_extension_id,
    finish_onboarding,
    login_existing_wallet_flow,
    open_onboarding,
    open_wallet_home,
    reveal_and_extract_seed,
    start_create_wallet,
    unlock_wallet_if_locked,
)

TASK_NAME = "wallet_metamask_aio"
TASK_VERSION = "1.0.0"
TASK_DESCRIPTION = "Run MetaMask wallet workflows from a GUI-selected action."
REQUIRED_COLUMNS = ["ProfileID", "ProfileName", "Password"]
STATUS_SUCCESS = "SUCCESS"
TASK_ARGUMENTS = [
    {
        "name": "action",
        "label": "Chế độ chạy",
        "type": "dropdown",
        "options": [
            "Create Wallet",
            "Login Only",
            "Backup Seed Phrase",
            "Backup Private Key",
            "Backup Both",
            "Import Wallet",
        ],
        "default": "Create Wallet",
    }
]


def run(context: TaskContext, row: dict[str, object]) -> TaskResult:
    action: str = selected_action(context)
    if action == "Create Wallet":
        return create_wallet(context, row)
    if action == "Login Only":
        return login_wallet(context, row)
    if action == "Backup Seed Phrase":
        return backup_seed_phrase(context, row)
    if action == "Backup Private Key":
        return backup_private_key(context, row)
    if action == "Backup Both":
        return backup_both(context, row)
    if action == "Import Wallet":
        return fail("FAIL_AT_ROUTE_BLOCK", "Import Wallet is not implemented yet.", None)
    return fail("FAIL_AT_ROUTE_BLOCK", f"Unsupported MetaMask action; action={action}", None)


def create_wallet(context: TaskContext, row: dict[str, object]) -> TaskResult:
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


def login_wallet(context: TaskContext, row: dict[str, object]) -> TaskResult:
    password: str = required_value(row, "Password")
    current_block: str = "FIND_EXTENSION_BLOCK"
    data: dict[str, object] = {}
    try:
        current_block = "FIND_EXTENSION_BLOCK"
        extension_id: str = find_metamask_extension_id(context)
        current_block = "OPEN_WALLET_HOME_BLOCK"
        open_wallet_home(context, extension_id)
        current_block = "LOGIN_WALLET_BLOCK"
        data = login_existing_wallet_flow(context, password)
        return ok("SUCCESS", data)
    except Exception as error:
        status: str = f"FAIL_AT_{current_block}: {type(error).__name__}: {error}"
        return fail(status, status, failure_data(context, current_block, data))


def backup_seed_phrase(context: TaskContext, row: dict[str, object]) -> TaskResult:
    password: str = required_value(row, "Password")
    current_block: str = "FIND_EXTENSION_BLOCK"
    data: dict[str, object] = {}
    try:
        current_block = "FIND_EXTENSION_BLOCK"
        extension_id: str = find_metamask_extension_id(context)
        current_block = "OPEN_WALLET_HOME_BLOCK"
        open_wallet_home(context, extension_id)
        current_block = "UNLOCK_EXTENSION_BLOCK"
        unlock_wallet_if_locked(context, password)
        current_block = "BACKUP_SEED_PHRASE_BLOCK"
        data = backup_existing_seed_phrase_flow(context, password)
        return ok("SUCCESS", data)
    except Exception as error:
        status: str = f"FAIL_AT_{current_block}: {type(error).__name__}: {error}"
        return fail(status, status, failure_data(context, current_block, data))


def backup_private_key(context: TaskContext, row: dict[str, object]) -> TaskResult:
    password: str = required_value(row, "Password")
    current_block: str = "FIND_EXTENSION_BLOCK"
    data: dict[str, object] = {}
    try:
        current_block = "FIND_EXTENSION_BLOCK"
        extension_id: str = find_metamask_extension_id(context)
        current_block = "OPEN_WALLET_HOME_BLOCK"
        open_wallet_home(context, extension_id)
        current_block = "UNLOCK_EXTENSION_BLOCK"
        unlock_wallet_if_locked(context, password)
        current_block = "BACKUP_PRIVATE_KEY_BLOCK"
        data = backup_ethereum_private_key_flow(context, password)
        return ok("SUCCESS", data)
    except Exception as error:
        status: str = f"FAIL_AT_{current_block}: {type(error).__name__}: {error}"
        return fail(status, status, failure_data(context, current_block, data))


def backup_both(context: TaskContext, row: dict[str, object]) -> TaskResult:
    password: str = required_value(row, "Password")
    current_block: str = "FIND_EXTENSION_BLOCK"
    data: dict[str, object] = {}
    try:
        current_block = "FIND_EXTENSION_BLOCK"
        extension_id: str = find_metamask_extension_id(context)
        current_block = "OPEN_WALLET_HOME_BLOCK"
        open_wallet_home(context, extension_id)
        current_block = "UNLOCK_EXTENSION_BLOCK"
        unlock_wallet_if_locked(context, password)
        current_block = "BACKUP_SEED_PHRASE_BLOCK"
        seed_data: dict[str, str] = backup_existing_seed_phrase_flow(context, password)
        data.update(seed_data)
        current_block = "OPEN_WALLET_HOME_FOR_PRIVATE_KEY_BLOCK"
        open_wallet_home(context, extension_id)
        current_block = "BACKUP_PRIVATE_KEY_BLOCK"
        private_key_data: dict[str, str] = backup_ethereum_private_key_flow(context, password)
        data.update(private_key_data)
        data["BackupMode"] = "RevealSeedPhraseAndEthereumPrivateKey"
        return ok("SUCCESS", data)
    except Exception as error:
        status: str = f"FAIL_AT_{current_block}: {type(error).__name__}: {error}"
        return fail(status, status, failure_data(context, current_block, data))


def selected_action(context: TaskContext) -> str:
    raw_task_args: Any = context.config.get("task_args")
    if not isinstance(raw_task_args, dict):
        return "Create Wallet"
    raw_action: Any = raw_task_args.get("action")
    action: str = "" if raw_action is None else str(raw_action).strip()
    return action if action != "" else "Create Wallet"


def required_value(row: dict[str, object], column_name: str) -> str:
    raw_value: Any = row.get(column_name)
    value: str = "" if raw_value is None else str(raw_value).strip()
    if value == "":
        raise ValueError(f"Row missing required value; column_name={column_name}")
    return value
