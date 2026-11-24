# Clarifying

Goal: before any worker starts, every decision that is expensive to reverse is made by the owner, explicitly. Cheap decisions you make yourself and record as assumptions.

## 1. Restate the task

Write back, in the owner's language and in a few sentences, what you understood: who it is for, what it must do, what "done" looks like. A restatement exposes misunderstandings that questions miss, because the owner reacts to a concrete picture.

## 2. Find the expensive decisions

A decision is expensive to reverse when changing it later means rewriting, migrating data, breaking users or redoing reviews. Walk this list and ask yourself, for each item, "if I guess wrong, what does it cost?":

- **Scope boundaries**: what is in, what is explicitly out, which existing behaviour must not change.
- **Stack**: language, framework, major libraries, versions to support.
- **Storage**: where data lives, its shape, migrations, retention, who else reads it.
- **Interfaces**: public APIs, CLI flags, file formats, URLs, anything other code or people depend on.
- **External services**: which APIs, accounts, keys, rate limits, costs.
- **Deployment**: where it runs, how it is released, environments, rollback.
- **Security and privacy**: authentication, authorization, secrets, personal data.
- **Compatibility**: platforms, browsers, backwards compatibility with existing data or clients.
- **Quality bar**: required tests, performance targets, accessibility, the meaning of "done".

Everything that is cheap to change later (internal names, file layout inside a module, a helper's signature) is not a question. Decide it, and list it as an assumption.

## 3. Phrase each question

Each question carries its own recommendation, so the owner can answer with one word.

- One decision per question.
- Give two to four concrete options, the recommended one first, and one line on the trade-off of each.
- Say why you recommend it, in terms of the owner's goal.
- Say what happens if the owner does not care: "If you have no preference, I will use X."

Example:

> **Storage for saved reports.** (a) **SQLite file next to the app (recommended)**: no new service, enough for one server; moving to Postgres later needs a migration. (b) Postgres: survives scaling to several servers, but needs a managed database and credentials. (c) JSON files: simplest, but no concurrent writes. If you have no preference, I will use (a).

Number the questions so the owner can answer "1a, 2b, 3 as recommended".

## 4. Know when facts must come first

If an honest recommendation depends on how the existing code works (which framework is already in use, how data is stored, whether a module already exists), do not guess. Ask the owner for permission to run a read-only scout, say what you want it to find out, and return with facts. Reason: a question built on a wrong picture of the code gets a confident answer that is wrong.

## 5. Restate the agreement

When the answers are in, write the agreement back in one short block: the task, the decisions taken, the assumptions you made, what is out of scope. Ask the owner to confirm. This becomes the core of the spec.

## Pitfalls

- Asking about things you could find out yourself by reading the code (via a scout) or by reasoning.
- Treating silence or "sounds good" on a long message as agreement to every point. If a decision is important, ask it so it cannot be skipped.
