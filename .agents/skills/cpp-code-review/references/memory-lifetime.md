# Memory And Lifetime Review

Use this reference for memory leaks, dangling pointers, object ownership, and RAII.

## Ownership Trace

For every pointer, handle, QObject, thread, buffer, callback token, frame, socket, fd, mutex, or C API object, answer:

- Who owns it?
- Is ownership unique, shared, borrowed, parent-owned, or transferred?
- What releases it on success, early return, exception, timeout, cancellation, and partial initialization?
- Can ownership be represented with RAII instead of manual cleanup?

## Leak Checks

- Raw `new`, `delete`, `malloc`, `free`, `fopen`, OS handles, OpenGL handles, FFmpeg `av_*_alloc`, OpenCV buffers, and custom create/destroy APIs.
- `unique_ptr::release()` without immediate transfer to a documented owner.
- `shared_ptr` cycles; prefer `weak_ptr` for back edges, observers, or parent links.
- Cleanup after failures in constructors, `init()` methods, retry loops, and frame pipelines.
- Resource acquisition before code that can throw or return early.

Escalate severity when the leak is in a loop, long-running service, UI recreation path, retry path, or video/image frame pipeline.

## Dangling Checks

- Returning pointers, references, views, spans, iterators, or `constData()`/`c_str()` results to locals, temporaries, moved-from objects, or short-lived buffers.
- Capturing by reference in queued signals, timers, futures, threads, stored callbacks, coroutines, or posted events.
- Capturing `this` without a receiver/context object or lifetime guard.
- Holding iterators/references across container mutation.
- Holding pointers into decoder/frame buffers after the next read, unref, or reuse.
- Observing externally owned QObjects without `QPointer` or equivalent lifetime checks.

## Safer Patterns

```cpp
auto resource = std::unique_ptr<T, Deleter>(create(), Deleter{});
```

```cpp
QPointer<Widget> guard = widget;
connect(worker, &Worker::done, receiver, [guard] {
    if (!guard) {
        return;
    }
    guard->update();
});
```

Prefer values for async data, RAII wrappers for C APIs, explicit ownership transfer, and QObject parent ownership only when the thread affinity and deletion context are safe.
