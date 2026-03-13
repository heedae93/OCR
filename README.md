# BBOCR (BabelBrain OCR)

이미지 및 PDF를 **검색 가능한(Searchable) PDF**로 변환하는 웹 애플리케이션입니다.
PaddleOCR 기반의 한국어 특화 OCR 엔진과 멀티 GPU 병렬 처리를 지원합니다.


---


## 1. 시스템 요구사항

| 항목 | 최소 | 권장 |
|------|------|------|
| OS | Ubuntu 20.04+ | Ubuntu 22.04 LTS |
| Python | 3.9 | 3.10 |
| Node.js | 18 LTS | 20 LTS |
| RAM | 16GB | 32GB+ |

### GPU 요구사항 (GPU 모드 사용 시)

| 항목 | 최소 | 권장 |
|------|------|------|
| NVIDIA Driver | 525+ | 550+ |
| CUDA Toolkit | 11.8 | 12.x |
| cuDNN | 8.6+ | 9.x |
| GPU VRAM | 8GB | 24GB (RTX 4090급) |

> GPU 없이도 CPU 모드로 작동합니다. `config.yaml`에서 `ocr.use_gpu: false`로 설정하세요.

### 현재 개발/검증 환경 (참고용)

| 항목 | 버전 |
|------|------|
| Ubuntu | 22.04 |
| Python | 3.10.18 |
| NVIDIA Driver | 565.57.01 |
| CUDA | 12.6 |
| cuDNN | 9.5.1 |
| GPU | RTX 4090 x3 |


---


## 2. 의존성 설치 (상세)

설치 순서가 중요합니다. 반드시 아래 순서를 따라주세요.

### 2-1. conda 가상환경 생성

```bash
conda create -n bbocr python=3.10 -y
conda activate bbocr
```

### 2-2. PaddlePaddle GPU 설치 (핵심)

PaddlePaddle은 **서버의 CUDA 버전과 정확히 매칭되는 빌드**를 설치해야 합니다.
잘못된 버전을 설치하면 GPU를 인식하지 못합니다.

먼저 서버의 CUDA 버전을 확인합니다:

```bash
nvidia-smi
# 오른쪽 상단에 "CUDA Version: 12.x" 표시 확인
```

그 다음 CUDA 버전에 맞는 PaddlePaddle을 설치합니다:

| 서버 CUDA 버전 | 설치 명령어 |
|---------------|------------|
| CUDA 11.8 | `pip install paddlepaddle-gpu==3.1.1 -i https://www.paddlepaddle.org.cn/packages/stable/cu118/` |
| CUDA 12.3 | `pip install paddlepaddle-gpu==3.1.1 -i https://www.paddlepaddle.org.cn/packages/stable/cu123/` |
| CUDA 12.6 | `pip install paddlepaddle-gpu==3.1.1 -i https://www.paddlepaddle.org.cn/packages/stable/cu126/` |
| CPU 전용 | `pip install paddlepaddle==3.1.1` |

> **공식 문서**: https://www.paddlepaddle.org.cn/install/quick
>
> 위 표에 없는 CUDA 버전이면 공식 문서에서 정확한 설치 명령어를 확인하세요.
> PaddlePaddle 3.x는 CUDA 11.8 / 12.3 / 12.6 빌드를 제공합니다.
> 서버의 CUDA가 12.4나 12.5라면 12.3 빌드를 사용하면 됩니다 (하위 호환).

설치 후 GPU 인식을 반드시 확인합니다:

```bash
python -c "import paddle; print(paddle.device.is_compiled_with_cuda())"
# True가 출력되어야 정상
```

### 2-3. 나머지 Python 의존성 설치

```bash
pip install -r backend/requirements.txt
```

이 명령으로 설치되는 주요 패키지:

| 패키지 | 용도 |
|--------|------|
| paddleocr | OCR 엔진 (텍스트 감지 + 인식) |
| paddlex | 레이아웃 감지 모델 (PP-DocLayout) |
| fastapi + uvicorn | 백엔드 API 서버 |
| opencv-python | 이미지 전처리 |
| Pillow | 이미지 처리 |
| PyMuPDF | PDF 읽기/쓰기 |
| reportlab | PDF 텍스트 레이어 생성 |
| pdf2image | PDF → 이미지 변환 |
| sqlalchemy | SQLite DB (세션/작업 관리) |
| pydantic | 데이터 검증 |
| PyYAML | config.yaml 파싱 |
| scikit-learn | 텍스트 블록 클러스터링 |

### 2-4. 시스템 패키지 설치

```bash
# PDF → 이미지 변환에 필요 (pdf2image가 내부적으로 사용)
sudo apt install poppler-utils -y

# 한글 폰트 (PDF 텍스트 레이어용)
sudo apt install fonts-nanum -y
```

### 2-5. Node.js 프론트엔드 의존성 설치

```bash
cd frontend
npm install
cd ..
```

### 의존성 버전 호환 매트릭스 (참고)

아래는 현재 검증된 조합입니다. 다른 버전을 사용할 경우 호환성 문제가 발생할 수 있습니다.

| 패키지 | 검증된 버전 | 비고 |
|--------|-----------|------|
| paddlepaddle-gpu | 3.1.1 | CUDA 버전별 빌드 필수 |
| paddleocr | 3.1.1 | PaddlePaddle 3.x 필요 |
| paddlex | 3.1.4 | PP-DocLayout 모델 제공 |
| opencv-python | 4.11.0 | 4.8+ 권장 |
| PyMuPDF | 1.26.0 | 1.23+ 권장 |
| Pillow | 11.2.1 | 10.0+ 권장 |
| NumPy | 1.26.4 | 2.x 미지원 (PaddlePaddle 호환) |
| FastAPI | 0.104.1 | |
| Node.js | 18.20.5 | 18 LTS 또는 20 LTS |
| Next.js | 14.x | package.json에 명시 |


---


## 3. 설정

모든 설정은 프로젝트 루트의 `config.yaml` **한 파일**에서 관리됩니다.
각 항목에 대한 상세 설명은 파일 내 한글 주석을 참고하세요.

### 필수 확인 항목

```yaml
# ── GPU 설정 ──
ocr:
  use_gpu: true          # false로 바꾸면 CPU 모드

gpu:
  cuda_visible_devices: "0"       # nvidia-smi에서 보이는 GPU 번호
  available_gpu_ids: [0]          # 병렬 처리할 GPU 목록
  # GPU 3장이면: cuda_visible_devices: "0,1,2"  available_gpu_ids: [0, 1, 2]

# ── 서버 포트 ──
server:
  backend:
    port: 6015     # 원하는 포트로 변경
  frontend:
    port: 6017     # 원하는 포트로 변경
```

### 포트 변경 시

포트를 변경하면 프론트엔드에 빌드된 API 주소도 갱신해야 합니다:

```bash
rm frontend/.env.local    # 기존 설정 삭제
./stop.sh && ./start.sh   # start.sh가 새 포트로 자동 생성
```


---


## 4. 서버 실행

```bash
# 시작 (백엔드 + 프론트엔드 동시)
./start.sh

# 종료
./stop.sh

# 상태 확인
./status.sh
```

시작 후 브라우저에서 접속:
```
http://<서버IP>:<프론트엔드포트>
```

> - `start.sh`는 config.yaml에서 포트를 읽고, 서버 IP를 자동 감지합니다.
> - 프론트엔드 빌드(`.next/`)가 없으면 자동으로 `npm run build`를 실행합니다.
> - 최초 실행 시 PaddleOCR 공식 모델을 자동 다운로드하므로 **인터넷 연결이 필요**합니다.

### 로그 확인

```bash
tail -f logs/backend.log     # 백엔드 로그
tail -f logs/frontend.log    # 프론트엔드 로그
```


---


## 5. 프로젝트 구조

```
BBOCR/
├── config.yaml              # 전체 설정 파일 (이것만 수정하면 됨)
├── start.sh / stop.sh / status.sh   # 서버 운영 스크립트
│
├── backend/                 # FastAPI 백엔드 (Python)
│   ├── main.py              # 앱 진입점
│   ├── config.py            # config.yaml 로더
│   ├── requirements.txt     # Python 의존성
│   ├── api/                 # API 라우터
│   │   ├── ocr.py           # 파일 업로드 + OCR 처리
│   │   ├── sessions.py      # 세션 관리 + 내보내기
│   │   └── export.py        # TXT/XML/Excel/ZIP 내보내기
│   ├── core/                # 핵심 엔진
│   │   ├── pdf_gen_pipeline.py  # OCR → PDF 생성 파이프라인
│   │   ├── layout_detector.py   # 문서 레이아웃 감지
│   │   ├── ocr_engine.py        # PaddleOCR 래퍼
│   │   └── ...
│   ├── models/              # 데이터 모델 (Job, Session)
│   └── utils/               # 유틸리티
│
├── frontend/                # Next.js 14 (TypeScript)
│   ├── src/
│   │   ├── app/             # 페이지 (대시보드, 에디터, 설정 등)
│   │   ├── components/      # React 컴포넌트
│   │   └── lib/             # API 클라이언트
│   └── package.json
│
└── data/                    # 런타임 데이터 (자동 생성됨)
    ├── models/best_0828/    # 커스텀 OCR 인식 모델
    ├── raw/                 # 업로드 원본
    ├── processed/           # 변환된 PDF
    ├── debug/               # 디버그 시각화
    └── temp/                # 임시 파일
```


---


## 6. 주요 기능

- **한국어 특화 OCR** — 커스텀 학습된 PaddleOCR 인식 모델
- **검색 가능한 PDF** — 투명 텍스트 레이어로 원본 품질 유지 + 텍스트 검색/복사
- **다단 레이아웃 감지** — 신문, 논문 등 멀티컬럼 문서의 읽기 순서 자동 적용
- **레이아웃 분석** — PP-DocLayout 모델로 제목/본문/표/그림 영역 구분
- **멀티 GPU 병렬 처리** — 여러 GPU에 페이지 분배하여 대량 문서 고속 처리
- **문자별 신뢰도** — CTC 확률 기반 개별 문자 단위 신뢰도 제공
- **결과 내보내기** — TXT, XML, Excel, ZIP 형식 지원
- **웹 UI** — 드래그 앤 드롭 업로드, 실시간 진행률, PDF 뷰어


---


## 7. 문제 해결

### GPU를 인식하지 못할 때

```bash
python -c "import paddle; print(paddle.device.is_compiled_with_cuda())"
```

`False`가 나오면 PaddlePaddle GPU 빌드가 CUDA와 맞지 않는 것입니다.
`nvidia-smi`로 CUDA 버전 확인 후 2-2절의 표를 참고하여 재설치하세요.

### 모델 로딩 실패

백엔드 로그에 `is not exists!`가 나오면 모델 파일이 없는 것입니다:

```bash
ls data/models/best_0828/
# 아래 4개 파일이 있어야 함:
# inference.json  inference.pdiparams  inference.yml  ppocrv5_dict.txt
```

### 포트 충돌

```bash
./stop.sh                    # 먼저 정상 종료 시도
lsof -i:6015 -sTCP:LISTEN   # 그래도 포트가 점유되어 있으면 PID 확인
kill <PID>                   # 해당 프로세스 종료
```

### 프론트엔드 빈 화면 / ChunkLoadError

브라우저 캐시 문제입니다. `Ctrl+Shift+R` (강력 새로고침)로 해결됩니다.
계속되면 프론트엔드를 재빌드하세요:

```bash
rm -rf frontend/.next
./stop.sh && ./start.sh    # start.sh가 자동으로 재빌드
```

### 한글이 깨질 때

나눔폰트가 설치되어 있는지 확인:

```bash
fc-list | grep Nanum
# NanumGothic이 표시되어야 함

# 없으면 설치
sudo apt install fonts-nanum -y
```
