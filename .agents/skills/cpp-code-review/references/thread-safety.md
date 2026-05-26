# Thread Safety Review

Use this reference for data races, locks, worker shutdown, UI-thread rules, and reentrancy.

## Build The Thread Model

Identify:

- Which thread owns each object?
- Which state is immutable, thread-confined, atomic, or lock-protected?
- Which functions can be called concurrently?
- Which callbacks can reenter the object?
- How shutdown prevents callbacks into destroyed objects?

## Common Findings

- Shared mutable state without mutex, atomic discipline, or thread confinement.
- Manual `lock()`/`unlock()` instead of RAII lock guards.
- Lock order inversion, nested locks, callbacks while holding locks, blocking waits while holding locks.
- `std::thread::detach()` hiding lifetime and shutdown bugs.
- Missing `joinable()` check or joining the current thread.
- Worker object destroyed before queued callbacks complete.
- Blocking file, network, database, decode, or join calls on the GUI thread.
- Unbounded queues, producer/consumer shutdown races, and lost cancellation.

## Qt Rules

- Do not touch QWidget, QPixmap, QPainter-on-widget, or UI state from worker threads.
- Prefer worker-object plus `moveToThread()` for QObject workers.
- Use queued signals back to the GUI thread.
- Verify receiver context lifetime for lambda connects.
- Be suspicious of `Qt::DirectConnection` across threads and `Qt::BlockingQueuedConnection` in GUI paths.
- Avoid `QThread::terminate()` except for last-resort process shutdown.

## Safer Patterns

```cpp
std::scoped_lock lock(mutex_);
state_ = nextState;
```

```cpp
connect(worker, &Worker::resultReady, this, &Controller::handleResult, Qt::QueuedConnection);
```

Prefer `std::jthread` when available, cancellation tokens, narrow lock scopes, immutable messages, and explicit shutdown order.
