# Verification

Each kind of claim has the evidence form that proves it. A false "it passes" costs more than an honest "not run".

## Evidence by kind of claim

- **Code behaviour** ("done", "fixed", "passing", "works", "no issues", or anything implying them) needs **a command run**: in this session, on the commit you report, with the whole relevant output read and saying what you claim. Give the exact command and the directory it ran from; the commit (`git rev-parse HEAD`) and whether the working tree was clean (`git status --short`); the observed output, quoted verbatim: the summary line (`Ran 36 tests ... OK`), the exit code, and any warning or error lines. Trim noise, never trim failures.
- Other claims rest on **a manual observation** (what you did, step by step, and what you saw) or **an external source** (the link, its publication or last-updated date, and the passage you rely on, quoted).

A claim is complete when its form has all its fields; otherwise the claim is not made, and you say what you did observe instead. A role with no repository, such as a researcher answering from sources, can report `DONE`.

What does not count: a previous run before your last change; output from someone else's report; "it should work"; a command that exited 0 but printed errors; a test run that silently collected zero tests; a green result on a different branch or commit.

## Before you claim

- After your last edit, rerun. Any edit, including "just a comment" or a formatting fix, invalidates earlier runs.
- Check that the command actually exercised what you claim: the test count is not zero, the file you changed was included, the suite you meant is the one that ran.
- If a run is flaky, say so: how many runs, how many failed, under what conditions. Do not report the one green run.
- If a check needs something you lack (credentials, a service, a platform), do not simulate it. Mark it as not run and say why.

## Reporting honestly

Report every check in the Evidence section of `shared/reporting.md`, as verified, not run or failed. A failed check is reported even if you believe the failure is unrelated; say why you believe that, and how you checked.

Wording follows evidence. "Tests pass" requires a passing run. "I expect this to pass" is allowed when labelled as expectation. Never upgrade one into the other.

## Read-only roles

The reviewer, scout, researcher and arbiter are read-only. A read-only role never changes a tracked file, and never commits, pushes or posts. It runs the project's own commands (the tests, a build, the acceptance commands) directly on the pinned commit; by-products those commands create on their own (caches, build output, anything ignored by version control) are acceptable and are never committed. Reason: the checkout is the evidence base for your report and for anyone rerunning your commands.

Any experiment that requires changing a tracked file, for example breaking the code to see whether a test really fails, happens in a throwaway copy of the tree outside the checkout, deleted afterwards. Evidence from it is labelled as coming from a modified copy and says what was modified.

Before reporting, confirm the checkout has no tracked changes: `git status --short` shows none.
