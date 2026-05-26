# Qt Review Rules

Use this reference for QObject ownership, signal-slot lifetime, Qt thread affinity, widgets, timers, and network objects.

## QObject Ownership

- If a QObject has a parent, do not also manually delete it unless ownership is explicit and safe.
- If a QObject has no parent, identify the RAII owner or deletion path.
- Do not create child QObjects on the stack and then give them a parent that may delete them.
- Use `deleteLater()` when deletion must happen in the object's thread with an active event loop.
- Check thread affinity before moving, deleting, or invoking QObject methods.

## Signal-Slot Lifetime

- Avoid repeated connections from functions called multiple times; use `Qt::UniqueConnection` when duplicate delivery is accidental.
- For lambda connects, provide a receiver/context object controlling lambda lifetime.
- Capture async data by value when the callback can outlive the stack frame.
- Guard externally owned QObjects with `QPointer`.

```cpp
connect(sender, &Sender::changed, receiver, [receiver] {
    receiver->refresh();
});
```

## Thread Affinity

- QWidget, QPixmap, and UI state stay on the GUI thread.
- Worker QObjects should be moved to worker threads before work starts.
- Prefer queued signals for worker-to-UI communication.
- Audit `Qt::DirectConnection`, `Qt::BlockingQueuedConnection`, and direct method calls across threads.

## Timers And Network Objects

- A `QTimer` should live in the thread whose event loop drives it.
- `QNetworkAccessManager` lifetime should outlive replies and normally stay in one thread.
- Connect reply cleanup with `deleteLater()` and handle error, timeout, and cancellation paths.

## UI Performance

- Avoid blocking file, network, database, or decode work on the GUI thread.
- Avoid repeated scaling, pixmap conversion, layout churn, or heavy logging in paint/update paths.
