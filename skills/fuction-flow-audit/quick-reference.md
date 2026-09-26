# Function-Flow Deep Audit — Quick Reference

## Start

1. Find the application's real entry points.
2. Identify the first function executed for each major feature.
3. Build the call chain from that entry point.

## For Every Function

Record:

`INPUT → PURPOSE → PRECONDITIONS → INTERNAL LOGIC → CALLED FUNCTIONS → SIDE EFFECTS → OUTPUT → EXIT CONDITIONS`

Then inspect every called function recursively.

## For Every Branch

Ask:

* What condition selects this branch?
* Why does the branch exist?
* What data enters it?
* What functions does it call?
* What state does it modify?
* What happens if the operation succeeds?
* What happens if it fails?
* What happens on exception?
* What is the terminal exit?
* Can execution become stuck, silent, duplicated or inconsistent?

## Branch Map

Example:

```text
ENTRY
├── VALID
│   ├── dependency OK → PROCESS → SUCCESS
│   └── dependency FAIL
│       ├── RETRY OK → PROCESS → SUCCESS
│       └── RETRY FAIL → ERROR → EXIT
└── INVALID → VALIDATION ERROR → EXIT
```

## Dead-Code Check

For every function ask:

`Who calls this?`

Then:

`Can that caller actually be reached?`

Also check:

* unused routes;
* handlers never connected to UI;
* functions whose output is ignored;
* configuration values never consumed;
* fallback branches never reachable.

## Behavior Check

After mapping the complete flow:

`What the code does ≠ necessarily what the application should do.`

Compare the reconstructed behavior with the intended workflow.

For every mismatch record:

`BUG / DESIGN WEAKNESS / NEEDS VERIFICATION`

## Memory Checkpoint

After each major module save:

```text
LAST ENTRY POINT:
LAST FUNCTION:
COMPLETED BRANCHES:
PENDING BRANCHES:
IMPORTANT CALL RELATIONSHIPS:
DISCOVERED BUGS:
QUESTIONS STILL OPEN:
NEXT FUNCTION TO ANALYZE:
```

## Final Audit

Do not finish until:

* every reachable major entry point is mapped;
* every branch has a terminal outcome;
* important callees have been inspected;
* dead/unreachable code has been checked;
* important state/data flows are understood;
* expected vs actual behavior has been compared;
* confirmed and probable bugs are separated;
* remaining untested areas are explicitly recorded.
