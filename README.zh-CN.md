# agents-context-router

[English](README.md) | [日本語](README.ja.md) | [한국어](README.ko.md) | **简体中文** | [繁體中文](README.zh-TW.md)

让 Agent 指令保持精简，只在任务需要时加载项目资料。

`agents-context-router` 可以把臃肿的 `AGENTS.md` 整理成精简的共用规则，以及按任务加载的 wiki topic。轻量级 Python 脚本只输出选中的 topic；历史记录保留在仓库中，不会默认进入每次任务的上下文。

<p align="center">
  <img src="context-router-stars.svg" alt="一颗可爱的小星星把任务引导到合适的项目文档" width="100%">
</p>

## 工作方式

所有任务都需要的规则放在 `AGENTS.md`。操作手册和参考资料放入 topic 页面，带日期的记录放入 history。Agent 读取共用规则、选择相关 topic，然后只加载该 topic。

<p align="center">
  <img src="context-router-comic-overload.svg" alt="三格漫画：Agent 被冗长指令淹没，找到深藏的规则，然后整理文档" width="100%">
</p>

<p align="center">
  <img src="context-router-comic-routing.svg" alt="三格漫画：任务经过精简规则，被引导到匹配的 wiki topic" width="100%">
</p>

## 功能

- 测量拆分前后每次都会加载的指令文件大小。
- 将内容分类为共用规则、任务 topic、历史记录和面向人的文档。
- 通过 `docs/ai-context.json` 将 topic 映射到完整文件或精确的 Markdown 标题。
- 内置无额外依赖的 `scripts/ai-context.py`，支持 `list`、topic 输出和 `check`。
- 检查字节数上限、缺失或重复的标题、未列出的 topic，以及未被路由的 wiki／history 文件。
- 在仓库内添加维护指南，方便移除 skill 后继续维护路由结构。

默认上限为根指令文件 8 KiB、每个 topic 16 KiB。topic 超限时应拆分，而不是调高上限。

## 安装

### Claude Code 插件

在 Claude Code 会话中运行：

```text
/plugin marketplace add runkids/agents-context-router
/plugin install agents-context-router@agents-context-router
```

### Codex 插件

添加仓库中的 Codex 插件市场，然后打开 `/plugins` 并安装 **agents-context-router**：

```bash
codex plugin marketplace add runkids/agents-context-router --sparse .agents/plugins
codex
```

### Skillshare

已经在用 [Skillshare](https://github.com/runkids/skillshare)？可以将这个插件和其他 Agent 插件一起安装、同步到 Claude Code 和 Codex：

```bash
skillshare plugin add runkids/agents-context-router \
  --plugin agents-context-router \
  --target claude --target codex --global
skillshare sync plugins
```

Skillshare 可以集中管理完整的原生插件，并查看各 Agent 的安装状态。参阅 [插件命令指南](https://skillshare.runkids.cc/docs/reference/commands/plugin/)。

### 其他兼容 skill 的 Agent

使用 [Vercel Skills CLI](https://github.com/vercel-labs/skills) 安装：

```bash
npx skills add runkids/agents-context-router
```

## 使用

在 Agent 文档已经膨胀的仓库中，告诉你的编程 Agent：

> “我们的 `AGENTS.md` 太大了。请把它拆成精简的共用规则和按任务加载的 wiki topic。”

Skill 会先测量现有上下文，再整理文档、配置路由并检查结果。它也会处理与 `AGENTS.md` 重叠的 `CLAUDE.md` 规则，并以原语言保留里程碑记录。

整理完成后，可在该仓库中运行：

```bash
python3 scripts/ai-context.py list
python3 scripts/ai-context.py debugging
python3 scripts/ai-context.py check
```

`list` 显示可用 topic。指定 topic 名称后，脚本只会输出映射的内容，并标注来源路径。`check` 会验证路由配置和所设上限。

## 仓库结构

```text
AGENTS.md                 每次加载的规则和 topic 索引
docs/ai-context.json      topic 与文档的映射
scripts/ai-context.py     输出 topic 并检查文档
wiki/<topic>.md           任务指南和操作手册
wiki/history/*.md         不会默认载入上下文的日期记录
wiki/README.md            面向人的 topic 与历史索引
```

脚本只使用 Python 标准库（Python 3.8+）。标题引用必须精确匹配；标题缺失或重复时检查会失败，避免重命名后悄悄加载错误内容。

## 参与贡献

欢迎提交 Issue 和 Pull Request。Skill 工作流程和 eval 提示词位于 [`skills/agents-context-router/`](skills/agents-context-router/)。

## 许可证

MIT

---

如果它帮你减少了 Agent 的上下文负担，欢迎点个 ⭐，让更多开发者发现这个项目。
