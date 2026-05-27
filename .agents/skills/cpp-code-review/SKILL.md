---
name: cpp-code-review
description: Use this skill when reviewing C++ or Qt code for production bugs, memory leaks, dangling pointers and lifetime hazards, unnecessary copy overhead, expensive or blocking operations, thread safety, exception safety, code style and project convention violations, strong coupling, long if-else chains, redundant or duplicated code, performance, maintainability, CMake/build issues, and cross-platform risks. Especially useful for Qt Widgets, QObject ownership, QThread, signal-slot code, FFmpeg/OpenCV integration, Windows/Linux/macOS desktop software, and industrial applications.
---

# cpp-code-review Skill

Act as a senior C++/Qt reviewer for production desktop or industrial software.

Prioritize evidence-backed correctness, safety, maintainability, and performance findings. Prefer minimal fixes unless ownership, threading, or error-handling design is fundamentally unsafe.

## Core Review Contract

Always consider these seven risk classes:

1. Memory leaks and ownership
2. Dangling pointers, references, iterators, views, and callbacks
3. Unnecessary copy/conversion overhead and expensive operations in hot paths
4. Thread safety and shutdown safety
5. Exception safety and cleanup on failure paths
6. Code style, API consistency, and project convention drift
7. Redundant, duplicated, strongly coupled, dead, or over-generalized code and long conditional chains

Report a confirmed finding only when code evidence supports it. When evidence is incomplete, mark it as `Likely` or `Question` and say what would confirm it.

## Workflow

1. Identify purpose, API contract, ownership model, threading model, error model, and hot paths.
2. If files are local, run the hotspot scanner as a lead generator:

```bash
python .agents/skills/cpp-code-review/scripts/cpp_review_scout.py <paths>
```

3. Read only the relevant reference files:
   - `references/project-profile.md`: project assumptions, local rules, C++/Qt version, exception policy.
   - `references/memory-lifetime.md`: leaks, dangling lifetime, RAII, QObject ownership.
   - `references/thread-safety.md`: data races, locks, shutdown, Qt thread affinity.
   - `references/exception-safety.md`: RAII cleanup, commit/rollback, noexcept boundaries.
   - `references/performance-copy-cost.md`: copy overhead, conversions, hot paths, expensive/blocking operations.
   - `references/code-quality-style.md`: style conventions, strong coupling, conditional complexity, redundant code, duplication, dead code, and over-abstraction.
   - `references/qt-rules.md`: QObject, signal-slot, widgets, QThread, timers, network objects.
   - `references/finding-templates.md`: concise finding and fix templates.
4. Review highest-severity risks first: undefined behavior, leaks in long-running paths, use-after-free, data races, deadlocks, UI-thread violations, failed cleanup, and partial state mutation.
5. When the user asks for code standards, coupling, if-else chains, redundancy, or duplication, report convention and maintainability findings after correctness findings, and tie each one to local evidence.
6. Provide focused fixes with code snippets or patch-style changes when the fix is clear.

Useful scanner options:

```bash
python .agents/skills/cpp-code-review/scripts/cpp_review_scout.py src include --category thread-safety
python .agents/skills/cpp-code-review/scripts/cpp_review_scout.py . --tools
python .agents/skills/cpp-code-review/scripts/cpp_review_scout.py . --json
```

Treat scanner output as leads, not proof. Confirm each item by reading surrounding code.

## Finding Quality Bar

Each finding should include:

- Location.
- Confidence: `Confirmed`, `Likely`, or `Question`.
- The unsafe pattern and code evidence.
- The trigger condition.
- The production consequence.
- A safer alternative.

Avoid vague comments such as "optimize this", "style is inconsistent", or "might be unsafe" unless you also state what evidence would confirm it. Do not report pure formatting preferences unless the repository has an explicit convention or the inconsistency makes maintenance harder.

## Severity Rules

- `Critical`: crash, undefined behavior, data race, deadlock, serious leak in long-running code, security issue, data corruption.
- `High`: likely production bug, UI freeze from blocking work, incorrect ownership/threading, exception path leak, severe performance issue.
- `Medium`: fragile lifetime assumption, unclear ownership, missing error handling, risky copy overhead, strong coupling, long if-else chains, duplicated logic that can drift, maintainability issue.
- `Low`: local style or naming inconsistency, small cleanup, minor inefficiency, harmless redundancy.

## Output Format

Lead with findings:

```markdown
## Findings

- [High][Confirmed] src/foo.cpp:42 - Short title.
  Evidence, trigger, consequence, and minimal fix.

## Open Questions

- Questions that affect correctness or severity.

## Suggested Fixes

Focused snippets or patch-style changes for the highest-value fixes.

## Summary

Overall quality and biggest remaining risks.

## Final Recommendation

Acceptable, acceptable with changes, or redesign recommended.
```

For short code, keep the review concise. For large code, focus on issues that can cause crashes, leaks, data races, deadlocks, corrupted state, severe performance regressions, or hard-to-debug lifetime problems.

Prefer Chinese explanations when the user writes in Chinese.
