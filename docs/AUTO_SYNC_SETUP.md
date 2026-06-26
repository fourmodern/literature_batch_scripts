# Zotero 자동 동기화 설정 가이드

macOS에서 Zotero-Obsidian 동기화를 자동으로 실행하는 시스템입니다.

## 🎯 기능

- **자동 변동 감지**: Zotero와 Obsidian 폴더를 비교하여 변동사항 감지
- **자동 처리**:
  - 추가된 논문 → 자동으로 마크다운 노트 생성
  - 삭제된 논문 → 아카이브로 이동
  - 이동된 논문 → 새 컬렉션 폴더로 이동
- **macOS 알림**: 동기화 시작/완료 시 알림
- **로그 기록**: 모든 작업 내역 저장

## 📋 설정 방법

### 1. 로그 디렉토리 생성

```bash
mkdir -p /Users/fourmodern/literature_batch_scripts/logs/auto_sync
```

### 2. 수동 테스트 (먼저 확인!)

```bash
# 가상환경 활성화
conda activate zot

# 스크립트 실행
python /Users/fourmodern/literature_batch_scripts/scripts/zotero_auto_sync.py
```

제대로 작동하면:
- ✅ 변동사항 감지
- ✅ 필요시 논문 처리
- ✅ macOS 알림 표시
- ✅ 로그 파일 생성

### 3. launchd 등록 (자동 실행)

```bash
# plist 파일을 LaunchAgents에 복사
cp /Users/fourmodern/literature_batch_scripts/config/com.fourmodern.zotero-sync.plist \
   ~/Library/LaunchAgents/

# 권한 설정
chmod 644 ~/Library/LaunchAgents/com.fourmodern.zotero-sync.plist

# launchd 등록
launchctl load ~/Library/LaunchAgents/com.fourmodern.zotero-sync.plist
```

### 4. 작동 확인

```bash
# 서비스 상태 확인
launchctl list | grep zotero-sync

# 로그 확인
tail -f /Users/fourmodern/literature_batch_scripts/logs/auto_sync/sync_*.log

# 표준 출력 확인
tail -f /Users/fourmodern/literature_batch_scripts/logs/auto_sync/launchd_stdout.log
```

## ⚙️ 설정 변경

### 실행 주기 변경

`config/com.fourmodern.zotero-sync.plist` 파일의 `StartInterval` 값 수정:

```xml
<!-- 30분마다 (1800초) -->
<key>StartInterval</key>
<integer>1800</integer>

<!-- 다른 예시 -->
<!-- 5분: 300 -->
<!-- 10분: 600 -->
<!-- 1시간: 3600 -->
<!-- 2시간: 7200 -->
```

변경 후 다시 로드:
```bash
launchctl unload ~/Library/LaunchAgents/com.fourmodern.zotero-sync.plist
launchctl load ~/Library/LaunchAgents/com.fourmodern.zotero-sync.plist
```

### Python 경로 변경

다른 Python 환경을 사용하려면 plist의 `ProgramArguments` 수정:

```xml
<key>ProgramArguments</key>
<array>
    <string>/your/custom/python/path</string>
    <string>/Users/fourmodern/literature_batch_scripts/scripts/zotero_auto_sync.py</string>
</array>
```

Python 경로 확인:
```bash
conda activate zot
which python
```

## 🛑 자동 실행 중지/제거

### 일시 중지
```bash
launchctl unload ~/Library/LaunchAgents/com.fourmodern.zotero-sync.plist
```

### 다시 시작
```bash
launchctl load ~/Library/LaunchAgents/com.fourmodern.zotero-sync.plist
```

### 완전 제거
```bash
launchctl unload ~/Library/LaunchAgents/com.fourmodern.zotero-sync.plist
rm ~/Library/LaunchAgents/com.fourmodern.zotero-sync.plist
```

## 📊 로그 확인

### 동기화 로그
```bash
# 오늘 로그 확인
tail -100 /Users/fourmodern/literature_batch_scripts/logs/auto_sync/sync_$(date +%Y%m%d).log

# 실시간 모니터링
tail -f /Users/fourmodern/literature_batch_scripts/logs/auto_sync/sync_$(date +%Y%m%d).log
```

### 변동사항 기록
```bash
# 최근 변동사항 JSON 파일
ls -lt /Users/fourmodern/literature_batch_scripts/logs/auto_sync/changes_*.json | head -5
```

### launchd 로그
```bash
# 표준 출력
tail -f /Users/fourmodern/literature_batch_scripts/logs/auto_sync/launchd_stdout.log

# 에러 출력
tail -f /Users/fourmodern/literature_batch_scripts/logs/auto_sync/launchd_stderr.log
```

## 🔧 문제 해결

### 1. 스크립트가 실행되지 않는 경우

**권한 확인:**
```bash
ls -l ~/Library/LaunchAgents/com.fourmodern.zotero-sync.plist
# -rw-r--r-- 형태여야 함 (644)
```

**Python 경로 확인:**
```bash
# plist의 Python 경로가 실제 존재하는지 확인
/opt/homebrew/anaconda3/envs/zot/bin/python --version
```

### 2. 환경 변수 문제

`.env` 파일이 제대로 로드되는지 확인:
```bash
cat /Users/fourmodern/literature_batch_scripts/.env | grep OUTPUT_DIR
```

### 3. 로그에 에러가 있는 경우

```bash
# 에러 로그 확인
grep -i error /Users/fourmodern/literature_batch_scripts/logs/auto_sync/*.log
```

### 4. 수동 실행은 되는데 launchd에서 안 되는 경우

PATH 문제일 가능성 높음. plist의 `EnvironmentVariables` 확인.

## 📱 알림 설정

macOS 알림을 받으려면:
1. **시스템 설정** → **알림**
2. **스크립트 편집기** 또는 **터미널** 찾기
3. **알림 허용** 활성화

## 🎨 커스터마이징

### 알림 끄기

`scripts/zotero_auto_sync.py`에서:
```python
send_macos_notification(...)  # 이 줄들을 주석 처리
```

### 백업 활성화

sync_executor 호출 시 `--no-backup` 제거:
```python
cmd = [
    sys.executable,
    str(Path(__file__).parent / 'sync_executor.py'),
    '--from-json', str(temp_json),
    # '--no-backup'  # 이 줄 주석 처리
]
```

### 특정 컬렉션만 동기화

`scripts/zotero_auto_sync.py`에서 `compare_zotero_obsidian()` 호출 시:
```python
changes = compare_zotero_obsidian(
    output_dir=output_dir,
    collection_filter='AIDD'  # 특정 컬렉션만
)
```

## 📅 권장 설정

- **개발/테스트**: 5분 간격 (300초)
- **일반 사용**: 30분 간격 (1800초) ← 기본값
- **가벼운 사용**: 2시간 간격 (7200초)

## ⚡ 성능 팁

1. **SSD 사용**: Zotero/Obsidian 모두 SSD에 위치
2. **백업 끄기**: 빈번한 동기화 시 `--no-backup` 사용
3. **우선순위 낮추기**: plist의 `Nice` 값 조정 (10 = 낮은 우선순위)
4. **로그 정리**: 오래된 로그 파일 정기 삭제

```bash
# 30일 이상 된 로그 삭제
find /Users/fourmodern/literature_batch_scripts/logs/auto_sync -name "*.log" -mtime +30 -delete
```

## 🆘 도움말

문제가 발생하면:
1. 로그 파일 확인
2. 수동 실행 테스트
3. launchd 상태 확인: `launchctl list | grep zotero`
4. 시스템 로그 확인: `log show --predicate 'process == "zotero_auto_sync.py"' --last 1h`
