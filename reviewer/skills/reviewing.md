# Reviewing

A review answers one question: does this exact commit do what the spec requires, correctly and safely, without breaking anything else? Everything you report must help answer it.

## Setup

1. Find the merge base with the target branch (`git merge-base HEAD origin/<base>`) and list the change: `git diff --stat <merge-base>..HEAD`, then `git log --oneline <merge-base>..HEAD`.
2. Read the spec in full, then the plan, then the project's instruction file.
3. Run the checks (role rule 3) before reading the code in depth. Failing checks tell you where to look first.

## What to check

Go through the whole diff. For each area, ask the questions; anything you cannot answer "yes" to with evidence is a candidate finding.

- **Requirements.** Is every acceptance criterion met, with the check passing when you run it? Is every decision in the spec implemented exactly (names, formats, values)? Is anything in the non-goals implemented anyway?
- **Architecture.** Does the change fit the existing structure, or does it duplicate, bypass or contradict it? Are the responsibilities in the right place? Are the project's living documents updated if the design changed?
- **Correctness.** Trace the main paths by reading the code. Are conditions, loops and boundaries right? Are errors handled and surfaced, not swallowed? Are resources released? Is concurrency safe where it matters?
- **Edge cases.** Empty, missing, maximum, malformed and duplicate inputs; unexpected types; first run and repeated run; partial failure halfway through.
- **Regressions.** What existing behaviour could this change affect? Do callers of changed functions still work? Do the old tests still pass, and were any removed or weakened (check the diff of the test files specifically)?
- **Compatibility.** Public interfaces, file formats, configuration, database schema, supported versions and platforms. Is anything removed or changed that someone depends on? Is there a migration where one is needed?
- **Security.** Input validation at trust boundaries, injection (SQL, shell, path, template), authentication and authorization checks, secrets in code or logs, unsafe deserialization, dependency additions and their source.
- **Tests.** Do the new tests test the behaviour the spec describes, through public interfaces? Would they fail if the code were wrong? Try it for the important ones in a throwaway copy of the tree (`shared/verification.md`): break the code there, run the test, see it fail, then delete the copy. Are the edge cases above covered?
- **Records.** Does the diff contain no spec, plan or report files? Does the pull request description carry the spec and the plan?
- **Readability.** Can the next engineer understand and change this code? Only report readability issues that will cause real mistakes; style preferences are not findings unless the project's instructions require them.

## Writing findings

Each finding:

```
[BLOCKING] src/export.py:42 — rows over the limit are silently truncated instead of rejected.
Consequence: users lose data without an error; violates acceptance criterion 4.
Evidence: `python -m pytest tests/test_export.py -k limit` → 1 failed: expected 413, got 200
          (test written in a throwaway copy of the tree; the checkout is unmodified).
```

- Be precise and neutral. Say what is wrong and why it matters; propose a fix only when it helps understanding.
- One problem per finding. If the same problem appears in several places, list the places in one finding.
- If you are not sure, say so and say what would settle it. Do not inflate uncertainty into a blocking finding or deflate a real problem into a note.

Before sending, reread each finding: does it name a place, a consequence and evidence that someone else can reproduce? If not, fix it or drop it.
