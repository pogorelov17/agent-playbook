# Researching

A research answer is only as good as its weakest source. Aim for answers the lead can rely on without re-checking: primary sources, dated, quoted, with the uncertainty stated.

## Plan the search

1. Restate each question as something checkable: "Does library X version 4 support streaming uploads larger than 2 GB?" rather than "Is X good for uploads?".
2. Identify what would answer it definitively, and where that lives: the official documentation, the specification, the changelog, the source code, the issue tracker, the vendor's pricing or limits page.
3. Note the version and date constraints before you start, so you do not collect answers for the wrong version.

## Rank sources

From most to least trustworthy, in general:

1. **Primary, authoritative**: the specification or standard; official documentation for the version in question; the source code and its tests; official changelogs and release notes; official security advisories.
2. **Primary, informal**: maintainers' statements in the official issue tracker or discussion forum; official blog posts.
3. **Secondary**: reputable technical articles, books, conference talks.
4. **Tertiary**: forum answers, aggregators, generated summaries.

When documentation and code disagree, the code (at the relevant version) describes the behaviour; the documentation describes the intent. Report both.

## Read and record

Record each source as the evidence form in `shared/verification.md` requires, plus its title, the version it describes and the date you accessed it. Use a stable link: a versioned docs page, a tagged file, a specific issue.

Check that the source applies: right product, right version, right platform, not superseded by a later release or advisory. A page from three major versions ago is not evidence about the current one.

## Reason

- Look for disconfirming evidence, not only confirming: search the issue tracker for bugs and limitations, the changelog for breaking changes and deprecations.
- When sources contradict each other, find the likely reason: version, platform, an outdated page.
- Assign confidence:
  - **high**: several primary sources agree, current version, no contradiction;
  - **medium**: one primary source, or primary sources with minor gaps;
  - **low**: secondary sources only, outdated sources, or unresolved contradictions.
- If you could not find an answer, say so, and list where you looked. "Not documented; not found in the source at tag v4.2; the closest is issue #123, unresolved" is a useful answer.
