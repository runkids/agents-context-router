# agents-context-router

[English](README.md) | [日本語](README.ja.md) | [한국어](README.ko.md) | [简体中文](README.zh-CN.md) | **繁體中文**

讓 Agent 指令保持精簡，只在任務需要時載入專案資料。

`agents-context-router` 能把臃腫的 `AGENTS.md` 整理成精簡的共用規則，以及依任務載入的 wiki topic。輕量的 Python 腳本只輸出選定的 topic；歷史紀錄留在 repo 裡，不會預設載入每次任務的 context。

<p align="center">
  <img src="context-router-stars.svg" alt="一顆可愛的小星星把任務引導到合適的專案文件" width="100%">
</p>

## 運作方式

所有任務都需要的規則放在 `AGENTS.md`。操作手冊和參考資料放進 topic 頁面，有日期的紀錄放進 history。Agent 讀取共用規則、選擇相關 topic，再只載入該 topic。

<p align="center">
  <img src="context-router-comic-overload.svg" alt="三格漫畫：Agent 被冗長指令淹沒、找到深藏的規則，接著整理文件" width="100%">
</p>

<p align="center">
  <img src="context-router-comic-routing.svg" alt="三格漫畫：任務經過精簡規則，被引導到符合需求的 wiki topic" width="100%">
</p>

## 功能

- 測量拆分前後，每次都會載入的指令文件大小。
- 將內容分類為共用規則、任務 topic、歷史紀錄和給人看的文件。
- 透過 `docs/ai-context.json` 將 topic 對應到完整文件或精確的 Markdown 標題。
- 內含零額外依賴的 `scripts/ai-context.py`，支援 `list`、topic 輸出和 `check`。
- 檢查位元組數上限、遺失或重複的標題、未列出的 topic，以及未被路由的 wiki／history 文件。
- 在 repo 內加入維護指南，移除 skill 後仍能繼續維護路由。

預設上限是根目錄指令文件 8 KiB、每個 topic 16 KiB。topic 超出上限時應拆分，而不是調高上限。

## 安裝

### Claude Code plugin

在 Claude Code session 中執行：

```text
/plugin marketplace add runkids/agents-context-router
/plugin install agents-context-router@agents-context-router
```

### Codex plugin

加入 repo 裡的 Codex plugin marketplace，再開啟 `/plugins` 安裝 **agents-context-router**：

```bash
codex plugin marketplace add runkids/agents-context-router --sparse .agents/plugins
codex
```

### Skillshare

已經在用 [Skillshare](https://github.com/runkids/skillshare) 嗎？可以和其他 Agent plugin 一起，將這個 plugin 安裝並同步到 Claude Code 和 Codex：

```bash
skillshare plugin add runkids/agents-context-router \
  --plugin agents-context-router \
  --target claude --target codex --global
skillshare sync plugins
```

Skillshare 可集中管理完整的原生 plugin，並查看各 Agent 的安裝狀態。請參閱 [plugin 指令指南](https://skillshare.runkids.cc/docs/reference/commands/plugin/)。

### 其他支援 skill 的 Agent

使用 [Vercel Skills CLI](https://github.com/vercel-labs/skills) 安裝：

```bash
npx skills add runkids/agents-context-router
```

## 使用方式

在 Agent 文件已經很龐大的 repo，告訴你的 coding agent：

>「我們的 `AGENTS.md` 太大了，請拆成精簡的共用規則和依任務載入的 wiki topic。」

Skill 會先測量目前的 context，再整理文件、設定路由並檢查結果。它也會處理和 `AGENTS.md` 重複的 `CLAUDE.md` 規則，並以原本語言保留里程碑紀錄。

整理完成後，可在該 repo 執行：

```bash
python3 scripts/ai-context.py list
python3 scripts/ai-context.py debugging
python3 scripts/ai-context.py check
```

`list` 顯示可用的 topic。指定 topic 名稱後，腳本只會輸出對應內容，並標示來源路徑。`check` 會驗證路由和設定的上限。

## Repo 結構

```text
AGENTS.md                 每次載入的規則與 topic 索引
docs/ai-context.json      topic 與文件的對應表
scripts/ai-context.py     輸出 topic 並檢查文件
wiki/<topic>.md           任務指南和操作手冊
wiki/history/*.md         不會預設載入 context 的日期紀錄
wiki/README.md            給人看的 topic 與歷史索引
```

隨附腳本只使用 Python 標準函式庫（Python 3.8+）。標題引用必須精確比對；若標題不存在或重複，檢查就會失敗，避免標題改名後悄悄載入錯誤內容。

## 參與貢獻

歡迎提出 Issue 和 Pull Request。Skill 工作流程和 eval prompts 位於 [`skills/agents-context-router/`](skills/agents-context-router/)。

## 授權條款

MIT

---

如果它幫你減少 Agent 的 context 負擔，歡迎給 repo 一顆 ⭐，讓更多開發者找到這個專案。
