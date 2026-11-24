# Researching

## Plan the search

1. Turn each question into a version-specific, checkable query: "Does library X version 4 support streaming uploads larger than 2 GB?" rather than "Is X good for uploads?". Fix the version and date constraints before you start, so you do not collect answers for the wrong version.
2. Identify what would answer it definitively, and where that lives: the official documentation, the specification, the changelog, the source code, the issue tracker, the vendor's pricing or limits page.

## Weigh sources

- Maintainers' statements in the official issue tracker or discussion forum, and official blog posts, are primary but informal: usable, labelled as such.
- When documentation and code disagree, the code (at the relevant version) describes the behaviour; the documentation describes the intent. Report both.
- Use a stable link: a versioned docs page, a tagged file, a specific issue. Check that no later release or advisory supersedes the source.

## Reason

- Look for disconfirming evidence, not only confirming: search the issue tracker for bugs and limitations, the changelog for breaking changes and deprecations.
- When sources contradict each other, find the likely reason: version, platform, an outdated page.
- Confidence levels:
  - **high**: several primary sources agree, current version, no contradiction;
  - **medium**: one primary source, or primary sources with minor gaps;
  - **low**: secondary sources only, outdated sources, or unresolved contradictions.
- When you find no answer, list where you looked: "Not documented; not found in the source at tag v4.2; the closest is issue #123, unresolved" is a useful answer.
