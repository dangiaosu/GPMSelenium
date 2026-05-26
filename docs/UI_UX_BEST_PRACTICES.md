# GPMSelenium UI/UX Best Practices For AI IDE

This document is for AI agents editing the PySide6 desktop UI.

## Current UI Architecture

- Main UI entrypoint: `src/gpm_selenium/gui.py`.
- Shared UI constants and formatting helpers: `src/gpm_selenium/ui_kit.py`.
- Keep reusable display rules in `ui_kit.py` when they are not tied to one widget.
- Keep one-off layout construction inside `gui.py`.

## Design Direction

GPMSelenium is an AI-code automation runtime, not a marketing landing page.

The UI should feel like a modern AI/SaaS operations console:

- Dark theme.
- Dense but readable panels.
- Clear task setup flow.
- No decorative cards inside cards.
- No oversized explanatory text.
- No one-note purple or blue-only palette.
- Tables and logs must remain legible over translucent backgrounds.

## Header Rules

- Keep the title cluster centered.
- Keep left spacer width equal to status pill width so the title does not drift.
- Use `HEADER_SIDE_WIDTH` from `src/gpm_selenium/ui_kit.py`.
- Do not set narrow fixed widths for dynamic status text.
- Convert long internal statuses through `run_status_display_text(...)`.

Current status mapping:

```text
DONE_WITH_ERRORS -> Done + errors
DONE             -> Done
STOPPED          -> Stopped
RUNNING          -> Running
STOPPING         -> Stopping
RETRYING         -> Retrying
ERROR            -> Error
IDLE             -> Idle
```

Always set the tooltip to the raw status value when shortening display text.

## Run Setup Layout

Run Setup is a workbench, not a flat form.

Current groups:

- `Input Source`: Excel checkbox, Excel path, browse, preview.
- `Execution`: GPM base URL, workers, retry count, debug artifacts, node timeout, page/result timeout.
- `Browser Window`: window width, height, and scale.

Keep new controls inside the group that owns the workflow responsibility.

Examples:

- Add proxy/run queue knobs to `Execution`.
- Add `win_pos` strategy, monitor selection, or screen fitting knobs to `Browser Window`.
- Add Excel mode, sheet selection, or output options to `Input Source`.

## Dynamic Task Arguments

Task-specific controls are rendered in the Scripts tab detail panel from `TASK_ARGUMENTS`.

Do not hardcode task-specific controls in Run Setup. Run Setup owns platform configuration only.

Use the schema:

```python
TASK_ARGUMENTS = [
    {
        "name": "action",
        "label": "Chế độ chạy",
        "type": "dropdown",
        "options": ["Create Wallet", "Login Only"],
        "default": "Create Wallet",
    }
]
```

The GUI passes selected values to:

```python
context.config["task_args"]
```

## Status And Error Display

- Status pill should show concise state only.
- Detailed row errors belong in Run Monitor table and logs.
- Long raw statuses should be kept in tooltips or log output.
- Do not show raw values like `DONE_WITH_ERRORS` in narrow header controls.

## Accessibility And Sizing

- Buttons must not clip text.
- Use minimum/fixed dimensions only for icons, tool tiles, and stable status pills.
- For dynamic text, prefer wider controls and concise display labels.
- Tables should use full available panel width.
- Avoid adding labels that explain obvious UI behavior.

## Validation Checklist

After UI changes:

```powershell
$env:PYTHONPATH='src'
$env:QT_QPA_PLATFORM='offscreen'
python -m py_compile src\gpm_selenium\gui.py src\gpm_selenium\ui_kit.py
```

Smoke check with an offscreen `QApplication` when changing widget construction.
