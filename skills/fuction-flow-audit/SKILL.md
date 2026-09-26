---

name: function-flow-deep-code-audit

description: Use when performing a deep audit of an application by reconstructing behavior function-by-function, tracing every branch from entry points through called functions to terminal outcomes, recording the reasoning path, identifying unreachable/dead code, validating intended behavior, and producing a complete bug/improvement list.

---

# Function-Flow Deep Code Audit

## Overview

This skill performs a deep structural audit by treating the codebase as a directed execution graph.

Do not primarily audit by scrolling through files line-by-line. Start from the application's entry points and analyze complete functions: inputs, outputs, side effects, called functions, callers, dependencies, purpose, assumptions, and terminal states.

For every branch, determine:

* where it starts;
* why it exists;
* what condition selects it;
* which functions it calls;
* what state/data it changes;
* where it exits;
* what happens on success, failure, exception, timeout, or missing data.

Every branch must have a known exit.

## When to Use

Use when you need to understand whether a complex codebase actually behaves as intended.

Do not use for formatting, naming, trivial refactoring, or isolated syntax fixes.

## Deep Audit Pipeline

| Step                             | Action                                                                                                                                         | Artefact               |
| -------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------- | ---------------------- |
| **0. Inventory**                 | Identify entry points, services, modules, main controllers, API routes, workers and event handlers.                                            | Entry-point map        |
| **1. Function Mapping**          | For every reachable function record input → purpose → calls → side effects → output → exit conditions.                                         | Function map           |
| **2. Branch Tracing**            | Follow every conditional/error/retry/async branch recursively until a terminal state is reached.                                               | Branch-flow graph      |
| **3. Context Reconstruction**    | For each function explain why it exists and how its result is used by its caller and downstream functions.                                     | Dependency/context map |
| **4. Dead-Code Scan**            | Search for functions, routes, handlers, variables and modules that are never reached or whose results are ignored.                             | Dead/unreachable list  |
| **5. State & Data Audit**        | Track important data from creation to transformation, persistence, retrieval and final use.                                                    | Data-flow map          |
| **6. Behavioral Validation**     | Compare reconstructed behavior with the intended application behavior. Distinguish expected, suspicious and clearly incorrect behavior.        | Behavior verdicts      |
| **7. Alternative Design Review** | For suspicious flows, determine whether a simpler, safer or more reliable implementation exists.                                               | Improvement proposals  |
| **8. Final Report**              | Produce all confirmed bugs, probable bugs, design weaknesses and verification tasks, ordered by severity.                                      | `AUDIT.md`             |
| **9. Memory Checkpoint**         | Save current audit position, completed branches, pending branches and discovered relationships so the audit can resume without repeating work. | `AUDIT_MEMORY.md`      |

## Mandatory Method

For each reachable function use:

`Caller → Function → Inputs → Preconditions → Internal steps → Called functions → State changes → Output → Exit branches`

Then recursively inspect every called function.

Construct an explicit branch tree such as:

`Entry`
`├─ valid input → process → success → return`
`├─ missing input → validation error → return`
`├─ dependency failure → retry`
`│  ├─ retry succeeds → continue`
`│  └─ retry exhausted → failure → return`
`└─ unexpected exception → handler → terminal state`

Never stop a branch at “calls function X”; continue into X until its behavior and terminal outcome are understood.

## Red Flags

* A reachable branch has no identifiable exit.
* A function's return value is ignored when it appears semantically important.
* A function exists but no caller can reach it.
* A caller assumes an invariant that the callee does not guarantee.
* A failure branch silently produces the same state as success.
* State is updated before an operation that can fail, leaving inconsistent state.
* A retry loop has no bounded or terminal failure condition.
* Async/background work has no observable completion/failure state.
* A function performs work inconsistent with its name or declared purpose.
* The reconstructed behavior makes the application's visible behavior impossible to explain.

## Final Output

`AUDIT.md` must contain:

1. Executive severity summary.
2. Entry-point map.
3. Function/dependency map.
4. Complete branch map.
5. Dead/unreachable code.
6. Data/state flow.
7. Confirmed bugs.
8. Probable bugs requiring runtime verification.
9. Design/architecture improvements.
10. Tests still required or blocked.
11. Exact audit stopping point.

Each finding should include:

`Severity → Location → Observed behavior → Expected behavior → Root cause → Impact → Recommended fix → Verification method`

## `AUDIT_MEMORY.md` must allow another audit session to continue from the exact last analyzed function/branch without reconstructing previous work.
