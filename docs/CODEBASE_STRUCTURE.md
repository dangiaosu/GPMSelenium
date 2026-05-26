# GPMSelenium Codebase Structure For AI IDE

File này là bản đồ codebase hiện tại của `GPMSelenium-OpenSource-v1.0`.

## Root Structure

```text
GPMSelenium-OpenSource-v1.0/
  src/gpm_selenium/
    __init__.py
    cli.py
    contracts.py
    excel.py
    gpm.py
    gui.py
    profile_rows.py
    runner.py
    session_cache.py
    store.py
    task_loader.py

  tasks/
    expandtesting_register.py
    nof1_waitlist.py
    wallet_create.py
    wallet_metamask_aio.py
    helpers/
      __init__.py
      metamask_lib.py

  scripts/
    auto_scout.py
    scout_profile.py

  docs/
    AI_SCRIPT_GUIDE.md
    WALLET_LIB_BEST_PRACTICES.md
    DOCS_INDEX.md
    README_FOR_AI.md
    CODEBASE_STRUCTURE.md
    METAMASK_WALLET_STATUS.md

  README.md
  pyproject.toml
  requirements.txt
  launch_gui.py
  run_gui.bat
  repair_venv.bat
  data.xlsx
  background.jpg
  github.png
  telegram.png
  facebook.png
```

Generated/local files may exist during development:

```text
.venv/
__pycache__/
gpm_selenium.sqlite3
.session/
artifacts/
*.xlsx
```

These should not be treated as source logic.

## Core Runtime Files

### `src/gpm_selenium/contracts.py`

Defines the task contract:

- `TaskResult`
- `ProfileContext`
- `TaskContext`
- `ok(...)`
- `fail(...)`

Important behavior:

- `TaskContext.page_wait()` returns Selenium `WebDriverWait` using page/result timeout.
- `TaskContext.node_wait()` returns Selenium `WebDriverWait` using node timeout.
- `TaskContext.open_new_tab(url)` opens a new tab and waits document ready.
- `TaskContext.screenshot(name)` is gated by `config["enable_debug_artifacts"]`.
- `TaskContext.save_html(name)` is gated by `config["enable_debug_artifacts"]`.

Do not move Excel/GPM logic into `TaskContext`.

### `src/gpm_selenium/gpm.py`

GPM Local API client.

Responsibilities:

- List profiles.
- List groups.
- Start profile.
- Close profile.
- Normalize GPM API response into typed objects.
- Apply request retry rules.

Important runtime requirement:

- Start profile must include window params such as `win_size`, `win_pos`, `win_scale`.

Task scripts must not import or call this client.

### `src/gpm_selenium/runner.py`

Execution engine.

Responsibilities:

- Build runtime config.
- Read pending rows.
- Run bounded worker queue.
- Start one GPM profile per row/profile.
- Attach Selenium to GPM returned debugging address and driver path.
- Create `TaskContext`.
- Call `task.run(context, row)`.
- Retry failed row based on retry count.
- Write status.
- Write extracted `TaskResult.data` through Excel runtime.
- Always cleanup: `driver.quit()` and GPM close.
- Respect stop event: active rows finish, no new rows start.

If a profile leaks open, inspect cleanup paths here first.

### `src/gpm_selenium/excel.py`

Excel runtime layer.

Responsibilities:

- Preview Excel rows.
- Skip `Status = SUCCESS` and legacy `Status = OKIE`.
- Write status to row.
- Write result data to dynamic columns.

Important function:

```python
write_result_data(excel_path, row_number, data)
```

This function creates missing columns based on keys in `data`, then writes values.

Task scripts must not duplicate this behavior.

### `src/gpm_selenium/task_loader.py`

Task module loader and contract validator.

Responsibilities:

- Import task from `.py` path.
- Validate metadata.
- Validate `REQUIRED_COLUMNS`.
- Ensure `ProfileID` exists.
- Read optional `TASK_ARGUMENTS`.
- Return `LoadedTask`.

Important current behavior:

- `TASK_ARGUMENTS` defaults to `[]`.
- Each argument must be a dictionary with string `name` and string `type`.

### `src/gpm_selenium/store.py`

SQLite store.

Responsibilities:

- Registered tasks.
- Run history.
- Run items.
- Logs.

Important current behavior:

- `RegisteredTask.arguments` stores task GUI arguments.
- `tasks.arguments_json` stores serialized `TASK_ARGUMENTS`.
- `_initialize()` performs safe migration:

```sql
ALTER TABLE tasks ADD COLUMN arguments_json TEXT NOT NULL DEFAULT '[]'
```

Do not store secrets in SQLite logs.

### `src/gpm_selenium/gui.py`

PySide6 desktop GUI.

Major tabs:

- Scripts.
- Profiles.
- Run Setup.
- Run Monitor.
- Run History.
- Settings.

Important current features:

- Profile group dropdown.
- Profile list table.
- Dynamic `Task Arguments` group in Run Setup.
- Retry count.
- Stop Run button with soft-stop semantics.
- Debug artifacts checkbox.
- Failed account reselect button.

Dynamic arguments flow:

1. `_show_task_detail(...)` loads selected task.
2. `_render_task_arguments(loaded.arguments)` clears and rebuilds widgets.
3. Dropdown args become `QComboBox`.
4. Text args become `QLineEdit`.
5. `_task_config()` returns:

```python
{
    "enable_debug_artifacts": ...,
    "task_args": self._dynamic_task_arguments(),
}
```

### `src/gpm_selenium/profile_rows.py`

Build rows when user selects GPM profiles directly from GUI.

Responsibilities:

- Convert selected profiles into task rows.
- Optionally merge Excel data by profile.
- Preview selected profile rows.

### `src/gpm_selenium/session_cache.py`

Session profile cache.

Responsibilities:

- Save loaded GPM profiles to `.session/profiles.json`.
- Load cached profile list.

Cache is only convenience state, not source of truth.

### `src/gpm_selenium/cli.py`

CLI runner.

Responsibilities:

- Parse command line.
- Load task.
- Preview Excel columns.
- Register task in store.
- Run task batch.

GUI is primary, CLI is useful for smoke tests.

## Task Files

### `tasks/expandtesting_register.py`

Sample task for:

```text
https://practice.expandtesting.com/register
```

Useful as simple example of:

- Open page.
- Fill fields.
- Submit.
- Wait result.
- Return status.

### `tasks/nof1_waitlist.py`

Sample waitlist task for `nof1.ai`.

Useful as example of:

- Form fill.
- Dropdown/select logic.
- Success text detection.

Do not use real user data when scouting this site.

### `tasks/wallet_create.py`

Legacy thin task for MetaMask create wallet.

Responsibilities:

- Read `Password` from row.
- Track `current_block`.
- Call functions from `tasks.helpers.metamask_lib`.
- Return `SeedPhrase`, `Address`, `EvmAddress`, `SolanaAddress`.

This file exists for backward compatibility. New MetaMask work should prefer `wallet_metamask_aio.py`.

### `tasks/wallet_metamask_aio.py`

Current AIO MetaMask task.

Metadata:

```python
TASK_NAME = "wallet_metamask_aio"
TASK_ARGUMENTS = [
    {
        "name": "action",
        "label": "Chế độ chạy",
        "type": "dropdown",
        "options": ["Create Wallet", "Import Wallet", "Login Only"],
        "default": "Create Wallet",
    }
]
```

Current actions:

- `Create Wallet`: implemented.
- `Import Wallet`: TODO, returns fail.
- `Login Only`: TODO, returns fail.

Expected future action:

- `Backup Seed Phrase`: not implemented yet.

### `tasks/helpers/metamask_lib.py`

MetaMask browser interaction helper.

Responsibilities:

- Find MetaMask extension ID.
- Open onboarding.
- Start create wallet.
- Create password.
- Reveal/extract seed during create flow.
- Confirm seed.
- Finish onboarding.
- Unlock if locked.
- Extract EVM and Solana addresses.
- CDP DOM/Input helpers for LavaMoat/CSP-resistant interaction.
- Failure debug data.

Important function families:

```text
find_metamask_extension_id
open_onboarding
start_create_wallet
create_password
reveal_and_extract_seed
confirm_seed_phrase
finish_onboarding
unlock_wallet_if_locked
extract_wallet_addresses
cdp_clickable_by_selector
cdp_type_text
cdp_clipboard_text_matching
failure_data
```

Do not put `TaskResult` logic in helper. Helper should raise clear errors; task catches and returns `fail(...)`.

## Scripts

### `scripts/scout_profile.py`

Standalone scout helper for a known GPM mock profile.

Purpose:

- Start GPM profile.
- Attach Selenium.
- Leave driver open for manual/DevTools investigation.

Do not use production user data.

### `scripts/auto_scout.py`

Scout automation/dump helper.

Purpose:

- Open profile/extension.
- Dump DOM snapshots into `artifacts/`.
- Help identify selectors.

Artifacts are local debugging files, not release source.

## Runtime Flow

```text
GUI/CLI
  -> load_task(module_path)
  -> validate Excel/profile rows
  -> create run in SQLite
  -> runner starts bounded workers
  -> worker starts GPM profile with window params
  -> worker attaches Selenium
  -> worker builds TaskContext
  -> task.run(context, row)
  -> task returns TaskResult
  -> runtime writes Status
  -> runtime writes TaskResult.data columns
  -> runtime logs run item
  -> worker driver.quit()
  -> worker GPM close profile
```

## Data Flow

Input sources:

- Excel file.
- Selected profiles from GUI.
- Selected profiles merged with Excel data.

Task receives:

```python
row: dict[str, object]
context: TaskContext
```

Task returns:

```python
TaskResult(success=True, status="SUCCESS", data={...}, error=None)
TaskResult(success=False, status="FAIL_AT_...", data={...}, error="...")
```

Runtime writes:

- `Status`.
- Any key from `TaskResult.data`.

## Where To Add New Features

Add a new website task:

```text
tasks/new_site_task.py
```

Add a new wallet:

```text
tasks/helpers/new_wallet_lib.py
tasks/wallet_new_wallet_aio.py
```

Add a new task GUI option:

```python
TASK_ARGUMENTS = [...]
```

Do not modify GUI for each new task option unless the argument type itself is not supported.

Add new runtime-level behavior:

- Excel/status behavior: `excel.py` and `runner.py`.
- GPM behavior: `gpm.py` and `runner.py`.
- UI render behavior: `gui.py`.
- Task metadata behavior: `task_loader.py` and `store.py`.

## Validation Commands

Compile:

```powershell
python -m py_compile src\gpm_selenium\*.py tasks\*.py tasks\helpers\*.py
```

Load MetaMask AIO:

```powershell
$env:PYTHONPATH='src'
$env:PYTHONIOENCODING='utf-8'
python -c "from pathlib import Path; from gpm_selenium.task_loader import load_task; t=load_task(Path('tasks/wallet_metamask_aio.py')); print(t.name, t.arguments)"
```

Offscreen GUI smoke:

```powershell
$env:PYTHONPATH='src'
$env:QT_QPA_PLATFORM='offscreen'
python -c "import sys; from PySide6.QtWidgets import QApplication; from gpm_selenium.gui import MainWindow; app=QApplication(sys.argv); w=MainWindow(); print(w.task_list.count()); w.close(); app.quit()"
```

## Known Cleanup Notes

The working folder may contain local generated files:

- `__pycache__/`
- `gpm_selenium.sqlite3`
- `artifacts/`
- `.session/`
- local Excel files

Do not delete these unless user explicitly asks. For open-source packaging, rely on `.gitignore` instead.
