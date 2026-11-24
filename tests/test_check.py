"""Tests for scripts/check.py, run against temporary fixture trees.

Each test builds a small valid tree, breaks exactly one thing, and asserts
that the validator reports it. Run: python3 -m unittest discover -s tests
"""

import importlib.util
import io
import json
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
SCRIPT = REPO / "scripts" / "check.py"


def load_check():
    spec = importlib.util.spec_from_file_location("check", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


check = load_check()

BAN = (
    "- You never start, spawn, schedule or delegate to other agents, "
    "sub-agents, threads, workflows or new machines."
)


def role_md(title, stamp=None, ban=True, headings=None):
    if headings is None:
        headings = [
            "## Who you are",
            "## What you receive",
            "## What you must deliver",
            "## Rules",
            "## You must not",
            "## Report",
        ]
    parts = [f"# {title}", ""]
    for h in headings:
        parts += [h, "", "Text.", ""]
        if h == "## Rules" and ban:
            parts += [BAN, ""]
        if h == "## Report" and stamp:
            parts += ["```", stamp, "```", ""]
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
        self.write("lead/skills/a.md", "# Skill A\n\nText.\n")
        self.write("executor/ROLE.md", role_md("Executor", "ROLE: executor"))
        self.write("reviewer/ROLE.md", role_md("Reviewer", "ROLE: reviewer"))
        self.write("shared/reporting.md", "# Reporting\n\nText.\n")
        self.save()

    def write(self, rel, text):
        path = self.root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
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

    def assertError(self, fragment):
        errors = self.fx.errors()
        self.assertTrue(
            any(fragment in e for e in errors),
            f"expected an error containing {fragment!r}, got {errors!r}",
        )

    # --- baseline ---------------------------------------------------------

    def test_valid_fixture_has_no_errors(self):
        self.assertEqual(self.fx.errors(), [])

    # --- team.json format -------------------------------------------------

    def test_invalid_json(self):
        self.fx.save()
        (self.fx.root / "team.json").write_text("{not json", encoding="utf-8")
        errors = check.validate(self.fx.root)
        self.assertTrue(any("team.json" in e and "JSON" in e for e in errors), errors)

    def test_wrong_schema_version(self):
        self.fx.team["schema"] = 2
        self.assertError("schema")

    def test_stamp_must_match_role(self):
        self.fx.team["roles"]["executor"]["stamp"] = "ROLE: builder"
        self.assertError("stamp")

    def test_bundle_must_start_with_role_md(self):
        self.fx.team["roles"]["executor"]["bundle"].reverse()
        self.assertError("must start with executor/ROLE.md")

    def test_instances_must_be_positive_int(self):
        self.fx.team["roles"]["executor"]["instances"] = 0
        self.assertError("instances")

    def test_lead_role_required(self):
        del self.fx.team["roles"]["lead"]
        self.fx.model_set["roles"].pop("lead")
        self.assertError("lead")

    # --- files ------------------------------------------------------------

    def test_missing_bundle_file(self):
        self.fx.team["roles"]["lead"]["bundle"].append("lead/skills/missing.md")
        self.assertError("lead/skills/missing.md")

    def test_missing_model_set_file(self):
        self.fx.team["model_sets"]["two"] = "models/two.json"
        self.assertError("models/two.json")

    def test_orphan_file(self):
        self.fx.write("lead/skills/orphan.md", "# Orphan\n")
        self.assertError("orphan")

    def test_orphan_in_shared(self):
        self.fx.write("shared/unused.md", "# Unused\n")
        self.assertError("shared/unused.md")

    # --- ROLE.md headings -------------------------------------------------

    def test_missing_heading(self):
        headings = [
            "## Who you are",
            "## What you receive",
            "## What you must deliver",
            "## Rules",
            "## Report",
        ]
        self.fx.write("executor/ROLE.md", role_md("Executor", "ROLE: executor", headings=headings))
        self.assertError("headings")

    def test_misordered_heading(self):
        headings = [
            "## Who you are",
            "## What you must deliver",
            "## What you receive",
            "## Rules",
            "## You must not",
            "## Report",
        ]
        self.fx.write("executor/ROLE.md", role_md("Executor", "ROLE: executor", headings=headings))
        self.assertError("headings")

    def test_wrong_title_heading(self):
        self.fx.write("executor/ROLE.md", role_md("Builder", "ROLE: executor"))
        self.assertError("headings")

    def test_extra_h2_heading(self):
        text = role_md("Executor", "ROLE: executor") + "\n## Extra\n\nText.\n"
        self.fx.write("executor/ROLE.md", text)
        self.assertError("headings")

    def test_subheadings_and_code_fences_are_allowed(self):
        text = role_md("Executor", "ROLE: executor").replace(
            "## Rules\n", "## Rules\n\n### Detail\n\n```\n# not a heading\n## nor this\n```\n"
        )
        self.fx.write("executor/ROLE.md", text)
        self.assertEqual(self.fx.errors(), [])

    # --- forbidden words --------------------------------------------------

    def test_forbidden_word_in_role(self):
        self.fx.write("executor/ROLE.md", role_md("Executor", "ROLE: executor") + "\nRun it in a VM.\n")
        self.assertError("VM")

    def test_forbidden_word_in_skill(self):
        self.fx.write("lead/skills/a.md", "# Skill A\n\nUse Boat to launch.\n")
        self.assertError("Boat")

    def test_forbidden_word_plural_and_t3(self):
        self.fx.write("shared/reporting.md", "# Reporting\n\nTwo VMs on T3.\n")
        errors = self.fx.errors()
        self.assertTrue(any("VMs" in e for e in errors), errors)
        self.assertTrue(any("T3" in e for e in errors), errors)

    def test_forbidden_words_only_as_whole_words(self):
        self.fx.write("shared/reporting.md", "# Reporting\n\nA boathouse, VMware, T35, sVM.\n")
        self.assertEqual(self.fx.errors(), [])

    # --- non-lead rules ---------------------------------------------------

    def test_missing_stamp_line(self):
        self.fx.write("executor/ROLE.md", role_md("Executor", stamp=None))
        self.assertError("stamp")

    def test_stamp_inside_prose_is_not_a_stamp_line(self):
        text = role_md("Executor", stamp=None) + "\nStart with ROLE: executor somewhere.\n"
        self.fx.write("executor/ROLE.md", text)
        self.assertError("stamp")

    def test_missing_agent_ban(self):
        self.fx.write("reviewer/ROLE.md", role_md("Reviewer", "ROLE: reviewer", ban=False))
        self.assertError("agent-ban")

    def test_lead_needs_no_ban_or_stamp(self):
        self.fx.write("lead/ROLE.md", role_md("Lead", stamp=None, ban=False))
        self.assertEqual(self.fx.errors(), [])

    # --- model sets -------------------------------------------------------

    def test_model_rule_violation(self):
        self.fx.model_set["roles"]["reviewer"][1] = model("claude", "opus", "medium")
        self.assertError("must differ")

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
        self.assertError("reason")

    def test_unused_exception(self):
        self.fx.model_set["exceptions"] = [
            {"role": "reviewer", "instance": 1, "must_differ_from": "executor", "reason": "Stale."}
        ]
        self.assertError("unused")

    def test_instance_count_must_match(self):
        self.fx.model_set["roles"]["reviewer"] = model("claude", "fable")
        self.assertError("reviewer")

    def test_model_set_missing_role(self):
        del self.fx.model_set["roles"]["executor"]
        self.assertError("executor")

    def test_unknown_provider(self):
        self.fx.model_set["roles"]["lead"] = model("other", "astra")
        self.assertError("provider")


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
    """The real repository must pass its own validator."""

    def test_repository_is_valid(self):
        self.assertEqual(check.validate(REPO), [])


if __name__ == "__main__":
    unittest.main()
