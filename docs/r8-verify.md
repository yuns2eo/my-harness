# r8-verify.md
> R8 산출물. 검증과 리뷰.
> 게이트 조건은 r5-gates.md, 오케스트레이터 규칙은 r7-orchestrator.md를 따른다.

## 1. 판정 스크립트 검증 (`pytest tests/`)
- `tests/fixtures/`에 **합성 run**. 실제 상품 이미지, 문구 금지 (공개 저장소). 이미지는 코드로 생성
- 게이트 규칙마다 PASS 사례 ≥ 1, FAIL 사례 ≥ 1

### 필수 FAIL 사례 (5개)
| # | 사례 | 걸려야 하는 게이트 |
|---|---|---|
| F1 | 할인율 한 글자 다름 (`20%` vs `25%`) | G2 ★1 |
| F2 | 강/고 분리인데 세트 1개 | G2 ★2 |
| F3 | 다른 브랜드의 logo variant | G2 ★3 |
| F4 | 메인 문구 어절 중간 줄바꿈 (`사료 할\n인`) | G2 어절 중간 줄바꿈 |
| F5 | `#image` 슬롯에 마스크 그룹 사용 | G3 마스크 |

### 필수 PASS 사례
- 흰 동물 + 밝은 배경 합성 이미지 → 표준편차 방식으로 피사체 bbox가 잡혀야 한다

- 통과 기준: `pytest tests/` 전부 PASS

## 2. 공개 검사 (`scripts/check_public.py`, pre-commit 훅)
**git 추적 파일** 전체에서 아래가 **0건**이어야 커밋된다.
- `rules.local.yaml`의 모든 값 (문자열 그대로)
- `rules.local.yaml`의 `PUBLIC_FORBIDDEN_WORDS` 공개 금지어 (대소문자 무시). 금지어는 공개 파일에 적지 않는다
- `--history`: 커밋 기록 전체도 같은 기준으로 검사
- Slack user ID 패턴 `U[A-Z0-9]{8,}`
- 실제 ID가 붙은 링크: `figma.com/design/[A-Za-z0-9]{10,}`, `notion.so/…[0-9a-f]{32}`, `drive.google.com/…/[A-Za-z0-9_-]{20,}`
  - 자리표시자 링크(`figma.com/design/${FIGMA_FILE_KEY}/…`)는 통과

### 자리표시자 교체 (완료)
| 자리표시자 | 대상 |
|---|---|
| `${FIGMA_FILE_KEY}` | 템플릿 Figma 파일 키 |
| `${CHANNEL_PRIMARY}` / `${CHANNEL_SECONDARY}` | 스캔 채널 2곳 |
| `${EMOJI_START}` / `${EMOJI_DONE}` | 작업 시작 / 전달 완료 이모지 |

- 실제 값은 `rules.local.yaml`(gitignore)에만 있다

## 3. 하네스 설정 검사 (`scripts/check_harness.py`)
- CLAUDE.md ≤ 150줄, rules.yaml 수치 0건
- CLAUDE.md에 적힌 문서 경로가 전부 존재
- `.claude/agents/judge.md` tools에 Edit, Write, Figma 쓰기 도구 없음
- 편집 폴더 훅: 에이전트별로 자기 폴더 밖 쓰기를 **실제로 시도해 차단되는지** 확인
- CLAUDE.md 트리거 표 = r6-roles.md 트리거 표

## 4. 실전 검증
### 골든 케이스 (dry-run)
- 이미 전달 완료된 과거 요청 1건을 dry-run으로 재실행
- dry-run = 외부 쓰기(Slack, 노션, 드라이브, 이모지) 미실행, "보낼 내용"만 로그
- 통과: ★1~3 PASS + 사람 결과물과의 차이 목록 출력

### 첫 실전 3건
- Slack처럼 드라이브, 노션 쓰기도 매번 확인 후 실행
- 3건 완료 후 원래대로 자동 실행

## 5. 운영 리뷰
- S4 반려 사유 중 기계 게이트에 없는 항목 → `docs/gate-backlog.md`에 한 줄씩 누적
- 같은 사유 **3회** 누적 → rules.yaml 게이트 추가 여부를 디자이너에게 제안
