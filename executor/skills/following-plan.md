# Following the plan

The plan records decisions already made with the owner. Following it faithfully is what lets the lead and the reviewers trust your result without redoing the reasoning. Your judgment goes into executing each step well, and into noticing when the plan is wrong.

## Before the first step

1. Read the whole spec and the whole plan before changing anything. Reason: later steps often constrain earlier ones.
2. Read the project's instruction file (`AGENTS.md` or `CLAUDE.md`) and the files the plan names.
3. Check that the plan's assumptions hold on the base commit: the files exist, the names match, the commands run. Run the existing test suite once to know the baseline. Record anything already failing before your change, with output; you are not responsible for it, but you must not hide it or confuse it with your failures.
4. If something the plan relies on is missing or different, decide whether it is an allowed deviation (below) or a stop.

## Working through steps

For each step, in order (unless the plan's dependencies allow reordering):

1. Write the test the step names, run it, and confirm it fails for the expected reason (`executor/skills/tests-first.md`).
2. Make the change the step describes.
3. Run the step's verification command. Compare its output with the expected output in the plan.
4. Run the wider test suite if the change could affect other areas.
5. Commit the step.
6. Tick the step in the plan checklist (in your working copy until the pull request exists, then in its description), and record the step's evidence (command, commit, observed output) in your running log; it goes into your report's Evidence section.

## Allowed deviations

A deviation is allowed when it does not change the result the spec and plan describe. Examples:

- a different file or module name, because the planned one collides with an existing one;
- a different order of steps, when dependencies allow;
- an extra helper, test or small refactor needed to implement a step cleanly;
- a different command to run the same check, because the planned one does not exist in this project.

Make the deviation, and record it in your report: what the plan said, what you did, why, and the effect (normally "none on the result").

## When to stop

Stop the affected part of the work and return a question to the lead when:

- the plan contradicts the spec, or the spec contradicts itself;
- following the plan would change a public interface, a data format, the architecture, or the scope in a way the spec does not state;
- a step cannot work as written and every fix you see changes the result;
- the base is not what the brief said (wrong origin, wrong commit);
- you would have to break a rule of your role to continue.

When you stop, report `NEEDS_CONTEXT` or `BLOCKED`, describe the problem precisely, give the options you see with your recommendation and the consequences of each, and say what you completed and verified meanwhile. Continue with independent steps if they are unaffected, and say so.

## Updating the pull request in a repair round

Push the new commits to the same branch; the pull request picks them up and stays a draft. Edit its description: add a section for the round listing what changed per finding, and tick any plan steps the round completes. Leave the spec and the earlier rounds as they are.
