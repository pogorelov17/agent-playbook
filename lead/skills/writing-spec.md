# Writing a spec

The spec says what will be true when the work is done, and how anyone can check it. It is read by workers who were not in your conversation with the owner: anything not in the spec does not exist for them.

## Template

```markdown
# Spec: <short title>   (version 1)

**Goal.** One or two sentences: what changes for whom, and why.

**Non-goals.** What this work deliberately does not do, including tempting adjacent improvements.

**Decisions.**
1. <Decision the owner took, stated as a fact.> (Reason, if not obvious.)
2. ...

**Acceptance criteria.**
1. <Observable outcome.>
   Check: `<exact command>` → <what output or exit status means it passed>.
2. <Observable outcome.>
   Manual check: <steps a person performs> → <what they must see>.
```

## Writing the parts

**Goal.** State the outcome, not the activity. "Users can export a report as CSV" rather than "Implement CSV export".

**Non-goals.** List what someone might reasonably assume is included but is not. Reason: workers fill silence with their own guesses; a non-goal stops scope creep before it starts.

**Decisions.** Every answer from the clarification gate, as a declarative fact: names, formats, versions, file paths, limits, the exact values. If a value appears in the spec, workers must use it verbatim, so get it right.

**Acceptance criteria.**

- Each criterion is observable from outside: a command and its output, a file and its content, a page and what it shows.
- Each has its check: the exact command to run and the observation that means it passed ("exits 0 and prints `OK`", "the response has status 201 and a `Location` header"). If no command can check it, write an explicit manual check with steps and the expected observation.
- Each is independent and numbered, so reports can say "criterion 3: passed".
- Cover the failure paths that matter, not only the happy path: invalid input, missing permissions, empty data.
- Include "existing tests still pass" when there are existing tests.

## Keeping it short and unambiguous

- One fact per sentence. No "should", "ideally", "where possible": a requirement is either required or not in the spec.
- Use the same name for the same thing everywhere. If the endpoint is `/reports/export`, never call it "the download route" elsewhere.
- Prefer numbers to adjectives: "under 200 ms at p95 for 1 000 rows", not "fast".
- Leave out implementation detail that is not a decision. The plan says how; the spec says what and how to tell.
- Read it as a stranger would: could two competent engineers implement it differently and both claim to satisfy it? If yes, and the difference matters, add a decision or a criterion.

## Versioning

Put a version number in the title. When the owner changes anything, increment it and say what changed. Reviews and approvals refer to a spec version.
