# Zotero-Obsidian 동기화 가이드

Zotero 라이브러리와 Obsidian vault를 동기화하는 완벽한 가이드입니다.

## 개요

이 시스템은 두 가지 방법으로 동기화를 제공합니다:

1. **Python 스크립트** (대량 초기 동기화): `sync_executor.py`
2. **Obsidian 플러그인** (실시간 자동 동기화): `obsidian-zotero-sync-checker`

## 방법 1: Python 스크립트 (초기 대량 동기화)

### 언제 사용?
- 처음 시스템을 설정할 때
- 많은 파일을 한 번에 정리해야 할 때
- Zotero에서 대규모 collection 재구성을 한 경우

### 단계별 가이드

#### 1단계: 현재 상태 확인

```bash
python scripts/sync_checker.py
```

출력 예시:
```
📊 통계:
  • Zotero 항목 수: 851
  • Obsidian 파일 수: 830
  • 동기화됨: 830

🔍 차이점:
  • 추가 필요 (Zotero에만 있음): 21
  • 삭제됨 (Obsidian에만 있음): 0
  • 이동됨 (Collection 변경): 250
```

#### 2단계: 변경사항 미리보기 (DRY RUN)

```bash
python scripts/sync_executor.py --dry-run
```

출력 예시:
```
⚠️  DRY RUN 모드: 실제로 파일을 변경하지 않습니다

📦 이동할 파일: 250개
--------------------------------------------------------------------------------

  • Compound signature detection on LINCS L1000 big data
    From: 000.Papers/010.AIDD/LINC project
    To:   000.Papers/010.AIDD/Drug repositioning
    [DRY RUN] Would move:
      /path/to/old/file.md
      → /path/to/new/file.md
```

#### 3단계: 실제 동기화 실행

```bash
# 백업 포함 (권장)
python scripts/sync_executor.py

# 백업 없이 (빠르지만 위험)
python scripts/sync_executor.py --no-backup
```

실행 과정:
1. 💾 전체 vault 백업 생성 (`backups/obsidian_backup_YYYYMMDD_HHMMSS.tar.gz`)
2. 📦 파일 이동 (moved items)
3. 🗑️ 파일 archive (deleted items → `_archived/{date}/`)
4. 📝 새 항목 안내 (added items)
5. 📊 결과 요약

#### 4단계: 새 논문 처리

동기화 후 Zotero에만 있는 새 논문을 처리:

```bash
# 모든 새 논문 처리
python scripts/run_literature_batch.py

# 특정 컬렉션만
python scripts/run_literature_batch.py --collection "AIDD"

# 제한된 수만
python scripts/run_literature_batch.py --limit 20
```

### 고급 옵션

#### 특정 컬렉션만 동기화

```bash
# 1. 체크
python scripts/sync_checker.py --collection "AIDD"

# 2. 미리보기
python scripts/sync_executor.py --dry-run --collection "AIDD"

# 3. 실행
python scripts/sync_executor.py --collection "AIDD"
```

#### JSON 파일 사용 (체크와 실행 분리)

```bash
# 1. 체크하고 JSON 저장
python scripts/sync_checker.py --output sync_report.json

# 2. JSON 확인 (편집기에서)
cat sync_report.json | jq

# 3. JSON 기반으로 실행
python scripts/sync_executor.py --from-json sync_report.json
```

## 방법 2: Obsidian 플러그인 (자동 동기화)

### 언제 사용?
- 일상적인 동기화 유지
- 실시간 변경 감지가 필요할 때
- n8n 워크플로우와 연동할 때

### 설치

```bash
# 1. Obsidian vault의 plugins 폴더로 복사
cp -r obsidian-zotero-sync-checker /path/to/vault/.obsidian/plugins/

# 2. 의존성 설치
cd /path/to/vault/.obsidian/plugins/obsidian-zotero-sync-checker
npm install

# 3. 빌드
npm run build

# 4. Obsidian 재시작 후 플러그인 활성화
```

### 설정

Settings → Zotero Sync Checker:

**필수 설정:**
- Zotero User ID: https://www.zotero.org/settings/keys
- Zotero API Key: https://www.zotero.org/settings/keys/new (Read-only)
- Literature Notes Path: `80. References/81. zotero`

**Auto-Sync 설정:**
- Enable Auto-Sync: ON
- Sync on Vault Changes: ON (파일 생성/삭제/이동 시 즉시 체크)
- Zotero Check Interval: 30분 (주기적 체크)
- Debounce Delay: 5000ms (변경 후 대기 시간)
- Silent Auto-Sync: ON (조용히 실행)

**n8n Webhook (선택사항):**
- n8n Webhook URL: `https://your-n8n.com/webhook/zotero-sync`
- Only send webhook on changes: ON

### 사용

**수동 체크:**
- 🔄 Ribbon icon 클릭
- 또는 `Ctrl/Cmd + P` → "Check Zotero sync"

**자동 체크:**
- 파일 추가/삭제/이동 → 5초 후 자동 체크
- 30분마다 Zotero API 자동 체크
- 변경사항 발견 시 알림: "📚 Zotero sync: 3 added, 0 deleted, 1 moved"
- n8n webhook 자동 전송 (설정된 경우)

## 두 방법의 비교

| 기능 | Python 스크립트 | Obsidian 플러그인 |
|------|----------------|-------------------|
| **초기 대량 동기화** | ⭐⭐⭐⭐⭐ | ⭐ |
| **자동 감지** | ❌ | ⭐⭐⭐⭐⭐ |
| **파일 이동** | ⭐⭐⭐⭐⭐ | ❌ (체크만) |
| **백업 생성** | ⭐⭐⭐⭐⭐ | ❌ |
| **n8n 연동** | ❌ | ⭐⭐⭐⭐⭐ |
| **속도** | 빠름 | 빠름 |
| **사용 편의성** | CLI | GUI + 자동 |

**권장 워크플로우:**
1. **처음**: Python 스크립트로 대량 동기화
2. **이후**: Obsidian 플러그인으로 자동 유지
3. **대규모 변경**: Python 스크립트로 다시 동기화

## 실전 시나리오

### 시나리오 1: 처음 시스템 설정

```bash
# 1. Zotero에서 모든 논문 처리
python scripts/run_literature_batch.py

# 2. 초기 동기화 (이미 완벽하므로 차이 없음)
python scripts/sync_checker.py
# → 모두 동기화됨

# 3. Obsidian 플러그인 설치 및 활성화
# 4. 이후로는 자동 유지
```

### 시나리오 2: Zotero에서 collection 대규모 재구성

```bash
# 1. Zotero에서 많은 논문을 다른 collection으로 이동
# (예: 50개 논문을 AIDD/old → AIDD/new로 이동)

# 2. 체크
python scripts/sync_checker.py
# → 50개 moved

# 3. 미리보기
python scripts/sync_executor.py --dry-run
# → 모든 이동 경로 확인

# 4. 실행
python scripts/sync_executor.py
# → 💾 백업 생성
# → 📦 50개 파일 이동
# → ✅ 완료

# 5. 확인
python scripts/sync_checker.py
# → 모두 동기화됨
```

### 시나리오 3: Obsidian에서 파일 추가

```bash
# 1. Obsidian에서 새 논문 노트 생성
# {title}_{KEY}.md

# 2. Obsidian 플러그인이 자동 감지
# → 5초 후 자동 체크
# → n8n webhook 전송
# → 알림: "📚 Zotero sync: 0 added, 0 deleted, 0 moved"

# 3. 수동으로 확인하려면
python scripts/sync_checker.py
```

### 시나리오 4: Zotero에서 논문 삭제

```bash
# 1. Zotero에서 논문 삭제 (또는 다른 라이브러리로 이동)

# 2. 30분 후 Obsidian 플러그인이 자동 감지
# → "📚 Zotero sync: 0 added, 1 deleted, 0 moved"
# → n8n webhook 전송

# 3. Python 스크립트로 archive
python scripts/sync_executor.py
# → 파일이 _archived/20250108/ 폴더로 이동
# → 삭제되지 않음 (안전)
```

## 백업 및 복구

### 백업 위치

```
~/path/to/vault/../backups/
├── obsidian_backup_20250108_100000.tar.gz
├── obsidian_backup_20250108_150000.tar.gz
└── obsidian_backup_20250108_200000.tar.gz
```

### 복구 방법

```bash
# 1. 백업 목록 확인
ls -lh ~/path/to/vault/../backups/

# 2. 백업 압축 해제
cd ~/path/to/vault/..
tar -xzf backups/obsidian_backup_20250108_100000.tar.gz

# 3. 폴더 이름 변경
mv "81. zotero" "81. zotero.restored"

# 4. Obsidian에서 확인
```

## 트러블슈팅

### 문제: "이동할 파일이 너무 많음"

**해결:**
```bash
# 특정 컬렉션만 먼저 처리
python scripts/sync_executor.py --collection "AIDD"
python scripts/sync_executor.py --collection "CancerResearch"
# ...
```

### 문제: "파일이 이동되지 않음"

**원인:**
- DRY RUN 모드였을 가능성
- 권한 문제
- 파일이 이미 존재

**해결:**
```bash
# 1. DRY RUN 없이 실행했는지 확인
python scripts/sync_executor.py  # --dry-run 없이

# 2. 권한 확인
ls -la /path/to/vault/

# 3. 로그 확인
# 오류 메시지에서 원인 파악
```

### 문제: "백업이 너무 느림"

**해결:**
```bash
# 백업 생성 건너뛰기 (주의: 위험!)
python scripts/sync_executor.py --no-backup

# 또는 수동으로 백업
tar -czf manual_backup.tar.gz /path/to/vault/
python scripts/sync_executor.py --no-backup
```

### 문제: "Obsidian 플러그인이 너무 자주 체크함"

**해결:**
Settings → Zotero Sync Checker:
- Debounce Delay: 5000 → 10000 (10초)
- Zotero Check Interval: 30 → 60 (60분)

## n8n 워크플로우 예시

### 기본 알림

```
Webhook → Set → Send to Slack
```

n8n Set 노드:
```javascript
const stats = $json.statistics;

return {
  message: `📚 Zotero 동기화\n` +
           `추가: ${stats.addedCount}\n` +
           `삭제: ${stats.deletedCount}\n` +
           `이동: ${stats.movedCount}`
};
```

### 자동 처리

```
Webhook → IF (changes > 0) → HTTP Request (trigger batch script)
```

## 모범 사례

1. **처음에는 항상 dry-run**: `--dry-run`으로 먼저 확인
2. **백업 유지**: `--no-backup` 사용 자제
3. **작은 단위로 테스트**: 전체 동기화 전에 작은 컬렉션으로 테스트
4. **정기적인 체크**: 주 1회 수동으로 `sync_checker.py` 실행
5. **로그 확인**: 오류 발생 시 로그에서 원인 파악

## 요약

```bash
# 🚀 빠른 시작 (초기 설정)
python scripts/sync_checker.py
python scripts/sync_executor.py --dry-run
python scripts/sync_executor.py

# 📅 일상적인 사용 (Obsidian 플러그인)
# - Auto-Sync 활성화
# - 30분마다 자동 체크
# - 변경 시 알림 + n8n webhook

# 🔧 대규모 변경 시
python scripts/sync_executor.py --dry-run
python scripts/sync_executor.py

# 📊 현재 상태 확인
python scripts/sync_checker.py
```
