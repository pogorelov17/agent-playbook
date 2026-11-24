# Reporting

Your report is the only thing the lead receives from you. The lead cannot see your workspace, your terminal or your reasoning. Write it so the lead can decide the next step without asking you anything.

## Format

Use this structure, in this order. Keep the headings so reports can be compared.

```
ROLE: <your role>
STATUS: DONE | DONE_WITH_CONCERNS | NEEDS_CONTEXT | BLOCKED

## Summary
One to three sentences: what was asked, what you did, the result.

## What was done
The concrete actions and outputs: files changed, branch, commit, pull request, findings, answers.

## Evidence
For each claim: the command, the commit it ran on, and the observed output (quoted).
Also list checks not run (with the reason) and checks that failed (with output).

## Deviations
Each place you departed from the brief or plan, why, and its effect on the result. "None" if none.

## Assumptions
Each minor ambiguity you resolved yourself, what you chose, and how to reverse it. "None" if none.

## Open questions
Questions only the lead or owner can answer. For each: the options, your recommendation, and the consequence of each option. "None" if none.
```

The first line is exactly the stamp, with nothing before it: no greeting, no blank line, no markdown heading marker. A report whose first line is not the stamp is rejected unread, because the lead uses the stamp to confirm which role produced the report.

## Statuses

Pick exactly one.

- `DONE` — everything asked is complete and verified. Nothing left that the lead must act on.
- `DONE_WITH_CONCERNS` — complete and verified, but you saw something the lead should weigh: a risk, a design smell, a check you could not run, an assumption that matters. Name each concern.
- `NEEDS_CONTEXT` — you cannot finish without information you lack. Say exactly what you need and why, and what you finished meanwhile.
- `BLOCKED` — you cannot proceed: a contradiction in the spec, missing access, a broken environment, a rule you would have to break. Say what blocks you, what you tried, and what would unblock you.

Do not use `DONE` to mean "I did what I could". If a part is unfinished or unverified, the status is not `DONE`.

## Writing rules

- Lead with facts the lead can act on; leave out narration of your process unless it matters to the result.
- Name things exactly: file paths with line numbers, full commit SHAs, full URLs, exact command lines.
- Quote output; do not paraphrase it.
- Keep observation and opinion apart. Mark opinion as such ("I recommend", "I believe").
- Report bad news as plainly as good news. A failed check reported early is cheap; a hidden one is expensive.
