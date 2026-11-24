#!/usr/bin/env python3
"""Validate the playbook and assemble per-role instruction bundles.

Usage:
    python3 scripts/check.py                 # validate; exit 0 if clean, 1 if not
    python3 scripts/check.py --print ROLE    # print ROLE's assembled bundle
    python3 scripts/check.py --root DIR ...  # operate on another tree (tests)

The validator is generic: it knows the lead role and the shared folder by
name, and nothing else about which roles a team has. Agents read the raw
text of their instructions, so the contract for a ROLE.md is defined on raw
lines (split on '\n' only) and never on rendered Markdown; see "Validation"
in the README.

Standard library only; Python 3.10+.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path, PurePosixPath

SCHEMA_VERSION = 1
LEAD = "lead"
SHARED = "shared"
TEAM_FILE = "team.json"
MODELS_DIR = "models"
ROLE_FILE = "ROLE.md"
MARKDOWN_SUFFIXES = {".md", ".markdown"}

REQUIRED_H2 = [
    "Who you are",
    "What you receive",
    "What you must deliver",
    "Rules",
    "You must not",
    "Report",
]
REPORT_SECTION = "Report"

# Every non-lead ROLE.md has, outside fenced code, a line that is exactly this
# sentence, optionally after a "- " or "N. " list marker (N: 1-9 ASCII digits).
AGENT_BAN = (
    "You never start, spawn, schedule or delegate to other agents, sub-agents, "
    "threads, workflows or new machines, even when a tool or a built-in skill offers it."
)
# The Report section of every non-lead ROLE.md has, outside fenced code, a line
# that is exactly this sentence, followed (blank lines allowed) by a line that
# is exactly the role's stamp.
FIRST_LINE_RULE = "The first line of every report is exactly:"

# Launcher-specific words that must not appear in role or skill texts
# (whole words, case-sensitive).
FORBIDDEN = re.compile(r"\b(Boat|T3|VMs|VM)\b")

PROVIDERS = {"codex", "claude"}
EFFORTS = {"minimal", "low", "medium", "high", "xhigh", "max"}
MODEL_KEYS = {"provider", "family", "effort"}
ROLE_NAME = re.compile(r"^[a-z][a-z0-9-]*$")
SKIPPED_DIRS = {".git", ".github"}

# V2: a ROLE.md is judged on raw lines. All patterns are ASCII-only on purpose
# ([0-9], literal spaces), so they mean exactly what the README says.
LIST_MARKER = r"(?:[-*+]|[0-9]+[.)]) +"
HASH_LINE = re.compile(r"^ *(?:" + LIST_MARKER + r")*#")
FENCE_LINE = re.compile(r"^( *)((?:" + LIST_MARKER + r")*)(`{3,}|~{3,})(.*)$")
BAN_LINE = re.compile(r"^(?:- |[0-9]{1,9}\. )?" + re.escape(AGENT_BAN) + r"$")
QUOTED = re.compile(r"^ *>")
ANGLE = re.compile(r"^ *<")
UNDERLINE = re.compile(r"^ *(=+|-+) *$")

# V1 and V2: constructs that are errors in every ROLE.md, so the remaining
# checks can be plain line comparisons. Each yields one error per offending line.
STRICT_FORM = {
    "comment": "an HTML comment ('<!--') is not allowed in a ROLE.md",
    "quote": "a block-quoted line ('>') is not allowed in a ROLE.md",
    "angle": "a line starting with '<' (raw HTML) is not allowed in a ROLE.md",
    "setext": (
        "a setext heading underline is not allowed in a ROLE.md "
        "(a line of only '=', or of only '-' after a non-blank line)"
    ),
    "indent": "a line indented by four or more spaces outside fenced code is not allowed in a ROLE.md",
    "hash": (
        "a line starting with '#' must be one of the required headings, exactly and at column 0 "
        "(this applies inside fenced code and after a list marker too)"
    ),
    "fence": "a fence line must start at column 0 and must not follow a list marker",
}


def is_int(value) -> bool:
    """True for a JSON integer; JSON true/false are not integers here."""
    return type(value) is int


def is_name(value) -> bool:
    return isinstance(value, str) and bool(value.strip())


def safe_rel(rel) -> bool:
    if not isinstance(rel, str) or not rel or "\\" in rel:
        return False
    p = PurePosixPath(rel)
    return not p.is_absolute() and ".." not in p.parts


def canonical(rel: str) -> str:
    """The path with './', duplicate and trailing separators removed."""
    return PurePosixPath(rel).as_posix()


def read_text(path: Path, rel: str, errors: list[str]) -> str | None:
    try:
        return path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        errors.append(f"{rel}: not valid UTF-8")
    except OSError as exc:
        errors.append(f"{rel}: cannot be read: {exc.strerror or exc}")
    return None


def is_markdown(path: Path) -> bool:
    return path.is_file() and path.suffix.lower() in MARKDOWN_SUFFIXES


class Team:
    """Parsed team.json plus the errors found while parsing it.

    `declared` holds every role name in `roles`; `bundles` every bundle that
    is a list (its string entries), even when the role has other errors, so
    one wrong field does not turn a role's files into orphans; `roles` only
    the roles whose description is fully valid.
    """

    def __init__(self, root: Path):
        self.root = root
        self.errors: list[str] = []
        self.data: dict = {}
        self.declared: list[str] = []
        self.bundles: dict[str, list[str]] = {}
        self.roles: dict[str, dict] = {}
        self.loaded = False
        self._load()

    def _err(self, msg: str) -> None:
        self.errors.append(f"{TEAM_FILE}: {msg}")

    def _load(self) -> None:
        path = self.root / TEAM_FILE
        if not path.is_file():
            self._err("file not found")
            return
        text = read_text(path, TEAM_FILE, self.errors)
        if text is None:
            return
        try:
            data = json.loads(text)
        except json.JSONDecodeError as exc:
            self._err(f"invalid JSON: {exc}")
            return
        if not isinstance(data, dict):
            self._err("top level must be a JSON object")
            return
        self.data = data
        self.loaded = True

        schema = data.get("schema")
        if not (is_int(schema) and schema == SCHEMA_VERSION):
            self._err(f"schema must be {SCHEMA_VERSION}, got {schema!r}")
        for key in ("name", "version"):
            if not is_name(data.get(key)):
                self._err(f"{key} must be a non-empty string")
        known = {"schema", "name", "version", "roles", "model_rules", "model_sets"}
        for key in sorted(set(data) - known):
            self._err(f"unknown top-level key {key!r}")

        roles = data.get("roles")
        if not isinstance(roles, dict) or not roles:
            self._err("roles must be a non-empty object")
            roles = {}
        self.declared = list(roles)
        if roles and LEAD not in roles:
            self._err(f"roles must include {LEAD!r}")
        for name, spec in roles.items():
            if self._check_role(name, spec):
                self.roles[name] = spec

        self._check_rules(data.get("model_rules"))
        sets = data.get("model_sets")
        if not isinstance(sets, dict) or not sets:
            self._err("model_sets must be a non-empty object")
        else:
            for set_name, rel in sets.items():
                if not safe_rel(rel):
                    self._err(f"model_sets.{set_name} must be a relative path inside the repository")

    def _check_role(self, name: str, spec) -> bool:
        where = f"roles.{name}"
        if not ROLE_NAME.match(name):
            self._err(f"{where}: role name must match {ROLE_NAME.pattern}")
            return False
        if not isinstance(spec, dict):
            self._err(f"{where} must be an object")
            return False
        ok = True
        for key in sorted(set(spec) - {"stamp", "instances", "bundle"}):
            self._err(f"{where}: unknown key {key!r}")
        if spec.get("stamp") != f"ROLE: {name}":
            self._err(f"{where}.stamp must be 'ROLE: {name}', got {spec.get('stamp')!r}")
            ok = False
        inst = spec.get("instances")
        if not is_int(inst) or inst < 1:
            self._err(f"{where}.instances must be a positive integer, got {inst!r}")
            ok = False
        bundle = spec.get("bundle")
        if isinstance(bundle, list):
            self.bundles[name] = [canonical(b) for b in bundle if isinstance(b, str) and b]
        if not isinstance(bundle, list) or not bundle or not all(isinstance(b, str) for b in bundle):
            self._err(f"{where}.bundle must be a non-empty list of paths")
            return False
        first = f"{name}/{ROLE_FILE}"
        if bundle[0] != first:
            self._err(f"{where}.bundle must start with {first}, got {bundle[0]!r}")
            ok = False
        seen: set[str] = set()
        in_shared = False
        for rel in bundle:
            canon = canonical(rel) if rel else rel
            if canon in seen:
                self._err(f"{where}.bundle lists {canon} twice")
                ok = False
            seen.add(canon)
            if not safe_rel(rel) or canon != rel or not rel.endswith(".md"):
                self._err(
                    f"{where}.bundle: {rel!r} must be a canonical relative .md path inside the "
                    f"repository (no './', '..', '//' or leading '/')"
                )
                ok = False
                continue
            top = PurePosixPath(rel).parts[0]
            if top == SHARED:
                in_shared = True
            elif top == name:
                if in_shared:
                    self._err(f"{where}.bundle: own file {rel} must come before shared files")
                    ok = False
            else:
                self._err(f"{where}.bundle: {rel} is neither under {name}/ nor {SHARED}/")
                ok = False
        return ok

    def _check_rules(self, rules) -> None:
        if not isinstance(rules, list):
            self._err("model_rules must be a list")
            return
        names = set(self.declared)
        for i, rule in enumerate(rules, 1):
            where = f"model_rules[{i}]"
            if not isinstance(rule, dict):
                self._err(f"{where} must be an object")
                continue
            for key in sorted(set(rule) - {"roles", "must_differ_from"}):
                self._err(f"{where}: unknown key {key!r}")
            roles = rule.get("roles")
            target = rule.get("must_differ_from")
            if not isinstance(roles, list) or not roles:
                self._err(f"{where}.roles must be a non-empty list")
                continue
            for r in roles:
                if not isinstance(r, str):
                    self._err(f"{where}.roles: each entry must be a role name, got {r!r}")
                elif r not in names:
                    self._err(f"{where}.roles: unknown role {r!r}")
            if not isinstance(target, str):
                self._err(f"{where}.must_differ_from must be a role name, got {target!r}")
            elif target not in names:
                self._err(f"{where}.must_differ_from: unknown role {target!r}")
            elif target in roles:
                self._err(f"{where}: a role cannot be required to differ from itself")

    def model_rules(self) -> list[dict]:
        rules = self.data.get("model_rules")
        if not isinstance(rules, list):
            return []
        return [
            r for r in rules
            if isinstance(r, dict)
            and isinstance(r.get("roles"), list)
            and all(isinstance(x, str) for x in r["roles"])
            and isinstance(r.get("must_differ_from"), str)
        ]

    def model_sets(self) -> dict[str, str]:
        sets = self.data.get("model_sets")
        if not isinstance(sets, dict):
            return {}
        return {k: v for k, v in sets.items() if safe_rel(v)}


def raw_lines(text: str) -> list[str]:
    """The file's lines: split on '\\n' only, after normalising '\\r\\n' and
    '\\r'. A final newline ends the last line; it does not start another."""
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    lines = text.split("\n")
    if lines and lines[-1] == "":
        lines.pop()
    return lines


def is_blank(line: str) -> bool:
    """Empty or ASCII spaces only; any other whitespace is not blank."""
    return line.strip(" ") == ""


def allowed_char(ch: str) -> bool:
    return ch == "\n" or "\x20" <= ch <= "\x7e"


def scan(lines: list[str]):
    """Yield (line number, kind, line) for each raw line: kind is 'fence' (an
    opening or closing fence line), 'code' (inside a fence) or 'text'; and,
    last, (line number of the opener, 'unclosed', line) if a fence is never
    closed.

    A fence line is one whose first non-space characters, after any list
    markers, are three or more backticks or tildes. Any fence line outside a
    fence opens one (a misplaced opener is reported separately, and treating
    what follows as code keeps it from satisfying a required line). A fence
    closes only with a fence line of the same character, at least as long,
    followed by nothing but spaces.
    """
    fence: tuple[str, int, int, str] | None = None
    for n, line in enumerate(lines, 1):
        m = FENCE_LINE.match(line)
        if fence:
            if m and m.group(3)[0] == fence[0] and len(m.group(3)) >= fence[1] and is_blank(m.group(4)):
                fence = None
                yield n, "fence", line
            else:
                yield n, "code", line
            continue
        if m:
            fence = (m.group(3)[0], len(m.group(3)), n, line)
            yield n, "fence", line
            continue
        yield n, "text", line
    if fence:
        yield fence[2], "unclosed", fence[3]


def strict_form_errors(rel: str, lines: list[tuple[int, str, str]], required: list[str]) -> list[str]:
    """The V1 and V2 line errors. Everywhere: characters, comments, quotes,
    '<' lines, setext underlines, hash lines other than the required headings
    and misplaced fence lines. Outside fenced code: four-space indentation."""
    errors = []
    prev_blank = True
    for n, kind, line in lines:
        if kind == "unclosed":
            errors.append(
                f"{rel}:{n}: this fence is never closed (a closing fence of the same character, "
                f"at least as long, must follow before the end of the file)"
            )
            continue
        for code in sorted({ord(ch) for ch in line if not allowed_char(ch)}):
            errors.append(
                f"{rel}:{n}: character U+{code:04X} is not allowed in a ROLE.md "
                f"(only printable ASCII, 0x20-0x7E, and line breaks)"
            )
        found = []
        if "<!--" in line:
            found.append("comment")
        if QUOTED.match(line):
            found.append("quote")
        if ANGLE.match(line):
            found.append("angle")
        m = UNDERLINE.match(line)
        if m and (m.group(1)[0] == "=" or not prev_blank):
            found.append("setext")
        if kind != "code" and line.startswith("    ") and not is_blank(line):
            found.append("indent")
        if HASH_LINE.match(line) and line not in required:
            found.append("hash")
        fm = FENCE_LINE.match(line)
        if fm and (fm.group(1) or fm.group(2)):
            found.append("fence")
        errors += [f"{rel}:{n}: {STRICT_FORM[key]}" for key in found]
        prev_blank = is_blank(line)
    return errors


def role_title(name: str) -> str:
    return name.replace("-", " ").title()


def check_role_md(name: str, rel: str, text: str) -> list[str]:
    raw = raw_lines(text)
    required = [f"# {role_title(name)}"] + [f"## {h}" for h in REQUIRED_H2]
    scanned = list(scan(raw))
    errors = strict_form_errors(rel, scanned, required)
    lines = [entry for entry in scanned if entry[1] != "unclosed"]

    # Rule 2 does not depend on fences: every hash line counts, wherever it is.
    hash_lines = [(n, line) for n, line in enumerate(raw, 1) if HASH_LINE.match(line)]
    found = [line for _, line in hash_lines]
    if found != required:
        i = next((k for k, (a, b) in enumerate(zip(found, required)) if a != b), min(len(found), len(required)))
        at = hash_lines[i][0] if i < len(hash_lines) else max(len(raw), 1)
        want = ", ".join(required)
        got = ", ".join(found) or "none"
        errors.append(
            f"{rel}:{at}: headings must be exactly [{want}] in this order, each once and at column 0, "
            f"with no other line starting with '#'; found [{got}]"
        )
    if name == LEAD:
        return errors

    sections: list[str | None] = []  # the section (required heading) each line is in
    section: str | None = None
    heading_at: dict[str, int] = {}
    for n, _, line in lines:
        if line in required:
            section = line[3:] if line.startswith("## ") else None
            heading_at.setdefault(line, n)
        sections.append(section)
    report_at = heading_at.get(f"## {REPORT_SECTION}", 1)

    if not any(kind == "text" and BAN_LINE.match(line) for _, kind, line in lines):
        errors.append(
            f"{rel}:1: missing the agent-ban sentence: outside fenced code, one line must be exactly "
            f"{AGENT_BAN!r}, optionally after a '- ' or 'N. ' list marker"
        )
    stamp = f"ROLE: {name}"
    report = [(i, kind, line) for i, (_, kind, line) in enumerate(lines) if sections[i] == REPORT_SECTION]
    if not any(kind == "text" and line == stamp for _, kind, line in report):
        errors.append(
            f"{rel}:{report_at}: the {REPORT_SECTION} section must contain a line consisting of exactly "
            f"{stamp!r}, outside fenced code"
        )
    rules = [i for i, kind, line in report if kind == "text" and line == FIRST_LINE_RULE]
    if not rules:
        errors.append(
            f"{rel}:{report_at}: the {REPORT_SECTION} section must contain the line {FIRST_LINE_RULE!r}, "
            f"exactly and on one line, outside fenced code"
        )
    elif not any(followed_by(lines, i, stamp) for i in rules):
        errors.append(
            f"{rel}:{lines[rules[0]][0]}: the line {FIRST_LINE_RULE!r} must be followed "
            f"(blank lines allowed) by the stamp line {stamp!r}"
        )
    return errors


def followed_by(lines: list[tuple[int, str, str]], i: int, wanted: str) -> bool:
    """True if the next non-blank line after lines[i] is a text line equal to `wanted`."""
    for _, kind, line in lines[i + 1:]:
        if not is_blank(line):
            return kind == "text" and line == wanted
    return False


def check_forbidden(rel: str, text: str) -> list[str]:
    errors = []
    for n, line in enumerate(raw_lines(text), 1):
        for m in FORBIDDEN.finditer(line):
            errors.append(f"{rel}:{n}: forbidden word {m.group(0)!r}")
    return errors


def instances_of(entry, count: int, where: str, errors: list[str]) -> list[dict] | None:
    """Validate a role's model entries; return them with families normalised."""
    if count == 1:
        items = [entry] if isinstance(entry, dict) else None
        shape = "an object"
    else:
        items = entry if isinstance(entry, list) and len(entry) == count else None
        shape = f"a list of {count} entries"
    if items is None:
        errors.append(f"{where} must be {shape} (instances: {count})")
        return None
    out = []
    for i, item in enumerate(items, 1):
        tag = where if count == 1 else f"{where} #{i}"
        if not isinstance(item, dict):
            errors.append(f"{tag} must be an object")
            continue
        ok = True
        for key in sorted(set(item) - MODEL_KEYS):
            errors.append(f"{tag}: unknown key {key!r}")
        provider, family, effort = item.get("provider"), item.get("family"), item.get("effort")
        if not isinstance(provider, str) or provider not in PROVIDERS:
            errors.append(f"{tag}: provider must be one of {sorted(PROVIDERS)}, got {provider!r}")
            ok = False
        if not is_name(family):
            errors.append(f"{tag}: family must be a non-empty string")
            ok = False
        if not isinstance(effort, str) or effort not in EFFORTS:
            errors.append(f"{tag}: effort must be one of {sorted(EFFORTS)}, got {effort!r}")
            ok = False
        if ok:
            out.append({"provider": provider, "family": family.strip().lower(), "effort": effort})
    return out if len(out) == len(items) else None


def check_model_set(root: Path, team: Team, set_name: str, rel: str) -> list[str]:
    errors: list[str] = []
    path = root / rel
    if not path.is_file():
        return [f"{TEAM_FILE}: model set {set_name!r} names {rel}, which does not exist"]
    text = read_text(path, rel, errors)
    if text is None:
        return errors
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        return [f"{rel}: invalid JSON: {exc}"]
    if not isinstance(data, dict):
        return [f"{rel}: top level must be a JSON object"]
    schema = data.get("schema")
    if not (is_int(schema) and schema == SCHEMA_VERSION):
        errors.append(f"{rel}: schema must be {SCHEMA_VERSION}, got {schema!r}")
    if data.get("name") != set_name:
        errors.append(f"{rel}: name must be {set_name!r}, got {data.get('name')!r}")
    for key in sorted(set(data) - {"schema", "name", "description", "roles", "exceptions"}):
        errors.append(f"{rel}: unknown key {key!r}")
    if "description" in data and not isinstance(data["description"], str):
        errors.append(f"{rel}: description must be a string, got {data['description']!r}")

    roles = data.get("roles")
    if not isinstance(roles, dict):
        return errors + [f"{rel}: roles must be an object"]
    for name in team.declared:
        if name not in roles:
            errors.append(f"{rel}: role {name!r} has no model")
    for name in roles:
        if name not in team.declared:
            errors.append(f"{rel}: unknown role {name!r}")
    models: dict[str, list[dict]] = {}
    for name, spec in team.roles.items():
        if name in roles:
            items = instances_of(roles[name], spec["instances"], f"{rel}: {name}", errors)
            if items is not None:
                models[name] = items

    exceptions = data.get("exceptions", [])
    declared: dict[tuple, bool] = {}
    if not isinstance(exceptions, list):
        errors.append(f"{rel}: exceptions must be a list")
        exceptions = []
    for i, exc in enumerate(exceptions, 1):
        where = f"{rel}: exceptions[{i}]"
        if not isinstance(exc, dict):
            errors.append(f"{where} must be an object")
            continue
        for key in sorted(set(exc) - {"role", "instance", "must_differ_from", "reason"}):
            errors.append(f"{where}: unknown key {key!r}")
        if not is_name(exc.get("reason")):
            errors.append(f"{where}: reason must be a non-empty string")
        bad = False
        for key in ("role", "must_differ_from"):
            if not isinstance(exc.get(key), str):
                errors.append(f"{where}: {key} must be a role name, got {exc.get(key)!r}")
                bad = True
        inst = exc.get("instance", 1)
        if not is_int(inst) or inst < 1:
            errors.append(f"{where}: instance must be a positive integer")
            bad = True
        if not bad:
            declared[(exc["role"], inst, exc["must_differ_from"])] = False

    for rule in team.model_rules():
        target = rule["must_differ_from"]
        for name in rule["roles"]:
            if name not in models or target not in models:
                continue
            for i, mine in enumerate(models[name], 1):
                for j, theirs in enumerate(models[target], 1):
                    if (mine["provider"], mine["family"]) != (theirs["provider"], theirs["family"]):
                        continue
                    key = (name, i, target)
                    if key in declared:
                        declared[key] = True
                        continue
                    tag = name if len(models[name]) == 1 else f"{name} #{i}"
                    ttag = target if len(models[target]) == 1 else f"{target} #{j}"
                    errors.append(
                        f"{rel}: {tag} ({mine['provider']} {mine['family']}) must differ from "
                        f"{ttag} ({theirs['provider']} {theirs['family']}) and no exception is declared"
                    )
    for (name, inst, target), used in declared.items():
        if not used:
            errors.append(
                f"{rel}: unused exception for {name} #{inst} vs {target}: no rule is violated there"
            )
    return errors


def link_problem(root: Path, rel: str) -> str | None:
    """Why a bundle path is not a plain file inside the repository, or None.

    No component of the path may be a symbolic link, and the resolved path
    must lie inside the repository root.
    """
    parts = PurePosixPath(rel).parts
    for k in range(1, len(parts) + 1):
        if (root / Path(*parts[:k])).is_symlink():
            return f"passes through a symbolic link ({'/'.join(parts[:k])}); bundle files must be plain files"
    try:
        (root / rel).resolve().relative_to(root.resolve())
    except ValueError:
        return "resolves outside the repository"
    return None


def role_folders(root: Path) -> list[str]:
    """Top-level directories that contain a ROLE.md, whatever team.json says,
    including dot-folders; only .git and .github are skipped."""
    return sorted(
        p.name for p in root.iterdir()
        if p.is_dir() and p.name not in SKIPPED_DIRS and (p / ROLE_FILE).is_file()
    )


def validate(root) -> list[str]:
    """Return a list of human-readable errors; empty means the tree is valid."""
    root = Path(root)
    team = Team(root)
    errors = list(team.errors)
    if not team.loaded:
        return errors

    bundled: set[str] = set()
    for name, bundle in team.bundles.items():
        for rel in bundle:
            bundled.add(rel)
            if not safe_rel(rel):
                continue
            problem = link_problem(root, rel)
            if problem:
                errors.append(f"{TEAM_FILE}: roles.{name}.bundle: {rel} {problem}")
            if not (root / rel).is_file():
                errors.append(f"{TEAM_FILE}: roles.{name}.bundle names {rel}, which does not exist")

    found_roles = role_folders(root)
    for name in found_roles:
        if name not in team.declared:
            errors.append(f"{name}/{ROLE_FILE}: {name}/ has a {ROLE_FILE} but is not a role in {TEAM_FILE}")

    # Every markdown file under a role folder (declared or found) or shared/.
    roles = sorted({n for n in team.declared if ROLE_NAME.match(n)} | set(found_roles))
    scanned: list[str] = []
    for top in roles + [SHARED]:
        folder = root / top
        if folder.is_dir():
            scanned += sorted(p.relative_to(root).as_posix() for p in folder.rglob("*") if is_markdown(p))
    texts: dict[str, str] = {}
    for rel in scanned:
        if rel not in bundled:
            errors.append(f"{rel}: orphan file, not listed in any bundle")
    # V3: scan everything the printer could emit, not only what discovery found.
    extra = sorted(rel for rel in bundled - set(scanned) if safe_rel(rel) and (root / rel).is_file())
    for rel in scanned + extra:
        text = read_text(root / rel, rel, errors)
        if text is not None:
            texts[rel] = text
            errors += check_forbidden(rel, text)

    for name in roles:
        rel = f"{name}/{ROLE_FILE}"
        if rel in texts:
            errors += check_role_md(name, rel, texts[rel])

    sets = team.model_sets()
    for set_name, rel in sets.items():
        errors += check_model_set(root, team, set_name, rel)
    listed = {PurePosixPath(rel).as_posix() for rel in sets.values()}
    models_dir = root / MODELS_DIR
    if models_dir.is_dir():
        for path in sorted(models_dir.glob("*.json")):
            rel = path.relative_to(root).as_posix()
            if rel not in listed:
                errors.append(f"{rel}: model set file is not listed in {TEAM_FILE} model_sets")
    return errors


def assemble(root: Path, team: Team, name: str) -> str:
    parts = []
    for rel in team.roles[name]["bundle"]:
        text = (root / rel).read_text(encoding="utf-8")
        if not text.endswith("\n"):
            text += "\n"
        parts.append(f"<!-- file: {rel} -->\n{text}")
    return "\n".join(parts)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--root", default=Path(__file__).resolve().parent.parent, type=Path,
                        help="repository root (default: the parent of scripts/)")
    parser.add_argument("--print", dest="role", metavar="ROLE",
                        help="print the assembled bundle for ROLE; word count goes to stderr")
    args = parser.parse_args(argv)
    root: Path = args.root

    if args.role is not None:
        team = Team(root)
        if not team.loaded:
            print("\n".join(team.errors), file=sys.stderr)
            return 2
        if args.role not in team.roles:
            known = ", ".join(sorted(team.roles)) or "none"
            print(f"unknown role {args.role!r}; known roles: {known}", file=sys.stderr)
            return 2
        missing = [r for r in team.roles[args.role]["bundle"] if not (root / r).is_file()]
        if missing:
            print(f"missing bundle files: {', '.join(missing)}", file=sys.stderr)
            return 1
        try:
            text = assemble(root, team, args.role)
        except UnicodeDecodeError:
            print("a bundle file is not valid UTF-8; run the validator for details", file=sys.stderr)
            return 1
        sys.stdout.write(text)
        body = "\n".join(l for l in text.splitlines() if not l.startswith("<!-- file: "))
        files = len(team.roles[args.role]["bundle"])
        print(f"{args.role}: {len(body.split())} words ({files} files)", file=sys.stderr)
        return 0

    errors = validate(root)
    if errors:
        for e in errors:
            print(f"ERROR: {e}")
        print(f"{len(errors)} error(s)", file=sys.stderr)
        return 1
    team = Team(root)
    files = len({r for spec in team.roles.values() for r in spec["bundle"]})
    print(f"OK: {len(team.roles)} roles, {files} bundled files, {len(team.model_sets())} model sets")
    return 0


if __name__ == "__main__":
    sys.exit(main())
