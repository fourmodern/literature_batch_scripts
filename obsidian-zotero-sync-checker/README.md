# Zotero Sync Checker for Obsidian

Obsidian 플러그인으로 Zotero 라이브러리와 Obsidian vault를 비교하여 동기화 상태를 확인하고 n8n webhook으로 전송합니다.

## 주요 기능

- ✅ **Zotero Web API 통합**: Journal articles 자동 가져오기
- ✅ **Obsidian Vault 스캔**: 문헌 노트 자동 감지
- ✅ **차이점 분석**:
  - **추가 필요**: Zotero에만 있는 항목
  - **삭제됨**: Obsidian에만 있는 항목
  - **이동됨**: Collection이 변경된 항목
- ✅ **n8n Webhook 자동 전송**: 변경사항 감지 시 즉시 전송
- ⚡ **자동 동기화**:
  - 📁 Vault 파일 변경 감지 (생성/삭제/이동)
  - ⏰ 주기적 Zotero 체크 (설정 가능한 간격)
  - 🔕 Debounce로 중복 체크 방지
  - 🤫 Silent 모드 (변경사항이 있을 때만 알림)
- ✅ **상세한 결과 모달** 표시
- ✅ **Ribbon icon** 및 **Command palette** 지원

## 설치 방법

### 수동 설치

1. 이 저장소를 다운로드하거나 클론합니다
2. `obsidian-zotero-sync-checker` 폴더를 Obsidian vault의 `.obsidian/plugins/` 디렉토리로 복사합니다
3. 플러그인 폴더에서 의존성을 설치합니다:
   ```bash
   cd .obsidian/plugins/obsidian-zotero-sync-checker
   npm install
   ```
4. 플러그인을 빌드합니다:
   ```bash
   npm run build
   ```
5. Obsidian에서 Settings → Community plugins → Installed plugins로 이동
6. "Zotero Sync Checker" 플러그인을 활성화합니다

### 개발 모드

개발하면서 실시간으로 변경사항을 확인하려면:

```bash
npm run dev
```

이렇게 하면 파일이 변경될 때마다 자동으로 다시 빌드됩니다.

## 설정

플러그인을 사용하기 전에 Settings에서 다음 정보를 설정해야 합니다:

### 1. Zotero User ID
- Zotero 웹사이트에서 확인: https://www.zotero.org/settings/keys
- "Your userID for use in API calls" 섹션에 표시됩니다

### 2. Zotero API Key
- 새 API 키 생성: https://www.zotero.org/settings/keys/new
- 권한:
  - ✅ Allow library access (Read only)
  - ✅ Allow notes access (선택사항)
- 생성된 키를 복사하여 설정에 붙여넣습니다

### 3. n8n Webhook URL (선택사항)
- n8n에서 Webhook 노드를 생성합니다
- Webhook URL을 복사하여 설정에 붙여넣습니다
- 비워두면 webhook 전송을 건너뜁니다

### 4. Literature Notes Path
- Obsidian vault 내 문헌 노트 폴더의 경로
- 기본값: `80. References/81. zotero`
- 환경에 맞게 조정하세요

### 5. Show Detailed Results
- 활성화: 동기화 후 상세 결과 모달 표시
- 비활성화: 간단한 알림만 표시

### 6. Auto-Sync Settings (자동 동기화)

#### Enable Auto-Sync
- 자동 동기화 기능을 활성화/비활성화합니다
- 활성화하면 파일 변경 및 주기적 체크가 시작됩니다

#### Sync on Vault Changes
- 문헌 노트 파일이 생성/삭제/이동될 때 자동으로 체크
- 기본값: 활성화

#### Zotero Check Interval
- Zotero API를 체크하는 주기 (분 단위)
- 기본값: 30분
- 0으로 설정하면 주기적 체크 비활성화

#### Debounce Delay
- Vault 변경 후 대기 시간 (밀리초)
- 기본값: 5000ms (5초)
- 여러 파일을 동시에 추가/수정할 때 중복 체크 방지

#### Silent Auto-Sync
- 자동 체크 중 알림을 숨김
- 변경사항이 발견되면 간단한 알림만 표시
- 기본값: 활성화

#### Only send webhook on changes
- 변경사항이 있을 때만 webhook 전송
- 기본값: 활성화
- 비활성화하면 체크할 때마다 webhook 전송

## 사용 방법

### Ribbon Icon 사용

왼쪽 사이드바의 Sync 아이콘(🔄)을 클릭합니다.

### Command Palette 사용

**수동 체크:**
1. `Ctrl/Cmd + P`를 눌러 Command Palette를 엽니다
2. "Check Zotero sync"을 입력합니다
3. 명령을 실행합니다

**Auto-Sync 토글:**
1. `Ctrl/Cmd + P`를 눌러 Command Palette를 엽니다
2. "Toggle auto-sync"을 입력합니다
3. 자동 동기화를 켜거나 끕니다

### 자동 동기화 사용

자동 동기화가 활성화되면:

1. **파일 변경 감지**:
   - 문헌 노트를 추가하면 → 5초 후 자동 체크
   - 문헌 노트를 삭제하면 → 5초 후 자동 체크
   - 문헌 노트를 이동하면 → 5초 후 자동 체크

2. **주기적 체크**:
   - 설정된 간격마다 Zotero API 체크 (기본 30분)
   - 백그라운드에서 조용히 실행

3. **알림**:
   - Silent 모드: 변경사항이 있을 때만 알림
   - 예: "📚 Zotero sync: 3 added, 0 deleted, 1 moved"

4. **Webhook 전송**:
   - 변경사항이 있을 때만 n8n으로 전송 (기본)
   - 또는 매번 체크마다 전송 (설정 변경 가능)

### 결과

플러그인이 다음을 수행합니다:

1. Zotero API에서 모든 journal articles 가져오기
2. Vault 내 문헌 노트 스캔
3. 차이점 비교
4. (설정된 경우) n8n webhook으로 결과 전송
5. 결과 모달 표시

## n8n Webhook 페이로드

플러그인은 다음 형식의 JSON을 n8n webhook으로 전송합니다:

```json
{
  "added": [
    {
      "key": "ABCD1234",
      "title": "Paper title",
      "collection": "Collection/Path"
    }
  ],
  "deleted": [
    {
      "key": "EFGH5678",
      "title": "Paper title",
      "collection": "Collection/Path",
      "filePath": "path/to/file.md"
    }
  ],
  "moved": [
    {
      "key": "IJKL9012",
      "title": "Paper title",
      "oldCollection": "Old/Collection",
      "newCollection": "New/Collection",
      "filePath": "path/to/file.md"
    }
  ],
  "statistics": {
    "zoteroTotal": 851,
    "obsidianTotal": 830,
    "synced": 830,
    "addedCount": 21,
    "deletedCount": 0,
    "movedCount": 250
  }
}
```

## n8n 워크플로우 예시

n8n에서 이 데이터를 활용하는 방법:

1. **Webhook 노드**: 플러그인에서 데이터 수신
2. **Function 노드**: 데이터 가공 또는 필터링
3. **Action 노드** (선택):
   - Slack/Discord에 알림 전송
   - Google Sheets에 기록
   - 이메일 리포트 발송
   - 데이터베이스에 저장

예시 Function 노드 코드:

```javascript
const data = $input.item.json;

// Added items만 필터링
const newPapers = data.added.map(item => ({
  title: item.title,
  collection: item.collection,
  zoteroUrl: `https://www.zotero.org/users/YOUR_USER_ID/items/${item.key}`
}));

return {
  json: {
    message: `${data.statistics.addedCount}개의 새로운 논문이 추가되었습니다.`,
    papers: newPapers
  }
};
```

## 파일명 규칙

플러그인은 다음 패턴의 파일명을 인식합니다:

```
{title}_{KEY}.md
```

예시:
- `Deep Learning in Drug Discovery_ABCD1234.md`
- `Protein Structure Prediction_EFGH5678.md`

`{KEY}`는 Zotero item key입니다 (8자리 대소문자 영숫자).

## 자동 동기화 시나리오

### 시나리오 1: 새 논문 추가
1. Zotero에 새 논문을 추가합니다
2. 30분 후 (또는 설정된 간격 후) 플러그인이 자동으로 체크
3. 변경사항 감지: "1 added"
4. n8n webhook으로 전송
5. 작은 알림 표시: "📚 Zotero sync: 1 added, 0 deleted, 0 moved"

### 시나리오 2: Obsidian에서 노트 생성
1. Obsidian에서 `{title}_{KEY}.md` 파일 생성
2. 5초 후 자동 체크
3. Vault 변경 감지됨
4. Zotero와 비교하여 동기화 상태 업데이트
5. n8n webhook 전송

### 시나리오 3: Collection 변경
1. Zotero에서 논문을 다른 Collection으로 이동
2. 30분 후 자동 체크
3. 변경사항 감지: "1 moved"
4. n8n webhook으로 전송
5. Obsidian에서 해당 파일 이동 필요 (수동 또는 별도 자동화)

## 성능 최적화

### Debounce 활용
- 여러 파일을 동시에 추가할 때 마지막 변경 후 5초 대기
- 불필요한 중복 체크 방지

### Silent 모드
- 자동 체크 시 알림을 최소화
- 변경사항이 있을 때만 알림 표시

### Webhook 최적화
- "Only send webhook on changes" 활성화
- 변경사항이 없으면 webhook 전송하지 않음
- n8n 실행 횟수 절약

## 문제 해결

### "Please configure Zotero credentials" 오류

Settings에서 Zotero User ID와 API Key를 설정했는지 확인하세요.

### "Zotero API error" 오류

- API Key가 유효한지 확인
- API Key에 library read 권한이 있는지 확인
- 인터넷 연결 확인

### Webhook 전송 실패

- n8n Webhook URL이 정확한지 확인
- n8n 워크플로우가 활성화되어 있는지 확인
- Webhook 노드가 POST 요청을 받도록 설정되어 있는지 확인

### 파일을 찾지 못함

- Literature Notes Path가 올바른지 확인
- 파일명이 `{title}_{KEY}.md` 패턴을 따르는지 확인
- 대소문자 구분 확인

### Auto-Sync가 작동하지 않음

- Settings에서 "Enable Auto-Sync"가 켜져 있는지 확인
- Console (Ctrl/Cmd + Shift + I)에서 로그 확인
- "Starting Zotero auto-sync..." 메시지 확인

### 너무 자주 체크됨

- Debounce Delay를 늘립니다 (예: 10000ms = 10초)
- Zotero Check Interval을 늘립니다 (예: 60분)

### 체크가 너무 느림

- Zotero Check Interval을 줄입니다 (예: 15분)
- Debounce Delay를 줄입니다 (예: 2000ms = 2초)

## 개발

### 요구사항

- Node.js 16+
- npm 또는 yarn

### 빌드

```bash
# 의존성 설치
npm install

# 개발 빌드 (watch 모드)
npm run dev

# 프로덕션 빌드
npm run build
```

### 프로젝트 구조

```
obsidian-zotero-sync-checker/
├── main.ts              # 메인 플러그인 코드
├── manifest.json        # 플러그인 메타데이터
├── package.json         # npm 의존성
├── tsconfig.json        # TypeScript 설정
├── esbuild.config.mjs   # 빌드 설정
└── README.md           # 이 문서
```

## 라이선스

MIT

## 기여

이슈와 PR을 환영합니다!

## 관련 프로젝트

이 플러그인은 [literature_batch_scripts](https://github.com/yourusername/literature_batch_scripts)의 일부로, Zotero와 Obsidian을 연동하는 전체 워크플로우를 제공합니다.
