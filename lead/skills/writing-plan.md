# Writing a plan

The plan tells the executor how to reach the spec. Write it for a capable engineer who has never seen this codebase and was not in your conversation with the owner. It fixes what has already been decided, so the executor spends effort on doing the work well, not on re-deciding it.

## What the plan fixes

- **Files**: the exact paths to create or change.
- **Names and signatures**: functions, classes, commands, flags, configuration keys, with their parameters and return types where they matter.
- **Values from the spec**: copied verbatim (formats, limits, messages, versions). Do not paraphrase a value; paraphrase creates a second, slightly different value.
- **Commands**: how to install, build and run the tests, exactly as typed.
- **Acceptance checks**: each in the spec's form, its command or its manual steps and expected observation; never replaced by a weaker command. Per-step verification commands are additional.
- **Living documents**: which ones (for example `DESIGN.md`, `README.md`) must be updated, and with what.

What the plan leaves open: anything that is cheap to change and does not affect the result. Say so ("helper names are yours") so the executor does not ask.

## Steps

A step is the smallest unit that carries its own test cycle: write a test, see it fail, make it pass, verify. Each step has:

```markdown
- [ ] **Step 3: Reject reports over the row limit**
  - Serves: acceptance criterion 4
  - Depends on: step 2
  - Test first: `tests/test_export.py::test_rejects_over_limit` — exporting 10 001 rows returns status 413 with body `{"error": "too_many_rows"}`.
  - Change: `app/export.py`, function `export_csv(rows, limit=10_000)`.
  - Verify: `python -m pytest tests/test_export.py -q` → `N passed`, including the new test.
```

Rules for steps:

- Every step names the acceptance criterion it serves. A step serving no criterion is either a missing criterion (ask the owner) or unrequested work (delete it).
- Every acceptance criterion is served by at least one step, and the last steps of each pull request run every acceptance check that applies to it on its final commit.
- State the test to write first and what it asserts, concretely enough that the executor writes the test you mean.
- State the command that verifies the step and the expected output.
- State dependencies, so the executor knows what may be reordered.
- For a step with no behaviour to test (docs, configuration, a workflow file), name an executable check that fits: a linter, a validator, a dry run, a grep for the required content.

## Shape of a good plan

- Top: the goal (see the lead role), the spec version it implements, the repository, base branch and commit, the task branch name.
- Then: a short "approach" paragraph: the design in a few sentences, so the steps make sense as a whole.
- Then: the steps, in order.
- End, per pull request when the plan is split: the pull request step (open a draft pull request with the spec and the ticked checklist in the description) and the final verification step (every acceptance check that applies to this pull request, in the spec's form, and the full test suite, on the head commit). A check that needs the pull request or hosted CI is ordered after the pull request exists.

## Splitting large work

If the plan has more steps than one reviewer can review well in one sitting, or touches unrelated areas, split it into sequential pull requests. Each slice:

- is a named group of steps in the plan, ending with its own pull request and final verification steps;
- delivers something that works and can be reviewed on its own;
- has its own subset of the spec's acceptance criteria, selected and never reworded; every criterion belongs to some slice;
- starts from the merged result of the previous slice, or from the previous slice's branch if the owner agrees to stacking.

Every brief for a slice (executor and both reviewers) names the slice and lists the acceptance criteria that apply to this pull request; a brief that lists none means all criteria of the spec apply. The last pull request of the sequence is verified and reviewed against the complete spec: its briefs list every criterion, or none.

## Before sending

Read the plan as the executor would, with only the spec beside it:

- Could you start step 1 without asking anything?
- Is every path, name and command real (confirmed in the repository or created by an earlier step)?
- Does every step have a test-first instruction and a verification command with expected output?
- Is there anything the executor must decide that changes the result? If so, decide it now.
