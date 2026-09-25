# agents-context-router

[English](README.md) | [日本語](README.ja.md) | **한국어** | [简体中文](README.zh-CN.md) | [繁體中文](README.zh-TW.md)

에이전트 지침은 짧게 유지하고, 프로젝트 세부 정보는 필요한 작업에서만 불러오세요.

`agents-context-router`는 비대해진 `AGENTS.md`를 작은 공통 규칙(kernel)과 작업별 wiki topic으로 정리하는 스킬입니다. 가벼운 Python 스크립트로 선택한 topic만 출력하고, 기록은 매 작업의 context에 넣지 않고 보관합니다.

<p align="center">
  <img src="context-router-stars.svg" alt="작은 별 모양 라우터가 작업에 맞는 문서로 안내합니다" width="100%">
</p>

## 작동 방식

모든 작업에 필요한 규칙은 `AGENTS.md`에 둡니다. runbook과 참고 자료는 topic 페이지로, 날짜가 있는 기록은 history로 옮깁니다. 에이전트는 공통 규칙을 읽고 맞는 topic을 골라 그 내용만 불러옵니다.

<p align="center">
  <img src="context-router-comic-overload.svg" alt="긴 지침 파일에 압도된 에이전트가 묻힌 규칙을 찾고 문서를 정리하는 3컷 만화" width="100%">
</p>

<p align="center">
  <img src="context-router-comic-routing.svg" alt="작업이 작은 공통 규칙을 거쳐 알맞은 wiki topic으로 연결되는 3컷 만화" width="100%">
</p>

## 주요 기능

- 분할 전후에 항상 로드되는 지침 파일의 크기를 측정합니다.
- 내용을 공통 규칙, 작업별 topic, history, 사용자 문서로 분류합니다.
- `docs/ai-context.json`에서 topic을 파일 전체 또는 정확한 Markdown 제목에 연결합니다.
- 의존성이 없는 `scripts/ai-context.py`를 포함하며 `list`, topic 출력, `check`를 지원합니다.
- 바이트 예산, 누락되거나 중복된 제목, 목록에 없는 topic, 연결되지 않은 wiki/history 파일을 검사합니다.
- 스킬을 제거한 뒤에도 router를 유지할 수 있도록 저장소 안에 관리 가이드를 추가합니다.

기본 예산은 루트 지침 파일 8 KiB, topic별 16 KiB입니다. topic이 한도를 넘으면 한도를 올리는 대신 나누세요.

## 설치

### Claude Code 플러그인

Claude Code 세션에서 실행하세요.

```text
/plugin marketplace add runkids/agents-context-router
/plugin install agents-context-router@agents-context-router
```

### Codex 플러그인

Codex 플러그인 마켓플레이스를 추가한 다음 `/plugins`를 열고 **agents-context-router**를 설치하세요.

```bash
codex plugin marketplace add runkids/agents-context-router --sparse .agents/plugins
codex
```

### Skillshare

[Skillshare](https://github.com/runkids/skillshare)를 이미 사용 중인가요? 다른 에이전트 플러그인과 함께 Claude Code와 Codex에 이 플러그인을 설치하고 동기화할 수 있습니다.

```bash
skillshare plugin add runkids/agents-context-router \
  --plugin agents-context-router \
  --target claude --target codex --global
skillshare sync plugins
```

Skillshare로 여러 네이티브 플러그인을 한곳에서 관리하고 에이전트별 설치 상태를 확인하세요. [플러그인 명령 가이드](https://skillshare.runkids.cc/docs/reference/commands/plugin/)를 참고하세요.

### 기타 스킬 호환 에이전트

[Vercel Skills CLI](https://github.com/vercel-labs/skills)로 스킬을 설치할 수 있습니다.

```bash
npx skills add runkids/agents-context-router
```

## 사용법

에이전트 지침이 너무 커진 저장소에서 다음과 같이 요청하세요.

> “우리 `AGENTS.md`가 너무 커요. 작은 공통 규칙과 작업별 wiki topic으로 나눠 주세요.”

스킬은 현재 context를 측정하고 문서를 정리한 다음 router를 연결하고 결과를 검사합니다. 겹치는 `CLAUDE.md` 규칙도 다루며 마일스톤 기록은 원래 언어 그대로 보존합니다.

정리한 뒤에는 해당 저장소에서 다음 명령을 사용할 수 있습니다.

```bash
python3 scripts/ai-context.py list
python3 scripts/ai-context.py debugging
python3 scripts/ai-context.py check
```

`list`는 사용 가능한 topic을 보여 줍니다. topic 이름을 지정하면 해당 부분만 원본 경로와 함께 출력합니다. `check`는 router와 설정된 한도를 검증합니다.

## 저장소 구조

```text
AGENTS.md                 항상 로드하는 규칙과 topic 목록
docs/ai-context.json      topic과 문서의 매핑
scripts/ai-context.py     topic 출력 및 문서 검사
wiki/<topic>.md           작업별 가이드와 runbook
wiki/history/*.md         기본 context에서 제외되는 날짜별 기록
wiki/README.md            사람이 읽는 topic 및 기록 목록
```

포함된 스크립트는 Python 표준 라이브러리만 사용합니다(Python 3.8 이상). 제목을 정확히 참조하며, 제목이 없거나 중복되면 실패하므로 제목이 바뀐 뒤 잘못된 지침이 조용히 로드되지 않습니다.

## 기여

Issue와 Pull Request를 환영합니다. 스킬 절차와 eval 프롬프트는 [`skills/agents-context-router/`](skills/agents-context-router/)에 있습니다.

## 라이선스

MIT

---

에이전트 context를 정리하는 데 도움이 됐다면 ⭐를 눌러 더 많은 개발자가 이 프로젝트를 찾을 수 있게 해 주세요.
