# GPMSelenium AI Wizard Guide

This guide controls how AI agents convert scout artifacts into GPMSelenium task scripts.

## Required Behavior

Do not write code immediately.

The AI Wizard must follow this order:

1. Analyze BrowserOS notes or Recorder JSON.
2. Propose a block flow.
3. Interview the user about uncertainty.
4. Generate code only after the interview is answered.
5. Recommend Mock QA before production.

## Accepted Inputs

The AI Wizard may receive:

- BrowserOS scout report.
- Recorder JSON from `artifacts/recorded_flow_<task_name>_<timestamp>.json`.
- Screenshots or debug artifacts.
- Existing task scripts or helper libraries.

When a Recorder JSON is provided, read:

- `metadata.taskName`
- `metadata.taskDescription`
- `metadata.requiredColumns`
- `recordedSteps`
- annotation/checkpoint steps
- `unrolledDOM`
- `networkSnapshot`

## Analysis Phase

Summarize:

- Target workflow.
- Happy path.
- Important selectors.
- Required data columns.
- Task arguments if needed.
- Possible business errors.
- Missing information.

Checkpoint notes must be treated as explicit design signals. They usually mean an IF/ELSE, retry, timeout override, or business error branch is required.

## Block Flow Proposal

Propose a block flow before code:

```text
OPEN_TARGET_BLOCK
CHECK_INITIAL_STATE_BLOCK
CONNECT_WALLET_BLOCK
FILL_FORM_BLOCK
SUBMIT_BLOCK
VERIFY_SUCCESS_BLOCK
```

Each block must include:

- Entry condition.
- Main action.
- Success condition.
- Failure condition.
- Whether it needs `context.node_wait(timeout=...)`.
- Whether a business failure should raise `RuntimeError(...)`.

## Mandatory Interview

Ask questions before code when any uncertainty exists.

Required question categories:

- IF/ELSE state handling.
- Retry vs fail behavior.
- Timeout adjustments.
- Captcha, OTP, 2FA, or modal handling.
- Wallet already connected, locked, missing, or wrong network.
- Business errors such as banned account, insufficient balance, or claim unavailable.
- Checkpoint/note interpretation.

Example:

```text
You added checkpoint "wallet may already be unlocked" after Step 2.
Should the script first check for the dashboard state and skip unlock if present?
```

Example:

```text
If the claim button is missing, should the script retry for 30 seconds or raise RuntimeError("Claim unavailable")?
```

## Code Generation Rules

Generated task scripts must follow `docs/AI_SCRIPT_GUIDE.md`.

Required:

- Export `TASK_NAME`, `TASK_VERSION`, `TASK_DESCRIPTION`, `REQUIRED_COLUMNS`, `STATUS_SUCCESS`.
- Use `run(context: TaskContext, row: dict[str, object]) -> TaskResult`.
- Use block-based `current_block`.
- Use `context.node_wait(timeout=...)` for selector-level waits.
- Use `context.page_wait(timeout=...)` for page/result waits.
- Raise `RuntimeError(...)` from helper functions for business errors.
- Return `ok("SUCCESS", data)` only after verified success.
- Never import or write Excel from task scripts.
- Never call GPM API from task scripts.
- Never log real secrets.

## Mock QA Requirement

After code generation, instruct the user to run Mock QA on a full Mock Group before production.

The script is not production-ready until:

- Mock success case passes.
- Known edge cases are handled or documented.
- Failed artifacts are reviewed.
- Retry and timeout settings are verified.

## Production Rule

Production execution uses GPMSelenium only.

BrowserOS and the Chrome Extension Recorder are scout/debug tools. They are prohibited for mass production runs unless the user explicitly performs a one-profile controlled debug session.
