#!/usr/bin/env python3
"""Heuristic hotspot scanner for C++/Qt code reviews.

The scanner reports suspicious lines for human review. It does not prove bugs.
Use it as an early pass before reading the surrounding code.
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable, List, Optional, Pattern, Sequence


SOURCE_EXTENSIONS = {
    ".c",
    ".cc",
    ".cpp",
    ".cxx",
    ".h",
    ".hh",
    ".hpp",
    ".hxx",
    ".ipp",
    ".ixx",
    ".m",
    ".mm",
}

SKIP_DIRS = {
    ".git",
    ".hg",
    ".svn",
    ".vs",
    ".idea",
    "__pycache__",
    "build",
    "cmake-build-debug",
    "cmake-build-release",
    "debug",
    "release",
    "out",
    "dist",
    "node_modules",
}

VENDOR_DIRS = {"3rdparty", "third_party", "external", "extern", "vendor", "vendors"}


@dataclass(frozen=True)
class Rule:
    rule_id: str
    category: str
    severity: str
    pattern: Pattern[str]
    message: str
    multiline: bool = False


@dataclass(frozen=True)
class Finding:
    path: str
    line: int
    category: str
    severity: str
    rule_id: str
    message: str
    code: str


def rx(pattern: str, *, multiline: bool = False) -> Pattern[str]:
    flags = re.MULTILINE
    if multiline:
        flags |= re.DOTALL
    return re.compile(pattern, flags)


RULES: Sequence[Rule] = (
    Rule("raw-new", "memory-lifetime", "High", rx(r"(?<!operator\s)\bnew\s+(?!\()"), "Raw allocation: confirm ownership transfer and exception-safe cleanup, or prefer RAII/make_unique."),
    Rule("manual-delete", "memory-lifetime", "High", rx(r"\bdelete\s*(?:\[\])?\s+"), "Manual delete: check double-delete risk, missing paths, and whether RAII/QObject ownership is clearer."),
    Rule("c-allocation", "memory-lifetime", "High", rx(r"\b(?:malloc|calloc|realloc)\s*\("), "C allocation: verify matching free on every path or wrap it in RAII."),
    Rule("c-free", "memory-lifetime", "Medium", rx(r"\bfree\s*\("), "Manual free: verify ownership, matching allocator, and no use-after-free."),
    Rule("release-without-owner", "memory-lifetime", "High", rx(r"\.release\s*\(\s*\)"), "release() drops RAII ownership: verify immediate transfer to a documented owner."),
    Rule("reset-raw-pointer", "memory-lifetime", "Medium", rx(r"\.reset\s*\(\s*(?:new\b|[A-Za-z_][A-Za-z0-9_]*\s*\))"), "reset() with raw ownership transfer: verify allocation and ownership are exception-safe."),
    Rule("qobject-new-empty-parent", "memory-lifetime", "Medium", rx(r"\bnew\s+Q[A-Za-z0-9_]+\s*\(\s*\)"), "Qt allocation without constructor arguments: confirm QObject parent or RAII owner is set soon after."),
    Rule("return-address", "dangling-lifetime", "Critical", rx(r"\breturn\s+&\s*[A-Za-z_][A-Za-z0-9_]*\s*;"), "Returning an address: confirm it is not a local object or temporary."),
    Rule("return-reference", "dangling-lifetime", "High", rx(r"\breturn\s+(?:std::)?(?:string_view|span)\s*\("), "Returning a view/span: verify referenced storage outlives the return value."),
    Rule("lambda-reference-capture", "dangling-lifetime", "High", rx(r"\[[^\]]*&[^\]]*\]"), "Reference capture: unsafe if the lambda can outlive the current stack frame."),
    Rule("lambda-this-capture", "dangling-lifetime", "Medium", rx(r"\[[^\]]*\bthis\b[^\]]*\]"), "Capturing this: verify callback lifetime is bounded by a receiver/context or guarded pointer."),
    Rule("view-type", "dangling-lifetime", "Medium", rx(r"\b(?:std::string_view|QStringView|QByteArrayView|std::span)\b"), "Non-owning view/span: verify the referenced storage outlives every use."),
    Rule("raw-buffer-pointer", "dangling-lifetime", "Medium", rx(r"\.(?:c_str|data|constData)\s*\(\s*\)"), "Borrowed buffer pointer: verify it is not stored past the source object's lifetime or mutation."),
    Rule("range-for-copy", "copy-overhead", "Medium", rx(r"\bfor\s*\(\s*(?:const\s+)?auto\s+[A-Za-z_][A-Za-z0-9_]*\s*:"), "Range-for by value: use const auto& unless an intentional copy is needed."),
    Rule(
        "heavy-value",
        "copy-overhead",
        "Medium",
        rx(r"\b(?:std::(?:vector|map|unordered_map|string|wstring|list|deque|set|unordered_set)|QString|QByteArray|QImage|QPixmap|QJsonObject|QJsonDocument|QList|QVector|QMap|QHash|cv::Mat)\s*(?:<[^;(){}]*>)?\s+[A-Za-z_][A-Za-z0-9_]*\s*(?:[,)=]|$)"),
        "Large or implicitly shared value: check whether this copy is intentional and cheap enough.",
    ),
    Rule("return-std-move", "copy-overhead", "Low", rx(r"\breturn\s+std::move\s*\("), "return std::move(local) can block NRVO; verify it is needed."),
    Rule("string-conversion", "copy-overhead", "Medium", rx(r"\b(?:toStdString|fromStdString|fromUtf8|toUtf8|toLocal8Bit)\s*\("), "String conversion: avoid repeated conversions in hot paths and check encoding assumptions."),
    Rule("image-conversion", "copy-overhead", "Medium", rx(r"\b(?:scaled|rgbSwapped|convertToFormat|fromImage|toImage|clone)\s*\("), "Image/frame conversion or clone: verify this is not repeated in a hot path."),
    Rule("thread-detach", "thread-safety", "High", rx(r"\bdetach\s*\(\s*\)"), "Detached thread: verify object lifetime, shutdown, and lost error handling."),
    Rule("thread-construction", "thread-safety", "Medium", rx(r"\bstd::thread\s+(?:[A-Za-z_][A-Za-z0-9_]*|\{|\()"), "std::thread creation: verify ownership, join path, cancellation, and exception boundaries."),
    Rule("manual-lock", "thread-safety", "High", rx(r"(?:\.|->)\s*lock\s*\(\s*\)"), "Manual lock: prefer RAII lock guards and check exception/early-return paths."),
    Rule("manual-unlock", "thread-safety", "Medium", rx(r"(?:\.|->)\s*unlock\s*\(\s*\)"), "Manual unlock: verify every path unlocks; RAII locks are safer."),
    Rule("qt-direct-connection", "thread-safety", "High", rx(r"\bQt::DirectConnection\b"), "Direct Qt connection: verify sender/receiver thread affinity and reentrancy."),
    Rule("qt-blocking-queued-connection", "thread-safety", "High", rx(r"\bQt::BlockingQueuedConnection\b"), "Blocking queued connection: check for deadlock, especially with GUI-thread calls."),
    Rule("qthread-terminate", "thread-safety", "Critical", rx(r"\bterminate\s*\(\s*\)"), "Thread termination: verify this is not QThread::terminate or forced shutdown causing leaks/deadlocks."),
    Rule("mutable-static", "thread-safety", "Medium", rx(r"\bstatic\s+(?!const\b|constexpr\b)[^;=()]+\s+[A-Za-z_][A-Za-z0-9_]*"), "Mutable static state: verify thread-safe initialization and access."),
    Rule("throw-expression", "exception-safety", "Medium", rx(r"\bthrow\b"), "Throwing path: check RAII cleanup, state invariants, and boundary handling."),
    Rule("destructor-body", "exception-safety", "Medium", rx(r"\b~[A-Za-z_][A-Za-z0-9_]*\s*\([^)]*\)\s*(?:noexcept\s*)?(?:override\s*)?\{"), "Destructor body: ensure no exception can escape and cleanup is no-fail."),
    Rule("empty-catch", "exception-safety", "Medium", rx(r"\bcatch\s*\([^)]*\)\s*\{\s*\}"), "Empty catch: verify errors are intentionally swallowed and state remains valid."),
    Rule("catch-all", "exception-safety", "Low", rx(r"\bcatch\s*\(\s*\.\.\.\s*\)"), "catch(...): verify it preserves diagnostics and keeps invariants valid."),
    Rule("noexcept-marker", "exception-safety", "Low", rx(r"\bnoexcept\b"), "noexcept boundary: verify called operations cannot throw or are caught."),
    Rule("connect-lambda", "qt-lifetime", "Medium", rx(r"\bconnect\s*\([^;]*\[[^\]]*\]", multiline=True), "Qt lambda connection: verify receiver/context lifetime and captures.", multiline=True),
    Rule("invoke-method", "qt-lifetime", "Medium", rx(r"\bQMetaObject::invokeMethod\s*\([^;]+", multiline=True), "invokeMethod: verify connection type, target thread, argument lifetime, and receiver lifetime.", multiline=True),
)


def parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    categories = sorted({rule.category for rule in RULES})
    parser = argparse.ArgumentParser(description="Scan C++/Qt files for review hotspots.")
    parser.add_argument("paths", nargs="*", default=["."], help="Files or directories to scan.")
    parser.add_argument("--category", choices=categories, help="Only report one category.")
    parser.add_argument("--list-categories", action="store_true", help="List scan categories and exit.")
    parser.add_argument("--tools", action="store_true", help="Print suggested local analysis commands.")
    parser.add_argument("--json", action="store_true", help="Emit JSON findings.")
    parser.add_argument("--max-findings", type=int, default=300, help="Maximum findings to print.")
    parser.add_argument("--include-vendor", action="store_true", help="Include vendor/third-party directories.")
    parser.add_argument("--self-test", action="store_true", help="Run a small built-in test sample.")
    return parser.parse_args(argv)


def read_text(path: Path) -> str:
    for encoding in ("utf-8-sig", "utf-8", "cp936", "latin-1"):
        try:
            return path.read_text(encoding=encoding)
        except UnicodeDecodeError:
            continue
    return path.read_text(errors="replace")


def strip_comments(text: str) -> List[str]:
    result: List[str] = []
    in_block = False
    for line in text.splitlines():
        i = 0
        out = []
        while i < len(line):
            if in_block:
                end = line.find("*/", i)
                if end == -1:
                    i = len(line)
                else:
                    in_block = False
                    i = end + 2
            else:
                block_start = line.find("/*", i)
                line_start = line.find("//", i)
                candidates = [pos for pos in (block_start, line_start) if pos != -1]
                if not candidates:
                    out.append(line[i:])
                    break
                next_pos = min(candidates)
                out.append(line[i:next_pos])
                if next_pos == line_start:
                    break
                in_block = True
                i = next_pos + 2
        result.append("".join(out))
    return result


def logical_chunks(lines: Sequence[str]) -> List[tuple[int, str]]:
    chunks: List[tuple[int, str]] = []
    start = 1
    current: List[str] = []
    depth = 0
    for index, line in enumerate(lines, start=1):
        stripped = line.strip()
        if not current:
            start = index
        current.append(line)
        depth += line.count("(") + line.count("{") - line.count(")") - line.count("}")
        if ";" in line or (depth <= 0 and stripped.endswith("}")):
            chunks.append((start, "\n".join(current)))
            current = []
            depth = 0
    if current:
        chunks.append((start, "\n".join(current)))
    return chunks


def is_source_file(path: Path) -> bool:
    return path.is_file() and path.suffix.lower() in SOURCE_EXTENSIONS


def should_skip(path: Path, include_vendor: bool) -> bool:
    parts = {part.lower() for part in path.parts}
    if parts & {item.lower() for item in SKIP_DIRS}:
        return True
    if not include_vendor and parts & VENDOR_DIRS:
        return True
    return False


def iter_source_files(paths: Iterable[str], include_vendor: bool) -> List[Path]:
    files: List[Path] = []
    for raw in paths:
        path = Path(raw)
        if path.is_file():
            if is_source_file(path) and not should_skip(path, include_vendor):
                files.append(path)
            continue
        if path.is_dir():
            for child in path.rglob("*"):
                if is_source_file(child) and not should_skip(child, include_vendor):
                    files.append(child)
    return sorted(set(files))


def make_finding(path_label: str, line: int, rule: Rule, code: str) -> Finding:
    return Finding(
        path=path_label,
        line=line,
        category=rule.category,
        severity=rule.severity,
        rule_id=rule.rule_id,
        message=rule.message,
        code=" ".join(code.strip().split()),
    )


def scan_text(path_label: str, text: str, category: Optional[str] = None) -> List[Finding]:
    raw_lines = text.splitlines()
    code_lines = strip_comments(text)
    findings: List[Finding] = []

    for number, (raw_line, code_line) in enumerate(zip(raw_lines, code_lines), start=1):
        code = code_line.strip()
        if not code:
            continue
        for rule in RULES:
            if rule.multiline or (category and rule.category != category):
                continue
            if rule.pattern.search(code):
                findings.append(make_finding(path_label, number, rule, raw_line))

    for start_line, chunk in logical_chunks(code_lines):
        if not chunk.strip():
            continue
        for rule in RULES:
            if not rule.multiline or (category and rule.category != category):
                continue
            if rule.pattern.search(chunk):
                findings.append(make_finding(path_label, start_line, rule, chunk))

    return sorted(findings, key=lambda item: (item.line, item.category, item.rule_id))


def scan_files(files: Sequence[Path], category: Optional[str]) -> List[Finding]:
    findings: List[Finding] = []
    for path in files:
        try:
            findings.extend(scan_text(str(path), read_text(path), category))
        except OSError as exc:
            print(f"warning: could not read {path}: {exc}", file=sys.stderr)
    return findings


def summarize(findings: Sequence[Finding]) -> str:
    by_category = {}
    by_severity = {}
    for finding in findings:
        by_category[finding.category] = by_category.get(finding.category, 0) + 1
        by_severity[finding.severity] = by_severity.get(finding.severity, 0) + 1
    lines = ["Categories:"]
    for category, count in sorted(by_category.items()):
        lines.append(f"  {category}: {count}")
    lines.append("Severity:")
    for severity in ("Critical", "High", "Medium", "Low"):
        if severity in by_severity:
            lines.append(f"  {severity}: {by_severity[severity]}")
    return "\n".join(lines)


def print_text(findings: Sequence[Finding], scanned_files: int, max_findings: int) -> None:
    print("C++ review scout")
    print(f"Scanned files: {scanned_files}")
    print(f"Findings: {len(findings)}")
    if findings:
        print(summarize(findings))
        print()
    for finding in findings[:max_findings]:
        print(
            f"{finding.path}:{finding.line}: "
            f"[{finding.severity}] {finding.category}/{finding.rule_id}: {finding.message}"
        )
        print(f"    {finding.code}")
    if len(findings) > max_findings:
        print(f"... truncated {len(findings) - max_findings} additional findings")


def find_upward(name: str, roots: Sequence[Path]) -> Optional[Path]:
    for root in roots:
        current = root.resolve() if root.exists() else root
        if current.is_file():
            current = current.parent
        for candidate in (current, *current.parents):
            path = candidate / name
            if path.exists():
                return path
    return None


def print_tool_suggestions(paths: Sequence[str]) -> None:
    roots = [Path(path) for path in paths]
    compile_commands = find_upward("compile_commands.json", roots)
    cmakelists = find_upward("CMakeLists.txt", roots)
    print("Suggested analysis commands:")
    if shutil.which("clang-tidy") and compile_commands:
        print(f"  clang-tidy <file.cpp> -p {compile_commands.parent}")
    elif compile_commands:
        print("  clang-tidy is not on PATH, but compile_commands.json exists.")
    else:
        print("  Generate compile_commands.json, then run clang-tidy on changed files.")

    if shutil.which("cppcheck"):
        print("  cppcheck --enable=warning,performance,portability --std=c++17 <paths>")
    else:
        print("  cppcheck is not on PATH.")

    if cmakelists:
        print("  For runtime checks, consider ASan/UBSan/TSan builds if the compiler and platform support them.")
    else:
        print("  No nearby CMakeLists.txt found; infer build-system-specific analyzer commands.")


def run_self_test() -> int:
    sample = r'''
class Worker : public QObject {
public:
    ~Worker() { cleanup(); }
    void run(QString text, std::vector<int> values) {
        auto *timer = new QTimer();
        auto *p = new int(1);
        for (auto value : values) { (void)value; }
        mutex.lock();
        connect(this,
                &Worker::done,
                [&, this] { use(text.constData()); });
        std::thread([&] { use(text.constData()); }).detach();
        throw std::runtime_error("boom");
        delete p;
    }
};
'''
    findings = scan_text("self_test.cpp", sample)
    categories = {finding.category for finding in findings}
    expected = {
        "memory-lifetime",
        "dangling-lifetime",
        "copy-overhead",
        "thread-safety",
        "exception-safety",
        "qt-lifetime",
    }
    missing = expected - categories
    if missing:
        print(f"self-test failed, missing categories: {sorted(missing)}", file=sys.stderr)
        return 1
    print(f"self-test passed: {len(findings)} findings across {len(categories)} categories")
    return 0


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = parse_args(argv)
    if args.self_test:
        return run_self_test()
    if args.list_categories:
        for category in sorted({rule.category for rule in RULES}):
            print(category)
        return 0
    if args.tools:
        print_tool_suggestions(args.paths)
        return 0

    files = iter_source_files(args.paths, args.include_vendor)
    findings = scan_files(files, args.category)

    if args.json:
        print(json.dumps([asdict(finding) for finding in findings[: args.max_findings]], indent=2))
    else:
        print_text(findings, len(files), args.max_findings)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
