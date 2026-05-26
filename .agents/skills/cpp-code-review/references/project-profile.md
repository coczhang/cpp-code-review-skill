# Project Profile

Use this file to align reviews with the current repository. If a field is unknown, infer from code and mark assumptions in the review.

## Defaults

- Language: C++ with possible Qt integration.
- Preferred ownership: RAII first; QObject parent ownership only when it is the established local pattern.
- Exceptions: infer from codebase. If exceptions are disabled or avoided, review throwing library boundaries and cleanup paths as failure-return paths.
- Threading: assume UI objects are GUI-thread confined and worker code must have explicit shutdown.
- Performance: treat paint events, frame pipelines, timers, logging loops, and signal-heavy paths as hot until proven otherwise.

## Fill In For A Repository

- C++ standard:
- Qt version:
- Exception policy:
- Threading model:
- QObject ownership conventions:
- Approved static analysis tools:
- Sanitizer support:
- Project-specific banned APIs or patterns:
