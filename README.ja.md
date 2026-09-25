# agents-context-router

[English](README.md) | **日本語** | [한국어](README.ko.md) | [简体中文](README.zh-CN.md) | [繁體中文](README.zh-TW.md)

エージェント向けの指示は短く。プロジェクトの詳細は、必要なタスクでだけ読み込みます。

`agents-context-router` は、肥大化した `AGENTS.md` を小さな共通ルールとタスク別の wiki トピックに整理するスキルです。軽量な Python スクリプトで選んだトピックだけを表示し、履歴は毎回のコンテキストに含めずに保管できます。

<p align="center">
  <img src="context-router-stars.svg" alt="小さな星のルーターがタスクに合ったドキュメントへ案内する" width="100%">
</p>

## 仕組み

すべてのタスクに必要なルールは `AGENTS.md` に残します。手順書やリファレンスはトピックページへ、日付付きの記録は履歴へ移します。エージェントは共通ルールを読んで該当トピックを選び、その内容だけを読み込みます。

<p align="center">
  <img src="context-router-comic-overload.svg" alt="長い指示ファイルに困るエージェントが、埋もれたルールを見つけてドキュメントを整理する3コマ漫画" width="100%">
</p>

<p align="center">
  <img src="context-router-comic-routing.svg" alt="タスクが小さな共通ルールから該当するwikiトピックへ案内される3コマ漫画" width="100%">
</p>

## できること

- 常時読み込まれる指示ファイルの分割前後のサイズを計測。
- 内容を共通ルール、タスク別トピック、履歴、人向けドキュメントに分類。
- `docs/ai-context.json` で、トピックとファイル全体または正確な見出しを対応付け。
- 依存関係のない `scripts/ai-context.py` を同梱。`list`、トピック表示、`check` に対応。
- バイト数の上限、見出しの欠落や重複、一覧にないトピック、参照されない wiki／履歴ファイルを検査。
- スキルを削除した後もルーターを保守できるよう、リポジトリ内のガイドを追加。

標準の上限はルート指示ファイルが 8 KiB、各トピックが 16 KiB です。トピックが大きくなったら上限を上げずに分割します。

## インストール

### Claude Code プラグイン

Claude Code のセッション内で実行します。

```text
/plugin marketplace add runkids/agents-context-router
/plugin install agents-context-router@agents-context-router
```

### Codex プラグイン

Codex のマーケットプレイスを追加し、`/plugins` を開いて **agents-context-router** をインストールします。

```bash
codex plugin marketplace add runkids/agents-context-router --sparse .agents/plugins
codex
```

### Skillshare

[Skillshare](https://github.com/runkids/skillshare) を使っていますか？ほかのエージェント用プラグインと一緒に、Claude Code と Codex へインストールして同期できます。

```bash
skillshare plugin add runkids/agents-context-router \
  --plugin agents-context-router \
  --target claude --target codex --global
skillshare sync plugins
```

Skillshare なら複数のネイティブプラグインをまとめて管理でき、エージェントごとのインストール状況も確認できます。[プラグインのコマンドガイド](https://skillshare.runkids.cc/docs/reference/commands/plugin/)を参照してください。

### その他のスキル対応エージェント

[Vercel Skills CLI](https://github.com/vercel-labs/skills) でスキルとしてインストールできます。

```bash
npx skills add runkids/agents-context-router
```

## 使い方

エージェント向けドキュメントが大きくなったリポジトリで、次のように依頼します。

> 「`AGENTS.md` が大きすぎます。小さな共通ルールとタスク別の wiki トピックに分けてください。」

スキルは現状のコンテキスト量を計測し、ドキュメントを整理してルーターを設定し、結果を検査します。重複した `CLAUDE.md` のルールも整理し、マイルストーン記録は元の言語のまま保管します。

整理後は、そのリポジトリで次のコマンドを使えます。

```bash
python3 scripts/ai-context.py list
python3 scripts/ai-context.py debugging
python3 scripts/ai-context.py check
```

`list` は利用できるトピックを表示します。トピック名を指定すると、対応するセクションだけを元ファイルのパス付きで表示します。`check` はルーターと設定された上限を検証します。

## リポジトリ構成

```text
AGENTS.md                 常時読み込むルールとトピック一覧
docs/ai-context.json      トピックとドキュメントの対応表
scripts/ai-context.py     トピック表示とドキュメント検査
wiki/<topic>.md           タスク別ガイドと手順書
wiki/history/*.md         通常のコンテキストに含めない日付付き記録
wiki/README.md            人向けのトピック・履歴一覧
```

同梱スクリプトは Python 標準ライブラリのみを使います（Python 3.8 以降）。正確な見出しを参照し、見出しがない場合や重複している場合は失敗するため、名前変更後に誤った指示が読み込まれることはありません。

## コントリビュート

Issue と Pull Request を歓迎します。スキルの手順と eval 用プロンプトは [`skills/agents-context-router/`](skills/agents-context-router/) にあります。

## ライセンス

MIT

---

エージェントのコンテキスト整理に役立ったら、⭐ を付けてほかの開発者にもこのプロジェクトを知らせてください。
