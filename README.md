# GPMSelenium

GPMSelenium là nền tảng desktop local để chạy automation Selenium trên profile GPMLogin. Mục tiêu của dự án là tách rõ hai phần:

- **Platform runtime**: quản lý GPM profile, queue đa luồng, Excel status, retry, log, lịch sử chạy.
- **Task script**: một file Python nhỏ do AI IDE hoặc developer viết để thao tác một website cụ thể.

Dự án này không phải drag-drop builder. Workflow chính là: dùng AI/BrowserOS để nghiên cứu trang bằng dữ liệu mock, viết task script Selenium, rồi để GPMSelenium chạy batch trên nhiều profile GPM.

## Tính năng chính

- Giao diện desktop PySide6.
- Lấy danh sách profile GPM qua Local API.
- Chọn profile bằng chuột, hỗ trợ chọn nhiều profile.
- Chạy task theo queue đa luồng có giới hạn.
- Stop mềm: profile đang chạy sẽ chạy xong, queue không nhận thêm profile mới.
- Retry count cho profile lỗi.
- Ghi status vào Excel theo từng row.
- Tự bỏ qua row có `Status = SUCCESS` hoặc legacy `Status = OKIE`.
- Chọn lại các account lỗi để chạy lại nhanh.
- Debug artifacts bằng checkbox: screenshot/HTML chỉ được lưu khi người dùng bật.
- Task contract ổn định cho AI IDE.

## Yêu cầu

- Windows 10/11.
- Python 3.11 trở lên.
- GPMLogin đang chạy local.
- GPM Local API mặc định: `http://127.0.0.1:19995`.
- Chrome driver/path do GPM API trả về khi start profile.

## Cài đặt nhanh

Mở terminal tại thư mục dự án:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -e .
```

Hoặc trên Windows có thể chạy:

```bat
repair_venv.bat
```

File này sẽ tạo lại `.venv` và cài dependencies cho đúng máy hiện tại.

## Chạy giao diện

```bat
run_gui.bat
```

Hoặc:

```powershell
.\.venv\Scripts\python.exe launch_gui.py
```

## Luồng sử dụng cơ bản

1. Mở GPMLogin trên máy.
2. Mở GPMSelenium.
3. Vào tab **Profiles**.
4. Bấm **Reload Groups** nếu muốn lấy danh sách group.
5. Chọn group hoặc để `All groups`.
6. Bấm **Refresh From GPM**.
7. Dùng chuột, Shift hoặc Ctrl để chọn nhiều profile.
8. Vào tab **Scripts** và chọn task.
9. Nếu dùng Excel, chọn file Excel ở tab **Run Setup**.
10. Chọn số worker, retry count, timeout.
11. Bấm **Start Run**.

## Excel input

Mỗi task định nghĩa cột bắt buộc qua `REQUIRED_COLUMNS`.

Ví dụ task sample `expandtesting_register.py` cần:

```text
ProfileID
ProfileName
Username
Password
```

File `data.xlsx` trong repo là dữ liệu mock để test nhanh task `nof1_waitlist.py`. File này có 25 dòng mẫu với các cột:

```text
ProfileName
ProfileID
Name
Email
Phone
Status
```

Trước khi chạy thật, hãy thay `ProfileID` mock bằng Profile ID thật trong GPMLogin. Các cột `Name`, `Email`, `Phone` đang là dữ liệu giả để người mới nhìn vào là hiểu format.

Runtime sẽ tự tạo hoặc dùng cột `Status`.

Quy tắc status:

- `SUCCESS`: bỏ qua khi chạy lại.
- `OKIE`: bỏ qua để tương thích dữ liệu cũ.
- Trống: sẽ chạy.
- Có lỗi: sẽ chạy lại.
- Nếu chạy lại thành công, lỗi cũ được overwrite bằng `SUCCESS`.

Không commit file Excel thật lên GitHub. `.gitignore` đã chặn `*.xlsx` và `*.csv`.

## Task script contract

Task script nằm trong thư mục `tasks/`.

Mỗi task phải export metadata:

```python
TASK_NAME = "example_task"
TASK_VERSION = "1.0.0"
TASK_DESCRIPTION = "Short description."
REQUIRED_COLUMNS = ["ProfileID", "ProfileName", "Username", "Password"]
STATUS_SUCCESS = "SUCCESS"
```

Và export hàm:

```python
def run(context: TaskContext, row: dict[str, object]) -> TaskResult:
    ...
```

Task chỉ xử lý website. Task không được:

- Start/close GPM profile.
- Đọc hoặc ghi Excel trực tiếp.
- Import `pandas`, `openpyxl`, hoặc `csv`.
- Ghi file tuỳ tiện ngoài artifact helper của runtime.

Task trả dữ liệu về runtime bằng:

```python
return ok("SUCCESS", data)
return fail("FAIL_AT_BLOCK", error, partial_data)
```

## Block-based status

Task nên viết theo block để dễ debug:

```python
current_block = "OPEN_BLOCK"
current_block = "FILL_FORM_BLOCK"
current_block = "SUBMIT_BLOCK"
current_block = "VERIFY_BLOCK"
```

Khi lỗi:

```python
status = f"FAIL_AT_{current_block}: {type(error).__name__}: {error}"
return fail(status, status, data)
```

## Debug artifacts

Runtime có checkbox **Save debug artifacts on failure**.

Task có thể gọi:

```python
screenshot_path = context.screenshot("error_name")
html_path = context.save_html("error_name")
```

Nếu checkbox tắt, core sẽ trả `None` ngay và không tạo file. Điều này bảo vệ ổ cứng khi chạy hàng trăm hoặc hàng nghìn profile.

## BrowserOS và dữ liệu mock

Khi dùng BrowserOS để scout website:

- Chỉ dùng dữ liệu mock.
- Không nhập dữ liệu thật từ Excel.
- Không nhập credential thật.
- Không paste token/profile ID thật vào BrowserOS.

Quy trình scout nên là:

1. Mở trang bằng dữ liệu mock.
2. Kiểm tra DOM selector ổn định.
3. Kiểm tra XHR/fetch request nếu có thể đi theo hướng API.
4. Ghi lại success condition và failure condition.
5. Viết task theo từng block, không viết một file dài đoán mò.

Xem thêm: `docs/AI_SCRIPT_GUIDE.md`.

## CLI runner

Chạy task bằng CLI:

```powershell
.\.venv\Scripts\gpm-selenium-run.exe --task-path tasks\expandtesting_register.py --excel-path data.xlsx --max-workers 3 --retry-count 1
```

Bật debug artifacts:

```powershell
.\.venv\Scripts\gpm-selenium-run.exe --task-path tasks\expandtesting_register.py --excel-path data.xlsx --enable-debug-artifacts
```

## File quan trọng

```text
src/gpm_selenium/contracts.py      TaskContext, TaskResult, ok/fail
src/gpm_selenium/gpm.py            GPM Local API client
src/gpm_selenium/runner.py         Queue, retry, lifecycle, cleanup
src/gpm_selenium/gui.py            Desktop UI
src/gpm_selenium/excel.py          Excel read/write handled by runtime
src/gpm_selenium/task_loader.py    Load and validate task scripts
tasks/expandtesting_register.py    Sample mock task
tasks/nof1_waitlist.py             Sample NOF1 waitlist task
data.xlsx                          Mock Excel data for NOF1 sample
docs/AI_SCRIPT_GUIDE.md            Guide cho AI viết task
```

## Ghi chú release

Bản open-source này đã loại khỏi source:

- Dữ liệu Excel thật.
- SQLite runtime database.
- Session cache.
- Artifact debug.
- Legacy waitlist tool cũ.

Repository này chỉ nên chứa core runtime và sample/mock task.
