# Tests first

A test you never saw fail proves nothing: it may not run, may test the wrong thing, or may pass for a reason unrelated to your code. Writing it first, and watching it fail, is how you know it can catch the bug it is meant to catch.

## The cycle

1. **Red.** Write one test for the next small behaviour. Run it. It must fail.
2. **Check the reason.** Read the failure. It must fail because the behaviour is missing or wrong: an assertion on the expected value, a "not implemented", a missing function the test calls. It must not fail because of a broken setup: a syntax error in the test, an import error from a typo, a missing fixture, a wrong path, the test not being collected at all. A broken setup is not a valid failure; fix the setup and run again until the failure is the right one.
3. **Green.** Write the minimum code that makes the test pass. Resist adding behaviour the test does not demand; the next test will demand it.
4. **Run the suite.** The new test passes, and no other test broke.
5. **Tidy.** Improve names, remove duplication, simplify, with all tests still green. Run them again after tidying.
6. **Commit.**

Then the next behaviour. Keep cycles short: minutes, not hours.

## Choosing tests

- Test behaviour through the public interface the spec describes, not private details. Reason: tests tied to internals break on every refactor and miss what users see.
- Cover the acceptance criteria first, then the edge cases that matter: empty input, boundaries, invalid input, error paths, permissions.
- One reason to fail per test. A name that says what is expected (`test_rejects_export_over_row_limit`).
- Use the project's existing test framework and conventions. Add a dependency only if the plan allows it.
- Make tests deterministic: no dependence on wall-clock time, ordering, network or randomness without control.

## Changes with no behaviour

For documentation, configuration, a CI workflow or similar, there is no behaviour to unit-test. Pick an executable check that fits, and still see it fail first where possible:

- a validator or schema check for a config or data file;
- a linter or a dry run (`--check`, `--dry-run`, a syntax check of the workflow);
- a build of the documentation;
- a script or `grep` that asserts the required content is present.

Report which check you chose and its output.

## Never

- Never weaken an assertion, mark a test skipped or expected-to-fail, delete a test, or widen a tolerance to get green. If a test is wrong, say why, fix it deliberately, and report it as a deviation.
- Never write the code first and the test after, then claim test-first.
- Never treat "the test passed the first time" as success without making it fail once (for example by temporarily breaking the code) to prove it can.
