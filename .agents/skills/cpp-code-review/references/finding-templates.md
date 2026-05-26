# Finding Templates

Use these templates to keep review output concise and actionable.

## Confirmed Bug

```markdown
- [High][Confirmed] path/file.cpp:42 - Callback can use a destroyed object.
  The lambda captures `this` and is delivered asynchronously without a receiver context. If the owner is destroyed before the queued callback runs, the lambda dereferences a dangling pointer. Give `connect` a receiver context, capture required values by value, or guard external QObject lifetime with `QPointer`.
```

## Likely Risk

```markdown
- [Medium][Likely] path/file.cpp:88 - Ownership transfer is unclear after `release()`.
  `release()` drops RAII ownership, but the surrounding code does not show an immediate owner. If the callee does not always take ownership, this leaks. Prefer passing `std::unique_ptr` or wrap the target API in a named transfer helper.
```

## Question

```markdown
- [Medium][Question] path/file.cpp:120 - Is this slot always called on the GUI thread?
  The slot updates QWidget state, but the signal source appears to live on a worker object. Confirm the connection type or route this update through a queued signal to the GUI thread.
```

## Fix Snippet

Suggested fix:

```cpp
auto resource = std::unique_ptr<T, Deleter>(create(), Deleter{});
```
