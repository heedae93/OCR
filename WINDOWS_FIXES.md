# BBOCR Windows 실행 수정 내역

> 작성일: 2026-03-27
> 환경: Windows 11 / Python 3.11.9 / NVIDIA RTX 4060 Laptop GPU / CUDA 12.7

---

## GPU / CPU 모드 설정

**현재 설정: GPU 모드 (`config.yaml`)**

```yaml
ocr:
  use_gpu: true    # GPU 모드 활성화
  gpu_id: 0

gpu:
  cuda_visible_devices: "0"
  available_gpu_ids: [0]
```

- NVIDIA RTX 4060 Laptop GPU (CUDA 12.7) 감지됨
- PaddlePaddle GPU 빌드(cu126) 설치 완료
- `python -c "import paddle; print(paddle.device.is_compiled_with_cuda())"` → `True` 확인

> CPU 모드로 전환하려면 `config.yaml`에서 `ocr.use_gpu: false` 로 변경 후 서버 재시작

---

## 수정 파일 목록

### 1. `start.sh`

#### 1-1. Windows CRLF 줄바꿈 제거
- **문제**: Windows에서 작성된 `\r\n` 줄바꿈으로 bash가 exit code 49 반환
- **수정**: `sed -i 's/\r//' start.sh stop.sh status.sh` 실행

#### 1-2. `python3` → `python` 명령어 변경
```bash
# 수정 전
python3 -c "import yaml, sys ..."

# 수정 후
python -c "import yaml, sys ..."
```
- **이유**: Windows에서 `python3` 명령이 비어있고 `python`이 Python 3.11을 가리킴

#### 1-3. `config.yaml` UTF-8 인코딩 명시
```bash
# 수정 전
with open('config.yaml', 'r') as f:

# 수정 후
with open('config.yaml', 'r', encoding='utf-8') as f:
```
- **이유**: Windows 기본 인코딩(cp949)이 UTF-8 파일의 한글 주석을 읽지 못함

#### 1-4. `lsof` → `netstat` 포트 확인으로 교체
```bash
# 수정 전
if lsof -i:"$BACKEND_PORT" -sTCP:LISTEN -t > /dev/null 2>&1; then

# 수정 후
port_in_use() {
    netstat -an 2>/dev/null | grep -q ":$1 .*LISTEN" || \
    netstat -an 2>/dev/null | grep -q ":$1 .*LISTENING"
}
if port_in_use "$BACKEND_PORT"; then
```
- **이유**: `lsof`는 Linux 전용 도구. Windows Git Bash에서 미제공

#### 1-5. `hostname -I` → `ipconfig` fallback 추가
```bash
# 수정 후
SERVER_IP=$(hostname -I 2>/dev/null | awk '{print $1}')
if [ -z "$SERVER_IP" ]; then
    SERVER_IP=$(ipconfig 2>/dev/null | grep -m1 "IPv4" | awk '{print $NF}' | tr -d '\r')
fi
```
- **이유**: `hostname -I`는 Linux 전용. Windows에서는 `ipconfig` 사용

---

### 2. `backend/main.py`

#### 2-1. paddlex 이중 초기화 오류 방지
```python
# 추가
os.environ.setdefault('PADDLE_PDX_EAGER_INIT', '0')
```
- **이유**: `paddleocr`와 `layout_detector`가 각각 `paddlex`를 import할 때
  `RuntimeError: PDX has already been initialized` 발생.
  `PADDLE_PDX_EAGER_INIT=0`으로 설정하면 repo_manager 초기화를 지연(lazy)으로 전환하여 충돌 방지

#### 2-2. `langchain.docstore` 호환 shim 주입
```python
# 추가
import sys, types
try:
    from langchain_community.docstore.document import Document as _LCDocument
    _ds_mod = types.ModuleType("langchain.docstore")
    _ds_doc_mod = types.ModuleType("langchain.docstore.document")
    _ds_doc_mod.Document = _LCDocument
    _ds_mod.document = _ds_doc_mod
    sys.modules.setdefault("langchain.docstore", _ds_mod)
    sys.modules.setdefault("langchain.docstore.document", _ds_doc_mod)
except ImportError:
    pass
```
- **이유**: `langchain 1.x`에서 `langchain.docstore` 모듈 제거됨.
  paddlex 내부에서 이 모듈을 참조하므로 langchain 0.3.x로 다운그레이드 + 호환 shim 추가

#### 2-3. CTC patch import 순서 변경
```python
# 수정 전
from core.ctc_patch import patch_ctc_decoder
patch_ctc_decoder()
from api import ocr, ...

# 수정 후
from core.ctc_patch import patch_ctc_decoder
from api import ocr, ...   # paddlex 먼저 초기화
patch_ctc_decoder()         # 이후 패치 적용
```
- **이유**: `patch_ctc_decoder()`가 먼저 paddlex를 초기화하면, 이후 `paddleocr` import 시
  paddlex 재초기화 시도로 충돌 발생

---

### 3. `backend/utils/job_manager.py`

#### fcntl → 크로스 플랫폼 파일 잠금
```python
# 수정 전
import fcntl
...
fcntl.flock(f.fileno(), fcntl.LOCK_EX)

# 수정 후
try:
    import fcntl
    _HAS_FCNTL = True
except ImportError:
    _HAS_FCNTL = False
...
if _HAS_FCNTL:
    fcntl.flock(f.fileno(), fcntl.LOCK_EX)
```
- **이유**: `fcntl`은 Unix 전용 모듈. Windows에서 `ModuleNotFoundError` 발생

---

### 4. `backend/api/sessions.py`

#### fcntl → 크로스 플랫폼 파일 잠금 (job_manager.py와 동일)
- **수정 내용**: `import fcntl` → try/except로 감싸고 `_HAS_FCNTL` 플래그 사용
- **이유**: `fcntl`은 Unix 전용. Windows에서 `ModuleNotFoundError` 발생

---

### 5. `backend/core/ctc_patch.py`

#### PaddleOCR 3.x `return_word_box` 인자 오류 수정
```python
# 수정 전
def __call__(self, pred):

# 수정 후
def __call__(self, pred, **kwargs):
```
- **이유**: PaddleOCR 3.x가 CTC 디코더 호출 시 `return_word_box=True` 등 추가 키워드 인자를 전달하는데,
  패치된 `__call__`이 고정 시그니처(`pred`만)여서 `TypeError` 발생.
  `**kwargs`를 추가해 현재 및 미래 추가 인자를 모두 수용하도록 수정.

---

### 6. `backend/api/ocr.py`

#### Windows 임시 파일 삭제 오류 수정 (WinError 32)
```python
# 수정 전
with tempfile.NamedTemporaryFile(suffix='.png', delete=False) as f:
    dummy_img.save(f.name)
    try:
        engine.predict(f.name)
    finally:
        os.unlink(f.name)  # ← Windows: 파일 핸들이 열려있어 삭제 실패

# 수정 후
with tempfile.NamedTemporaryFile(suffix='.png', delete=False) as f:
    tmp_path = f.name
dummy_img.save(tmp_path)    # with 블록 종료 후 파일 핸들 닫힘
try:
    engine.predict(tmp_path)
finally:
    try:
        os.unlink(tmp_path)
    except OSError:
        pass
```
- **이유**: Windows에서는 파일 핸들이 열린 상태에서 삭제 불가.
  `with` 블록 종료 후(핸들 닫힌 뒤) 삭제해야 함

---

### 7. `frontend/src/components/UploadQueueModal.tsx` (신규)

#### 7-1. 업로드 후 OCR 처리 시작 누락 버그 수정

```typescript
// 수정 전 (처리 시작 호출 없음)
await fetch(`${API_BASE}/sessions/${sessionId}/documents`, { ... })
await pollStatus(jobId, qf.id)   // ← queued 상태에서 영원히 대기

// 수정 후
await fetch(`${API_BASE}/sessions/${sessionId}/documents`, { ... })
await fetch(`${API_BASE}/process/${jobId}`, { method: 'POST' })  // ← 추가
await pollStatus(jobId, qf.id)
```
- **이유**: `/api/upload`는 파일 저장 및 job 생성만 하고 OCR을 시작하지 않음.
  반드시 `POST /api/process/{job_id}`를 호출해야 OCR 워커가 실행됨.
  누락 시 파일이 `queued` 상태에서 멈춤.

#### 7-2. 다중 파일 업로드 큐 모달 구현 (FileZilla 방식)

- **변경 내용**: 기존 단순 업로드 모달 → 파일별 진행률 표시 큐 방식으로 교체
- **업로드 진행률**: XHR `upload.onprogress` 이벤트로 0~50% 표시
- **OCR 진행률**: `GET /api/status/{job_id}` 2초 폴링으로 50~100% 표시
- **파일 선택**: `window.showOpenFilePicker()` (File System Access API) 사용 — 네이티브 탐색기에서 다중 선택 가능
- **순차 처리**: GPU 메모리 충돌 방지를 위해 파일 1개씩 순차 처리

#### 7-3. 백그라운드 처리 지원

- **변경 내용**: 모달을 닫아도 OCR 처리가 백그라운드에서 계속 진행
- **구현**: 모달을 조건부 렌더링(`&&`) 대신 `visible` prop + `hidden` 클래스로 제어 (컴포넌트 언마운트 방지)
- **플로팅 위젯**: 처리 중 모달을 닫으면 오른쪽 하단에 진행 상황 표시 버튼 노출

---

### 8. `frontend/src/app/icon.svg` (신규)

#### 파비콘 추가

- **변경 내용**: 기본 Next.js 파비콘 → 앱 전용 SVG 아이콘 적용
- **디자인**: 파란 그라데이션 배경 + 흰색 문서 + OCR 스캔 라인
- **적용 방법**: Next.js App Router의 `app/icon.svg` 규칙으로 자동 적용 (별도 설정 불필요)

---

## 설치된 패키지

| 패키지 | 버전 | 비고 |
|--------|------|------|
| paddlepaddle-gpu | 3.1.1 | CUDA 12.6 빌드 (12.7과 호환) |
| paddleocr | 3.1.1 | PaddlePaddle 3.x 기반 |
| paddlex | 3.1.4 | PP-DocLayout 모델 제공 |
| reportlab | 4.4.10 | PDF 텍스트 레이어 생성 |
| pdf2image | 1.17.0 | PDF → 이미지 변환 |
| PyPDF2 | 3.0.1 | PDF 처리 |
| aiofiles | 25.1.0 | 비동기 파일 I/O |
| langchain | 0.3.25 | paddlex 호환 버전으로 다운그레이드 |
| langchain-community | 0.4 | docstore.Document 호환성 |

---

## 서버 상태

| 구분 | URL |
|------|-----|
| 백엔드 API | http://192.168.0.69:6015 |
| 프론트엔드 UI | http://192.168.0.69:6017 |
| API 문서 | http://192.168.0.69:6015/docs |

```bash
# 시작
bash start.sh

# 종료
bash stop.sh

# 상태 확인
bash status.sh
```
