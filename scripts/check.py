#!/usr/bin/env python3
"""Validate the playbook and assemble per-role instruction bundles.

Usage:
    python3 scripts/check.py                 # validate; exit 0 if clean, 1 if not
    python3 scripts/check.py --print ROLE    # print ROLE's assembled bundle
    python3 scripts/check.py --root DIR ...  # operate on another tree (tests)

The validator is generic: it knows the lead role and the shared folder by
name, and nothing else about which roles a team has.

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

# Every non-lead ROLE.md contains this exact sentence, outside code, at the
# start of a line (optionally after a list marker) and followed by nothing
# but the end of the line or the next sentence.
AGENT_BAN = (
    "You never start, spawn, schedule or delegate to other agents, sub-agents, "
    "threads, workflows or new machines, even when a tool or a built-in skill offers it."
)
# The Report section of every non-lead ROLE.md states this, and contains a
# line consisting of exactly the role's stamp.
STAMP_RULE = "The first line of every report is exactly:"

# Launcher-specific words that must not appear in role or skill texts
# (whole words, case-sensitive).
FORBIDDEN = re.compile(r"\b(Boat|T3|VMs|VM)\b")

PROVIDERS = {"codex", "claude"}
EFFORTS = {"minimal", "low", "medium", "high", "xhigh", "max"}
MODEL_KEYS = {"provider", "family", "effort"}
ROLE_NAME = re.compile(r"^[a-z][a-z0-9-]*$")

ATX = re.compile(r"^ {0,3}(#{1,6})(?=[ \t]|$)(.*)$")
ATX_CLOSE = re.compile(r"(^|[ \t])#+$")
FENCE_OPEN = re.compile(r"^ {0,3}(`{3,}|~{3,})(.*)$")
FENCE_CLOSE = re.compile(r"^ {0,3}(`{3,}|~{3,})[ \t]*$")
SETEXT = re.compile(r"^ {0,3}(=+|-+)[ \t]*$")
NOT_PARAGRAPH = re.compile(
    r"^ {0,3}(?:[-*+](?:[ \t]|$)|\d{1,9}[.)](?:[ \t]|$)|>|<|([-*_])(?:[ \t]*\1){2,}[ \t]*$)"
)
LIST_MARKER = r"(?:(?:[-*+]|\d{1,9}[.)]) )?"


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
            self.bundles[name] = [b for b in bundle if isinstance(b, str)]
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
            if rel in seen:
                self._err(f"{where}.bundle lists {rel} twice")
                ok = False
            seen.add(rel)
            if not safe_rel(rel) or not rel.endswith(".md"):
                self._err(f"{where}.bundle: {rel!r} must be a relative .md path inside the repository")
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


def scan(text: str):
    """Yield (kind, line) for each line: kind is 'fence', 'code' or 'text'.

    A fence opens with three or more backticks or tildes and closes only with
    a line of the same character, at least as long, and nothing else. A
    backtick opener whose rest contains a backtick is inline code, not a fence.
    """
    fence: tuple[str, int] | None = None
    for line in text.splitlines():
        if fence:
            m = FENCE_CLOSE.match(line)
            if m and m.group(1)[0] == fence[0] and len(m.group(1)) >= fence[1]:
                fence = None
                yield "fence", line
            else:
                yield "code", line
            continue
        m = FENCE_OPEN.match(line)
        if m and not (m.group(1)[0] == "`" and "`" in m.group(2)):
            fence = (m.group(1)[0], len(m.group(1)))
            yield "fence", line
            continue
        yield "text", line


def atx(line: str) -> tuple[int, str] | None:
    m = ATX.match(line)
    if not m:
        return None
    title = ATX_CLOSE.sub("", m.group(2).strip()).strip()
    return len(m.group(1)), title


def is_paragraph_line(line: str) -> bool:
    if not line.strip() or line.startswith("    ") or line.startswith("\t"):
        return False
    return not NOT_PARAGRAPH.match(line) and atx(line) is None


def parse(text: str) -> tuple[list[tuple[int, str]], list[tuple[str | None, str, str]]]:
    """Return every heading (ATX of any level and setext) outside code, and
    every line as (current level-1/2 section title, kind, line)."""
    found: list[tuple[int, str]] = []
    body: list[tuple[str | None, str, str]] = []
    section: str | None = None
    prev: str | None = None
    for kind, line in scan(text):
        heading = None
        if kind == "text":
            heading = atx(line)
            m = SETEXT.match(line)
            if heading is None and m and prev is not None:
                heading = (1 if m.group(1)[0] == "=" else 2, prev.strip())
            prev = line if heading is None and is_paragraph_line(line) else None
        else:
            prev = None
        if heading:
            found.append(heading)
            if heading[0] <= 2:
                section = heading[1]
            continue
        body.append((section, kind, line))
    return found, body


def role_title(name: str) -> str:
    return name.replace("-", " ").title()


def check_role_md(name: str, rel: str, text: str) -> list[str]:
    errors = []
    found, body = parse(text)
    expected = [(1, role_title(name))] + [(2, h) for h in REQUIRED_H2]
    if found != expected:
        want = ", ".join("#" * lvl + " " + t for lvl, t in expected)
        got = ", ".join("#" * lvl + " " + t for lvl, t in found) or "none"
        errors.append(
            f"{rel}: headings must be exactly [{want}] in this order, with no other headings; "
            f"found [{got}]"
        )
    if name == LEAD:
        return errors

    ban = re.compile("^" + LIST_MARKER + re.escape(AGENT_BAN) + "(?: |$)")
    if not any(kind == "text" and ban.match(" ".join(line.split())) for _, kind, line in body):
        errors.append(
            f"{rel}: missing the agent-ban sentence; a line must start (after an optional list marker) "
            f"with exactly: {AGENT_BAN!r}"
        )
    stamp = f"ROLE: {name}"
    report = [(kind, line) for sec, kind, line in body if sec == REPORT_SECTION]
    if not any(kind != "fence" and line.strip() == stamp for kind, line in report):
        errors.append(
            f"{rel}: the {REPORT_SECTION} section must contain a line consisting of exactly {stamp!r}"
        )
    prose = " ".join(" ".join(line for kind, line in report if kind == "text").split())
    if STAMP_RULE not in prose:
        errors.append(f"{rel}: the {REPORT_SECTION} section must state {STAMP_RULE!r}")
    return errors


def check_forbidden(rel: str, text: str) -> list[str]:
    errors = []
    for n, line in enumerate(text.splitlines(), 1):
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


def role_folders(root: Path) -> list[str]:
    """Top-level directories that contain a ROLE.md, whatever team.json says."""
    return sorted(
        p.name for p in root.iterdir()
        if p.is_dir() and not p.name.startswith(".") and (p / ROLE_FILE).is_file()
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
            if safe_rel(rel) and not (root / rel).is_file():
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
    for rel in scanned:
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
