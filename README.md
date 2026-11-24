# agent-playbook
Roles and skills for a team of AI coding agents — who does what, and how.

A **lead** talks to the human owner, clarifies the task, writes a spec and a plan, and dispatches **workers**. Each worker runs alone in its own isolated workspace, with no shared memory and no view of the others. This repository holds the instructions each of them reads. It is plain Markdown and JSON with no tie to any particular launcher: any tool can assemble one instruction file per role from it.

## Roles

| Role | Purpose | Instances |
| --- | --- | --- |
| `lead` | Talks to the owner; clarification gate, spec, plan, goal, dispatch, delivery. Never edits code, never merges. | 1 |
| `executor` | Implements the plan test-first on a task branch and opens a draft pull request. | 1 |
| `reviewer` | Independently reviews one exact commit against the spec; returns `APPROVE` or `REQUEST_CHANGES`. | 2 |
| `scout` | Read-only code discovery; answers specific questions with paths and line numbers. | 1 |
| `researcher` | Answers questions that need outside sources, with links, dates and confidence. | 1 |
| `arbiter` | Settles disputed review claims by reproduction; cannot waive an approval. | 1 |

The delivery flow: the executor opens a draft pull request; two reviewers on different models review the same commit independently; if either requests changes, a fresh executor fixes on the same branch and both reviews repeat; the arbiter steps in on conflicts or after two failed repair rounds; only the owner merges.

## Layout

```
team.json                 team description: bundles, stamps, model rules, model sets
models/                   model sets (codex-only, claude-only, codex+claude)
lead/ROLE.md              one folder per role, each with ROLE.md ...
lead/skills/*.md          ... and, where the role has them, its own skills
executor/ reviewer/ scout/ researcher/ arbiter/
shared/                   skills used by several roles (verification, debugging, reporting)
scripts/check.py          validator and bundle printer (Python 3.10+, standard library only)
tests/                    unit tests for the validator
.github/workflows/        CI: runs the validator and the tests
```

Every `ROLE.md` has exactly these headings, in this order: `# <Role name>`, `## Who you are`, `## What you receive`, `## What you must deliver`, `## Rules`, `## You must not`, `## Report`. Deeper headings (`###`) inside sections are free.

Every role except `lead` states, in its `ROLE.md`: the ban on starting other agents, the duty to read and follow the project's own instruction file (`AGENTS.md` or `CLAUDE.md`), and its report stamp (`ROLE: <role>`), which must be the first line of every report.

## How a bundle is assembled

`team.json` lists, per role, the ordered files of its **bundle**:

```json
"executor": {
  "stamp": "ROLE: executor",
  "instances": 1,
  "bundle": [
    "executor/ROLE.md",
    "executor/skills/following-plan.md",
    "executor/skills/tests-first.md",
    "executor/skills/handling-review.md",
    "shared/verification.md",
    "shared/debugging.md",
    "shared/reporting.md"
  ]
}
```

A bundle always starts with the role's `ROLE.md`, then the role's own skills, then the shared files it needs. The instruction file for a role is these files concatenated in that order. A launcher loads it into the agent's context before the agent does anything. `instances: 2` means two agents with the same instructions run independently.

To see exactly what an agent receives:

```sh
python3 scripts/check.py --print executor > executor.md   # word count on stderr
```

Each file in the output is preceded by an HTML comment naming it, e.g. `<!-- file: executor/ROLE.md -->`.

## Validating

```sh
python3 scripts/check.py                    # exits 0 when the playbook is valid
python3 -m unittest discover -s tests       # tests for the validator
```

`check.py` verifies that:

- `team.json` matches the format (schema 1; each role has stamp `ROLE: <name>`, a positive `instances`, and a bundle that starts with its `ROLE.md`, then its own files, then `shared/` files);
- every file it names exists, including the model sets;
- no Markdown file under a role folder or `shared/` is left out of every bundle (no orphans);
- every `ROLE.md` has the required headings, in order;
- no role or skill text contains the launcher-specific words the project bans (see `FORBIDDEN` in `scripts/check.py`); texts say "isolated workspace", "the lead", "the owner" instead;
- every non-lead `ROLE.md` contains the agent-ban sentence (`You never start, spawn, schedule or delegate to other agents`) and a line consisting of exactly its stamp;
- every model set covers every role with the right number of entries and satisfies `model_rules`, allowing only its declared exceptions.

CI (`.github/workflows/check.yml`) runs both commands on every pull request and on pushes to `main`.

## Changing or adding a role

To change a role, edit its `ROLE.md` or skills and run `python3 scripts/check.py`. Keep the required headings. Write for an agent that knows nothing else: imperative, specific, each non-obvious rule with a one-line reason.

To add a skill, create `<role>/skills/<name>.md` (or `shared/<name>.md`) and add it to the bundle of every role that needs it in `team.json`. An unbundled file fails the check as an orphan.

To add a role:

1. Create `<role>/ROLE.md` with the seven required headings; the title is the role name (`# Release Manager` for `release-manager`).
2. Unless it is the lead, include the common worker rules (copy them from an existing worker role), with the agent-ban sentence and a line with exactly `ROLE: <role>`.
3. Add the role to `team.json` with its stamp, instances and bundle (always including `shared/reporting.md` and `shared/verification.md`).
4. Add a model for it to every file in `models/`, and add it to `model_rules` if it must run on a model different from another role.
5. Run the validator and the tests.

## Model sets

A model set picks a provider (`codex` or `claude`), a model family and an effort for each role; a launcher resolves the family to its newest release. A role with two instances has a list of two entries.

| Role | `codex-only` | `claude-only` | `codex+claude` |
| --- | --- | --- | --- |
| lead | codex astra high | claude opus high | codex astra high |
| executor | codex sol medium | claude opus high | claude opus high |
| reviewer #1 | codex astra high | claude fable high | claude fable high |
| reviewer #2 | codex sol high | claude sonnet high | codex astra high |
| scout | codex luna low | claude haiku medium | claude haiku medium |
| researcher | codex sol high | claude opus high | codex sol high |
| arbiter | codex astra xhigh | claude fable high | codex astra xhigh |

`team.json` declares the rule that reviewers and the arbiter must run on a model (provider and family) different from the executor's, so the change is never judged by the model that wrote it. A set may declare an exception to a rule, with a reason. `codex-only` declares one: reviewer #2 shares the executor's family (`sol`), because that provider set has too few distinct families; it runs at a different effort in its own isolated workspace.

A model set file looks like this (abridged):

```json
{
  "schema": 1,
  "name": "codex-only",
  "roles": {
    "executor": {"provider": "codex", "family": "sol", "effort": "medium"},
    "reviewer": [
      {"provider": "codex", "family": "astra", "effort": "high"},
      {"provider": "codex", "family": "sol", "effort": "high"}
    ]
  },
  "exceptions": [
    {"role": "reviewer", "instance": 2, "must_differ_from": "executor", "reason": "..."}
  ]
}
```

An exception that no longer matches a violation fails the check, so stale exceptions do not linger.

## Credits

Several methods here (clarifying before building, writing plans for an engineer with no context, test-first development, systematic debugging, verification before claiming completion, independent review) are adapted in spirit from the open-source [obra/superpowers](https://github.com/obra/superpowers) project, under the MIT license. The texts in this repository are written independently; none of its text is copied.

## License

MIT. See [LICENSE](LICENSE).
