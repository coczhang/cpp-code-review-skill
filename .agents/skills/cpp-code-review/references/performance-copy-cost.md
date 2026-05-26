# Performance And Copy-Cost Review

Use this reference for unnecessary copies, conversions, allocations, and hot-path performance.

## Hot Paths

Inspect paint events, frame callbacks, timers, signal-heavy paths, logging loops, parsing loops, UI refresh code, image/video conversion, and network/database polling first.

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
