# GPMSelenium Docs Index For AI IDE

Đọc file này trước khi tiếp tục code GPMSelenium.

Mục tiêu của thư mục `docs/` là làm nơi handoff cho AI IDE kế tiếp. Khi thread hiện tại bị usage limit hoặc người khác vào tiếp, AI mới phải đọc theo thứ tự dưới đây để hiểu dự án đang ở đâu, file nào chịu trách nhiệm gì, và phần MetaMask còn thiếu gì.

## Reading Order

1. `docs/README_FOR_AI.md`

   Handoff nhanh cho AI IDE: dự án là gì, trạng thái hiện tại, cách chạy, nguyên tắc không được phá.

2. `docs/CODEBASE_STRUCTURE.md`

   Bản đồ codebase: toàn bộ cấu trúc thư mục, trách nhiệm từng file, luồng runtime, GUI, task loader, Excel, SQLite.

3. `docs/AI_SCRIPT_GUIDE.md`

   Quy tắc viết task script nói chung cho GPMSelenium.

4. `docs/WALLET_LIB_BEST_PRACTICES.md`

   Quy tắc viết helper library cho ví Web3 như MetaMask, Rabby, Phantom, OKX, Keplr.

5. `docs/METAMASK_WALLET_STATUS.md`

   Trạng thái hiện tại của MetaMask automation, những gì đã xong, những gì chưa xong, và plan cụ thể cho Backup Seed Phrase khi profile đã có sẵn ví.

6. `docs/UI_UX_BEST_PRACTICES.md`

   UI/UX rules for PySide6 edits, Run Setup structure, status display, dynamic task arguments, and shared UI kit usage.

7. `docs/SCOUT_TO_PRODUCTION_LIFECYCLE.md`

   Hybrid BrowserOS-first scout, recorder fallback, Mock QA, and production release rules.

8. `docs/BROWSEROS_SCOUT_GUIDE.md`

   BrowserOS scout rules, selector discovery, mock-data safety, and fallback criteria.

9. `docs/AI_WIZARD_GUIDE.md`

   AI Wizard workflow for turning BrowserOS notes or recorder JSON into GPMSelenium scripts.

## Current Project Snapshot

Project chính đang làm:

```text
C:\Users\Admin\Desktop\CodeLinhTinh\NewProject\GPMSelenium-OpenSource-v1.0
```

Runtime chính:

```text
src/gpm_selenium/
```

Task scripts:

```text
tasks/
```

Wallet helper libraries:

```text
tasks/helpers/
```

MetaMask files quan trọng:

```text
tasks/helpers/metamask_lib.py
tasks/wallet_create.py
tasks/wallet_metamask_aio.py
```

## Non-Negotiable Rules

- Không dùng dữ liệu thật trong BrowserOS/scout.
- Không đọc/ghi Excel trực tiếp trong task script.
- Không gọi GPM API trong task/helper.
- Không dùng `time.sleep()` trong task/helper.
- Không in seed phrase, password, token ra log/console.
- Không sửa runtime để phục vụ riêng một website hoặc một ví.
- Không xóa file user đang dùng nếu user không yêu cầu rõ.
- Khi test profile GPM bằng script scout, luôn close profile sau khi test.

## What To Do Before Coding

1. Đọc `docs/README_FOR_AI.md`.
2. Đọc file source liên quan trước khi sửa.
3. Nếu sửa MetaMask, đọc `tasks/helpers/metamask_lib.py` và `docs/METAMASK_WALLET_STATUS.md`.
4. Nếu thêm task argument, kiểm tra `src/gpm_selenium/task_loader.py`, `src/gpm_selenium/store.py`, `src/gpm_selenium/gui.py`.
5. Sau khi sửa Python, chạy compile:

```powershell
python -m py_compile src\gpm_selenium\*.py tasks\*.py tasks\helpers\*.py
```

6. Nếu sửa task contract, test `load_task()` bằng `PYTHONPATH=src`.

## Documentation Policy

Docs này viết cho AI IDE, không phải tài liệu marketing cho người dùng cuối. Viết ngắn, rõ, đúng trạng thái hiện tại. Nếu một feature chưa code xong, ghi là chưa xong và nêu bước tiếp theo, không viết như đã hoàn thành.
