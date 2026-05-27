# Performance And Copy-Cost Review

Use this reference for unnecessary copies, conversions, allocations, expensive/blocking operations, and hot-path performance.

## Hot Paths

Inspect paint events, frame callbacks, timers, signal-heavy paths, logging loops, parsing loops, UI refresh code, image/video conversion, and network/database polling first.

Also inspect blocking disk/network/database I/O, synchronous process calls, sleep/wait calls, large parsing/compression/encryption/model-inference work, and heavy initialization performed on the GUI thread or in signal-heavy paths.

## Expensive Or Blocking Operation Checks

- Blocking disk, network, database, IPC, process, or device I/O on the GUI thread or in latency-sensitive callbacks.
- Synchronous waits such as `wait()`, `waitFor...()`, nested `QEventLoop::exec()`, `sleep()`, busy polling, or blocking future/result retrieval.
- Large JSON/XML/CSV parsing, compression, encryption, model inference, image/video conversion, or report generation in UI slots, paint events, timers, or signal-heavy paths.
- Repeated initialization of FFmpeg/OpenCV contexts, database connections, network clients, regex engines, large lookup tables, or caches inside loops.
- Unbounded loops over files, frames, rows, widgets, or messages without batching, cancellation, progress, or back-pressure.
- Excessive synchronous logging or formatting in hot paths.

## Copy And Conversion Checks

- Large types passed by value: `std::vector`, maps, strings, `QString`, `QByteArray`, `QImage`, `QPixmap`, `QJsonObject`, `cv::Mat`, frames, and custom buffers.
- Range-for loops using `auto item` instead of `const auto& item`.
- Qt implicit-sharing detach caused by non-const access or unnecessary mutation.
- Repeated `QString <-> std::string`, encoding conversions, `QImage <-> QPixmap`, scaling, `cv::Mat::clone()`, `QByteArray` construction, or FFmpeg conversion setup.
- Large queued signal-slot arguments copied across threads.
- `return std::move(local)` blocking NRVO.
- Repeated allocation inside loops, paint events, and per-frame callbacks.

## Safer Patterns

- Use `const T&` for read-only large inputs.
- Use pass-by-value-then-move only for sink APIs.
- Use `T&&` for explicit move-only transfer.
- Use views only when lifetime is obvious and documented.
- Cache conversion contexts, scaled images, and reusable buffers when inputs are stable.

- Move blocking work to worker threads or async APIs, and return results to the GUI thread with queued signals.
- Cache expensive setup and reuse buffers in frame, paint, timer, parsing, and polling loops.
- Bound long loops with batching, cancellation, progress reporting, or back-pressure.

Example:

```cpp
void setImage(QImage image) {
    image_ = std::move(image);
}
```

This is reasonable for a sink API. For read-only inspection, prefer:

```cpp
void inspectImage(const QImage& image);
```
