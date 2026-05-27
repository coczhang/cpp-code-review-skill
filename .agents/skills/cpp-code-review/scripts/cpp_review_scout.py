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

EXTRA_CATEGORIES = {
    "conditional-complexity",
    "coupling",
    "duplicate-code",
    "expensive-operation",
}


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
    Rule("qt-wait-for", "expensive-operation", "High", rx(r"\bwaitFor(?:ReadyRead|BytesWritten|Connected|Disconnected|Finished)\s*\("), "Blocking Qt wait: verify it is not on the GUI thread or a latency-sensitive path."),
    Rule("event-loop-exec", "expensive-operation", "High", rx(r"\bQEventLoop\b|\.exec\s*\(\s*\)"), "Nested or blocking event loop: check UI freeze, reentrancy, and shutdown behavior."),
    Rule("sleep-call", "expensive-operation", "Medium", rx(r"\b(?:QThread::(?:m?sleep|usleep)|std::this_thread::sleep_for|Sleep|sleep|usleep)\s*\("), "Sleep/wait call: verify this does not block UI, worker shutdown, or hot paths."),
    Rule("future-blocking-wait", "expensive-operation", "Medium", rx(r"\.(?:get|wait|wait_for|wait_until)\s*\("), "Blocking future/result wait: check thread, timeout, cancellation, and UI responsiveness."),
    Rule("process-blocking", "expensive-operation", "High", rx(r"\bQProcess\b|\bstd::system\s*\("), "Process launch or wait: verify it is asynchronous or off the GUI thread with timeout/error handling."),
    Rule("file-io", "expensive-operation", "Medium", rx(r"\b(?:QFile|QSaveFile|QDirIterator|std::ifstream|std::ofstream|fopen|fread|fwrite)\b"), "File I/O: verify it is not repeated in hot paths or blocking the GUI thread."),
    Rule("database-query", "expensive-operation", "Medium", rx(r"\bQSqlQuery\b|\.(?:exec|prepare)\s*\("), "Database operation: verify thread affinity, latency, error handling, and batching."),
    Rule("heavy-parse-convert", "expensive-operation", "Medium", rx(r"\b(?:QJsonDocument::fromJson|QXmlStreamReader|QImageReader|QImageWriter|cv::imread|cv::imwrite|avformat_open_input|compress|uncompress)\b"), "Heavy parse/convert operation: verify it is cached, batched, or moved out of hot/UI paths."),
    Rule("global-singleton", "coupling", "Medium", rx(r"\b(?:ServiceLocator|ApplicationContext|Global[A-Za-z0-9_]*|Registry)::|\b(?:instance|getInstance)\s*\(\s*\)|\bqApp\b|\bQApplication::instance\s*\("), "Global singleton/service locator: check hidden coupling, testability, and initialization order."),
    Rule("ui-heavy-include", "coupling", "Medium", rx(r"^\s*#\s*include\s*[<\"].*(?:QWidget|QDialog|QMainWindow|QTableWidget|QTreeWidget|ui_[^>\"]+|[/\\]ui[/\\])"), "UI dependency in include: verify this layer should depend on widgets or generated UI classes."),
    Rule("infra-heavy-include", "coupling", "Medium", rx(r"^\s*#\s*include\s*[<\"].*(?:QSql|QNetwork|Database|Repository|Dao|Device|Serial|Modbus|Protocol)"), "Infrastructure dependency in include: check module boundaries and whether a narrower interface belongs in the header."),
    Rule("long-if-line", "conditional-complexity", "Low", rx(r"\belse\s+if\s*\("), "else-if branch: count chain length and consider guard clauses/table dispatch when chains grow."),
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
    categories = sorted({rule.category for rule in RULES} | EXTRA_CATEGORIES)
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


def make_dynamic_finding(path_label: str, line: int, category: str, severity: str, rule_id: str, message: str, code: str) -> Finding:
    return Finding(
        path=path_label,
        line=line,
        category=category,
        severity=severity,
        rule_id=rule_id,
        message=message,
        code=" ".join(code.strip().split()),
    )


def normalize_duplicate_line(line: str) -> str:
    stripped = line.strip()
    if not stripped or stripped in {"{", "}", "};", ";"}:
        return ""
    if stripped.startswith("#include") or stripped.startswith("#pragma"):
        return ""
    stripped = re.sub(r'"(?:\\.|[^"\\])*"', '"STR"', stripped)
    stripped = re.sub(r"'(?:\\.|[^'\\])*'", "'CHR'", stripped)
    stripped = re.sub(r"\b\d+(?:\.\d+)?\b", "NUM", stripped)
    stripped = re.sub(r"\s+", " ", stripped)
    return stripped


def scan_conditional_complexity(path_label: str, raw_lines: Sequence[str], code_lines: Sequence[str], category: Optional[str]) -> List[Finding]:
    if category and category != "conditional-complexity":
        return []

    findings: List[Finding] = []
    chain_start = 0
    chain_count = 0
    chain_sample = ""

    for number, code_line in enumerate(code_lines, start=1):
        stripped = code_line.strip()
        if re.search(r"\belse\s+if\s*\(", stripped):
            if chain_count == 0:
                chain_start = number
                chain_sample = raw_lines[number - 1].strip() if number - 1 < len(raw_lines) else stripped
            chain_count += 1
            if chain_count == 3:
                findings.append(make_dynamic_finding(
                    path_label,
                    chain_start,
                    "conditional-complexity",
                    "Medium",
                    "long-else-if-chain",
                    "Long else-if chain: consider guard clauses, table-driven dispatch, or strategy only if cases are stable and repeated.",
                    chain_sample,
                ))
        elif stripped and stripped not in {"{", "}"}:
            chain_start = 0
            chain_count = 0
            chain_sample = ""

    brace_depth = 0
    reported_deep_nesting = False
    for number, code_line in enumerate(code_lines, start=1):
        stripped = code_line.strip()
        if not reported_deep_nesting and brace_depth >= 5 and re.search(r"\b(?:if|for|while|switch)\s*\(", stripped):
            findings.append(make_dynamic_finding(
                path_label,
                number,
                "conditional-complexity",
                "Medium",
                "deep-control-nesting",
                "Deep control nesting: verify readability, early exits, and separation of validation/state mutation/I/O.",
                raw_lines[number - 1] if number - 1 < len(raw_lines) else stripped,
            ))
            reported_deep_nesting = True
        brace_depth += code_line.count("{") - code_line.count("}")
        if brace_depth < 0:
            brace_depth = 0

    return findings


def scan_duplicate_blocks(path_label: str, raw_lines: Sequence[str], code_lines: Sequence[str], category: Optional[str]) -> List[Finding]:
    if category and category != "duplicate-code":
        return []

    normalized: List[tuple[int, str, str]] = []
    for number, (raw_line, code_line) in enumerate(zip(raw_lines, code_lines), start=1):
        norm = normalize_duplicate_line(code_line)
        if norm:
            normalized.append((number, norm, raw_line.strip()))

    window = 8
    seen: dict[tuple[str, ...], int] = {}
    reported: set[tuple[str, ...]] = set()
    findings: List[Finding] = []

    for index in range(0, max(0, len(normalized) - window + 1)):
        block = tuple(item[1] for item in normalized[index : index + window])
        if sum(len(item) for item in block) < 120:
            continue
        line = normalized[index][0]
        previous = seen.get(block)
        if previous is None:
            seen[block] = line
            continue
        if block in reported:
            continue
        reported.add(block)
        findings.append(make_dynamic_finding(
            path_label,
            line,
            "duplicate-code",
            "Medium",
            "duplicate-code-block",
            f"Duplicate code block: similar {window}-line normalized block previously starts near line {previous}; confirm whether shared validation/conversion/cleanup should be extracted.",
            normalized[index][2],
        ))
        if len(findings) >= 20:
            break

    return findings


def scan_structural_patterns(path_label: str, raw_lines: Sequence[str], code_lines: Sequence[str], category: Optional[str]) -> List[Finding]:
    findings: List[Finding] = []
    findings.extend(scan_conditional_complexity(path_label, raw_lines, code_lines, category))
    findings.extend(scan_duplicate_blocks(path_label, raw_lines, code_lines, category))
    return findings


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

    findings.extend(scan_structural_patterns(path_label, raw_lines, code_lines, category))

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
        QFile file("large.json");
        QThread::sleep(1);
        ServiceLocator::instance().database();
        if (mode == 1) { handleA(); }
        else if (mode == 2) { handleB(); }
        else if (mode == 3) { handleC(); }
        else if (mode == 4) { handleD(); }
        validate(text);
        convert(text);
        persist(text);
        cleanup(values);
        notify(text);
        updateState(values);
        logState(text);
        finish(values);
        validate(text);
        convert(text);
        persist(text);
        cleanup(values);
        notify(text);
        updateState(values);
        logState(text);
        finish(values);
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
        "expensive-operation",
        "coupling",
        "conditional-complexity",
        "duplicate-code",
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
