# 설치 및 사용 가이드

## 빠른 시작

### 1. 플러그인 설치

```bash
# 1. Obsidian vault로 이동
cd /path/to/your/vault

# 2. plugins 폴더로 이동 (없으면 생성)
mkdir -p .obsidian/plugins
cd .obsidian/plugins

# 3. 이 플러그인 폴더를 복사
cp -r /Users/fourmodern/literature_batch_scripts/obsidian-zotero-sync-checker .

# 4. 플러그인 폴더로 이동
cd obsidian-zotero-sync-checker

# 5. 의존성 설치
npm install

# 6. 플러그인 빌드
npm run build
```

### 2. Obsidian에서 활성화

1. Obsidian을 재시작합니다
2. Settings (⚙️) → Community plugins로 이동
3. "Zotero Sync Checker" 찾기
4. 토글 스위치를 켜서 플러그인 활성화

### 3. 플러그인 설정

Settings → Zotero Sync Checker로 이동하여 다음을 설정:

#### Zotero User ID 가져오기
1. https://www.zotero.org/settings/keys 방문
2. 로그인
3. "Your userID for use in API calls" 섹션에서 숫자 복사
4. 플러그인 설정에 붙여넣기

#### Zotero API Key 생성
1. https://www.zotero.org/settings/keys/new 방문
2. Description: "Obsidian Sync Checker" 입력
3. Personal Library 권한 설정:
   - ✅ Allow library access: Read Only
   - ⬜ Allow write access: 비활성화 (읽기만 필요)
4. "Save Key" 클릭
5. 생성된 키를 복사하여 플러그인 설정에 붙여넣기
   - ⚠️ 중요: 이 키는 한 번만 표시됩니다! 안전한 곳에 저장하세요.

#### n8n Webhook 설정 (선택사항)

n8n을 사용하는 경우:

1. n8n 워크플로우 생성
2. Webhook 노드 추가
3. Webhook 노드 설정:
   - HTTP Method: POST
   - Path: /zotero-sync (또는 원하는 경로)
4. "Production Webhook URL" 복사
5. 플러그인 설정에 붙여넣기

예시 URL: `https://your-n8n-instance.com/webhook/zotero-sync`

#### Literature Notes Path 설정

Vault 내 문헌 노트가 있는 폴더의 상대 경로를 입력합니다.

예시:
- `80. References/81. zotero`
- `Literature/Notes`
- `Research/Papers`

### 4. 첫 실행

#### 방법 1: Ribbon Icon
왼쪽 사이드바에서 🔄 (sync) 아이콘을 클릭합니다.

#### 방법 2: Command Palette
1. `Ctrl/Cmd + P` 눌러 Command Palette 열기
2. "sync" 입력
3. "Check Zotero sync status" 선택

### 5. 결과 확인

플러그인이 다음을 수행합니다:

1. **Zotero 데이터 가져오기**
   - 알림: "Fetching Zotero data..."
   - 완료: "Found X Zotero articles"

2. **Vault 스캔**
   - 완료: "Found X Obsidian files"

3. **비교 및 전송**
   - n8n webhook 설정 시: "Sync status sent to n8n webhook"
   - 결과 모달 표시

## 개발 모드

플러그인을 수정하고 개발하려면:

```bash
cd .obsidian/plugins/obsidian-zotero-sync-checker

# Watch 모드로 실행 (파일 변경 시 자동 빌드)
npm run dev
```

Obsidian에서 `Ctrl/Cmd + R`을 눌러 플러그인을 다시 로드합니다.

## 문제 해결

### 플러그인이 목록에 나타나지 않음

1. 플러그인 폴더 구조 확인:
   ```
   .obsidian/plugins/obsidian-zotero-sync-checker/
   ├── main.js          ← 이 파일이 있어야 함
   ├── manifest.json
   └── styles.css
   ```

2. `npm run build`를 실행했는지 확인

3. Obsidian 재시작

### "Zotero API error" 발생

- API Key가 정확한지 확인
- User ID가 정확한지 확인
- 인터넷 연결 확인
- Zotero API 상태 확인: https://status.zotero.org

### Webhook 전송 실패

- n8n Webhook URL이 정확한지 확인
- n8n 워크플로우가 활성화되어 있는지 확인
- n8n 워크플로우 로그 확인

### 파일을 찾지 못함

- Literature Notes Path가 정확한지 확인 (대소문자 구분)
- 파일명이 `{title}_{KEY}.md` 형식인지 확인
- `{KEY}`가 8자리 영숫자인지 확인

## n8n 워크플로우 샘플

### 기본 알림 워크플로우

1. **Webhook** 노드
   - Method: POST
   - Path: /zotero-sync

2. **Function** 노드 - 데이터 가공
   ```javascript
   const stats = $input.item.json.statistics;

   return {
     json: {
       message: `동기화 체크 완료!\n` +
                `새 논문: ${stats.addedCount}\n` +
                `삭제됨: ${stats.deletedCount}\n` +
                `이동됨: ${stats.movedCount}`
     }
   };
   ```

3. **Slack/Discord** 노드 - 알림 전송

### 상세 리포트 워크플로우

1. **Webhook** 노드

2. **Function** 노드 - Added 항목 포맷팅
   ```javascript
   const data = $input.item.json;
   const added = data.added;

   const report = added.map(item =>
     `• [${item.collection}] ${item.title}`
   ).join('\n');

   return {
     json: {
       title: `${added.length}개의 새로운 논문`,
       report: report
     }
   };
   ```

3. **Email** 노드 - 이메일 발송

### Google Sheets 기록

1. **Webhook** 노드

2. **Google Sheets** 노드
   - Operation: Append
   - 컬럼: Date, Added Count, Deleted Count, Moved Count

## 추가 리소스

- [Obsidian Plugin API 문서](https://docs.obsidian.md/Plugins/Getting+started/Build+a+plugin)
- [Zotero Web API 문서](https://www.zotero.org/support/dev/web_api/v3/start)
- [n8n 문서](https://docs.n8n.io/)

## 지원

문제가 발생하면 GitHub Issues에 등록해주세요.
