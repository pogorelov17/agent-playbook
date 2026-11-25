"""Tests for scripts/check.py, run against temporary fixture trees.

Each test builds a small valid tree, breaks exactly one thing, and asserts
that the validator reports it with the specific message for that check.
Run: python3 -m unittest discover -s tests
"""

import importlib.util
import json
import re
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
# The canonical first-line instruction, spelled out for the same reason.
STAMP_RULE = "The first line of every report is exactly:"
# V2 messages.
TAB = "character U+0009 is not allowed in a ROLE.md"
HASH_LINE = "a line starting with '#' must be one of the required headings"
FENCE_FORM = "a fence line must start at column 0 and must not follow a list marker"
FENCE_OPEN = "this fence is never closed"
ANGLE = "a line starting with '<' (raw HTML) is not allowed in a ROLE.md"
SYMLINK = "passes through a symbolic link"
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
            parts += [f"- {BAN}", "  Only the lead dispatches agents.", ""]
        if h == "## Report" and stamp:
            parts += [STAMP_RULE, "", stamp, ""]
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
                    "bundle": ["roles/lead/ROLE.md", "roles/lead/skills/a.md", "shared/reporting.md"],
                },
                "executor": {
                    "stamp": "ROLE: executor",
                    "instances": 1,
                    "bundle": ["roles/executor/ROLE.md", "shared/reporting.md"],
                },
                "reviewer": {
                    "stamp": "ROLE: reviewer",
                    "instances": 2,
                    "bundle": ["roles/reviewer/ROLE.md", "shared/reporting.md"],
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
        self.write("roles/lead/ROLE.md", role_md("Lead", ban=False))
        self.write("roles/lead/skills/a.md", "# Skill A\n\n### Sub-headings are fine in skills\n\nText.\n")
        self.write("roles/executor/ROLE.md", role_md("Executor", "ROLE: executor"))
        self.write("roles/reviewer/ROLE.md", role_md("Reviewer", "ROLE: reviewer"))
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
        text = text.replace(old, new, 1)
        self.fx.write("roles/executor/ROLE.md", text)
        return text

    def assertLineError(self, text, line, fragment, errors=None, rel="roles/executor/ROLE.md"):
        """Assert an error for the first raw line of `text` equal to `line`, naming file and line."""
        n = text.split("\n").index(line) + 1  # raw lines, as V2 defines them
        return self.assertError(f"{rel}:{n}: {fragment}", errors)

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
        self.assertError("roles.executor.bundle must start with roles/executor/ROLE.md")

    def test_own_files_before_shared(self):
        self.fx.write("roles/executor/skills/x.md", "# X\n")
        self.fx.team["roles"]["executor"]["bundle"].append("roles/executor/skills/x.md")
        self.assertError(
            "roles.executor.bundle: own file roles/executor/skills/x.md must come before shared files"
        )

    def test_foreign_role_file_in_bundle(self):
        self.fx.team["roles"]["executor"]["bundle"].insert(1, "roles/lead/skills/a.md")
        self.assertError("roles.executor.bundle: roles/lead/skills/a.md is neither under roles/executor/ nor shared/")

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
        self.fx.team["roles"]["executor"]["bundle"].insert(1, "roles/executor/skills/x.md")
        self.fx.write("roles/executor/skills/x.md", "# X\n")
        self.executor_role("## Rules\n", "## Rule\n")
        errors = self.assertError("roles.executor.stamp must be 'ROLE: executor'")
        self.assertNoError("orphan", errors)
        # The role's own file problems are still reported.
        self.assertError("headings must be exactly", errors)

    # --- encoding ---------------------------------------------------------

    def test_non_utf8_markdown(self):
        self.fx.write("roles/lead/skills/a.md", b"# Skill A\n\n\xff\xfe\n")
        self.assertError("roles/lead/skills/a.md: not valid UTF-8")

    def test_non_utf8_role_md(self):
        self.fx.write("roles/executor/ROLE.md", role_md("Executor", "ROLE: executor").encode() + b"\xff\n")
        self.assertError("roles/executor/ROLE.md: not valid UTF-8")

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
        self.fx.team["roles"]["lead"]["bundle"].insert(2, "roles/lead/skills/missing.md")
        self.assertEqual(
            self.fx.errors(),
            ["team.json: roles.lead.bundle names roles/lead/skills/missing.md, which does not exist"],
        )

    def test_missing_role_md(self):
        self.fx.save()
        (self.fx.root / "roles/executor/ROLE.md").unlink()
        errors = check.validate(self.fx.root)
        self.assertError(
            "team.json: roles.executor.bundle names roles/executor/ROLE.md, which does not exist", errors
        )

    def test_missing_model_set_file(self):
        self.fx.team["model_sets"]["two"] = "models/two.json"
        self.assertError("model set 'two' names models/two.json, which does not exist")

    def test_orphan_file(self):
        self.fx.write("roles/lead/skills/orphan.md", "# Orphan\n")
        self.assertError("roles/lead/skills/orphan.md: orphan file, not listed in any bundle")

    def test_orphan_in_shared(self):
        self.fx.write("shared/unused.md", "# Unused\n")
        self.assertError("shared/unused.md: orphan file, not listed in any bundle")

    def test_orphan_with_other_markdown_extensions(self):
        self.fx.write("roles/lead/skills/upper.MD", "# Upper\n")
        self.fx.write("shared/long.markdown", "# Long\n")
        errors = self.assertError("roles/lead/skills/upper.MD: orphan file")
        self.assertError("shared/long.markdown: orphan file", errors)

    def test_undeclared_role_folder(self):
        self.fx.write("roles/tester/ROLE.md", role_md("Tester", "ROLE: tester") + "\nRun it in a VM.\n")
        self.fx.write("roles/tester/skills/t.md", "# T\n")
        errors = self.assertError("roles/tester/ROLE.md: roles/tester/ has a ROLE.md but is not a role in team.json")
        self.assertError("roles/tester/ROLE.md: orphan file", errors)
        self.assertError("roles/tester/skills/t.md: orphan file", errors)
        self.assertError("forbidden word 'VM'", errors)

    def test_role_removed_from_manifests_but_folder_left(self):
        del self.fx.team["roles"]["reviewer"]
        self.fx.team["model_rules"] = []
        del self.fx.model_set["roles"]["reviewer"]
        errors = self.assertError("roles/reviewer/ROLE.md: roles/reviewer/ has a ROLE.md but is not a role in team.json")
        self.assertError("roles/reviewer/ROLE.md: orphan file", errors)

    def test_undeclared_role_headings_are_checked(self):
        self.fx.write("roles/tester/ROLE.md", "# Tester\n\n## Who you are\n")
        self.assertError("roles/tester/ROLE.md:3: headings must be exactly")

    # --- ROLE.md headings -------------------------------------------------

    def test_missing_heading(self):
        headings = [h for h in HEADINGS if h != "## You must not"]
        self.fx.write("roles/executor/ROLE.md", role_md("Executor", "ROLE: executor", headings=headings))
        self.assertError("headings must be exactly")

    def test_misordered_heading(self):
        headings = list(HEADINGS)
        headings[1], headings[2] = headings[2], headings[1]
        self.fx.write("roles/executor/ROLE.md", role_md("Executor", "ROLE: executor", headings=headings))
        self.assertError("headings must be exactly")

    def test_wrong_title_heading(self):
        self.fx.write("roles/executor/ROLE.md", role_md("Builder", "ROLE: executor"))
        self.assertError("headings must be exactly")

    def test_heading_text_is_exact(self):
        self.executor_role("## Rules\n", "## rules\n")
        self.assertError("headings must be exactly")

    def test_extra_h2_heading(self):
        self.fx.write("roles/executor/ROLE.md", role_md("Executor", "ROLE: executor") + "\n## Extra\n\nText.\n")
        self.assertError("headings must be exactly")

    def test_subheading_in_role_md_rejected(self):
        self.executor_role("## Rules\n", "## Rules\n\n### Detail\n")
        self.assertError("headings must be exactly")

    def test_deep_subheading_in_role_md_rejected(self):
        self.executor_role("## Rules\n", "## Rules\n\n###### Detail\n")
        self.assertError("headings must be exactly")


    def test_thematic_break_is_not_a_heading(self):
        self.executor_role("## Rules\n", "## Rules\n\n---\n")
        self.assertEqual(self.fx.errors(), [])

    def test_code_fence_contents_without_hash_lines_accepted(self):
        self.executor_role(
            "## Rules\n",
            "## Rules\n\n```markdown\nnot a heading\n    indented code\n```\n\n"
            "~~~\nnor this\n~~~\n",
        )
        self.assertEqual(self.fx.errors(), [])

    def test_hash_line_inside_code_fence_rejected(self):
        # V2: there is no exemption for code; a ROLE.md has no other '#' lines.
        for form, line in (("```markdown\n# not a heading\n```", "# not a heading"),
                           ("~~~\n### nor this\n~~~", "### nor this"),
                           ("````\n```\n## inside\n```\n````", "## inside")):
            with self.subTest(form):
                text = self.executor_role("## Rules\n", f"## Rules\n\n{form}\n")
                errors = self.assertLineError(text, line, HASH_LINE)
                self.assertError("headings must be exactly", errors)

    def test_shorter_fence_does_not_close_longer_one(self):
        # If the inner ``` closed the fence, the outer ```` would open a new one
        # that is never closed.
        self.executor_role("## Rules\n", "## Rules\n\n````\n```\n    code\n```\n````\n")
        self.assertEqual(self.fx.errors(), [])

    def test_other_fence_character_does_not_close(self):
        self.executor_role("## Rules\n", "## Rules\n\n```\n~~~\n    code\n~~~\n```\n")
        self.assertEqual(self.fx.errors(), [])

    def test_closing_fence_may_be_followed_by_text(self):
        # C3 (repair round 5): same character, at least as long; nothing more.
        for form in ("~~~\nordinary text\n~~~end", "```\ntext\n````  info", "~~~\ntext\n~~~"):
            with self.subTest(form):
                self.executor_role("## Rules\n", f"## Rules\n\n{form}\n")
                self.assertEqual(self.fx.errors(), [])

    def test_closer_with_text_ends_the_fence(self):
        # After '~~~end' closes the block, the next line is text again.
        text = self.executor_role("## Rules\n", "## Rules\n\n~~~\ncode\n~~~end\n\n    Indented.\n")
        self.assertLineError(text, "    Indented.", "a line indented by four or more spaces")

    def test_shorter_or_other_closer_with_text_does_not_close(self):
        for form, line in (("````\ncode\n```end", "````"), ("~~~\ncode\n```end", "~~~")):
            with self.subTest(form):
                text = self.executor_role("ROLE: executor\n", f"ROLE: executor\n\n{form}\n")
                self.assertLineError(text, line, FENCE_OPEN)

    def test_fence_is_closed_after_matching_line(self):
        text = self.executor_role("## Rules\n", "## Rules\n\n````\ncode\n`````\n\n    Indented.\n")
        self.assertLineError(text, "    Indented.", "a line indented by four or more spaces")

    # --- forbidden words --------------------------------------------------

    def test_forbidden_word_in_role(self):
        self.fx.write("roles/executor/ROLE.md", role_md("Executor", "ROLE: executor") + "\nRun it in a VM.\n")
        self.assertError("roles/executor/ROLE.md:")
        self.assertError("forbidden word 'VM'")

    def test_forbidden_word_in_skill(self):
        self.fx.write("roles/lead/skills/a.md", "# Skill A\n\nUse Boat to launch.\n")
        self.assertError("roles/lead/skills/a.md:3: forbidden word 'Boat'")

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
        self.fx.write("roles/executor/ROLE.md", role_md("Executor", stamp=None))
        self.assertError("the Report section must contain a line consisting of exactly 'ROLE: executor'")

    def test_stamp_inside_prose_is_not_a_stamp_line(self):
        self.executor_role("\nROLE: executor\n", "\nStart with ROLE: executor somewhere.\n")
        self.assertError("the Report section must contain a line consisting of exactly 'ROLE: executor'")

    def test_stamp_outside_report_section_rejected(self):
        text = role_md("Executor", stamp=None).replace("## You must not\n", "ROLE: executor\n\n## You must not\n")
        self.fx.write("roles/executor/ROLE.md", text)
        self.assertError("the Report section must contain a line consisting of exactly 'ROLE: executor'")

    def test_stamp_without_first_line_instruction_rejected(self):
        self.executor_role(STAMP_RULE, "Use this stamp:")
        self.assertError(f"the Report section must contain the line {STAMP_RULE!r}")

    # --- non-lead rules: agent ban ----------------------------------------

    def test_canonical_ban_sentence_accepted(self):
        for line in (BAN, f"- {BAN}", f"1. {BAN}", f"12. {BAN}"):
            with self.subTest(line):
                self.executor_role(f"- {BAN}", line)
                self.assertEqual(self.fx.errors(), [])

    def test_ban_must_be_the_whole_line(self):
        for line in (f"- {BAN} Only the lead dispatches agents.", f"* {BAN}", f"  - {BAN}",
                     f"-  {BAN}", f"1) {BAN}", f"{BAN} ", f"Rule: {BAN}"):
            with self.subTest(line):
                self.executor_role(f"- {BAN}", line)
                self.assertError("missing the agent-ban sentence")

    def test_missing_agent_ban(self):
        self.fx.write("roles/reviewer/ROLE.md", role_md("Reviewer", "ROLE: reviewer", ban=False))
        self.assertError("roles/reviewer/ROLE.md:1: missing the agent-ban sentence")

    def test_ban_with_conditional_suffix_rejected(self):
        for suffix in ("offers it, unless the lead allows it.", "offers it unless the task is urgent."):
            with self.subTest(suffix):
                self.executor_role("offers it.", suffix)
                self.assertError("missing the agent-ban sentence")

    def test_ban_permission_variant_rejected(self):
        self.executor_role(BAN, "You never start, spawn, schedule or delegate to other agents unless a tool offers it.")
        self.assertError("missing the agent-ban sentence")

    def test_truncated_ban_rejected(self):
        self.executor_role(BAN, "You never start, spawn, schedule or delegate to other agents.")
        self.assertError("missing the agent-ban sentence")

    def test_quoted_and_negated_ban_rejected(self):
        self.executor_role(f"- {BAN}", f'- It is not true that "{BAN}"')
        self.assertError("missing the agent-ban sentence")

    def test_ban_inside_code_fence_rejected(self):
        self.executor_role(f"- {BAN}", f"```\n{BAN}\n```")
        self.assertError("missing the agent-ban sentence")

    # --- V1: strict form of ROLE.md ----------------------------------------

    def test_html_comment_rejected(self):
        for form, line in (("<!-- note -->", "<!-- note -->"),
                           ("<!--\nhidden\n-->", "<!--"),
                           ("Text <!-- inline --> text.", "Text <!-- inline --> text."),
                           ("```\n<!-- in a fence -->\n```", "<!-- in a fence -->")):
            with self.subTest(form):
                text = self.executor_role("## Rules\n", f"## Rules\n\n{form}\n")
                self.assertLineError(text, line, "an HTML comment ('<!--') is not allowed in a ROLE.md")

    def test_comment_around_required_lines_rejected(self):
        for old in (f"- {BAN}", STAMP_RULE, "\nROLE: executor\n"):
            with self.subTest(old):
                text = self.executor_role(old, f"<!--\n{old}\n-->")
                self.assertLineError(text, "<!--", "an HTML comment")

    def test_block_quoted_line_rejected(self):
        for line in ("> Quoted", "   > Quoted", ">## Extra", "> ## Extra", "> > ### Extra", ">"):
            with self.subTest(line):
                text = self.executor_role("## Rules\n", f"## Rules\n\n{line}\n")
                self.assertLineError(text, line, "a block-quoted line ('>') is not allowed in a ROLE.md")

    def test_quote_then_tab_then_heading(self):
        line = ">\t## Additional heading"
        text = self.executor_role("## Rules\n", f"## Rules\n\n{line}\n")
        errors = self.assertLineError(text, line, "a block-quoted line")
        self.assertLineError(text, line, TAB, errors)

    def test_quoted_paragraph_continuing_onto_required_line(self):
        # Without a blank line, the next line would continue the quoted paragraph.
        for old in (f"- {BAN}", STAMP_RULE, "ROLE: executor"):
            with self.subTest(old):
                text = self.executor_role(f"\n{old}\n", f"\n> Quoted paragraph\n{old}\n")
                self.assertLineError(text, "> Quoted paragraph", "a block-quoted line")

    def test_block_quoted_required_lines_rejected(self):
        for old in (f"- {BAN}", STAMP_RULE, "ROLE: executor"):
            with self.subTest(old):
                text = self.executor_role(f"\n{old}\n", f"\n> {old}\n")
                self.assertLineError(text, f"> {old}", "a block-quoted line")

    def test_setext_underline_rejected(self):
        message = "a setext heading underline is not allowed in a ROLE.md"
        for form, line in (("Detail\n=====", "====="), ("Detail\n-----", "-----"),
                           ("Detail\n---", "---"), ("Detail\n=", "="), ("Detail\n====", "===="),
                           ("\n===", "==="), ("```\nNor\n===\n```", "===")):
            with self.subTest(form):
                text = self.executor_role("## Rules\n", f"## Rules\n\n{form}\n")
                self.assertLineError(text, line, message)

    def test_setext_rule_matches_the_raw_line_exactly(self):
        # C1 (repair round 5): only '=' characters, or three or more '-' after
        # a non-blank line, and nothing else on the line.
        for form in ("Text\n--", "Text\n-", "Text\n = ", "Text\n- -", "Text\n  ---  ", "Text\n=== "):
            with self.subTest(form):
                self.executor_role("## Rules\n", f"## Rules\n\n{form}\n")
                self.assertEqual(self.fx.errors(), [])

    def test_two_line_setext_title(self):
        text = self.executor_role("## Report\n", "Draft\nReport\n------\n")
        errors = self.assertLineError(text, "------", "a setext heading underline")
        self.assertError("headings must be exactly", errors)

    def test_space_tab_text_then_rule(self):
        line = " \tText"
        text = self.executor_role("## Rules\n", f"## Rules\n\n{line}\n---\n")
        errors = self.assertLineError(text, line, TAB)
        self.assertLineError(text, "---", "a setext heading underline", errors)

    def test_thematic_break_after_blank_line_accepted(self):
        for rule in ("---", "-----", "***", "- - -"):
            with self.subTest(rule):
                self.executor_role("## Rules\n", f"## Rules\n\n{rule}\n")
                self.assertEqual(self.fx.errors(), [])

    def test_tab_rejected_anywhere(self):
        for form, line in (("Text\twith a tab.", "Text\twith a tab."), ("\tIndented.", "\tIndented."),
                           ("```\n\tcode\n```", "\tcode")):
            with self.subTest(form):
                text = self.executor_role("## Rules\n", f"## Rules\n\n{form}\n")
                self.assertLineError(text, line, TAB)

    def test_indented_line_outside_fence_rejected(self):
        message = "a line indented by four or more spaces outside fenced code is not allowed in a ROLE.md"
        for line in ("    Indented code.", "        Deeper.", "    ```"):
            with self.subTest(line):
                text = self.executor_role("## Rules\n", f"## Rules\n\n{line}\n")
                self.assertLineError(text, line, message)

    def test_indented_lines_inside_fence_and_blank_lines_accepted(self):
        self.executor_role("## Rules\n", "## Rules\n\n```\n    code\n```\n\n    \n   Three spaces.\n")
        self.assertEqual(self.fx.errors(), [])

    def test_indented_ban_rejected(self):
        line = f"    {BAN}"
        text = self.executor_role(f"- {BAN}", line)
        errors = self.assertLineError(text, line, "a line indented by four or more spaces")
        self.assertError("missing the agent-ban sentence", errors)

    def test_stamp_inside_code_fence_rejected(self):
        self.executor_role("\nROLE: executor\n", "\n```\nROLE: executor\n```\n")
        self.assertError("the Report section must contain a line consisting of exactly 'ROLE: executor'")

    def test_stamp_with_surrounding_whitespace_rejected(self):
        for line in (" ROLE: executor", "  ROLE: executor", "   ROLE: executor",
                     "ROLE: executor ", "ROLE: executor\t"):
            with self.subTest(repr(line)):
                self.executor_role("\nROLE: executor\n", f"\n{line}\n")
                self.assertError(
                    "the Report section must contain a line consisting of exactly 'ROLE: executor'"
                )

    def test_first_line_instruction_must_be_one_exact_line(self):
        for form in (f"T{STAMP_RULE}", f"Follow the format. {STAMP_RULE}", f"- {STAMP_RULE}",
                     f" {STAMP_RULE}", f"{STAMP_RULE} ", "The first line of every\nreport is exactly:"):
            with self.subTest(form):
                self.executor_role(STAMP_RULE, form)
                self.assertError(f"the Report section must contain the line {STAMP_RULE!r}")

    def test_first_line_instruction_inside_fence_rejected(self):
        self.executor_role(STAMP_RULE, f"```\n{STAMP_RULE}\n```")
        self.assertError(f"the Report section must contain the line {STAMP_RULE!r}")

    def test_first_line_instruction_must_be_followed_by_stamp(self):
        text = self.executor_role(f"{STAMP_RULE}\n\nROLE: executor", f"{STAMP_RULE}\n\nText.\n\nROLE: executor")
        self.assertLineError(
            text, STAMP_RULE, f"the line {STAMP_RULE!r} must be followed (blank lines allowed) by the stamp line"
        )

    def test_first_line_instruction_then_stamp_with_or_without_blank_lines(self):
        for gap in ("\n", "\n\n", "\n\n\n\n"):
            with self.subTest(repr(gap)):
                self.executor_role(f"{STAMP_RULE}\n\nROLE: executor", f"{STAMP_RULE}{gap}ROLE: executor")
                self.assertEqual(self.fx.errors(), [])

    def test_first_line_instruction_outside_report_rejected(self):
        text = role_md("Executor", stamp=None).replace(
            "## You must not\n", f"{STAMP_RULE}\n\nROLE: executor\n\n## You must not\n"
        )
        self.fx.write("roles/executor/ROLE.md", text)
        errors = self.assertError(f"the Report section must contain the line {STAMP_RULE!r}")
        self.assertError("the Report section must contain a line consisting of exactly 'ROLE: executor'", errors)

    def test_strict_form_applies_to_lead_role_md(self):
        text = role_md("Lead", ban=False).replace("## Rules\n", "## Rules\n\n> Quoted\n")
        self.fx.write("roles/lead/ROLE.md", text)
        self.assertLineError(text, "> Quoted", "a block-quoted line", rel="roles/lead/ROLE.md")

    def test_strict_form_does_not_apply_to_skills_and_shared_files(self):
        body = "\n> Quoted\n\n<!-- comment -->\n\n\tTabbed\n\n    Indented\n\nTitle\n=====\n"
        self.fx.write("roles/lead/skills/a.md", "# Skill A\n" + body)
        self.fx.write("shared/reporting.md", "# Reporting\n" + body)
        self.assertEqual(self.fx.errors(), [])

    def test_forbidden_word_inside_comment_still_reported(self):
        self.fx.write("shared/reporting.md", "# Reporting\n\n<!-- Use T3. -->\n")
        self.assertError("shared/reporting.md:3: forbidden word 'T3'")

    # --- V2: the contract is about raw lines --------------------------------

    def assertCharError(self, text, line_no, code, errors=None):
        return self.assertError(f"roles/executor/ROLE.md:{line_no}: character {code} is not allowed in a ROLE.md", errors)

    def line_no(self, text, fragment):
        """1-based number of the first raw line (split on '\\n' only) containing `fragment`."""
        return next(i for i, l in enumerate(text.split("\n"), 1) if fragment in l)

    def test_role_md_errors_carry_a_line_number(self):
        self.fx.write("roles/executor/ROLE.md", "# Executor\n\nText.\n")
        errors = [e for e in self.fx.errors() if e.startswith("roles/executor/ROLE.md")]
        self.assertTrue(errors)
        for e in errors:
            self.assertRegex(e, r"^roles/executor/ROLE\.md:\d+: ")

    def test_non_ascii_and_control_characters_rejected(self):
        for ch, code in (("\x0c", "U+000C"), ("\x0b", "U+000B"), ("\x00", "U+0000"), ("\x7f", "U+007F"),
                         (" ", "U+00A0"), ("—", "U+2014"), ("“", "U+201C"),
                         ("→", "U+2192"), ("é", "U+00E9"), (" ", "U+2028")):
            with self.subTest(code):
                text = self.executor_role("## Rules\n\nText.", f"## Rules\n\nText{ch}here.")
                self.assertCharError(text, self.line_no(text, f"Text{ch}here."), code)

    def test_byte_order_mark_rejected(self):
        text = "﻿" + role_md("Executor", "ROLE: executor")
        self.fx.write("roles/executor/ROLE.md", text)
        self.assertCharError(text, 1, "U+FEFF")

    def test_stamp_with_form_feed_rejected(self):
        for line in ("ROLE: executor\x0c", "\x0cROLE: executor"):
            with self.subTest(repr(line)):
                text = self.executor_role("\nROLE: executor\n", f"\n{line}\n")
                errors = self.assertCharError(text, self.line_no(text, line), "U+000C")
                self.assertError("the Report section must contain a line consisting of exactly 'ROLE: executor'",
                                 errors)

    def test_ban_wrapped_in_vertical_tabs_rejected(self):
        line = f"\x0b- {BAN}\x0b"
        text = self.executor_role(f"- {BAN}", line)
        errors = self.assertCharError(text, self.line_no(text, BAN), "U+000B")
        self.assertError("missing the agent-ban sentence", errors)

    def test_rules_heading_hidden_behind_form_feed_rejected(self):
        text = self.executor_role("## Rules\n", "Rules follow.\x0c## Rules\n")
        errors = self.assertCharError(text, self.line_no(text, "Rules follow."), "U+000C")
        self.assertError("headings must be exactly", errors)

    def test_setext_title_using_form_feed_or_non_breaking_space(self):
        for form, code in (("Draft\x0cReport\n------", "U+000C"), ("Draft\n\x0c\n------", "U+000C"),
                           ("Draft\n \n------", "U+00A0")):
            with self.subTest(repr(form)):
                text = self.executor_role("## Report\n", f"{form}\n")
                errors = self.assertCharError(text, self.line_no(text, "Draft") + form.count("\n") - 1, code)
                self.assertLineError(text, "------", "a setext heading underline", errors)
                self.assertError("headings must be exactly", errors)

    def test_literal_separator_rejected_for_the_character_not_as_heading(self):
        for sep, code in ((" ", "U+2028"), ("\x0c", "U+000C"), ("\x1c", "U+001C"), ("\x85", "U+0085")):
            with self.subTest(code):
                line = f"Literal separator:{sep}## Example"
                text = self.executor_role("## Rules\n\nText.", f"## Rules\n\n{line}")
                errors = self.assertCharError(text, self.line_no(text, "Literal separator"), code)
                self.assertNoError(HASH_LINE, errors)
                self.assertNoError("headings must be exactly", errors)

    def test_non_breaking_space_between_instruction_and_stamp(self):
        text = self.executor_role(f"{STAMP_RULE}\n\nROLE: executor", f"{STAMP_RULE}\n \nROLE: executor")
        errors = self.assertCharError(text, self.line_no(text, STAMP_RULE) + 1, "U+00A0")
        self.assertLineError(
            text, STAMP_RULE, f"the line {STAMP_RULE!r} must be followed (blank lines allowed) by the stamp line",
            errors,
        )

    def test_four_spaces_then_non_breaking_space(self):
        line = "     "
        text = self.executor_role("## Rules\n", f"## Rules\n\n{line}\n")
        errors = self.assertCharError(text, self.line_no(text, line), "U+00A0")
        self.assertLineError(text, line, "a line indented by four or more spaces", errors)

    def test_ban_with_arabic_indic_digit_rejected(self):
        line = f"١. {BAN}"
        text = self.executor_role(f"- {BAN}", line)
        errors = self.assertCharError(text, self.line_no(text, BAN), "U+0661")
        self.assertError("missing the agent-ban sentence", errors)

    def test_ban_markers(self):
        for marker in ("", "- ", "1. ", "123456789. "):
            with self.subTest(marker):
                self.executor_role(f"- {BAN}", f"{marker}{BAN}")
                self.assertEqual(self.fx.errors(), [])
        for marker in ("1) ", "* ", "+ ", "-  ", "1234567890. ", " - ", "- - "):
            with self.subTest(marker):
                self.executor_role(f"- {BAN}", f"{marker}{BAN}")
                self.assertError("missing the agent-ban sentence")

    def test_hash_lines_rejected(self):
        for line in ("- ## Hidden extra heading", "* # Hidden", "+   ### Hidden", "1. ## Hidden",
                     "12) ## Hidden", "## Extra", "   ## Rules", "#Hashtag", "####### Seven",
                     "- ## example", "1. ## example", "  ## example", "#"):
            with self.subTest(line):
                text = self.executor_role("## Rules\n", f"## Rules\n\n{line}\n")
                errors = self.assertLineError(text, line, HASH_LINE)
                self.assertError("headings must be exactly", errors)

    def test_hash_after_two_list_markers_is_ordinary_text(self):
        # C2 (repair round 5): at most one list marker before the '#'.
        for line in ("- - ## example", "1. - # example", "* + ### example"):
            with self.subTest(line):
                self.executor_role("## Rules\n", f"## Rules\n\n{line}\n")
                self.assertEqual(self.fx.errors(), [])

    def test_required_heading_must_be_exact_and_at_column_zero(self):
        for line in (" ## Rules", "## Rules ", "## Rules #", "##  Rules", "- ## Rules"):
            with self.subTest(line):
                text = self.executor_role("## Rules\n", f"{line}\n")
                errors = self.assertLineError(text, line, HASH_LINE)
                self.assertError("headings must be exactly", errors)

    def test_required_heading_only_once(self):
        text = self.executor_role("## You must not\n", "## Rules\n\nText.\n\n## You must not\n")
        self.assertError("headings must be exactly", self.fx.errors())
        self.assertIn("## Rules", text)

    def test_hash_not_first_is_ordinary_text(self):
        self.executor_role("## Rules\n\nText.", "## Rules\n\nIssue #12 and C# are fine.\n-#not a list item")
        self.assertEqual(self.fx.errors(), [])

    def test_fence_in_list_item_hiding_a_heading(self):
        text = self.executor_role("## Rules\n", "## Rules\n\n- ```\n## Hidden\n```\n")
        errors = self.assertLineError(text, "- ```", FENCE_FORM)
        self.assertLineError(text, "## Hidden", HASH_LINE, errors)

    def test_fence_in_list_item_around_rules_heading(self):
        text = self.executor_role("## Rules\n", "- ```\n## Rules\n```\n")
        self.assertLineError(text, "- ```", FENCE_FORM)

    def test_fence_in_list_item_around_ban(self):
        text = self.executor_role(f"- {BAN}", f"1. ~~~\n- {BAN}\n~~~")
        errors = self.assertLineError(text, "1. ~~~", FENCE_FORM)
        self.assertError("missing the agent-ban sentence", errors)

    def test_indented_fence_rejected(self):
        for line in (" ```", "   ~~~"):
            with self.subTest(line):
                text = self.executor_role("## Rules\n", f"## Rules\n\n{line}\ncode\n```\n~~~\n")
                self.assertLineError(text, line, FENCE_FORM)

    def test_unclosed_fence_rejected(self):
        for form, line in (("```\ncode", "```"), ("````\ncode\n```", "````"), ("~~~\ncode\n```", "~~~"),
                           ("```inline code```", "```inline code```")):
            with self.subTest(form):
                text = self.executor_role("ROLE: executor\n", f"ROLE: executor\n\n{form}\n")
                self.assertLineError(text, line, FENCE_OPEN)

    def test_angle_bracket_line_rejected(self):
        for line in ("<div>", "  <b>bold</b>", "<", "<https://example.com>"):
            with self.subTest(line):
                text = self.executor_role("## Rules\n", f"## Rules\n\n{line}\n")
                self.assertLineError(text, line, ANGLE)

    def test_angle_bracket_inside_a_line_accepted(self):
        self.executor_role("## Rules\n\nText.", "## Rules\n\nUse `git log -1 <sha>` and a < b.")
        self.assertEqual(self.fx.errors(), [])

    # positive controls

    def test_three_space_nested_list_accepted(self):
        self.executor_role("## Rules\n\nText.", "## Rules\n\n- Item\n   - Nested item\n   1. Numbered")
        self.assertEqual(self.fx.errors(), [])

    def test_crlf_and_cr_line_endings_accepted(self):
        for eol in ("\r\n", "\r"):
            with self.subTest(repr(eol)):
                text = role_md("Executor", "ROLE: executor").replace("\n", eol)
                self.fx.write("roles/executor/ROLE.md", text.encode("ascii"))
                self.assertEqual(self.fx.errors(), [])

    def test_missing_final_newline_accepted(self):
        text = role_md("Executor", "ROLE: executor").rstrip("\n")
        self.assertTrue(text.endswith("ROLE: executor"))
        self.fx.write("roles/executor/ROLE.md", text)
        self.assertEqual(self.fx.errors(), [])

    def test_column_zero_fenced_example_accepted(self):
        self.executor_role("## Rules\n\nText.", "## Rules\n\n```text\nAn example: ROLE: executor\n```\n\n~~~~\nMore.\n~~~~")
        self.assertEqual(self.fx.errors(), [])

    # --- V3: bundled files and symbolic links --------------------------------

    def bundle_executor(self, rel):
        self.fx.team["roles"]["executor"]["bundle"] = ["roles/executor/ROLE.md", rel, "shared/reporting.md"]

    def test_symlinked_directory_in_bundle_path(self):
        outside = tempfile.TemporaryDirectory()
        self.addCleanup(outside.cleanup)
        for target in (Path(outside.name), self.fx.root / "notes"):
            with self.subTest(str(target)):
                (target / "bad.md").parent.mkdir(parents=True, exist_ok=True)
                (target / "bad.md").write_text("# Bad\n\nRun it in a VM.\n", encoding="utf-8")
                link = self.fx.root / "roles/executor/skills/linked"
                link.parent.mkdir(parents=True, exist_ok=True)
                if link.is_symlink():
                    link.unlink()
                link.symlink_to(target, target_is_directory=True)
                self.bundle_executor("roles/executor/skills/linked/bad.md")
                errors = self.assertError(f"roles/executor/skills/linked/bad.md {SYMLINK}")
                self.assertError("roles/executor/skills/linked/bad.md:3: forbidden word 'VM'", errors)

    def test_symlinked_file_in_bundle(self):
        self.fx.write("notes/target.md", "# Target\n\nUse T3.\n")
        link = self.fx.root / "roles/executor/skills/f.md"
        link.parent.mkdir(parents=True, exist_ok=True)
        link.symlink_to(self.fx.root / "notes/target.md")
        self.bundle_executor("roles/executor/skills/f.md")
        errors = self.assertError(f"roles/executor/skills/f.md {SYMLINK}")
        self.assertError("roles/executor/skills/f.md:3: forbidden word 'T3'", errors)

    def test_bundled_file_outside_discovery_is_checked_for_utf8(self):
        outside = tempfile.TemporaryDirectory()
        self.addCleanup(outside.cleanup)
        Path(outside.name, "bad.md").write_bytes(b"# Bad\n\xff\n")
        (self.fx.root / "roles/executor/skills").mkdir(parents=True, exist_ok=True)
        (self.fx.root / "roles/executor/skills/linked").symlink_to(outside.name, target_is_directory=True)
        self.bundle_executor("roles/executor/skills/linked/bad.md")
        errors = self.assertError("roles/executor/skills/linked/bad.md: not valid UTF-8")
        self.assertError(SYMLINK, errors)

    def test_symlinked_role_md(self):
        self.fx.write("notes/ROLE.md", role_md("Executor", "ROLE: executor"))
        (self.fx.root / "roles/executor/ROLE.md").unlink()
        (self.fx.root / "roles/executor/ROLE.md").symlink_to(self.fx.root / "notes/ROLE.md")
        self.assertError(f"roles/executor/ROLE.md {SYMLINK}")

    # --- E5: discovery, paths, model-set fields ----------------------------

    def test_dot_role_folder_discovered(self):
        self.fx.write("roles/.hidden/ROLE.md", role_md("Hidden", "ROLE: hidden"))
        self.fx.write("roles/.hidden/skills/h.md", "# H\n")
        errors = self.assertError("roles/.hidden/ROLE.md: roles/.hidden/ has a ROLE.md but is not a role in team.json")
        self.assertError("roles/.hidden/skills/h.md: orphan file", errors)

    def test_git_and_github_folders_skipped(self):
        self.fx.write(".git/ROLE.md", "Run it in a VM.\n")
        self.fx.write(".github/ROLE.md", "Run it in a VM.\n")
        self.assertEqual(self.fx.errors(), [])

    def test_role_folder_outside_roles_dir(self):
        # A role folder left at the top level (the layout before roles/) is never used.
        self.fx.write("executor/ROLE.md", role_md("Executor", "ROLE: executor"))
        self.fx.write(".hidden/ROLE.md", role_md("Hidden", "ROLE: hidden"))
        errors = self.assertError(
            "executor/ROLE.md: executor/ has a ROLE.md outside roles/; role folders live in roles/<role>/"
        )
        self.assertError(".hidden/ROLE.md: .hidden/ has a ROLE.md outside roles/", errors)

    def test_old_layout_bundle_path_rejected(self):
        self.fx.write("executor/ROLE.md", role_md("Executor", "ROLE: executor"))
        self.fx.team["roles"]["executor"]["bundle"][0] = "executor/ROLE.md"
        errors = self.assertError("roles.executor.bundle must start with roles/executor/ROLE.md, got 'executor/ROLE.md'")
        self.assertError("roles.executor.bundle: executor/ROLE.md is neither under roles/executor/ nor shared/", errors)

    def test_own_files_must_be_inside_the_role_folder(self):
        self.fx.write("roles/executor.md", "# X\n")
        self.fx.team["roles"]["executor"]["bundle"].insert(1, "roles/executor.md")
        self.assertError("roles.executor.bundle: roles/executor.md is neither under roles/executor/ nor shared/")

    def test_missing_roles_folder(self):
        import shutil
        shutil.rmtree(self.fx.root / "roles")
        errors = self.assertError("team.json: roles.lead.bundle names roles/lead/ROLE.md, which does not exist")
        self.assertNoError("orphan", errors)

    def test_bundle_paths_must_be_canonical(self):
        for rel in ("./shared/reporting.md", "shared//reporting.md", "shared/./reporting.md",
                    "/shared/reporting.md", "roles/executor/../shared/reporting.md"):
            with self.subTest(rel):
                fx = Fixture()
                self.addCleanup(fx.cleanup)
                fx.team["roles"]["executor"]["bundle"][1] = rel
                self.assertError(
                    f"roles.executor.bundle: {rel!r} must be a canonical relative .md path", fx.errors()
                )

    def test_duplicate_detected_on_canonical_form(self):
        self.fx.team["roles"]["executor"]["bundle"].append("shared//reporting.md")
        self.assertError("roles.executor.bundle lists shared/reporting.md twice")

    def test_model_set_description_must_be_string(self):
        for value in (5, ["text"], None):
            with self.subTest(repr(value)):
                fx = Fixture()
                self.addCleanup(fx.cleanup)
                fx.model_set["description"] = value
                self.assertError("models/one.json: description must be a string", fx.errors())

    def test_model_set_description_string_accepted(self):
        self.fx.model_set["description"] = "One provider."
        self.assertEqual(self.fx.errors(), [])

    def test_lead_needs_no_ban_or_stamp(self):
        self.fx.write("roles/lead/ROLE.md", role_md("Lead", stamp=None, ban=False))
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
                "<!-- file: roles/lead/ROLE.md -->",
                "<!-- file: roles/lead/skills/a.md -->",
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


# A repository-relative path to a Markdown file, as instructions and the README
# write it: at least one '/', no placeholder such as <role>, not part of a URL.
PATH_REF = re.compile(r"(?<![\w/.:<>-])((?:[\w.-]+/)+[\w.-]+\.md)\b")


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

    def test_role_folders_live_under_roles(self):
        self.assertEqual(check.misplaced_role_folders(REPO), [])
        self.assertEqual(check.role_folders(REPO), sorted(self.team["roles"]))
        for name, spec in self.team["roles"].items():
            with self.subTest(name):
                self.assertEqual(spec["bundle"][0], f"roles/{name}/ROLE.md")

    def test_paths_named_in_instructions_exist(self):
        # Role and skill texts point to each other by path (`roles/lead/skills/briefing.md`,
        # shared/verification.md); every such path must name a file in the repository,
        # so a path from an older layout (lead/skills/briefing.md) fails here.
        pattern = PATH_REF
        bundled = sorted({rel for spec in self.team["roles"].values() for rel in spec["bundle"]})
        found = 0
        for rel in bundled:
            text = (REPO / rel).read_text(encoding="utf-8")
            for ref in pattern.findall(text):
                found += 1
                with self.subTest(file=rel, ref=ref):
                    self.assertTrue((REPO / ref).is_file(), f"{rel} names {ref}, which does not exist")
        self.assertGreater(found, 0)

    def test_readme_names_only_existing_paths(self):
        readme = (REPO / "README.md").read_text(encoding="utf-8")
        for ref in PATH_REF.findall(readme):
            with self.subTest(ref):
                self.assertTrue((REPO / ref).is_file(), f"README.md names {ref}, which does not exist")

    def test_readme_documents_the_ban_sentence(self):
        readme = (REPO / "README.md").read_text(encoding="utf-8")
        self.assertIn(BAN, " ".join(readme.split()))
        self.assertEqual(check.AGENT_BAN, BAN)

    def test_readme_documents_the_first_line_instruction(self):
        readme = (REPO / "README.md").read_text(encoding="utf-8")
        self.assertIn(STAMP_RULE, readme)
        self.assertEqual(check.FIRST_LINE_RULE, STAMP_RULE)


if __name__ == "__main__":
    unittest.main()
