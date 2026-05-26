# Exception Safety Review

Use this reference for cleanup on failure paths, invariants, partial construction, and `noexcept` boundaries.

## First Determine The Error Model

Check whether the project uses exceptions, error codes, Qt signals, `std::optional`, `expected`-style results, or mixed styles. If exceptions are disabled or avoided, still review throwing library calls, allocation, and constructors as failure boundaries.

## Guarantees

- Strong guarantee: operation succeeds or leaves state unchanged.
- Basic guarantee: invariants hold and resources do not leak after failure.
- No-throw guarantee: destructors, cleanup callbacks, C callbacks, thread entry boundaries, and `noexcept` functions must not let exceptions escape.

## Common Findings

- Acquire resource, then call throwing code before wrapping the resource in RAII.
- Mutate object state before an operation that can fail, with no rollback.
- Constructor starts a thread or registers a callback before all required state is initialized.
- Destructor, Qt slot, C callback, thread entry function, or `noexcept` function can throw.
- Manual lock/unlock skipped by exception.
- File/database/config writes can leave partially committed state.

## Safer Patterns

Use local temporaries first, then commit:

```cpp
auto next = buildState(input);
validate(next);
state_ = std::move(next);
```

Catch at framework or thread boundaries:

```cpp
try {
    runWorker();
} catch (const std::exception& e) {
    emit failed(QString::fromUtf8(e.what()));
}
```

Prefer RAII members, transaction guards, swap/commit patterns, and destructors that are effectively `noexcept`.
