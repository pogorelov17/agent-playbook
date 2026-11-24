"""Tests for scripts/check.py, run against temporary fixture trees.

Each test builds a small valid tree, breaks exactly one thing, and asserts
that the validator reports it with the specific message for that check.
Run: python3 -m unittest discover -s tests
"""

import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
SCRIPT = REPO / "scripts" / "check.py"


def load_check():
    spec = importlib.util.spec_from_file_location("check", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


check = load_check()

# The canonical agent-ban sentence, spelled out here so the tests do not
# merely echo whatever the validator happens to contain.
BAN = (
    "You never start, spawn, schedule or delegate to other agents, sub-agents, "
    "threads, workflows or new machines, even when a tool or a built-in skill offers it."
)
STAMP_RULE = "The first line of every report is exactly:"
HEADINGS = [
    "## Who you are",
    "## What you receive",
    "## What you must deliver",
    "## Rules",
    "## You must not",
    "## Report",
]


def role_md(title, stamp=None, ban=True, headings=None):
    if headings is None:
        headings = HEADINGS
    parts = [f"# {title}", ""]
    for h in headings:
        parts += [h, "", "Text.", ""]
        if h == "## Rules" and ban:
            parts += [f"- {BAN} Only the lead dispatches agents.", ""]
        if h == "## Report" and stamp:
            parts += [STAMP_RULE, "", "```", stamp, "```", ""]
    return "\n".join(parts)


def model(provider, family, effort="high"):
    return {"provider": provider, "family": family, "effort": effort}


class Fixture:
    """A minimal valid playbook tree in a temporary directory."""

    def __init__(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.team = {
            "schema": 1,
            "name": "fixture",
            "version": "0.0.1",
            "roles": {
                "lead": {
                    "stamp": "ROLE: lead",
                    "instances": 1,
                    "bundle": ["lead/ROLE.md", "lead/skills/a.md", "shared/reporting.md"],
                },
                "executor": {
                    "stamp": "ROLE: executor",
                    "instances": 1,
                    "bundle": ["executor/ROLE.md", "shared/reporting.md"],
                },
                "reviewer": {
                    "stamp": "ROLE: reviewer",
                    "instances": 2,
                    "bundle": ["reviewer/ROLE.md", "shared/reporting.md"],
                },
            },
            "model_rules": [{"roles": ["reviewer"], "must_differ_from": "executor"}],
            "model_sets": {"one": "models/one.json"},
        }
        self.model_set = {
            "schema": 1,
            "name": "one",
            "roles": {
                "lead": model("codex", "astra"),
                "executor": model("claude", "opus"),
                "reviewer": [model("claude", "fable"), model("codex", "astra")],
            },
        }
        self.write("lead/ROLE.md", role_md("Lead", ban=False))
        self.write("lead/skills/a.md", "# Skill A\n\n### Sub-headings are fine in skills\n\nText.\n")
        self.write("executor/ROLE.md", role_md("Executor", "ROLE: executor"))
        self.write("reviewer/ROLE.md", role_md("Reviewer", "ROLE: reviewer"))
        self.write("shared/reporting.md", "# Reporting\n\nText.\n")
        self.save()

    def write(self, rel, text):
        path = self.root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        if isinstance(text, bytes):
            path.write_bytes(text)
        else:
            path.write_text(text, encoding="utf-8")

    def save(self):
        self.write("team.json", json.dumps(self.team, indent=2))
        self.write("models/one.json", json.dumps(self.model_set, indent=2))

    def errors(self):
        self.save()
        return check.validate(self.root)

    def cleanup(self):
        self._tmp.cleanup()


class ValidatorTest(unittest.TestCase):
    def setUp(self):
        self.fx = Fixture()
        self.addCleanup(self.fx.cleanup)

    def assertError(self, fragment, errors=None):
        if errors is None:
            errors = self.fx.errors()
        self.assertTrue(
            any(fragment in e for e in errors),
            f"expected an error containing {fragment!r}, got {errors!r}",
        )
        return errors

    def assertNoError(self, fragment, errors):
        self.assertFalse(
            any(fragment in e for e in errors),
            f"expected no error containing {fragment!r}, got {errors!r}",
        )

    def executor_role(self, old, new):
        text = role_md("Executor", "ROLE: executor")
        self.assertIn(old, text)
        self.fx.write("executor/ROLE.md", text.replace(old, new))

    # --- baseline ---------------------------------------------------------

    def test_valid_fixture_has_no_errors(self):
        self.assertEqual(self.fx.errors(), [])

    # --- team.json format -------------------------------------------------

    def test_invalid_json(self):
        self.fx.save()
        (self.fx.root / "team.json").write_text("{not json", encoding="utf-8")
        errors = check.validate(self.fx.root)
        self.assertError("team.json: invalid JSON", errors)

    def test_wrong_schema_version(self):
        self.fx.team["schema"] = 2
        self.assertError("team.json: schema must be 1, got 2")

    def test_schema_true_is_not_1(self):
        self.fx.team["schema"] = True
        self.assertError("team.json: schema must be 1, got True")

    def test_model_set_schema_true_is_not_1(self):
        self.fx.model_set["schema"] = True
        self.assertError("models/one.json: schema must be 1")

    def test_stamp_must_match_role(self):
        self.fx.team["roles"]["executor"]["stamp"] = "ROLE: builder"
        self.assertError("roles.executor.stamp must be 'ROLE: executor', got 'ROLE: builder'")

    def test_bundle_must_start_with_role_md(self):
        self.fx.team["roles"]["executor"]["bundle"].reverse()
        self.assertError("roles.executor.bundle must start with executor/ROLE.md")

    def test_own_files_before_shared(self):
        self.fx.write("executor/skills/x.md", "# X\n")
        self.fx.team["roles"]["executor"]["bundle"].append("executor/skills/x.md")
        self.assertError(
            "roles.executor.bundle: own file executor/skills/x.md must come before shared files"
        )

    def test_foreign_role_file_in_bundle(self):
        self.fx.team["roles"]["executor"]["bundle"].insert(1, "lead/skills/a.md")
        self.assertError("roles.executor.bundle: lead/skills/a.md is neither under executor/ nor shared/")

    def test_duplicate_bundle_entry(self):
        self.fx.team["roles"]["executor"]["bundle"].append("shared/reporting.md")
        self.assertError("roles.executor.bundle lists shared/reporting.md twice")

    def test_instances_must_be_positive_int(self):
        self.fx.team["roles"]["executor"]["instances"] = 0
        self.assertError("roles.executor.instances must be a positive integer, got 0")

    def test_lead_role_required(self):
        del self.fx.team["roles"]["lead"]
        self.fx.model_set["roles"].pop("lead")
        self.assertError("roles must include 'lead'")

    def test_roles_given_as_list(self):
        self.fx.team["roles"] = list(self.fx.team["roles"].values())
        self.assertError("team.json: roles must be a non-empty object")

    def test_list_where_string_expected(self):
        cases = [
            ("team name", lambda fx: fx.team.__setitem__("name", ["fixture"]),
             "team.json: name must be a non-empty string"),
            ("rule target", lambda fx: fx.team["model_rules"][0].__setitem__("must_differ_from", ["executor"]),
             "team.json: model_rules[1].must_differ_from must be a role name"),
            ("rule roles", lambda fx: fx.team["model_rules"][0].__setitem__("roles", [["reviewer"]]),
             "team.json: model_rules[1].roles: each entry must be a role name"),
            ("model set path", lambda fx: fx.team["model_sets"].__setitem__("one", ["models/one.json"]),
             "team.json: model_sets.one must be a relative path inside the repository"),
            ("provider", lambda fx: fx.model_set["roles"].__setitem__("lead", model(["codex"], "astra")),
             "models/one.json: lead: provider must be one of"),
            ("effort", lambda fx: fx.model_set["roles"].__setitem__("lead", model("codex", "astra", ["high"])),
             "models/one.json: lead: effort must be one of"),
            ("family", lambda fx: fx.model_set["roles"].__setitem__("lead", model("codex", ["astra"])),
             "models/one.json: lead: family must be a non-empty string"),
            ("exception role", lambda fx: fx.model_set.__setitem__("exceptions", [
                {"role": ["reviewer"], "instance": 2, "must_differ_from": "executor", "reason": "R."}]),
             "models/one.json: exceptions[1]: role must be a role name"),
            ("exception target", lambda fx: fx.model_set.__setitem__("exceptions", [
                {"role": "reviewer", "instance": 2, "must_differ_from": ["executor"], "reason": "R."}]),
             "models/one.json: exceptions[1]: must_differ_from must be a role name"),
        ]
        for label, mutate, fragment in cases:
            with self.subTest(label):
                fx = Fixture()
                self.addCleanup(fx.cleanup)
                mutate(fx)
                self.assertError(fragment, fx.errors())

    def test_invalid_role_does_not_turn_its_files_into_orphans(self):
        self.fx.team["roles"]["executor"]["stamp"] = "ROLE: builder"
        self.fx.team["roles"]["executor"]["bundle"].insert(1, "executor/skills/x.md")
        self.fx.write("executor/skills/x.md", "# X\n")
        self.executor_role("## Rules\n", "## Rule\n")
        errors = self.assertError("roles.executor.stamp must be 'ROLE: executor'")
        self.assertNoError("orphan", errors)
        # The role's own file problems are still reported.
        self.assertError("executor/ROLE.md: headings must be exactly", errors)

    # --- encoding ---------------------------------------------------------

    def test_non_utf8_markdown(self):
        self.fx.write("lead/skills/a.md", b"# Skill A\n\n\xff\xfe\n")
        self.assertError("lead/skills/a.md: not valid UTF-8")

    def test_non_utf8_role_md(self):
        self.fx.write("executor/ROLE.md", role_md("Executor", "ROLE: executor").encode() + b"\xff\n")
        self.assertError("executor/ROLE.md: not valid UTF-8")

    def test_non_utf8_team_json(self):
        self.fx.save()
        (self.fx.root / "team.json").write_bytes(b'{"schema": 1, "name": "\xff"}')
        errors = check.validate(self.fx.root)
        self.assertError("team.json: not valid UTF-8", errors)

    def test_non_utf8_model_set(self):
        self.fx.save()
        (self.fx.root / "models/one.json").write_bytes(b'{"schema": 1, "name": "\xff"}')
        self.assertError("models/one.json: not valid UTF-8", check.validate(self.fx.root))

    # --- files ------------------------------------------------------------

    def test_missing_bundle_file(self):
        # Inserted where ordering is valid, so only the existence check can fire.
        self.fx.team["roles"]["lead"]["bundle"].insert(2, "lead/skills/missing.md")
        self.assertEqual(
            self.fx.errors(),
            ["team.json: roles.lead.bundle names lead/skills/missing.md, which does not exist"],
        )

    def test_missing_role_md(self):
        self.fx.save()
        (self.fx.root / "executor/ROLE.md").unlink()
        errors = check.validate(self.fx.root)
        self.assertError(
            "team.json: roles.executor.bundle names executor/ROLE.md, which does not exist", errors
        )

    def test_missing_model_set_file(self):
        self.fx.team["model_sets"]["two"] = "models/two.json"
        self.assertError("model set 'two' names models/two.json, which does not exist")

    def test_orphan_file(self):
        self.fx.write("lead/skills/orphan.md", "# Orphan\n")
        self.assertError("lead/skills/orphan.md: orphan file, not listed in any bundle")

    def test_orphan_in_shared(self):
        self.fx.write("shared/unused.md", "# Unused\n")
        self.assertError("shared/unused.md: orphan file, not listed in any bundle")

    def test_orphan_with_other_markdown_extensions(self):
        self.fx.write("lead/skills/upper.MD", "# Upper\n")
        self.fx.write("shared/long.markdown", "# Long\n")
        errors = self.assertError("lead/skills/upper.MD: orphan file")
        self.assertError("shared/long.markdown: orphan file", errors)

    def test_undeclared_role_folder(self):
        self.fx.write("tester/ROLE.md", role_md("Tester", "ROLE: tester") + "\nRun it in a VM.\n")
        self.fx.write("tester/skills/t.md", "# T\n")
        errors = self.assertError("tester/ROLE.md: tester/ has a ROLE.md but is not a role in team.json")
        self.assertError("tester/ROLE.md: orphan file", errors)
        self.assertError("tester/skills/t.md: orphan file", errors)
        self.assertError("forbidden word 'VM'", errors)

    def test_role_removed_from_manifests_but_folder_left(self):
        del self.fx.team["roles"]["reviewer"]
        self.fx.team["model_rules"] = []
        del self.fx.model_set["roles"]["reviewer"]
        errors = self.assertError("reviewer/ROLE.md: reviewer/ has a ROLE.md but is not a role in team.json")
        self.assertError("reviewer/ROLE.md: orphan file", errors)

    def test_undeclared_role_headings_are_checked(self):
        self.fx.write("tester/ROLE.md", "# Tester\n\n## Who you are\n")
        self.assertError("tester/ROLE.md: headings must be exactly")

    # --- ROLE.md headings -------------------------------------------------

    def test_missing_heading(self):
        headings = [h for h in HEADINGS if h != "## You must not"]
        self.fx.write("executor/ROLE.md", role_md("Executor", "ROLE: executor", headings=headings))
        self.assertError("executor/ROLE.md: headings must be exactly")

    def test_misordered_heading(self):
        headings = list(HEADINGS)
        headings[1], headings[2] = headings[2], headings[1]
        self.fx.write("executor/ROLE.md", role_md("Executor", "ROLE: executor", headings=headings))
        self.assertError("executor/ROLE.md: headings must be exactly")

    def test_wrong_title_heading(self):
        self.fx.write("executor/ROLE.md", role_md("Builder", "ROLE: executor"))
        self.assertError("executor/ROLE.md: headings must be exactly")

    def test_heading_text_is_exact(self):
        self.executor_role("## Rules\n", "## rules\n")
        self.assertError("executor/ROLE.md: headings must be exactly")

    def test_extra_h2_heading(self):
        self.fx.write("executor/ROLE.md", role_md("Executor", "ROLE: executor") + "\n## Extra\n\nText.\n")
        self.assertError("executor/ROLE.md: headings must be exactly")

    def test_subheading_in_role_md_rejected(self):
        self.executor_role("## Rules\n", "## Rules\n\n### Detail\n")
        self.assertError("executor/ROLE.md: headings must be exactly")

    def test_deep_subheading_in_role_md_rejected(self):
        self.executor_role("## Rules\n", "## Rules\n\n###### Detail\n")
        self.assertError("executor/ROLE.md: headings must be exactly")

    def test_setext_headings_in_role_md_rejected(self):
        for underline in ("=====", "-----"):
            with self.subTest(underline):
                self.executor_role("## Rules\n", f"## Rules\n\nDetail\n{underline}\n")
                self.assertError("executor/ROLE.md: headings must be exactly")

    def test_thematic_break_is_not_a_heading(self):
        self.executor_role("## Rules\n", "## Rules\n\n---\n")
        self.assertEqual(self.fx.errors(), [])

    def test_code_fence_contents_are_not_headings(self):
        self.executor_role(
            "## Rules\n",
            "## Rules\n\n```markdown\n# not a heading\n## nor this\nNor\n===\n```\n\n"
            "~~~\n### nor this\n~~~\n",
        )
        self.assertEqual(self.fx.errors(), [])

    def test_one_line_backtick_span_does_not_open_a_fence(self):
        self.executor_role("## Rules\n", "## Rules\n\n```inline code```\n\n## Extra\n")
        self.assertError("executor/ROLE.md: headings must be exactly")

    def test_shorter_fence_does_not_close_longer_one(self):
        self.executor_role("## Rules\n", "## Rules\n\n````\n```\n## inside\n```\n````\n")
        self.assertEqual(self.fx.errors(), [])

    def test_other_fence_character_does_not_close(self):
        self.executor_role("## Rules\n", "## Rules\n\n```\n~~~\n## inside\n~~~\n```\n")
        self.assertEqual(self.fx.errors(), [])

    def test_fence_is_closed_after_matching_line(self):
        self.executor_role("## Rules\n", "## Rules\n\n````\ncode\n`````\n\n## Extra\n")
        self.assertError("executor/ROLE.md: headings must be exactly")

    # --- forbidden words --------------------------------------------------

    def test_forbidden_word_in_role(self):
        self.fx.write("executor/ROLE.md", role_md("Executor", "ROLE: executor") + "\nRun it in a VM.\n")
        self.assertError("executor/ROLE.md:")
        self.assertError("forbidden word 'VM'")

    def test_forbidden_word_in_skill(self):
        self.fx.write("lead/skills/a.md", "# Skill A\n\nUse Boat to launch.\n")
        self.assertError("lead/skills/a.md:3: forbidden word 'Boat'")

    def test_forbidden_word_plural_and_t3(self):
        self.fx.write("shared/reporting.md", "# Reporting\n\nTwo VMs on T3.\n")
        errors = self.assertError("shared/reporting.md:3: forbidden word 'VMs'")
        self.assertError("shared/reporting.md:3: forbidden word 'T3'", errors)

    def test_forbidden_words_only_as_whole_words(self):
        self.fx.write("shared/reporting.md", "# Reporting\n\nA boathouse, VMware, T35, sVM.\n")
        self.assertEqual(self.fx.errors(), [])

    def test_forbidden_words_are_case_sensitive(self):
        self.fx.write("shared/reporting.md", "# Reporting\n\nRow the boat; a vm, vms, t3 or BOAT.\n")
        self.assertEqual(self.fx.errors(), [])

    def test_forbidden_word_in_undeclared_markdown_file(self):
        self.fx.write("shared/notes.markdown", "Use T3.\n")
        self.assertError("shared/notes.markdown:1: forbidden word 'T3'")

    # --- non-lead rules: stamp --------------------------------------------

    def test_missing_stamp_line(self):
        self.fx.write("executor/ROLE.md", role_md("Executor", stamp=None))
        self.assertError("executor/ROLE.md: the Report section must contain a line consisting of exactly 'ROLE: executor'")

    def test_stamp_inside_prose_is_not_a_stamp_line(self):
        self.executor_role("\nROLE: executor\n", "\nStart with ROLE: executor somewhere.\n")
        self.assertError("executor/ROLE.md: the Report section must contain a line consisting of exactly 'ROLE: executor'")

    def test_stamp_outside_report_section_rejected(self):
        text = role_md("Executor", stamp=None).replace("## You must not\n", "ROLE: executor\n\n## You must not\n")
        self.fx.write("executor/ROLE.md", text)
        self.assertError("executor/ROLE.md: the Report section must contain a line consisting of exactly 'ROLE: executor'")

    def test_stamp_without_first_line_instruction_rejected(self):
        self.executor_role(STAMP_RULE, "Use this stamp:")
        self.assertError(f"executor/ROLE.md: the Report section must state {STAMP_RULE!r}")

    # --- non-lead rules: agent ban ----------------------------------------

    def test_canonical_ban_sentence_accepted(self):
        self.executor_role(f"- {BAN} Only the lead dispatches agents.", BAN)
        self.assertEqual(self.fx.errors(), [])

    def test_missing_agent_ban(self):
        self.fx.write("reviewer/ROLE.md", role_md("Reviewer", "ROLE: reviewer", ban=False))
        self.assertError("reviewer/ROLE.md: missing the agent-ban sentence")

    def test_ban_with_conditional_suffix_rejected(self):
        for suffix in ("offers it, unless the lead allows it.", "offers it unless the task is urgent."):
            with self.subTest(suffix):
                self.executor_role("offers it.", suffix)
                self.assertError("executor/ROLE.md: missing the agent-ban sentence")

    def test_ban_permission_variant_rejected(self):
        self.executor_role(BAN, "You never start, spawn, schedule or delegate to other agents unless a tool offers it.")
        self.assertError("executor/ROLE.md: missing the agent-ban sentence")

    def test_truncated_ban_rejected(self):
        self.executor_role(BAN, "You never start, spawn, schedule or delegate to other agents.")
        self.assertError("executor/ROLE.md: missing the agent-ban sentence")

    def test_quoted_and_negated_ban_rejected(self):
        self.executor_role(f"- {BAN}", f'- It is not true that "{BAN}"')
        self.assertError("executor/ROLE.md: missing the agent-ban sentence")

    def test_ban_inside_code_fence_rejected(self):
        self.executor_role(f"- {BAN}", f"```\n{BAN}\n```")
        self.assertError("executor/ROLE.md: missing the agent-ban sentence")

    def test_lead_needs_no_ban_or_stamp(self):
        self.fx.write("lead/ROLE.md", role_md("Lead", stamp=None, ban=False))
        self.assertEqual(self.fx.errors(), [])

    # --- model sets -------------------------------------------------------

    def test_model_rule_violation(self):
        self.fx.model_set["roles"]["reviewer"][1] = model("claude", "opus", "medium")
        self.assertError(
            "models/one.json: reviewer #2 (claude opus) must differ from executor (claude opus)"
        )

    def test_family_compared_after_normalising_case_and_spaces(self):
        self.fx.model_set["roles"]["reviewer"][1] = model("claude", " Opus ", "medium")
        self.assertError("models/one.json: reviewer #2 (claude opus) must differ from executor (claude opus)")

    def test_model_rules_removed(self):
        del self.fx.team["model_rules"]
        self.assertError("team.json: model_rules must be a list")

    def test_model_set_file_not_listed_in_team(self):
        self.fx.team["model_sets"] = {}
        self.fx.team["model_sets"]["one"] = "models/one.json"
        self.fx.save()
        two = dict(self.fx.model_set, name="two")
        self.fx.write("models/two.json", json.dumps(two))
        errors = check.validate(self.fx.root)
        self.assertError("models/two.json: model set file is not listed in team.json model_sets", errors)

    def test_model_rule_exception_allows_violation(self):
        self.fx.model_set["roles"]["reviewer"][1] = model("claude", "opus", "medium")
        self.fx.model_set["exceptions"] = [
            {
                "role": "reviewer",
                "instance": 2,
                "must_differ_from": "executor",
                "reason": "Too few families in this provider set.",
            }
        ]
        self.assertEqual(self.fx.errors(), [])

    def test_exception_without_reason(self):
        self.fx.model_set["roles"]["reviewer"][1] = model("claude", "opus", "medium")
        self.fx.model_set["exceptions"] = [
            {"role": "reviewer", "instance": 2, "must_differ_from": "executor", "reason": ""}
        ]
        self.assertError("models/one.json: exceptions[1]: reason must be a non-empty string")

    def test_unused_exception(self):
        self.fx.model_set["exceptions"] = [
            {"role": "reviewer", "instance": 1, "must_differ_from": "executor", "reason": "Stale."}
        ]
        self.assertError("models/one.json: unused exception for reviewer #1 vs executor")

    def test_instance_count_must_match(self):
        self.fx.model_set["roles"]["reviewer"] = model("claude", "fable")
        self.assertError("models/one.json: reviewer must be a list of 2 entries (instances: 2)")

    def test_model_set_missing_role(self):
        del self.fx.model_set["roles"]["executor"]
        self.assertError("models/one.json: role 'executor' has no model")

    def test_unknown_provider(self):
        self.fx.model_set["roles"]["lead"] = model("other", "astra")
        self.assertError("models/one.json: lead: provider must be one of")

    def test_unknown_effort(self):
        self.fx.model_set["roles"]["lead"] = model("codex", "astra", "extreme")
        self.assertError("models/one.json: lead: effort must be one of")


class CliTest(unittest.TestCase):
    def setUp(self):
        self.fx = Fixture()
        self.addCleanup(self.fx.cleanup)

    def run_cli(self, *args):
        return subprocess.run(
            [sys.executable, str(SCRIPT), "--root", str(self.fx.root), *args],
            capture_output=True,
            text=True,
        )

    def test_exit_zero_when_valid(self):
        result = self.run_cli()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_exit_nonzero_when_invalid(self):
        self.fx.write("shared/unused.md", "# Unused\n")
        result = self.run_cli()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("shared/unused.md", result.stdout + result.stderr)

    def test_print_bundle(self):
        result = self.run_cli("--print", "lead")
        self.assertEqual(result.returncode, 0, result.stderr)
        out = result.stdout
        markers = [line for line in out.splitlines() if line.startswith("<!--")]
        self.assertEqual(
            markers,
            [
                "<!-- file: lead/ROLE.md -->",
                "<!-- file: lead/skills/a.md -->",
                "<!-- file: shared/reporting.md -->",
            ],
        )
        self.assertLess(out.index("# Lead"), out.index("# Skill A"))
        self.assertLess(out.index("# Skill A"), out.index("# Reporting"))
        self.assertRegex(result.stderr, r"lead: \d+ words")

    def test_print_unknown_role(self):
        result = self.run_cli("--print", "nobody")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("nobody", result.stderr)


class RepositoryTest(unittest.TestCase):
    """The real repository passes its own validator, with the team the owner approved."""

    @classmethod
    def setUpClass(cls):
        cls.team = json.loads((REPO / "team.json").read_text(encoding="utf-8"))

    def test_repository_is_valid(self):
        self.assertEqual(check.validate(REPO), [])

    def test_roles_and_instances(self):
        instances = {name: spec["instances"] for name, spec in self.team["roles"].items()}
        self.assertEqual(
            instances,
            {"lead": 1, "executor": 1, "reviewer": 2, "scout": 1, "researcher": 1, "arbiter": 1},
        )

    def test_shared_files_per_bundle(self):
        roles = self.team["roles"]
        for name, spec in roles.items():
            with self.subTest(name):
                self.assertIn("shared/reporting.md", spec["bundle"])
                self.assertIn("shared/verification.md", spec["bundle"])
        for name in ("executor", "scout", "arbiter"):
            self.assertIn("shared/debugging.md", roles[name]["bundle"], name)
        # A reviewer establishes causes but never instruments or fixes.
        self.assertNotIn("shared/debugging.md", roles["reviewer"]["bundle"])

    def test_model_sets_and_rules(self):
        self.assertEqual(
            self.team["model_sets"],
            {
                "codex-only": "models/codex-only.json",
                "claude-only": "models/claude-only.json",
                "codex+claude": "models/codex+claude.json",
            },
        )
        self.assertEqual(
            self.team["model_rules"], [{"roles": ["reviewer", "arbiter"], "must_differ_from": "executor"}]
        )

    def test_readme_documents_the_ban_sentence(self):
        readme = (REPO / "README.md").read_text(encoding="utf-8")
        self.assertIn(BAN, " ".join(readme.split()))
        self.assertEqual(check.AGENT_BAN, BAN)


if __name__ == "__main__":
    unittest.main()
