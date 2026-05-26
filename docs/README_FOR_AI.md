# GPMSelenium README For AI IDE

Đây là README dành cho AI IDE kế tiếp khi tiếp tục làm việc trên GPMSelenium. Đọc file này trước khi sửa code.

## Project Goal

GPMSelenium là local desktop platform chạy automation Selenium trên GPMLogin profiles.

Dự án không phải drag-drop builder. Kiến trúc đúng là:

- AI IDE và BrowserOS dùng để scout website/extension bằng dữ liệu mock.
- AI IDE viết Python task script và helper library.
- GPMSelenium runtime quản lý GPM profile lifecycle, Selenium attach, queue đa luồng, retry, Excel, SQLite, GUI, logs.

## Active Workspace

```text
C:\Users\Admin\Desktop\CodeLinhTinh\NewProject\GPMSelenium-OpenSource-v1.0
```

Nếu user nói `GPMSelenium` nhưng đang làm bản open source, ưu tiên kiểm tra thư mục trên trước.

## Current State

Core runtime đã có:

- PySide6 desktop GUI.
- GPM profile list, group filter, session cache.
- Profile selection bằng table, hỗ trợ chọn nhiều profile.
- Excel optional input/status.
- Skip row có `Status = SUCCESS` hoặc legacy `Status = OKIE`.
- Retry count.
- Stop mềm: profile đang chạy sẽ chạy xong, queue không nhận thêm profile mới.
- SQLite run history/logs.
- Dynamic UI Arguments qua `TASK_ARGUMENTS`.
- Excel writeback cho `TaskResult.data`, tự tạo cột mới nếu cần.
- Debug artifacts được gate trong `TaskContext`, task gọi screenshot/html cũng không lưu nếu GUI không bật.

MetaMask hiện tại:

- `tasks/helpers/metamask_lib.py` chứa logic CDP/Selenium cho MetaMask.
- `tasks/wallet_create.py` là legacy thin task cho create wallet.
- `tasks/wallet_metamask_aio.py` là AIO task có dropdown `action`.
- AIO action `Create Wallet` đã route sang helper và return `SeedPhrase`, `Address`, `EvmAddress`, `SolanaAddress`.
- AIO action `Login Only` đã mở ví có sẵn, unlock bằng `Password`, verify dashboard, và return address.
- AIO action `Backup Seed Phrase` đã reveal/copy seed phrase ví có sẵn và return `SeedPhrase`.
- AIO action `Backup Private Key` đã confirm password và copy Ethereum private key, return `PrivateKey` và `EthereumPrivateKey`.
- AIO action `Backup Both` đã chạy cả hai bước trên trong một lần.
- AIO action `Import Wallet` hiện đang TODO, trả `fail(...)` rõ ràng.
- Import wallet vẫn chưa implement. Xem `docs/METAMASK_WALLET_STATUS.md`.

## Runtime Boundary

Runtime ở `src/gpm_selenium/` chịu trách nhiệm:

- GPM API.
- Start/close profile.
- Window params: `win_size`, `win_pos`, `win_scale`.
- Selenium attach.
- Queue worker.
- Retry.
- Excel read/write.
- SQLite store.
- GUI.
- Artifact gate.

Task ở `tasks/` chỉ chịu trách nhiệm:

- Đọc `row`.
- Đọc `context.config["task_args"]`.
- Thao tác DOM/network trong browser đã attach.
- Return `ok(...)` hoặc `fail(...)`.

Task/helper không được:

- Import `openpyxl`, `pandas`, `csv`, `sqlite3`, `requests`.
- Tự start/close GPM profile.
- Tự ghi Excel.
- Tự ghi SQLite.
- Dùng dữ liệu thật trong scout.

## How To Run

Tạo hoặc repair venv:

```powershell
.\repair_venv.bat
```

Chạy GUI:

```powershell
.\run_gui.bat
```

Hoặc:

```powershell
.\.venv\Scripts\python.exe launch_gui.py
```

Compile check:

```powershell
python -m py_compile src\gpm_selenium\*.py tasks\*.py tasks\helpers\*.py
```

Load task check:

```powershell
$env:PYTHONPATH='src'
$env:PYTHONIOENCODING='utf-8'
python -c "from pathlib import Path; from gpm_selenium.task_loader import load_task; print(load_task(Path('tasks/wallet_metamask_aio.py')).arguments)"
```

## BrowserOS And Scout Rules

BrowserOS/scout chỉ dùng mock data.

Không bao giờ nhập:

- Seed phrase thật.
- Password thật.
- Email/phone/name thật từ Excel.
- Token thật.
- Production profile ID nếu user chưa cho phép rõ.

Khi cần scout wallet extension:

1. Start profile mock.
2. Mở extension/page cần test.
3. Dump DOM hoặc dùng BrowserOS inspect.
4. Xác định selector ổn định.
5. Viết code cho một block nhỏ.
6. Compile.
7. Smoke test.
8. Close GPM profile.

## Dynamic UI Arguments

Task có thể định nghĩa:

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

GUI sẽ tự render field trong tab Run Setup. Giá trị được truyền vào:

```python
context.config["task_args"]
```

Task đọc:

```python
raw_task_args = context.config.get("task_args")
task_args = raw_task_args if isinstance(raw_task_args, dict) else {}
action = str(task_args.get("action", "Create Wallet")).strip()
```

## Excel Result Data

Task trả data:

```python
return ok("SUCCESS", {"SeedPhrase": seed, "EvmAddress": evm, "SolanaAddress": sol})
```

Runtime sẽ tự ghi data vào Excel. Nếu cột chưa tồn tại, runtime tự tạo cột.

Không viết Excel trong task/helper.

## Where To Continue MetaMask Work

Nếu user yêu cầu làm tiếp MetaMask:

1. Đọc `docs/METAMASK_WALLET_STATUS.md`.
2. Đọc `tasks/helpers/metamask_lib.py`.
3. Đọc `tasks/wallet_metamask_aio.py`.
4. Scout bằng mock profile nếu cần selector mới.
5. Implement helper function trong `metamask_lib.py`.
6. Route action trong `wallet_metamask_aio.py`.
7. Compile và load task.
8. Nếu có live smoke test, close profile sau test.

## Known Risk

MetaMask extension có thể bị LavaMoat/CSP làm Selenium thường lỗi. Logic hiện tại đã dùng CDP DOM/Input cho nhiều bước. Nếu gặp lỗi kiểu:

```text
LavaMoat - property "Window" of globalThis is inaccessible under scuttling mode
```

Không cố dùng `find_element` hoặc JavaScript click mù. Dùng CDP DOM/Input pattern trong `metamask_lib.py`.

## Handoff Summary

Nếu chỉ có vài phút để hiểu dự án:

- Core runtime tương đối ổn, đừng viết logic website/ví vào runtime.
- Wallet code nên sống ở `tasks/helpers/*_lib.py`.
- Task AIO chỉ route action và return `TaskResult`.
- MetaMask create wallet đã làm.
- MetaMask backup seed/import/login chưa hoàn tất.
- Mọi dữ liệu extract được phải return qua `ok(..., data)` để runtime ghi Excel.
