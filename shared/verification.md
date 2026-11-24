# Verification

A claim is worth only the evidence behind it. The reader of your report cannot see your workspace; they act on what you write. A false "it passes" costs more than an honest "not run".

## The rule

Never write "done", "fixed", "passing", "works", "no issues" or anything that implies them unless, in this session, you have:

1. run the command that proves it,
2. on the commit you are reporting,
3. read the whole relevant output, including the exit status and the summary line,
4. and seen it say what you claim.

If any of the four is missing, the claim is not made. Say what you did observe instead.

## What counts as evidence

- The exact command, as you ran it, from which directory.
- The commit it ran against (`git rev-parse HEAD`), and whether the working tree was clean (`git status --short`).
- The relevant part of the output, quoted verbatim: the summary line (`Ran 36 tests ... OK`, `5 passed, 0 failed`), the exit code, and any warning or error lines. Trim noise, never trim failures.
- For a manual check: what you did, step by step, and what you saw.

What does not count: a previous run before your last change; output from someone else's report; "it should work"; a command that exited 0 but printed errors; a test run that silently collected zero tests; a green result on a different branch or commit.

## Before you claim

- After your last edit, rerun. Any edit, including "just a comment" or a formatting fix, invalidates earlier runs.
- Check that the command actually exercised what you claim: the test count is not zero, the file you changed was included, the suite you meant is the one that ran.
- If a run is flaky, say so: how many runs, how many failed, under what conditions. Do not report the one green run.
- If a check needs something you lack (credentials, a service, a platform), do not simulate it. Mark it as not run and say why.

## Reporting honestly

Every report lists three things separately:

- **Verified**: claims with their command, commit and observed output.
- **Not run / skipped**: each check you did not perform and the reason.
- **Failed**: each check that failed, with its output, even if you believe the failure is unrelated. Say why you believe that, and how you checked.

Wording follows evidence. "Tests pass" requires a passing run. "I expect this to pass" is allowed when labelled as expectation. Never upgrade one into the other.
