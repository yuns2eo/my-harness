# r6-roles.md
> R6 산출물. 에이전트별 편집 폴더 1개 / 읽기전용 판정자 / 자연어 트리거.
> 폴더 구조는 r4-artifacts.md, 게이트는 r5-gates.md를 따른다.

## 1. 에이전트 (1 에이전트 = 1 편집 폴더)
| 에이전트 | 단계 | 편집 폴더 | 외부 쓰기 |
|---|---|---|---|
| `brief-agent` | S1 | `runs/{id}/01/` | `${EMOJI_START}` 이모지 |
| `figma-agent` | S2, S3 배치 | `runs/{id}/02/` | Figma (복제 섹션, 신규 logo variant) |
| `image-agent` | S3 프롬프트, 이미지 반입 | `runs/{id}/03/` | 없음 |
| `judge` | G1~G3 | `runs/{id}/04/` (판정 스크립트만 씀) | 없음 |
| `delivery-agent` | S5 | `runs/{id}/05/` | 드라이브, 노션, Slack, `${EMOJI_DONE}` |

- `state.json`, `04/approval.json` → **오케스트레이터(메인 세션)만** 쓴다
- `rules.yaml`, `rules.local.yaml`, `scripts/`, `docs/`, `.claude/` → **에이전트 전원 편집 금지**. 사람만
- Figma 쓰기는 `figma-agent` 1개로 제한 (동시 편집 방지)
- 신규 logo variant 등록, Slack 전송은 디자이너 확인 뒤에만 (r5-gates.md §4)

## 2. 읽기전용 판정자 `judge`
- 도구: `Read`, `Bash(python scripts/judge/*)`, Figma **읽기** MCP만. Edit/Write, Figma 쓰기 도구 없음
- `04/qa-report.md`, `04/preview/*.png`는 **판정 스크립트가 출력**한다. judge는 실행하고 결과를 읽기만 한다
- 훅(PreToolUse): 모든 에이전트의 Edit/Write 경로가 자기 편집 폴더 밖이면 차단

## 3. 판정 PNG = 전달 PNG
1. judge가 Figma 읽기 export로 `04/preview/`에 3x PNG 생성 → G3 판정
2. 승인 시 `approval.json`에 PNG별 sha256 기록
3. S5는 **승인된 바로 그 PNG**를 올린다. 업로드 전 해시 일치 확인, 불일치면 중단

## 4. 자연어 트리거
| 말 | 동작 |
|---|---|
| "배너 요청 확인해줘" / "브랜드전 작업 시작해줘" | 채널 2곳 스캔 → 1건이면 S1 시작, 2건 이상이면 목록 표시 |
| "`<스레드URL>` 작업해줘" | 그 스레드로 S1 시작 |
| "이미지 넣었어" | S3 재개 (반입 → G3) |
| "승인" | S4 승인 기록 → S5 |
| "반려: 사유" | 사유로 복귀 지점 결정 (r3-pipeline.md §3) |
| "보내" | Slack 문구 확인 → 전송 |
| "이어서 해줘" | `state.json` 기준 재개 |
| "`<스레드URL>` 수정: {배너}" | 수정 경로 (r3-pipeline.md §4) |
