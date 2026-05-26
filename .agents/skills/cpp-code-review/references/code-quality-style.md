# Code Quality, Style, And Duplication Review

Use this reference when the review includes C++ code standards, maintainability, redundant code, duplicated logic, dead code, or over-abstraction.

## Review Order

Correctness still comes first. Report style and redundancy findings after crash, leak, lifetime, threading, exception-safety, and severe performance findings unless the style issue directly causes a bug.

## Code Style And Project Conventions

Prefer local evidence over generic preferences:

- Match the repository's naming, formatting, include ordering, namespace style, error-handling style, logging style, and Qt/C++ idioms.
- Check header hygiene: avoid unnecessary includes, global `using namespace`, macros in headers, and definitions that force rebuilds or pollute consumers.
- Prefer `const`, narrow scope, clear ownership names, and explicit APIs when they reduce misuse.
- Prefer standard library or Qt facilities already used by the project over one-off helpers.
- Flag inconsistent error handling only when one path silently drops diagnostics, bypasses cleanup, or makes callers handle the same failure differently.

Do not report a style finding only because another style is personally preferable. Tie it to an explicit local convention, maintainability cost, or API misuse risk.

## Redundancy And Duplication

Look for evidence of copy-paste or repeated logic:

- Repeated branches, duplicated conditions, or switch cases with nearly identical bodies.
- Multiple functions that differ only by a type, constant, field name, log message, or UI label.
- Repeated validation, conversion, parsing, locking, cleanup, or error-reporting code.
- Dead code, obsolete feature flags, unused helper functions, unreachable branches, and commented-out code left as implementation history.
- Wrapper functions that add no invariant, no naming clarity, and no boundary between modules.
- Over-generalized helpers, templates, or inheritance introduced for only one caller or two coincidental call sites.

Prefer small, local simplifications: extract a helper only when it removes real duplication, names a shared invariant, or makes future changes less error-prone. Do not propose abstraction when the repeated code is short, clearer inline, or likely to diverge intentionally.

## Severity Guidance

- `High`: duplicated logic already diverges in a way that can produce wrong behavior, missed cleanup, inconsistent locking, or inconsistent validation.
- `Medium`: repeated code is likely to drift, hides a shared invariant, makes fixes easy to miss, or creates conflicting behavior across call sites.
- `Low`: harmless style drift, minor dead code, or local redundancy that is easy to clean up.

## Finding Evidence

For each code-quality finding, include:

- The repeated or inconsistent locations.
- The specific local convention or duplicated behavior.
- Why it matters beyond preference.
- A minimal simplification or extraction.

Example:

```markdown
- [Medium][Confirmed] src/dialog.cpp:42 and src/dialog.cpp:88 - Validation logic is duplicated and already diverged.
  Both slots validate the same path field, but only one rejects empty strings before starting the worker. Extract a single `validateInputPath()` helper or route both actions through the same command path so future validation changes are applied once.
```
