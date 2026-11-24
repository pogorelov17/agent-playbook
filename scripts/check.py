#!/usr/bin/env python3
"""Validate the playbook and assemble per-role instruction bundles.

Usage:
    python3 scripts/check.py                 # validate; exit 0 if clean, 1 if not
    python3 scripts/check.py --print ROLE    # print ROLE's assembled bundle
    python3 scripts/check.py --root DIR ...  # operate on another tree (tests)

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

REQUIRED_H2 = [
    "Who you are",
    "What you receive",
    "What you must deliver",
    "Rules",
    "You must not",
    "Report",
]

# Every non-lead ROLE.md must contain this sentence (whitespace-insensitive).
AGENT_BAN = "You never start, spawn, schedule or delegate to other agents"

# Launcher-specific words that must not appear in role or skill texts.
FORBIDDEN = re.compile(r"\b(Boat|T3|VMs|VM)\b", re.IGNORECASE)

PROVIDERS = {"codex", "claude"}
EFFORTS = {"minimal", "low", "medium", "high", "xhigh", "max"}
MODEL_KEYS = {"provider", "family", "effort"}
ROLE_NAME = re.compile(r"^[a-z][a-z0-9-]*$")
HEADING = re.compile(r"^(#{1,6})\s+(.*?)\s*#*\s*$")
FENCE = re.compile(r"^\s*(```|~~~)")


class Team:
    """Parsed team.json plus the errors found while parsing it."""

    def __init__(self, root: Path):
        self.root = root
        self.errors: list[str] = []
        self.data: dict = {}
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
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            self._err(f"invalid JSON: {exc}")
            return
        if not isinstance(data, dict):
            self._err("top level must be a JSON object")
            return
        self.data = data
        self.loaded = True

        if data.get("schema") != SCHEMA_VERSION:
            self._err(f"schema must be {SCHEMA_VERSION}, got {data.get('schema')!r}")
        for key in ("name", "version"):
            if not isinstance(data.get(key), str) or not data[key].strip():
                self._err(f"{key} must be a non-empty string")
        known = {"schema", "name", "version", "roles", "model_rules", "model_sets"}
        for key in sorted(set(data) - known):
            self._err(f"unknown top-level key {key!r}")

        roles = data.get("roles")
        if not isinstance(roles, dict) or not roles:
            self._err("roles must be a non-empty object")
            roles = {}
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
                if not isinstance(rel, str) or not safe_rel(rel):
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
        if not isinstance(inst, int) or isinstance(inst, bool) or inst < 1:
            self._err(f"{where}.instances must be a positive integer, got {inst!r}")
            ok = False
        bundle = spec.get("bundle")
        if not isinstance(bundle, list) or not bundle or not all(isinstance(b, str) for b in bundle):
            self._err(f"{where}.bundle must be a non-empty list of paths")
            return False
        first = f"{name}/ROLE.md"
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
        names = set(self.data.get("roles") or {})
        for i, rule in enumerate(rules, 1):
            where = f"model_rules[{i}]"
            if not isinstance(rule, dict):
                self._err(f"{where} must be an object")
                continue
            roles = rule.get("roles")
            target = rule.get("must_differ_from")
            if not isinstance(roles, list) or not roles:
                self._err(f"{where}.roles must be a non-empty list")
                continue
            for r in roles:
                if r not in names:
                    self._err(f"{where}.roles: unknown role {r!r}")
            if target not in names:
                self._err(f"{where}.must_differ_from: unknown role {target!r}")
            elif target in roles:
                self._err(f"{where}: a role cannot be required to differ from itself")

    def model_rules(self) -> list[dict]:
        rules = self.data.get("model_rules")
        if not isinstance(rules, list):
            return []
        return [r for r in rules if isinstance(r, dict) and isinstance(r.get("roles"), list)]

    def model_sets(self) -> dict[str, str]:
        sets = self.data.get("model_sets")
        if not isinstance(sets, dict):
            return {}
        return {k: v for k, v in sets.items() if isinstance(v, str) and safe_rel(v)}


def safe_rel(rel: str) -> bool:
    p = PurePosixPath(rel)
    return bool(rel) and not p.is_absolute() and ".." not in p.parts and "\\" not in rel


def read(root: Path, rel: str) -> str:
    return (root / rel).read_text(encoding="utf-8")


def headings(text: str) -> list[tuple[int, str]]:
    """Return (level, title) for every ATX heading outside fenced code."""
    out = []
    in_fence = False
    for line in text.splitlines():
        if FENCE.match(line):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        m = HEADING.match(line)
        if m:
            out.append((len(m.group(1)), m.group(2)))
    return out


def role_title(name: str) -> str:
    return name.replace("-", " ").title()


def check_role_md(name: str, rel: str, text: str, stamp: str) -> list[str]:
    errors = []
    found = [(lvl, t) for lvl, t in headings(text) if lvl <= 2]
    expected = [(1, role_title(name))] + [(2, h) for h in REQUIRED_H2]
    norm = [(lvl, t.strip().lower()) for lvl, t in found]
    if norm != [(lvl, t.lower()) for lvl, t in expected]:
        want = ", ".join("#" * lvl + " " + t for lvl, t in expected)
        got = ", ".join("#" * lvl + " " + t for lvl, t in found) or "none"
        errors.append(f"{rel}: headings must be exactly [{want}] in this order; found [{got}]")
    if name != LEAD:
        flat = " ".join(text.split())
        if AGENT_BAN not in flat:
            errors.append(f"{rel}: missing the agent-ban rule (must contain: {AGENT_BAN!r})")
        lines = {line.strip().strip("`").strip() for line in text.splitlines()}
        if stamp not in lines:
            errors.append(f"{rel}: missing a stamp line consisting of exactly {stamp!r}")
    return errors


def check_forbidden(rel: str, text: str) -> list[str]:
    errors = []
    for n, line in enumerate(text.splitlines(), 1):
        for m in FORBIDDEN.finditer(line):
            errors.append(f"{rel}:{n}: forbidden word {m.group(0)!r}")
    return errors


def instances_of(entry, count: int, where: str, errors: list[str]) -> list[dict] | None:
    if count == 1:
        items = [entry] if isinstance(entry, dict) else None
        shape = "an object"
    else:
        items = entry if isinstance(entry, list) and len(entry) == count else None
        shape = f"a list of {count} entries"
    if items is None:
        errors.append(f"{where} must be {shape} (instances: {count})")
        return None
    ok = True
    for i, item in enumerate(items, 1):
        tag = where if count == 1 else f"{where} #{i}"
        if not isinstance(item, dict):
            errors.append(f"{tag} must be an object")
            ok = False
            continue
        for key in sorted(set(item) - MODEL_KEYS):
            errors.append(f"{tag}: unknown key {key!r}")
        if item.get("provider") not in PROVIDERS:
            errors.append(f"{tag}: provider must be one of {sorted(PROVIDERS)}, got {item.get('provider')!r}")
            ok = False
        if not isinstance(item.get("family"), str) or not item["family"].strip():
            errors.append(f"{tag}: family must be a non-empty string")
            ok = False
        if item.get("effort") not in EFFORTS:
            errors.append(f"{tag}: effort must be one of {sorted(EFFORTS)}, got {item.get('effort')!r}")
            ok = False
    return items if ok else None


def check_model_set(root: Path, team: Team, set_name: str, rel: str) -> list[str]:
    errors: list[str] = []
    path = root / rel
    if not path.is_file():
        return [f"{TEAM_FILE}: model set {set_name!r} names {rel}, which does not exist"]
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return [f"{rel}: invalid JSON: {exc}"]
    if not isinstance(data, dict):
        return [f"{rel}: top level must be a JSON object"]
    if data.get("schema") != SCHEMA_VERSION:
        errors.append(f"{rel}: schema must be {SCHEMA_VERSION}")
    if data.get("name") != set_name:
        errors.append(f"{rel}: name must be {set_name!r}, got {data.get('name')!r}")
    for key in sorted(set(data) - {"schema", "name", "description", "roles", "exceptions"}):
        errors.append(f"{rel}: unknown key {key!r}")

    roles = data.get("roles")
    if not isinstance(roles, dict):
        return errors + [f"{rel}: roles must be an object"]
    for name in team.roles:
        if name not in roles:
            errors.append(f"{rel}: role {name!r} has no model")
    for name in roles:
        if name not in (team.data.get("roles") or {}):
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
        if not isinstance(exc.get("reason"), str) or not exc["reason"].strip():
            errors.append(f"{where}: reason must be a non-empty string")
        inst = exc.get("instance", 1)
        if not isinstance(inst, int) or isinstance(inst, bool) or inst < 1:
            errors.append(f"{where}: instance must be a positive integer")
            continue
        declared[(exc.get("role"), inst, exc.get("must_differ_from"))] = False

    for rule in team.model_rules():
        target = rule.get("must_differ_from")
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


def validate(root) -> list[str]:
    """Return a list of human-readable errors; empty means the tree is valid."""
    root = Path(root)
    team = Team(root)
    errors = list(team.errors)
    if not team.loaded:
        return errors

    bundled: set[str] = set()
    for name, spec in team.roles.items():
        for rel in spec["bundle"]:
            bundled.add(rel)
            if not (root / rel).is_file():
                errors.append(f"{TEAM_FILE}: roles.{name}.bundle names {rel}, which does not exist")

    # Orphans: every markdown file under a role folder or shared/ must be bundled.
    scanned: list[str] = []
    for top in sorted(set(team.data.get("roles") or {}) | {SHARED}):
        folder = root / top
        if folder.is_dir():
            scanned += sorted(p.relative_to(root).as_posix() for p in folder.rglob("*.md"))
    for rel in scanned:
        if rel not in bundled:
            errors.append(f"{rel}: orphan file, not listed in any bundle")

    for rel in scanned:
        errors += check_forbidden(rel, read(root, rel))

    for name, spec in team.roles.items():
        rel = f"{name}/ROLE.md"
        if (root / rel).is_file():
            errors += check_role_md(name, rel, read(root, rel), spec["stamp"])

    for set_name, rel in team.model_sets().items():
        errors += check_model_set(root, team, set_name, rel)
    return errors


def assemble(root: Path, team: Team, name: str) -> str:
    parts = []
    for rel in team.roles[name]["bundle"]:
        text = read(root, rel)
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
        text = assemble(root, team, args.role)
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
