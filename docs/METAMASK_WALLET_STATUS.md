# MetaMask Wallet Automation Status For AI IDE

File này ghi trạng thái hiện tại của MetaMask automation trong GPMSelenium và phần còn thiếu cần làm tiếp.

## Source Files

```text
tasks/helpers/metamask_lib.py
tasks/wallet_create.py
tasks/wallet_metamask_aio.py
docs/WALLET_LIB_BEST_PRACTICES.md
```

## Current Implemented Features

### Create Wallet

Implemented in:

```text
tasks/helpers/metamask_lib.py
tasks/wallet_create.py
tasks/wallet_metamask_aio.py
```

Current block flow:

```text
FIND_EXTENSION_BLOCK
OPEN_ONBOARDING_BLOCK
START_CREATE_BLOCK
CREATE_PASSWORD_BLOCK
SAVE_SEED_BLOCK
CONFIRM_SEED_BLOCK
FINISH_ONBOARDING_BLOCK
UNLOCK_EXTENSION_BLOCK
EXTRACT_ADDRESSES_BLOCK
```

Current output data:

```python
{
    "SeedPhrase": "...",
    "Address": evm_address,
    "EvmAddress": evm_address,
    "SolanaAddress": solana_address,
}
```

Runtime writes these keys back to Excel through `write_result_data(...)`.

### Login Only

Implemented in:

```text
tasks/helpers/metamask_lib.py
tasks/wallet_metamask_aio.py
```

Current block flow:

```text
FIND_EXTENSION_BLOCK
OPEN_WALLET_HOME_BLOCK
LOGIN_WALLET_BLOCK
```

The helper flow expands `LOGIN_WALLET_BLOCK` into:

```text
UNLOCK_EXTENSION_BLOCK
VERIFY_DASHBOARD_BLOCK
EXTRACT_ADDRESSES_BLOCK
```

Current output data:

```python
{
    "Address": evm_address,
    "EvmAddress": evm_address,
    "SolanaAddress": solana_address,
    "WalletState": "Unlocked",
}
```

Use this action before scouting Backup Seed Phrase or Private Key export on an existing wallet profile.

Validation:

```text
Mock profile login smoke: passed
Profile closed after smoke: yes
Printed seed/address/private key: no
```

### Backup Seed Phrase

Implemented in:

```text
tasks/helpers/metamask_lib.py
tasks/wallet_metamask_aio.py
```

Current block flow:

```text
FIND_EXTENSION_BLOCK
OPEN_WALLET_HOME_BLOCK
UNLOCK_EXTENSION_BLOCK
BACKUP_SEED_PHRASE_BLOCK
```

The helper flow expands `BACKUP_SEED_PHRASE_BLOCK` into:

```text
OPEN_ACCOUNT_DETAILS_BLOCK
START_REVEAL_SRP_BLOCK
COMPLETE_SRP_QUIZ_BLOCK
CONFIRM_PASSWORD_BLOCK
REVEAL_AND_COPY_SEED_BLOCK
```

Current output data:

```python
{
    "SeedPhrase": seed_phrase,
    "WalletState": "ExistingWallet",
    "BackupMode": "RevealExistingSeedPhrase",
}
```

Validation:

```text
Mock profile CDP scout: passed
Seed word count: 12
Clipboard word count after copy: 12
Printed seed/private key after masking rule: no
```

### Backup Private Key

Implemented in:

```text
tasks/helpers/metamask_lib.py
tasks/wallet_metamask_aio.py
```

Current block flow:

```text
FIND_EXTENSION_BLOCK
OPEN_WALLET_HOME_BLOCK
UNLOCK_EXTENSION_BLOCK
BACKUP_PRIVATE_KEY_BLOCK
```

The helper flow expands `BACKUP_PRIVATE_KEY_BLOCK` into:

```text
OPEN_ACCOUNT_DETAILS_BLOCK
OPEN_PRIVATE_KEY_REVEAL_BLOCK
CONFIRM_PASSWORD_BLOCK
COPY_ETHEREUM_PRIVATE_KEY_BLOCK
```

Current output data:

```python
{
    "PrivateKey": ethereum_private_key,
    "EthereumPrivateKey": ethereum_private_key,
    "PrivateKeyNetwork": "Ethereum",
    "WalletState": "ExistingWallet",
    "BackupMode": "RevealEthereumPrivateKey",
}
```

Validation:

```text
Mock profile CDP scout: passed
Ethereum copy clipboard length: 64
Ethereum copy clipboard pattern: 64 hex private key
Printed private key: no
```

### Backup Both

Implemented in:

```text
tasks/wallet_metamask_aio.py
```

This action runs Backup Seed Phrase first, reopens MetaMask home, then runs Backup Private Key.

Current output data includes:

```text
SeedPhrase
PrivateKey
EthereumPrivateKey
PrivateKeyNetwork
WalletState
BackupMode
```

### MetaMask Selectors Already Verified By Scout

Verified create flow selectors:

```text
button[data-testid="onboarding-create-wallet"]
button[data-testid="onboarding-create-with-srp-button"]
input[data-testid="create-password-new-input"]
input[data-testid="create-password-confirm-input"]
label[data-testid="create-password-terms"]
button[data-testid="create-password-submit"]:not([disabled])
button[data-testid="secure-wallet-recommended"]
[data-testid="recovery-phrase-reveal"]
[data-testid="recovery-phrase-chips"]
button[data-testid="recovery-phrase-continue"]:not([disabled])
button[data-testid="recovery-phrase-quiz-unanswered-{index}"]
button[data-testid="recovery-phrase-confirm"]:not([disabled])
button[data-testid="confirm-srp-modal-button"]
button[data-testid="metametrics-i-agree"]
button[data-testid="onboarding-complete-done"]
button[data-testid="pin-extension-next"]
button[data-testid="pin-extension-done"]
```

Verified unlock/address selectors:

```text
input[data-testid="unlock-password"]
button[data-testid="unlock-submit"]:not([disabled])
[data-testid="network-group-with-copy-icon"]
button[data-testid="eth-overview-receive"]
[data-testid="multichain-address-rows-list"]
[data-testid="multichain-address-row"]
[data-testid="multichain-address-row-network-name"]
[data-testid="multichain-address-row-address"]
[data-testid="multichain-address-row-copy-button"]
```

Verified account details and backup selectors:

```text
button[data-testid="account-menu-icon"]
[data-testid="multichain-account-cell-end-accessory"]
[data-testid="multichain-account-menu-item-accountDetails"]
button[data-testid="private-keys-action"]
[data-testid="multichain-srp-backup"]
[data-testid="reveal-seed-page"]
button[data-testid="reveal-seed-quiz-get-started"]
button[data-testid="srp-quiz-right-answer"]
button[data-testid="srp-quiz-continue"]
input[data-testid="input-password"]
button[data-testid="reveal-seed-password-continue"]
[data-testid="recovery-phrase-reveal"]
[data-testid^="recovery-phrase-chip-"]
button[data-testid="reveal-seed-copy-button"]
input[data-testid="multichain-private-key-password-input"]
button[data-testid="confirm-button"]
[data-testid="multichain-address-row"]
[data-testid="multichain-address-row-network-name"]
[data-testid="multichain-address-row-copy-button"]
```

### CDP Requirement

MetaMask may trigger LavaMoat/CSP issues where standard Selenium fails.

Known error class:

```text
LavaMoat - property "Window" of globalThis is inaccessible under scuttling mode
```

Current helper uses CDP DOM/Input patterns:

```text
DOM.enable
DOM.getDocument
DOM.querySelector
DOM.scrollIntoViewIfNeeded
DOM.getBoxModel
Input.dispatchMouseEvent
Input.insertText
Runtime.evaluate
```

When adding new MetaMask blocks, prefer existing CDP helper functions from `metamask_lib.py` before writing new Selenium-only logic.

## Current AIO Task State

`tasks/wallet_metamask_aio.py` currently declares:

```python
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
```

Current routing:

- `Create Wallet`: implemented.
- `Import Wallet`: TODO.
- `Login Only`: implemented.
- `Backup Seed Phrase`: implemented.
- `Backup Private Key`: implemented.
- `Backup Both`: implemented.

## Implemented Feature: Backup Seed Phrase For Existing Wallet

User explicitly asked to document this unfinished part.

### Goal

When a GPM profile already has an existing MetaMask wallet, the task should unlock the wallet, navigate to MetaMask security/backup flow, reveal the Secret Recovery Phrase, extract it, then write it to Excel.

Expected output:

```python
{
    "SeedPhrase": seed_phrase,
    "Address": evm_address,
    "EvmAddress": evm_address,
    "SolanaAddress": solana_address,
    "WalletState": "ExistingWallet",
    "BackupMode": "RevealExistingSeedPhrase",
}
```

### Implementation Note

The exact MetaMask UI path and selectors for revealing an existing SRP were scouted on a mock profile through CDP. The implementation uses those selectors and returns data through `TaskResult.data` only.

### Required GUI Action

Current `TASK_ARGUMENTS` options in `tasks/wallet_metamask_aio.py`:

```python
"options": ["Create Wallet", "Login Only", "Backup Seed Phrase", "Backup Private Key", "Backup Both", "Import Wallet"]
```

Route:

```python
if action == "Backup Seed Phrase":
    return backup_seed_phrase(context, row)
```

### Required Task Block Flow

Proposed block flow:

```text
FIND_EXTENSION_BLOCK
OPEN_WALLET_HOME_BLOCK
UNLOCK_EXTENSION_BLOCK
VERIFY_EXISTING_WALLET_BLOCK
OPEN_SETTINGS_BLOCK
OPEN_SECURITY_PRIVACY_BLOCK
START_REVEAL_SRP_BLOCK
CONFIRM_PASSWORD_BLOCK
REVEAL_EXISTING_SEED_BLOCK
EXTRACT_EXISTING_SEED_BLOCK
EXTRACT_ADDRESSES_BLOCK
```

Return success only after:

- Seed phrase has 12 or 24 valid words.
- EVM address extraction succeeds.
- Solana address extraction either succeeds or fails with clear block status, depending on user requirement.

### Required Helper Functions

Add to `tasks/helpers/metamask_lib.py`:

```python
def open_wallet_home(context: TaskContext, extension_id: str) -> None:
    ...


def verify_existing_wallet(context: TaskContext) -> None:
    ...


def open_settings(context: TaskContext) -> None:
    ...


def open_security_privacy(context: TaskContext) -> None:
    ...


def start_reveal_secret_recovery_phrase(context: TaskContext) -> None:
    ...


def confirm_password_for_seed_reveal(context: TaskContext, password: str) -> None:
    ...


def reveal_existing_seed_phrase(context: TaskContext) -> list[str]:
    ...


def backup_existing_seed_phrase_flow(context: TaskContext, password: str) -> dict[str, str]:
    ...
```

The final flow function should return only plain data:

```python
{
    "SeedPhrase": "...",
    "Address": "...",
    "EvmAddress": "...",
    "SolanaAddress": "...",
    "WalletState": "ExistingWallet",
    "BackupMode": "RevealExistingSeedPhrase",
}
```

It must not return `TaskResult`. The task script returns `TaskResult`.

### Candidate UI Path To Scout

This is a candidate only, not verified as current selector truth:

```text
MetaMask dashboard
  -> account/menu/settings
  -> Settings
  -> Security & privacy
  -> Reveal Secret Recovery Phrase
  -> Enter password
  -> Hold/click reveal
  -> Read seed words
```

AI IDE must verify actual UI path in BrowserOS/scout with a mock profile.

### Candidate Selector Families To Scout

Scout for stable selectors like:

```text
[data-testid="account-options-menu-button"]
[data-testid="global-menu"]
[data-testid="settings-page"]
[data-testid="settings-security-privacy"]
[data-testid="reveal-seed-phrase"]
[data-testid="srp-password-input"]
[data-testid="srp-reveal-button"]
[data-testid="srp-word"]
```

These are not confirmed. Do not implement until scout confirms actual selectors.

### Password Handling

Use `Password` from row:

```python
password: str = required_value(row, "Password")
```

Do not hard-code password.

If password is wrong, fail:

```text
FAIL_AT_CONFIRM_PASSWORD_BLOCK
```

Include current URL and short page text in failure data, but do not include password.

### Seed Handling

Rules:

- Do not print seed phrase.
- Do not log seed phrase.
- Do not write seed to arbitrary file.
- Do not screenshot seed phrase unless debug artifacts are enabled by runtime and the screenshot is unavoidable for debugging.
- Prefer DOM extraction from attributes/text over OCR.
- Validate word count is 12 or 24.

Suggested validation:

```python
def validate_seed_words(seed_words: list[str]) -> list[str]:
    if len(seed_words) not in {12, 24}:
        raise RuntimeError(f"Invalid seed word count; word_count={len(seed_words)}")
    if any(word.strip() == "" for word in seed_words):
        raise RuntimeError("Seed phrase contains blank words.")
    return [word.strip().lower() for word in seed_words]
```

### Idempotency

Backup flow must work if:

- Wallet is already unlocked.
- Wallet is locked and needs password.
- Dashboard is already open in another tab.
- Current tab is not MetaMask.

Do not open onboarding for existing-wallet backup.

### Expected AIO Task Wrapper

Add function in `tasks/wallet_metamask_aio.py`:

```python
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
```

This was the design guidance. The implemented task uses the same block structure.

## Implemented Feature: Login Only

Goal:

Unlock existing MetaMask and return wallet status/address.

Proposed flow:

```text
FIND_EXTENSION_BLOCK
OPEN_WALLET_HOME_BLOCK
UNLOCK_EXTENSION_BLOCK
VERIFY_DASHBOARD_BLOCK
EXTRACT_ADDRESSES_BLOCK
```

Expected data:

```python
{
    "Address": evm_address,
    "EvmAddress": evm_address,
    "SolanaAddress": solana_address,
    "WalletState": "Unlocked",
}
```

Needed helper:

```python
def login_existing_wallet_flow(context: TaskContext, password: str) -> dict[str, str]:
    ...
```

This helper now exists. Future work should reuse it before navigating to backup/private-key screens.

## Missing Feature: Import Wallet

Goal:

Import wallet from existing `SeedPhrase` and `Password`.

Required columns:

```python
REQUIRED_COLUMNS = ["ProfileID", "ProfileName", "SeedPhrase", "Password"]
```

Current complication:

The AIO task currently has one `REQUIRED_COLUMNS` list. If `Create Wallet` and `Login Only` do not require `SeedPhrase`, but `Import Wallet` does, there are two possible designs:

1. Keep one AIO task and include `SeedPhrase` in `REQUIRED_COLUMNS`, meaning create/login Excel also needs a blank/placeholder column.
2. Split import into a separate task `wallet_metamask_import.py`.

Preferred pragmatic approach:

- For v1, make separate `wallet_metamask_import.py` if user wants import soon.
- Later, add runtime support for action-specific required columns if needed.

Proposed import flow:

```text
FIND_EXTENSION_BLOCK
OPEN_ONBOARDING_BLOCK
START_IMPORT_BLOCK
FILL_SEED_WORDS_BLOCK
CREATE_PASSWORD_BLOCK
FINISH_ONBOARDING_BLOCK
EXTRACT_ADDRESSES_BLOCK
```

Do not implement import until BrowserOS/scout maps current MetaMask import selectors.

## Implementation Priority

Recommended order:

1. Decide whether `Import Wallet` belongs in AIO or separate task.

2. Implement `Import Wallet` after scout.

3. Add optional per-network private key export if the user wants networks beyond Ethereum.

## Scout Plan For Backup Seed Phrase

Use mock profile only.

Steps:

```text
1. Start mock GPM profile that already has MetaMask wallet.
2. Attach Selenium.
3. Open MetaMask home page.
4. Unlock with mock password.
5. Navigate manually or via BrowserOS to seed backup page.
6. Dump DOM at each step:
   artifacts/metamask_backup_step_1_dashboard.html
   artifacts/metamask_backup_step_2_settings.html
   artifacts/metamask_backup_step_3_security.html
   artifacts/metamask_backup_step_4_password.html
   artifacts/metamask_backup_step_5_seed.html
7. Extract stable selectors.
8. Implement one helper function per block.
9. Compile.
10. Smoke test.
11. Close GPM profile.
```

Never use real seed/password in the scout.

## Acceptance Criteria For Backup Seed Phrase

Feature is done only when:

- AIO dropdown includes `Backup Seed Phrase`: done.
- Task route calls backup flow: done.
- Existing unlocked wallet works: scout verified.
- Locked wallet unlocks with row password: uses existing unlock flow.
- Wrong password fails at password block: implemented through explicit wait failure.
- Seed phrase extraction returns 12 or 24 words: done.
- Runtime writes `SeedPhrase` back to Excel: supported by runtime writeback.
- No seed is printed to console/log: required; one early scout dump leaked mock seed before masking was tightened, do not repeat.
- Profile closes after normal runtime success and failure: handled by runner.
- `python -m py_compile` passes: done.
- `load_task(Path("tasks/wallet_metamask_aio.py"))` passes: done.

## Known Data Keys

Use these stable output keys across wallet tasks:

```text
SeedPhrase
Address
EvmAddress
SolanaAddress
WalletState
BackupMode
PrivateKey
EthereumPrivateKey
PrivateKeyNetwork
```

Do not create random alternate names such as `seed`, `wallet`, `evm`, `sol`.

## Notes For Future AI

If usage limit interrupts work, continue from:

1. `docs/DOCS_INDEX.md`
2. `docs/README_FOR_AI.md`
3. `docs/CODEBASE_STRUCTURE.md`
4. this file
5. `tasks/helpers/metamask_lib.py`
6. `tasks/wallet_metamask_aio.py`

Do not start by rewriting the whole MetaMask helper. Extend it block by block.
