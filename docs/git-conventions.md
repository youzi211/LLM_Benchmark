# Git 规范

本文是仓库的 git 操作约定，与 `CLAUDE.md` / `AGENTS.md` 中的 Commit & Pull Request Guidelines 保持一致。冲突时以本文为准，并同步更新另外两份文件。

## 分支

- `master` 是唯一主干，保持可运行（`uv run pytest -q` 通过、前端 `npm run build` 通过）。
- 功能与修复在短生命周期分支上做，命名 `<type>/<kebab-简述>`，`type` 取与提交相同的类型：
  - `feat/stress-group-by-config`
  - `fix/stress-duration-display`
  - `docs/git-conventions`
  - `chore/ignore-tmp`
  - 工具自动生成的分支前缀（如 `codex/...`）保留原样。
- 不要直接在 `master` 上积累多个不相关改动；合并后删除分支（本地与远端）。

## 提交信息（Conventional Commits）

格式：

```
<type>(<scope>): <简述>

<正文：为什么、改了什么、影响面>

<可选脚注>
```

- **type**：`feat` `fix` `docs` `test` `refactor` `chore` `perf` `build` `ci`。仓库历史只用前六种之外的也要属这一类，不要自造类型。
- **scope**：必填，用模块名或前端目录名，与代码结构对应：`stress`、`intelligence`、`suites`、`overview`、`reports`、`api`、`frontend`、`a11y`、`design-system`、`scripts`、`docs`。改动确实横跨多个模块时写主要模块。
- **简述**：用中文，一句话说清做了什么，不加句号。type、scope、`BREAKING CHANGE` 等约定关键字保持英文，其余内容一律中文。
- **正文**：用中文，说明动机与影响，需要时可列出改动点或验收命令；简短改动可以省略，最近一次验收结果（测试、构建、Playwright）值得写进正文。
- **脚注**：破坏性变更用 `BREAKING CHANGE: ...`；关联 issue 用 `Closes #12`。

示例：

```
feat(stress): 压测任务按运行配置归组

同一模型 + 同配置的压测任务在列表页归组展示，忽略 parallel/number 差异。
前端 vue-tsc 类型检查通过。

Co-Authored-By: Claude Code <noreply@anthropic.com>
```

## 暂存与检查（提交前）

- **只显式暂存文件**：`git add <文件路径>`，禁止 `git add .` / `git add -A` —— 运行目录里可能有明文密钥。
- 提交前看一遍 `git diff --cached`，确认：
  - 不包含 `data/models.json`、`data/evalscope.json`、`data/*_tasks/`、`reports/`、`outputs/`、`.env`；
  - 不含真实 `sk-...` / `ark-...` 密钥；
  - 不含临时文件（`*.tmp`、`*.diff`、评审快照、`tsconfig.*.tsbuildinfo` 等）。
- 标题用中文简述：`feat(stress): 中文描述`，不要 `feat(stress): group stress tasks`。
- 代码类提交至少跑一次相关验证：

  ```powershell
  $env:LLM_BENCHMARK_SCHEDULER_DISABLED='1'
  uv run pytest -q
  cd frontend; npm run build
  ```

  纯文档 / chore 提交可跳过，但在正文里说明没跑什么。
- 一个提交只做一件事：顺手的格式化、无关重构、依赖升级拆成单独提交。

## 与远端同步

- 同步用 `git pull --ff-only`，冲突就地解决；需要 rebase 时用 `git pull --rebase`（仓库当前 `pull.rebase=false`）。不要用 `git pull` 默认的 merge 方式制造推进提交。
- 推送前先 `git fetch` 看远端是否领先，领先则先同步再推。
- 不要对已推送的提交做 `rebase` / `amend` / 强推；已推错了就补一个修正提交。
- 推送后确认 `git status -sb` 显示 `## master...origin/master`（无 ahead/behind）。

## Pull Request

- 标题同提交格式；正文说明改动、验证命令，以及 API / 指标 / 架构 / 报告有变化时的文档更新。
- 合并到 `master` 用 squash 或仓库当前习惯的合并方式，合并标题沿用提交标题。

## 禁止事项

- 不强推 `master`，不直接改写已推送历史。
- 不提交密钥、运行产物与个人本地配置（见 `CLAUDE.md` 的 Security & Configuration Tips）。
- 不把多个不相关改动塞进一个提交或一个 PR。
- 不用空提交、以及 `fix: fix bug`、`update` 这类无信息量的标题。