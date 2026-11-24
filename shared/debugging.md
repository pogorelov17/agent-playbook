# Debugging

Fixing a symptom you do not understand creates a second bug and hides the first. Find the cause first, then fix it once.

**Who does what.** This file covers finding the cause. Fixing it is the executor's work, described in its own skills. A read-only role (see `shared/verification.md`) stops once the cause is established and reports it; it may instrument (logging, assertions, a test) only inside the throwaway copy that file describes.

## Process

Work these phases in order. Do not skip ahead because a fix "looks obvious".

### 1. Reproduce

- Write down the exact symptom: the command, the input, the observed output, the expected output.
- Reproduce it yourself, on a known commit, with the smallest command you can. If you cannot reproduce it, you cannot claim to have fixed it.
- Reduce: strip away inputs, steps and configuration until removing anything more makes the symptom disappear. The minimal case is usually half the diagnosis.
- Capture the reproduction as a failing test when the project has tests. It becomes the proof of the fix and the guard against regression.

### 2. Locate

- Read the full error message and stack trace before forming any idea. The first line is often not the cause; the deepest frame in project code often is.
- Follow the bad value backwards: where was it produced, where was it last correct? Add temporary logging or assertions at the boundary, not everywhere.
- Check what changed: `git log`, `git diff` against the last known good commit. If one exists, `git bisect` finds the breaking commit mechanically; a read-only role then runs `git bisect reset` to return to the pinned commit before reporting.
- Compare with a working example of the same thing elsewhere in the codebase. The difference is a list of suspects.

### 3. Test one hypothesis at a time

- State the hypothesis in one sentence: "X happens because Y."
- Predict what you will see if it is true, then run the one experiment that distinguishes it from the alternatives.
- Change one thing per experiment. Two changes at once tell you nothing about either.
- If the prediction fails, the hypothesis is wrong. Revert the experiment and form a new one; do not stack fixes.
- After three failed hypotheses, stop and question your assumptions: the environment, the version actually running, whether the code you are reading is the code being executed.

## Intermittent failures

- Do not call an intermittent failure fixed after one green run.
- Measure it: run it N times (for example 20 or 50) and record how many failed; when a change is under test, record the count both before and after it.
- Record the conditions under which it reproduces: ordering, parallelism, timing, load, environment, data. "Fails 3 of 50 runs when tests run in parallel; 0 of 50 serially" is a finding; "flaky" is not.
- Look for shared state, unawaited work, time and randomness, ordering assumptions and external services.

## Rules

- In your report, give the symptom, the reproduction, the cause and the evidence for it. If the cause is not found, say so and list the hypotheses you ruled out and how.
