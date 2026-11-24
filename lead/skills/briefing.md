# Briefing workers

A worker starts with nothing but its role instructions and your brief. It cannot ask a colleague, read your conversation, or see another worker's output. If the brief is incomplete, the worker either stops and asks (a wasted round) or guesses (a wrong result). Write the brief so neither happens.

## Checklist for every brief

1. **One role.** Name it, and say which stamp the report must start with. Never mix roles ("review and then fix"); dispatch two workers instead.
2. **The outcome wanted**, in one or two sentences, and how it will be judged.
3. **Inputs**: the spec and plan as read-only files (say where they are), any earlier reports the worker needs (for example review findings for a repair round), and anything else it must read.
4. **Repository**: the URL, the base branch and the exact base commit SHA. For the executor, the task branch name. For reviewers and the arbiter, the pull request URL and the exact commit to review.
5. **Permissions**: what the worker may do (read, run tests, create a branch, push to the task branch, open a draft pull request, browse the web) and what it may not.
6. **Scope limits**: what is out of scope, which files or areas must not be touched, the time or effort expected.
7. **Report format**: the stamp, the status, and any extra fields you need (for example "the word count of each bundle", "the exact head SHA").

Never include an instruction to start, spawn or delegate to other agents. If the work needs more hands, you dispatch more workers.

## Briefs per role

- **Scout**: the specific questions, numbered; the commit to examine; what you will use the answers for (so it knows what detail matters).
- **Researcher**: the questions; the decision they inform; how recent sources must be; any sources to prefer or avoid.
- **Executor**: spec, plan, repository, base commit, task branch; in a repair round, the review findings to address, and the existing pull request URL.
- **Reviewer**: spec, plan, pull request URL, exact commit. Never the other reviewer's report.
- **Arbiter**: spec, pull request URL, exact commit, both reviewers' reports (only after both are finished), the executor's response if any, and the specific disputed claims.

## Handling the status a worker returns

- `DONE` — check the evidence against the brief and the acceptance criteria. If it holds, move to the next step of the flow. If it does not hold, treat the report as `DONE_WITH_CONCERNS` at best and decide what to rerun.
- `DONE_WITH_CONCERNS` — read every concern. Decide for each: accept (and tell the owner if it affects them), fix in a new round, or take to the owner if it touches the spec. Do not ignore concerns because the status says done.
- `NEEDS_CONTEXT` — supply the missing information. If you have it, dispatch a fresh worker with the improved brief (the old worker's workspace may be gone). If only the owner has it, ask the owner. Then improve your brief template so the gap does not recur.
- `BLOCKED` — find what blocks it. If it is a contradiction or impossibility in the spec, take it to the owner with options and a recommendation. If it is environment or access, fix it and dispatch a fresh worker. Never tell a worker to break a rule to get unblocked.

In every case, also check the stamp line first: a report that does not start with the expected stamp is rejected regardless of its status.
