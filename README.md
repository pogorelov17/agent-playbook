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

The delivery flow: the executor opens a draft pull request; two reviewers review the same commit independently. When the verdicts conflict, or a finding is disputed (or after two failed repair rounds), the arbiter rules before any repair. An upheld finding leads to a repair by a fresh executor on the same branch and two fresh reviews of the new commit; if every finding behind a `REQUEST_CHANGES` is overturned, a replacement reviewer reviews the unchanged commit; a ruling that stays unresolved goes to the owner. Only the owner merges.

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

Every `ROLE.md` has exactly these headings, in this order: `# <Role name>`, `## Who you are`, `## What you receive`, `## What you must deliver`, `## Rules`, `## You must not`, `## Report`, and no other heading of any level. Inside a section, structure with bold lead-in labels or numbered paragraphs. Skills and shared files may use sub-headings.

**The `ROLE.md` contract is about raw lines.** Agents read the raw text of their instruction file; nothing renders it. So the check works on raw lines and does not render or interpret Markdown. A *line* is what you get by splitting the file on `\n` only (after turning `\r\n` and `\r` into `\n`); a *blank* line is empty or ASCII spaces only. Each of these is an error, reported with file and line:

1. **Characters.** Any character other than `\n` and printable ASCII (0x20-0x7E): tab, other control characters, non-breaking space, byte-order mark, typographic quotes, dashes and arrows, any non-ASCII letter. The message names the code point.
2. **Hash lines.** Any line whose first non-space character is `#`, or whose first non-space characters are a list marker (`-`, `*`, `+`, or digits followed by `.` or `)`) followed by spaces and then `#`, unless it is one of the seven required heading lines, exactly, at column 0, in order, each once. This applies everywhere, inside fenced code too.
3. **Fences.** A fence line (first non-space characters three or more backticks or tildes) that does not start at column 0 or follows a list marker; a fence that is not closed by a fence of the same character, at least as long, before the end of the file.
4. **Angle brackets.** A line whose first non-space character is `<` (no raw HTML).
5. **Comments, quotes, setext underlines, indentation.** `<!--` anywhere; a block-quoted line (optional spaces, then `>`); a line that is one or more `=` and nothing else, or three or more `-` and nothing else directly after a non-blank line (put a blank line before a `---` thematic break); a line indented by four or more spaces outside fenced code.
6. **Required lines.** The ban, the first-line instruction and the stamp (below) are compared as whole raw lines and must be outside fenced code.

Every role except `lead` states, in its `ROLE.md`: the ban on starting other agents, the duty to read and follow the project's own instruction file (`AGENTS.md` or `CLAUDE.md`), and its report stamp (`ROLE: <role>`), which must be the first line of every report.

The ban is one canonical sentence (`AGENT_BAN` in `scripts/check.py`). One line outside fenced code must be exactly this sentence, optionally after a `- ` or `N. ` list marker (`N`: one to nine ASCII digits), with nothing else on the line; further text goes on the next line:

```text
You never start, spawn, schedule or delegate to other agents, sub-agents, threads, workflows or new machines, even when a tool or a built-in skill offers it.
```

The first-line instruction is also one canonical sentence (`FIRST_LINE_RULE`). Inside the `## Report` section, one line must be exactly this sentence, and the next non-blank line must be exactly the stamp `ROLE: <role>`, with no leading or trailing whitespace:

```text
The first line of every report is exactly:

ROLE: <role>
```

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
- every top-level folder that contains a `ROLE.md` (including dot-folders; only `.git` and `.github` are skipped) is a role in `team.json`;
- every bundle path is in canonical form (no `./`, `..`, `//` or leading `/`), no bundle lists a file twice, no component of a bundle path is a symbolic link, and every bundled file resolves inside the repository;
- no Markdown file (`.md` or `.markdown`, in any letter case) under a role folder or `shared/` is left out of every bundle (no orphans);
- every `ROLE.md` keeps the raw-line contract above, including exactly the required heading lines, in order, and no other line starting with `#`;
- no role or skill text contains the launcher-specific words the project bans (whole words, case-sensitive; see `FORBIDDEN` in `scripts/check.py`); texts say "isolated workspace", "the lead", "the owner" instead;
- every non-lead `ROLE.md` contains the agent-ban line and, in its `## Report` section, the first-line instruction directly followed by the stamp line;
- every model set covers every role with the right number of entries and satisfies `model_rules`, allowing only its declared exceptions; families are compared ignoring letter case and surrounding spaces;
- every `models/*.json` file is listed in `model_sets`.

The forbidden-word scan and the UTF-8 check read every Markdown file under the role folders and `shared/` and every file named in any bundle, raw, so `--print` never emits text the check did not read. Files that are not valid UTF-8, and fields of the wrong JSON type (including a model set's optional `description`, which must be a string), are reported as errors with the file and field named.

**Limits of the check.** The check guards this repository's own files against accidental damage; it is not a general Markdown linter and does not claim to classify every possible input. It checks that the ban, the instruction and the stamp are present, not what neighbouring sentences say about them; reviewers read the text. Skill and shared files have no structural checks.

CI (`.github/workflows/check.yml`) runs both commands on every pull request and on pushes to `main`.

## Changing or adding a role

To change a role, edit its `ROLE.md` or skills and run `python3 scripts/check.py`. Keep the required headings. Write for an agent that knows nothing else: imperative, specific, each non-obvious rule with a one-line reason.

To add a skill, create `<role>/skills/<name>.md` (or `shared/<name>.md`) and add it to the bundle of every role that needs it in `team.json`. An unbundled Markdown file fails the check as an orphan, and so does every Markdown file of a role folder that is not in `team.json`.

To add a role:

1. Create `<role>/ROLE.md` with the seven required headings; the title is the role name (`# Release Manager` for `release-manager`).
2. Unless it is the lead, include the common worker rules (copy them from an existing worker role), with the agent-ban line, and put the first-line instruction and the stamp line `ROLE: <role>` in the `## Report` section.
3. Add the role to `team.json` with its stamp, instances and bundle (always including `shared/reporting.md` and `shared/verification.md`).
4. Add a model for it to every file in `models/`, and add it to `model_rules` if it must run on a model different from another role.
5. Update the approved-team assertions in `tests/` (the repository test pins the six roles).
6. Run the validator and the tests.

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

`team.json` declares the rule that reviewers and the arbiter must run on a model (provider and family) different from the executor's. The lead receives the assignment as an input and also checks it against every model that actually authored commits on the pull request, across all rounds. A set may declare an exception to a rule, with a reason. `codex-only` declares one: reviewer #2 shares the executor's family (`sol`), because that provider set has too few distinct families; it runs at a different effort in its own isolated workspace.

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
