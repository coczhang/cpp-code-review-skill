# Code Quality, Style, And Duplication Review

Use this reference when the review includes C++ code standards, maintainability, strong coupling, long if-else chains, conditional complexity, redundant code, duplicated logic, dead code, or over-abstraction.

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

## Strong Coupling And Module Boundaries

Look for code that makes modules hard to change, test, or reuse independently:

- UI code directly owns persistence, networking, device, parsing, or business-rule details instead of calling a narrow service/API boundary.
- Worker, storage, protocol, or algorithm code directly depends on widgets, dialogs, global application state, or concrete UI classes.
- Business rules are duplicated across UI slots, threads, command handlers, and validation helpers.
- Headers expose private implementation details, heavy dependencies, concrete singletons, or large transitive includes.
- Bidirectional dependencies, circular includes, service locator/global access, or callbacks that require unrelated subsystems to be initialized.
- Tests for one class require constructing broad application infrastructure because dependencies are not injectable or interface-shaped.

Prefer a smaller boundary only when it removes real coupling: pass a narrow interface, data object, callback, or service dependency; move UI-independent rules out of widgets; hide implementation details behind `.cpp`, pimpl, or local helpers when that matches the project style.

## Long If-Else Chains And Conditional Complexity

Look for conditionals that hide duplicated behavior or make new cases risky:

- Long `if` / `else if` chains branching on type names, command strings, status codes, modes, UI labels, or enum values.
- Multiple files repeat the same condition chain or switch over the same modes.
- Deeply nested branches mix validation, state mutation, logging, UI updates, and I/O in one function.
- Branches differ only by constants, field names, messages, or target handlers.
- New cases require editing several unrelated functions, which suggests missing dispatch, table data, or a shared command path.

Prefer guard clauses, early returns, small extracted handlers, table-driven dispatch, maps from key to handler, or strategy/polymorphism only when the set of variants is stable enough to justify it. Do not replace a short, readable two- or three-branch condition just to apply a pattern.

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

- `High`: duplicated logic, strong coupling, or branch complexity already diverges in a way that can produce wrong behavior, missed cleanup, inconsistent locking, or inconsistent validation.
- `Medium`: repeated code, strong coupling, or long conditional chains are likely to drift, hide a shared invariant, make fixes easy to miss, or create conflicting behavior across call sites.
- `Low`: harmless style drift, minor dead code, or local redundancy that is easy to clean up.

## Finding Evidence

For each code-quality finding, include:

- The repeated or inconsistent locations.
- The specific local convention or duplicated behavior.

- The coupling direction, branching structure, or repeated condition chain that makes change risky.
- Why it matters beyond preference.
- A minimal simplification or extraction.

Example:

```markdown
- [Medium][Confirmed] src/dialog.cpp:42 and src/dialog.cpp:88 - Validation logic is duplicated and already diverged.
  Both slots validate the same path field, but only one rejects empty strings before starting the worker. Extract a single `validateInputPath()` helper or route both actions through the same command path so future validation changes are applied once.
```
