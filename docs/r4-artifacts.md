# r4-artifacts.md
> R4 산출물. 단계별 파일명 / 규칙 SSOT 파일 1개 / 재개 가능 여부.
> 단계 정의는 r3-pipeline.md, 입력 변수 V1~V13은 r2-scope.md, 편집 권한은 r6-roles.md를 따른다.

## 1. 요청 1건 = run 폴더 1개 (단계별 하위 폴더)
단계 폴더 1개 = 에이전트 1개의 편집 폴더 (r6-roles.md).
```
runs/{YYMMDD}_{작업명}/
├── state.json                  # 현재 단계, 단계별 상태, 복귀 횟수 (오케스트레이터만)
├── 01/                         # brief-agent
│   ├── brief.md                # V1~V13 + 노션/시트 원문 링크
│   └── sheet.json              # 시트 원문 스냅샷 (★1 비교 기준)
├── 02/                         # figma-agent
│   └── figma.json              # 복제 섹션 ID, 배너별 프레임/텍스트/로고 노드 ID
├── 03/                         # image-agent
│   ├── prompt_{배너}.txt       # 배너별 GPT 프롬프트 (V11=Y일 때만)
│   ├── images/                 # 반입 이미지 원본
│   └── images.json             # sha256, 바이트 수
├── 04/                         # judge (판정 스크립트가 씀)
│   ├── preview/                # 판정용 3x PNG = 전달 PNG
│   ├── qa-report.md            # 규칙별 PASS/FAIL + 측정값
│   └── approval.json           # 승인 시각, qa-report 해시, PNG별 sha256 (오케스트레이터만)
└── 05/                         # delivery-agent
    └── delivery.json           # 드라이브 file ID/링크, 노션 속성 값, Slack 댓글 ts, 이모지 기록
```

- 전달 PNG 파일명: `{YYMMDD}_{작업명}_{배너종류}{_강|_고}.png` (`04/preview/`에서 이 이름으로 생성)

## 2. 이미지 반입
- 디자이너는 `input/images/`에 이미지를 넣는다
- S3 재개 시 하네스가 `input/images/` → `runs/{id}/03/images/`로 **이동**하고 `input/images/`를 비운다
- 이동 전후 sha256이 같아야 한다. 다르면 FAIL (= 원본 바이트 보장)

## 3. 규칙 SSOT: `rules.yaml` 1개
- 포함: design.md 🚦 수치, ★1~3 판정 조건, 운영값(채널 2곳, 확인 이모지 3종, Slack 문구 2종, 복귀 최대 3회)
- 사내 값은 `rules.local.yaml`(gitignore)로 분리, `rules.yaml`에는 자리표시자만 (r5-gates.md §5)
- 판정 스크립트와 에이전트는 수치를 **rules.yaml(+local)에서만** 읽는다
- design.md, r2~r6 문서는 사람용 설명서. 값이 다르면 **rules.yaml이 이긴다**. 수치 변경은 rules.yaml 먼저
- 예: `main.subject_height: [170, 175]`, `seam.max_col_diff: 10`, `retry.max: 3`

## 4. 재개
- **트리거:** "이어서 해줘". 폴더 지정이 없으면 `state.json`이 완료가 아닌 가장 최근 run
- **규칙:** `state.json`의 현재 단계부터. 앞 단계 출력 파일이 없으면 그 단계부터 다시
- **외부 작업 멱등성:** 이모지, 업로드, 댓글은 `05/delivery.json`(`${EMOJI_START}`은 `01/brief.md`)에 기록이 있으면 다시 하지 않는다

## 5. 공개 저장소 (GitHub Public)
- `runs/`, `input/images/`, `rules.local.yaml`은 `.gitignore` 처리. 사내 링크, 상품 이미지, 요청 문구 비공개
- 폴더 구조만 보이도록 `runs/.gitkeep`, `input/images/.gitkeep`만 커밋
