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

Evidence takes one of three forms, each with all of its fields:

- **A command run**: the exact command and the directory it ran from; the commit (`git rev-parse HEAD`) and whether the working tree was clean (`git status --short`); the observed output, quoted verbatim: the summary line (`Ran 36 tests ... OK`), the exit code, and any warning or error lines. Trim noise, never trim failures.
- **A manual observation**: what you did, step by step, and what you saw.
- **An external source**: the link, its publication or last-updated date, and the passage you rely on, quoted.

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

The reviewer, scout, researcher and arbiter are read-only. For them, the checkout under review or study is never modified: not edited, not instrumented, not even temporarily. Running the project's existing commands there (the tests, a build) is allowed; editing, adding or removing source files is not. Reason: the checkout is the evidence base for your report and for anyone rerunning your commands, and a change, even reverted, can leak into what you observe.

When you need an experiment, for example to see whether a test really fails when the code is broken: copy the tree to a temporary directory outside the checkout, experiment there, delete the copy afterwards, and say in your report that the evidence came from a modified copy and what you modified. Nothing is committed, pushed or posted.
