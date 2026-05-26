# cpp-code-review-skill
`cpp-code-review-skill` 是一个面向 Codex 的 C++ / Qt 代码审查 skill。它把 Codex 的审查重点收束到生产环境里最容易造成事故的 C++ 问题：内存泄漏、悬空指针、拷贝开销、线程安全、异常安全，以及 Qt 对象生命周期和线程亲和性。

这个仓库适合放到 GitHub 后作为可复用 skill 使用：你可以把它安装到某个项目的 `.agents/skills` 目录，也可以安装到个人 Codex skills 目录，让 Codex 在审查 C++ / Qt 代码时自动加载这套审查流程。

## 主要能力

这个 skill 会引导 Codex 重点检查：

- 内存泄漏和所有权：`new/delete`、RAII、`unique_ptr::release()`、`shared_ptr` 环、C API 资源释放、QObject parent ownership。
- 悬空指针和生命周期：lambda 捕获、异步回调、`std::string_view` / `QStringView` / `std::span`、`constData()` / `c_str()`、QObject 被销毁后的访问。
- 拷贝开销和性能：大对象按值传参、range-for 按值复制、Qt 隐式共享 detach、字符串/图像/视频帧反复转换、热路径分配。
- 线程安全：数据竞争、锁顺序、手动 `lock/unlock`、`std::thread` / `QThread` 退出、UI 线程访问、Qt 跨线程 signal-slot。
- 异常安全：构造失败、部分初始化、失败路径清理、状态提交/回滚、`noexcept` 边界、析构函数异常。
- Qt 专项风险：QObject ownership、`deleteLater()`、lambda connect 生命周期、`Qt::DirectConnection`、`Qt::BlockingQueuedConnection`、`QTimer` / `QNetworkAccessManager` 生命周期。

它还包含一个启发式热点扫描脚本 `cpp_review_scout.py`，用于在审查前快速找出值得人工确认的代码线索。

## 仓库结构

```text
cpp-code-review-skill/
  README.md
  .agents/
    skills/
      cpp-code-review/
        SKILL.md
        scripts/
          cpp_review_scout.py
        references/
          cpp-risk-checklists.md
          exception-safety.md
          finding-templates.md
          memory-lifetime.md
          performance-copy-cost.md
          project-profile.md
          qt-rules.md
          thread-safety.md
```

核心入口是 `.agents/skills/cpp-code-review/SKILL.md`。`references/` 目录按主题拆分详细规则，Codex 会在需要时加载相关文件，避免一次性塞入过多上下文。`scripts/` 目录提供可选辅助扫描器。

## 安装到 Codex 项目

推荐使用项目级安装。把本仓库的 `.agents` 目录复制到你的 C++ / Qt 项目根目录：

```text
your-cpp-project/
  .agents/
    skills/
      cpp-code-review/
        SKILL.md
        scripts/
        references/
```

Windows PowerShell 示例：

```powershell
git clone https://github.com/<your-github-user>/cpp-code-review-skill.git

cd C:\path\to\your-cpp-project
Copy-Item C:\path\to\cpp-code-review-skill\.agents . -Recurse -Force
```

macOS / Linux 示例：

```bash
git clone https://github.com/<your-github-user>/cpp-code-review-skill.git

cd /path/to/your-cpp-project
cp -R /path/to/cpp-code-review-skill/.agents .
```

然后在 Codex 中打开 `your-cpp-project`。如果 Codex 已经打开该项目，建议重新打开工作区或重启 Codex，让它重新发现 `.agents/skills/cpp-code-review`。

## 安装到个人 Codex skills 目录

如果你希望所有项目都能使用这个 skill，可以复制 skill 文件夹到个人 Codex skills 目录。

Windows PowerShell：

```powershell
New-Item -ItemType Directory -Force "$env:USERPROFILE\.codex\skills"
Copy-Item .agents\skills\cpp-code-review "$env:USERPROFILE\.codex\skills\cpp-code-review" -Recurse -Force
```

macOS / Linux：

```bash
mkdir -p ~/.codex/skills
cp -R .agents/skills/cpp-code-review ~/.codex/skills/cpp-code-review
```

如果你设置了 `CODEX_HOME`，个人 skills 目录通常位于：

```text
$CODEX_HOME/skills
```

项目级安装更适合团队共享；个人级安装更适合你自己的常用审查习惯。

## 如何在 Codex 中使用

安装后，可以直接在 Codex 里这样请求：

```text
Use cpp-code-review to review this Qt class.
```

```text
使用 cpp-code-review 审查这个 C++ 模块，重点看内存泄漏、悬空指针和线程安全。
```

```text
Use cpp-code-review to check this QThread shutdown logic.
```

```text
帮我 review 这次改动，使用 cpp-code-review，优先找 crash、data race、leak 和 exception-safety 问题。
```

Codex 也可能根据 skill 描述自动触发，但在重要审查里建议显式写出 `cpp-code-review`，这样更稳定。

## 辅助扫描脚本

这个 skill 自带扫描脚本：

```powershell
python -B .agents\skills\cpp-code-review\scripts\cpp_review_scout.py <路径>
```

示例：

```powershell
python -B .agents\skills\cpp-code-review\scripts\cpp_review_scout.py src include
python -B .agents\skills\cpp-code-review\scripts\cpp_review_scout.py . --category thread-safety
python -B .agents\skills\cpp-code-review\scripts\cpp_review_scout.py . --json
python -B .agents\skills\cpp-code-review\scripts\cpp_review_scout.py . --tools
```

macOS / Linux 路径写法：

```bash
python3 -B .agents/skills/cpp-code-review/scripts/cpp_review_scout.py src include
```

脚本会扫描常见 C++ / Qt 风险线索，例如：

- 原始 `new/delete`
- `malloc/free`
- `unique_ptr::release()`
- lambda 引用捕获或 `this` 捕获
- `std::string_view` / `QStringView` / `std::span`
- `constData()` / `c_str()` 借用指针
- range-for 按值复制
- 字符串、图像、视频帧转换
- `std::thread::detach()`
- 手动 `lock/unlock`
- `Qt::DirectConnection`
- `Qt::BlockingQueuedConnection`
- `QMetaObject::invokeMethod`
- 析构函数、`throw`、`noexcept`、空 `catch`

注意：扫描器只是“线索生成器”，不是静态分析器。它的输出需要结合上下文确认，不能直接当作最终审查结论。

## 验证安装

在目标项目根目录运行：

```powershell
python -B .agents\skills\cpp-code-review\scripts\cpp_review_scout.py --self-test
```

成功时会看到类似输出：

```text
self-test passed: 15 findings across 6 categories
```

也可以查看扫描分类：

```powershell
python -B .agents\skills\cpp-code-review\scripts\cpp_review_scout.py --list-categories
```

预期分类包括：

```text
copy-overhead
dangling-lifetime
exception-safety
memory-lifetime
qt-lifetime
thread-safety
```

## 审查输出风格

skill 要求 Codex 优先输出高风险 finding，并给出证据、触发条件、后果和修复建议。典型格式：

```markdown
## Findings

- [High][Confirmed] src/foo.cpp:42 - Callback can use a destroyed object.
  Evidence, trigger, consequence, and minimal fix.

## Open Questions

- Questions that affect correctness or severity.

## Suggested Fixes

Focused snippets or patch-style changes.

## Summary

Overall quality and biggest remaining risks.

## Final Recommendation

Acceptable, acceptable with changes, or redesign recommended.
```

它会尽量避免泛泛而谈，例如只说“这里可以优化”。每条问题都应该说明为什么有风险、什么情况下触发、会造成什么生产后果，以及如何改。

## 自定义项目规则

可以编辑：

```text
.agents/skills/cpp-code-review/references/project-profile.md
```

建议填入：

- C++ 标准版本
- Qt 版本
- 是否允许异常
- 线程模型
- QObject ownership 约定
- 已批准的静态分析工具
- Sanitizer 支持情况
- 项目内禁止使用的 API 或模式

这样 Codex 在审查时会更贴近你的项目规范。

## 与 clang-tidy / cppcheck 的关系

这个 skill 不替代 `clang-tidy`、`cppcheck`、ASan、UBSan、TSan 或编译器警告。它的定位是：

- 帮 Codex 按生产风险组织审查思路。
- 把 C++ / Qt 常见事故模式变成可重复检查的流程。
- 用脚本快速生成热点线索。
- 把工具输出和人工上下文判断结合起来形成可执行 review。

如果项目有 `compile_commands.json`，建议同时运行 `clang-tidy`。可以用：

```powershell
python -B .agents\skills\cpp-code-review\scripts\cpp_review_scout.py . --tools
```

查看当前环境下的建议分析命令。

## 适用场景

适合：

- Qt Widgets / Qt Quick 桌面应用
- 工业软件、采集软件、上位机、长时间运行服务
- 包含 `QObject` / `QThread` / signal-slot 的代码
- 包含 OpenCV / FFmpeg / 图像视频处理的 C++ 项目
- 对内存、线程、异常路径和性能稳定性要求较高的代码审查

不适合把它当作：

- 完整静态分析器
- 编译器或单元测试替代品
- 自动修复所有 C++ 问题的工具
