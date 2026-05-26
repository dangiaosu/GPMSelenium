# BrowserOS Scout Guide For GPMSelenium

This guide is for AI agents using BrowserOS during Stage 1 scouting.

## Boundaries

BrowserOS is the primary scout tool, not the production executor.

Use BrowserOS to:

- Explore pages with mock data.
- Understand the user journey.
- Identify stable selectors and page states.
- Detect blockers and edge cases.
- Produce a block-flow proposal for GPMSelenium scripts.

Do not use BrowserOS to:

- Run production batches.
- Enter real user data.
- Enter seed phrases, private keys, passwords, tokens, or real account credentials.
- Assume access to GPM profile wallet state unless official BrowserOS tooling explicitly supports attaching to the running GPM browser.

## Scout Inputs

Before scouting, capture:

- Target URL.
- Mock data to use.
- User goal.
- Expected success condition.
- Known blockers or required wallet state.

If the task requires a wallet already installed/imported in a GPM profile and BrowserOS cannot access that exact state, switch to the Chrome Extension Recorder fallback.

## BrowserOS Scout Process

1. Open the target page in BrowserOS.
2. Use mock data only.
3. Execute the user's intended flow step by step.
4. Observe visible UI state after every important action.
5. Inspect DOM clues and stable selector candidates.
6. Note network behavior at a high level when visible or available.
7. Stop before code generation.

## Scout Report Format

BrowserOS scouting must produce a concise report:

```text
Target URL:
Mock data used:
Observed flow:
Stable selectors:
DOM clues:
Network notes:
Screenshots/artifacts:
Blockers:
Proposed block flow:
Open questions for AI Wizard interview:
```

## Selector Discovery Rules

Prefer selectors in this order:

1. `data-testid`
2. `data-cy`
3. stable `id`
4. `aria-label`
5. `name`
6. role + visible text
7. scoped CSS under stable parent
8. relative XPath anchored to stable text

Avoid absolute XPath, generated class hashes, and selectors that depend on random indexes unless there is no better option.

## Interview Questions

BrowserOS scout output must include questions for the AI Wizard when the flow has uncertainty.

Examples:

- What if the wallet is already connected?
- What if the unlock screen appears instead of onboarding?
- What if captcha or 2FA appears?
- What if the success button is disabled because balance is insufficient?
- Should a missing condition retry, skip, or raise `RuntimeError(...)`?
- Does this block need a longer `context.node_wait(timeout=...)`?

## Fallback To Recorder

Use `scripts/scout_server.py` and `extension_record_flow/` when:

- Shadow DOM must be dumped.
- BrowserOS misses event details.
- A GPM mock profile has wallet state that BrowserOS cannot reproduce.
- The AI needs raw recorded steps and checkpoint notes.

The recorder artifact must be passed to the AI Wizard together with any BrowserOS scout report.
