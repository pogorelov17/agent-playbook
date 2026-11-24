# Exploring a codebase

Your goal is accurate answers with references, fast. Breadth first to find where things are, then depth only where the questions need it.

## Orient (a few minutes)

1. Confirm the commit: `git rev-parse HEAD`.
2. Read the project's instruction file (`AGENTS.md` or `CLAUDE.md`), the `README`, and any design document (`DESIGN.md`, `docs/`).
3. Get the shape: the top-level layout (`git ls-files | head -200`, or a directory listing two levels deep), the build and dependency files (`package.json`, `pyproject.toml`, `go.mod`, `Cargo.toml`, `Makefile`, CI workflows), the entry points.
4. Note the languages, frameworks and test setup. Many questions are answered here.

## Find

- Search for names before reading files: `git grep -n "<name>"`, or a fast search tool if present. Search for the user-visible string (an error message, a URL path, a CLI flag) to find where a feature lives.
- Follow from the entry point: route or command → handler → service → storage. Note each hop with its file and line.
- Find all callers before claiming a function is unused or safe to change: search for its name, its import, and dynamic uses (string names, registries, reflection).
- Look at the tests for a module: they show intended behaviour and the supported cases.
- Use history when the question is "why": `git log -p --follow <file>`, `git blame -L <start>,<end> <file>`.

## Confirm

- Open the file and read the actual lines before citing them. Search hits without context mislead.
- When behaviour matters and can be observed safely, run it: the existing tests for that module, a build, a small read-only command. Quote the output.
- If two places seem to implement the same thing, say which one is actually used, and how you know (the import chain, a log line, a test).

## Answer

For each question:

- Lead with the direct answer in one or two sentences.
- Then the references: `path/file.ext:line` or `path/file.ext:start-end`, at the examined commit.
- Then the evidence: a short quote of the decisive lines, or the command and its output.
- Then the confidence: **confirmed** (read the code path end to end, or ran it), or **inferred** (based on naming, partial reading, or convention), with what would confirm it.

Answer what was asked, at the level of detail the lead needs for its stated purpose. If the purpose is "name the files to change", give the files and the functions; do not explain the whole subsystem.

## Pitfalls

- Trusting file names or comments over the code.
- Missing generated, vendored or configuration-driven code (code generation, dependency injection, plugin registries, environment-based switches).
- Answering for the wrong branch or an outdated checkout.
- Stopping at the first match when there are several.
