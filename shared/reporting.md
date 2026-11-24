# Reporting

This is the format in which every worker reports to the lead. The lead requires it from workers; the lead's own reports to the owner follow the lead role and carry no stamp.

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
Three lists:
- Verified: each claim with its evidence, in the form shared/verification.md gives for it.
- Not run: each check you did not perform, and the reason.
- Failed: each check that failed, with its output.

## Deviations
Each place you departed from the brief or plan, why, and its effect on the result. "None" if none.

## Assumptions
Each minor ambiguity you resolved yourself, what you chose, and how to reverse it. "None" if none.

## Open questions
Questions only the lead or owner can answer. For each: the options, your recommendation, and the consequence of each option. "None" if none.
```

Your role's Report section names what else your report carries. A line it places after STATUS goes there; everything else goes under "What was done", in the order your role gives, except commands and their output, which go under "Evidence".

The first line is exactly the stamp, with nothing before it: no greeting, no blank line, no markdown heading marker. A report whose first line is not the stamp is rejected unread, because the lead uses the stamp to confirm which role produced the report.

## Statuses

Pick exactly one. The status says whether the work you were assigned is complete, not whether its outcome is good or whether the lead must act next: a finished review is `DONE` whether the verdict is `APPROVE` or `REQUEST_CHANGES`. A completed review always carries exactly one verdict; a `NEEDS_CONTEXT` or `BLOCKED` review report is interim, carries no verdict, and names exactly what is missing.

- `DONE` — the assigned work is complete and verified.
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
