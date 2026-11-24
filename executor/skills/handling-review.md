# Handling review findings

In a repair round you receive the reviewers' findings through the lead. Your job is to make the code right, not to make the reviewers happy. A finding is a claim about the code; treat it like any claim: check it.

## For every finding

1. **Read it fully.** Identify the place (file and line), the claimed consequence, and the evidence offered.
2. **Check it against the code** on the current head of the branch. Reproduce it if it is reproducible: run the command, write the failing test, read the code path.
3. **Classify it:**
   - **Confirmed**: the problem is real. Fix it (test first where it has behaviour), verify, commit.
   - **Disputed**: you believe the finding is wrong. Gather reproducible evidence: a test that shows the claimed failure does not occur, the spec text that requires the current behaviour, the command output. Do not change the code for it.
   - **Unclear**: you cannot tell what is meant or cannot reproduce it. Say exactly what you tried.
4. Record the outcome per finding: fixed (commit SHA and verification output), disputed (evidence), or unclear (what you tried).

## Rules

- No agreeing for politeness. "Good catch, fixed" without checking produces changes nobody verified, and sometimes breaks correct code.
- No dismissing for convenience either. If you cannot show the finding is wrong, treat it as confirmed.
- Never close an objection yourself. You report your outcome; the reviewers re-review the new commit, and the lead decides on disputes (with the arbiter if needed).
- Return disputed findings to the lead with the evidence, in your report. Do not argue in the pull request.
- Fix the cause, not the symptom the reviewer pointed at. If the same problem exists elsewhere, fix it there too and say so.
- Keep the scope: a finding does not license unrelated changes. If you notice something unrelated, report it.
- Stay on the same branch and the same pull request. Push new commits. Do not force-push over commits the reviewers have reviewed unless the lead asks; reviewers need to see what changed since their review.
- After all fixes, rerun the full test suite and every acceptance check on the new head commit, and report that exact SHA. Both reviews will be repeated on it.
