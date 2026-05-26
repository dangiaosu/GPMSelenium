# GPMSelenium Scout To Production Lifecycle

This document defines the required workflow for building automation tasks with GPMSelenium.

## Goal

GPMSelenium uses a hybrid scout architecture:

- BrowserOS is the primary scout tool because AI-native exploration is fast.
- Chrome Extension Recorder is the fallback scout tool when exact selectors, Shadow DOM, or GPM wallet state is required.
- GPMSelenium is the only runtime for Mock QA and Production.

No production mass run should depend on BrowserOS or the recorder extension.

## Stage 1: Hybrid Scout

Use mock data only. Do not enter real passwords, seed phrases, private keys, tokens, emails, phones, or user production data.

### Primary Path: BrowserOS Scout

Use BrowserOS Agent Mode first when the target can be explored without a prepared GPM wallet state.

The scout output must capture:

- Target URL.
- Observed user flow.
- Stable selector candidates.
- DOM clues and visible text.
- Screenshots when useful.
- Blockers such as captcha, OTP, wallet popup, modal, or missing state.
- Proposed GPMSelenium block flow.

BrowserOS is for understanding the page and generating a scout report. It is not the production executor.

### Fallback Path: Chrome Extension Recorder

Use the Record & Flow extension when:

- BrowserOS cannot access the required state.
- The target depends on a GPM profile with prepared wallet/extensions.
- Shadow DOM details are required.
- Raw recorded steps are needed for AI review.
- BrowserOS misses selectors or overgeneralizes the flow.

The fallback path is:

```text
python scripts/scout_server.py
select Mock group/profile
GPM starts the selected profile with extension_record_flow loaded
user records a mock flow with Start/Stop/Checkpoint/Dump
artifact is saved under artifacts/recorded_flow_<task_name>_<timestamp>.json
```

The recorder supports a linear happy path plus checkpoint notes. Checkpoint notes are not code. They are prompts for AI Wizard interview questions.

## Stage 2: Mock QA Testing

AI converts the Stage 1 output into a draft GPMSelenium task script only after the interview step is complete.

The draft script must follow `docs/AI_SCRIPT_GUIDE.md`:

- Use `TaskContext`.
- Use `context.node_wait(timeout=...)` for node-specific waits.
- Use `context.page_wait(timeout=...)` for page/result waits.
- Keep GPM and Excel logic out of task scripts.
- Raise `RuntimeError(...)` for business errors from helper code.
- Return extracted data through `ok(...)` or `fail(...)`.

Run the draft script against a full Mock Group before production.

Recommended mock cases:

- Success path.
- Already initialized or already connected.
- Missing wallet or missing extension state.
- Insufficient balance.
- Banned or blocked account.
- Captcha or 2FA.
- Slow proxy or delayed UI.
- Unexpected modal.

If Mock QA fails, inspect row status, logs, screenshots, HTML artifacts, and recorded scout data. Refine the script and rerun Mock QA.

## Stage 3: Production Execution

Production starts only when Mock QA passes.

Before production, create a short release report:

- Task script path.
- Target workflow.
- Required Excel columns.
- Task arguments.
- Mock cases tested.
- Known limitations.
- Recommended workers, retry count, node timeout, and page timeout.

Production rules:

- Use GPMSelenium runtime only.
- Do not use BrowserOS for mass execution.
- Do not use the recorder extension for mass execution.
- Use BrowserOS or recorder only for single-profile debugging after reproducing an issue on mock or controlled data.

## Decision Rule

Use BrowserOS first for fast exploration. Use the recorder fallback when correctness depends on GPM profile state, wallet extension internals, or raw DOM/Shadow DOM artifacts.
