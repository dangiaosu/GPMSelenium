# Wallet Helper Library Best Practices For AI IDE

Tài liệu này dành cho AI IDE khi viết thêm helper library cho các ví Web3 khác trong GPMSelenium, ví dụ Rabby, OKX Wallet, Phantom, Backpack, Keplr, Bitget Wallet hoặc các extension wallet tương tự.

Mục tiêu: tách rõ **Platform Runtime**, **Task Script** và **Wallet Helper Library** để automation chạy ổn định trên nhiều GPM profiles, ghi dữ liệu về Excel qua runtime, và không biến mỗi task thành một file Selenium khổng lồ.

## Architecture Boundary

GPMSelenium có 3 lớp. Không trộn trách nhiệm giữa các lớp.

`src/gpm_selenium/*` là Platform Runtime:

- Quản lý GPM API, start/close profile, Selenium attach, queue, retry, SQLite, Excel writeback.
- Tạo `TaskContext`.
- Ghi `TaskResult.data` về Excel.
- Quyết định debug artifact có được lưu hay không.

`tasks/*.py` là Task Script:

- Export metadata: `TASK_NAME`, `TASK_VERSION`, `TASK_DESCRIPTION`, `REQUIRED_COLUMNS`, `STATUS_SUCCESS`, có thể thêm `TASK_ARGUMENTS`.
- Đọc dữ liệu từ `row`.
- Đọc lựa chọn GUI từ `context.config["task_args"]`.
- Route action theo block.
- Gọi helper library.
- Return `ok(status, data)` hoặc `fail(status, error, data)`.

`tasks/helpers/*_lib.py` là Wallet Helper Library:

- Chứa Selenium/CDP DOM interaction riêng cho từng ví.
- Không export task metadata.
- Không return `TaskResult`.
- Không đọc/ghi Excel, SQLite, CSV hoặc file data.
- Không gọi GPM API trực tiếp.
- Nhận `context: TaskContext` làm tham số đầu tiên ở mọi function thao tác browser.

## File Naming

Mỗi ví nên có một helper riêng:

```text
tasks/helpers/metamask_lib.py
tasks/helpers/rabby_lib.py
tasks/helpers/phantom_lib.py
tasks/helpers/okx_wallet_lib.py
tasks/helpers/keplr_lib.py
```

Task AIO nên đứng ở `tasks/`:

```text
tasks/wallet_metamask_aio.py
tasks/wallet_rabby_aio.py
tasks/wallet_phantom_aio.py
```

Không viết logic ví mới vào `wallet_metamask_aio.py`. Nếu cần support ví khác, tạo helper và task riêng.

## Task Arguments Contract

Nếu task cần lựa chọn trên GUI, định nghĩa `TASK_ARGUMENTS`.

```python
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

Task đọc giá trị như sau:

```python
raw_task_args: object = context.config.get("task_args")
task_args: dict[str, object] = raw_task_args if isinstance(raw_task_args, dict) else {}
action: str = str(task_args.get("action", "Create Wallet")).strip()
```

Không tự parse GUI state bằng cách khác. Runtime đã chuẩn hóa `task_args`.

## Required Columns

Task phải khai báo đúng các cột Excel cần thiết.

Create wallet thường cần:

```python
REQUIRED_COLUMNS = ["ProfileID", "ProfileName", "Password"]
```

Import wallet thường cần:

```python
REQUIRED_COLUMNS = ["ProfileID", "ProfileName", "SeedPhrase", "Password"]
```

Login only thường cần:

```python
REQUIRED_COLUMNS = ["ProfileID", "ProfileName", "Password"]
```

Task không được dùng `openpyxl`, `pandas`, `csv`, `sqlite3` hoặc tự ghi file Excel. Mọi dữ liệu extract được phải return qua `TaskResult.data`.

Ví dụ:

```python
return ok(
    "SUCCESS",
    {
        "SeedPhrase": seed_phrase,
        "EvmAddress": evm_address,
        "SolanaAddress": solana_address,
    },
)
```

Runtime sẽ tự tạo cột và ghi dữ liệu về Excel.

## Helper Function Shape

Helper function phải nhỏ, một mục đích, không multi-mode.

Tốt:

```python
def open_onboarding(context: TaskContext, extension_id: str) -> None:
    ...


def create_password(context: TaskContext, password: str) -> None:
    ...


def extract_wallet_addresses(context: TaskContext) -> dict[str, str]:
    ...
```

Không tốt:

```python
def run_wallet(context: TaskContext, action: str, row: dict[str, object]) -> dict[str, object]:
    ...
```

Helper không nên nhận cả `row` nếu chỉ cần một field. Task script chịu trách nhiệm validate row và truyền value đã sạch vào helper.

## Block Naming

Task script phải giữ `current_block` để khi fail có status chính xác.

```python
current_block: str = "FIND_EXTENSION_BLOCK"
try:
    current_block = "FIND_EXTENSION_BLOCK"
    extension_id: str = find_wallet_extension_id(context)

    current_block = "OPEN_ONBOARDING_BLOCK"
    open_onboarding(context, extension_id)

    current_block = "CREATE_PASSWORD_BLOCK"
    create_password(context, password)

    return ok("SUCCESS", data)
except Exception as error:
    status: str = f"FAIL_AT_{current_block}: {type(error).__name__}: {error}"
    return fail(status, status, failure_data(context, current_block, partial_data))
```

Status fail phải bắt đầu bằng `FAIL_AT_`.

## Wait Strategy

Không dùng `time.sleep()`.

Dùng:

- `context.node_wait().until(...)` cho element/action nhỏ.
- `context.page_wait().until(...)` cho page state hoặc dashboard state.
- CDP polling function trả về object hoặc `False`.

Ví dụ:

```python
button: CdpClickableElement = context.node_wait().until(
    lambda driver: cdp_clickable_by_selector(driver, 'button[data-testid="create-wallet"]')
)
button.click()
```

Nếu ví chậm do proxy hoặc extension lag, tăng timeout ở GUI/runtime, không hard-code sleep vào helper.

## Selector Strategy

Ưu tiên selector theo thứ tự:

1. `data-testid`, `data-test-id`, `data-qa`, `aria-label`.
2. Stable button text hoặc label text.
3. Relative XPath anchored vào container ổn định.
4. CSS class chỉ khi class không random/hash.
5. Absolute XPath là cấm, trừ khi scout chứng minh không còn cách nào khác và phải ghi rõ lý do trong docstring function.

Không dùng selector kiểu:

```text
/html/body/div[1]/div/div[2]/div[3]/button
.css-1abc2de .x9f3aa
```

Nên dùng:

```text
button[data-testid="onboarding-create-wallet"]
[aria-label="Copy address"]
//button[normalize-space()="Create wallet"]
```

## Extension Pages And CDP

Nhiều wallet extension có CSP, Shadow DOM hoặc LavaMoat làm Selenium thường bị lỗi. Helper nên có CDP utilities tương tự MetaMask:

- `cdp_clickable_by_selector(driver, selector)`
- `cdp_selector_exists(driver, selector)`
- `cdp_attribute_by_selector(driver, selector, attribute_name)`
- `cdp_type_text(context, selector, value)`
- `cdp_clipboard_text_matching(driver, pattern)`

Nếu Selenium `find_element` ổn định thì dùng Selenium. Nếu gặp extension security layer, chuyển sang CDP DOM/Input.

CDP click nên:

1. `DOM.enable`.
2. `DOM.getDocument` với `pierce=True`.
3. `DOM.querySelector`.
4. `DOM.scrollIntoViewIfNeeded`.
5. `DOM.getBoxModel`.
6. `Input.dispatchMouseEvent` mousePressed/mouseReleased.

Không dùng JavaScript click làm mặc định nếu extension có security layer. Chỉ dùng khi đã scout và biết nó hoạt động.

## Extension ID Discovery

Không hard-code extension ID nếu có thể tìm từ `chrome://extensions/`.

Pattern nên dùng:

```python
def find_wallet_extension_id(context: TaskContext) -> str:
    context.open_new_tab("chrome://extensions/")
    return str(context.node_wait().until(lambda driver: extension_id_from_extensions_page(driver, "Wallet Name")))
```

Nếu wallet có nhiều bản hoặc tên thay đổi, helper nên nhận `extension_name: str` hoặc có list tên chấp nhận được.

Không gọi GPM API trong helper để tìm extension. Helper chỉ thao tác với browser đã attach.

## State Detection

Không viết flow tuyến tính mù. Wallet helper cần có state detector:

- `wallet_dashboard_visible(context) -> bool`
- `wallet_unlock_visible(context) -> bool`
- `wallet_onboarding_visible(context) -> bool`
- `switch_to_existing_wallet_dashboard(context) -> bool`
- `switch_to_existing_wallet_unlock(context) -> bool`

Login flow nên idempotent:

```python
def unlock_wallet_if_locked(context: TaskContext, password: str) -> None:
    if wallet_dashboard_visible(context):
        return
    context.node_wait().until(lambda _driver: wallet_dashboard_visible(context) or wallet_unlock_visible(context))
    if wallet_dashboard_visible(context):
        return
    ...
```

Nếu profile đã unlock sẵn, không nhập password lại.

Nếu profile đang ở dashboard tab khác, switch sang tab đó thay vì mở onboarding mới.

## Seed Phrase Handling

Seed phrase là dữ liệu nhạy cảm. Helper chỉ được extract và return qua `TaskResult.data`.

Không được:

- Print seed ra console.
- Ghi seed vào log.
- Ghi seed vào file tạm.
- Screenshot seed phrase trừ khi user bật debug artifacts, và kể cả khi bật thì nên cân nhắc chỉ chụp màn hình lỗi sau khi seed đã qua bước reveal nếu thật sự cần debug.

Khi import seed:

- Validate đủ 12/24 words trước khi fill.
- Trim whitespace.
- Lowercase nếu wallet yêu cầu.
- Fail rõ: `FAIL_AT_IMPORT_SEED_BLOCK` nếu không map được input.

## Address Extraction

Luôn return address theo key rõ nghĩa.

Recommended keys:

```python
{
    "Address": evm_address,
    "EvmAddress": evm_address,
    "SolanaAddress": solana_address,
    "BtcAddress": btc_address,
    "CosmosAddress": cosmos_address,
}
```

Nếu một ví support nhiều chain, helper nên có function riêng:

```python
def extract_evm_address(context: TaskContext) -> str:
    ...


def extract_solana_address(context: TaskContext) -> str:
    ...
```

Validate bằng regex hoặc chain-specific parser tối thiểu.

Ví dụ:

```python
EVM_ADDRESS_PATTERN = re.compile(r"^0x[a-fA-F0-9]{40}$")
SOLANA_ADDRESS_PATTERN = re.compile(r"^[1-9A-HJ-NP-Za-km-z]{32,44}$")
```

Không ghi address giả vào Excel nếu extract fail. Fail ở block extract để runtime retry hoặc ghi status lỗi.

## Error Artifacts

Task/helper có thể gọi:

```python
context.screenshot(...)
context.save_html(...)
```

Không cần tự check `enable_debug_artifacts`. `TaskContext` đã tự bỏ qua và return `None` nếu GUI không bật debug artifacts.

`failure_data()` nên chỉ lấy dữ liệu debug ngắn:

```python
{
    "current_block": block_name,
    "url": context.driver.current_url,
    "page_text": context.page_text()[:500],
}
```

Không đưa seed phrase vào error text. Nếu cần partial data, pass seed qua `data` để runtime ghi Excel, không đưa vào log message.

## Import Rules

Task scripts được import:

```python
from gpm_selenium.contracts import TaskContext, TaskResult, fail, ok
from tasks.helpers.some_wallet_lib import ...
```

Helper libraries được import:

```python
from gpm_selenium.contracts import TaskContext
from selenium.common.exceptions import TimeoutException, WebDriverException
```

Task scripts không được import:

```python
import openpyxl
import pandas
import csv
import sqlite3
import requests
```

Helper libraries cũng không nên import các module trên. Wallet helper chỉ thao tác browser thông qua `context.driver`.

## Dynamic GUI Arguments For Wallet Tasks

Khi ví có nhiều mode, dùng `TASK_ARGUMENTS` thay vì tạo nhiều task trùng code.

Ví dụ:

```python
TASK_ARGUMENTS = [
    {
        "name": "action",
        "label": "Chế độ chạy",
        "type": "dropdown",
        "options": ["Create Wallet", "Import Wallet", "Login Only"],
        "default": "Create Wallet",
    },
    {
        "name": "network",
        "label": "Network",
        "type": "dropdown",
        "options": ["Ethereum", "Solana", "All"],
        "default": "All",
    },
]
```

Task route theo argument:

```python
if action == "Create Wallet":
    return create_wallet(context, row)
if action == "Import Wallet":
    return import_wallet(context, row)
if action == "Login Only":
    return login_wallet(context, row)
return fail("FAIL_AT_ROUTE_BLOCK", f"Unsupported action; action={action}", None)
```

Không đặt logic dropdown trong helper. Helper chỉ cung cấp function thực thi.

## Scouting Workflow

Khi viết helper cho ví mới, AI IDE phải scout bằng mock profile/mock data trước.

Quy trình:

1. Start GPM profile mock.
2. Mở extension hoặc target page.
3. Quan sát state hiện tại.
4. Tìm selector ổn định.
5. Kiểm tra Selenium thường có bị CSP/LavaMoat/Shadow DOM block không.
6. Nếu block, dùng CDP DOM/Input.
7. Viết helper function cho đúng một block.
8. Compile task.
9. Test live trên mock profile.
10. Đóng profile sau test.

Không dùng dữ liệu Excel thật khi scout. Không paste seed thật, password thật, email thật hoặc profile production thật vào BrowserOS/scout.

## Minimal AIO Task Template

```python
from __future__ import annotations

from typing import Any

from gpm_selenium.contracts import TaskContext, TaskResult, fail, ok
from tasks.helpers.example_wallet_lib import create_wallet_flow, failure_data, login_wallet_flow

TASK_NAME = "wallet_example_aio"
TASK_VERSION = "1.0.0"
TASK_DESCRIPTION = "Run Example Wallet workflows from GUI-selected action."
REQUIRED_COLUMNS = ["ProfileID", "ProfileName", "Password"]
STATUS_SUCCESS = "SUCCESS"
TASK_ARGUMENTS = [
    {
        "name": "action",
        "label": "Chế độ chạy",
        "type": "dropdown",
        "options": ["Create Wallet", "Import Wallet", "Login Only"],
        "default": "Create Wallet",
    }
]


def run(context: TaskContext, row: dict[str, object]) -> TaskResult:
    action: str = selected_action(context)
    if action == "Create Wallet":
        return create_wallet(context, row)
    if action == "Login Only":
        return login_wallet(context, row)
    return fail("FAIL_AT_ROUTE_BLOCK", f"Unsupported action; action={action}", None)


def create_wallet(context: TaskContext, row: dict[str, object]) -> TaskResult:
    password: str = required_value(row, "Password")
    current_block: str = "CREATE_WALLET_BLOCK"
    data: dict[str, object] = {}
    try:
        data = create_wallet_flow(context, password)
        return ok("SUCCESS", data)
    except Exception as error:
        status: str = f"FAIL_AT_{current_block}: {type(error).__name__}: {error}"
        return fail(status, status, failure_data(context, current_block, data))


def login_wallet(context: TaskContext, row: dict[str, object]) -> TaskResult:
    password: str = required_value(row, "Password")
    current_block: str = "LOGIN_WALLET_BLOCK"
    try:
        login_wallet_flow(context, password)
        return ok("SUCCESS", {})
    except Exception as error:
        status: str = f"FAIL_AT_{current_block}: {type(error).__name__}: {error}"
        return fail(status, status, failure_data(context, current_block, {}))


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
```

## Helper Library Checklist

Trước khi coi một wallet helper là usable, AI IDE phải kiểm tra:

- File helper không export `TASK_NAME`.
- Mọi browser function nhận `context: TaskContext` là tham số đầu tiên.
- Không có `time.sleep()`.
- Không import Excel/SQLite/requests trong task/helper.
- Không có absolute XPath.
- Có state detector cho dashboard/unlock/onboarding.
- Có function unlock idempotent.
- Có block rõ cho create/import/login.
- Có address validation.
- Có `failure_data()` ngắn, không leak seed vào log.
- Task AIO có `TASK_ARGUMENTS` nếu có nhiều mode.
- `python -m py_compile` pass.
- `load_task()` pass.
- Live smoke test bằng mock profile pass.
- GPM profile được đóng sau smoke test.

## When To Stop And Ask The User

AI IDE phải dừng và hỏi user nếu gặp:

- Captcha, Cloudflare, password prompt ngoài dự kiến, hardware wallet prompt hoặc OTP.
- Wallet UI đổi lớn làm selector cũ không còn đúng.
- Seed phrase không extract được từ DOM và cần OCR/manual.
- Wallet yêu cầu user xác nhận extension permission không thể tự động hóa an toàn.
- Có nguy cơ dùng dữ liệu thật trong BrowserOS/scout.

Không đoán selector khi chưa scout. Không ghi fallback mơ hồ để che lỗi. Fail rõ ở đúng block để runtime retry và ghi status.
