# BBOCR 기술 아키텍처 문서

이 문서는 BBOCR 시스템의 전체 구조와 각 파일의 역할을 설명합니다.


---


## 전체 처리 흐름

```
[사용자 브라우저]
    │
    ▼
[프론트엔드 - Next.js 14]  ← http://서버IP:6017
    │  axios API 호출
    ▼
[백엔드 - FastAPI]          ← http://서버IP:6015
    │
    ├─ 파일 업로드 → data/raw/
    ├─ OCR 엔진 (PaddleOCR + 커스텀 모델)
    ├─ 레이아웃 감지 (PP-DocLayout)
    ├─ 읽기 순서 정렬
    ├─ 검색 가능한 PDF 생성 (투명 텍스트 레이어)
    ├─ 결과 저장 → data/processed/
    └─ SQLite DB (작업/세션 관리)
```

### 상세 처리 순서

1. 사용자가 웹 UI에서 PDF/이미지를 업로드
2. 백엔드가 파일을 `data/raw/`에 저장하고 DB에 작업(Job) 생성
3. PDF인 경우 페이지별 이미지로 변환
4. 각 페이지를 GPU별로 분배하여 병렬 OCR 처리
5. 레이아웃 감지 모델로 영역 분류 (제목/본문/표/그림 등)
6. 읽기 순서 정렬 (다단 문서 지원)
7. OCR 결과 + 원본 이미지 → 투명 텍스트 레이어가 있는 PDF 생성
8. 결과 PDF + OCR JSON을 `data/processed/`에 저장
9. 프론트엔드에서 결과 PDF 뷰어로 표시, 편집/내보내기 가능


---


## 백엔드 구조 (`backend/`)


### 진입점

| 파일 | 설명 |
|------|------|
| `main.py` | FastAPI 앱 진입점. CORS 설정, 라우터 등록, 정적 파일 마운트, DB 초기화. CTC 패치를 PaddleOCR import 전에 적용 |
| `config.py` | `config.yaml`을 읽어 전역 설정 클래스(`Config`)로 변환. 모든 모듈이 이 클래스를 참조 |
| `database.py` | SQLAlchemy ORM 모델 정의 (User, Job, OCRPage, Session, SessionDocument). DB 테이블 생성 및 기본 사용자 초기화 |
| `debug_reading_order.py` | 읽기 순서 디버깅용 CLI 도구. OCR JSON 파일을 읽어 텍스트 블록 순서를 시각적으로 출력 |


### API 라우터 (`backend/api/`)

| 파일 | 라우트 | 설명 |
|------|--------|------|
| `ocr.py` | `/api/process` | **핵심 OCR 처리**. 파일 업로드 → OCR 실행 → PDF 생성. GPU별 엔진 풀 관리, 멀티 GPU 병렬 처리. 작업 상태 조회 및 취소 |
| `jobs.py` | `/api/jobs` | 작업 목록 조회, 상세 조회, 삭제. 상태 필터링과 페이지네이션 지원 |
| `sessions.py` | `/api/sessions` | 세션(문서 그룹) 관리. 여러 문서를 세션으로 묶어 일괄 내보내기 가능 |
| `storage.py` | `/api/files` | 원본/처리 파일 목록 조회 및 다운로드 |
| `drive.py` | `/api/drive` | 파일 관리자. 폴더 탐색/생성, 파일 복사/이동/삭제, PDF 병합/분할 |
| `export.py` | `/api/export` | OCR 결과를 TXT, XML(ABBYY 호환), Excel 형식으로 내보내기 |
| `settings.py` | `/api/settings` | 웹 UI에서 config.yaml 설정을 조회/변경하는 REST API |


### 핵심 엔진 (`backend/core/`)

| 파일 | 설명 |
|------|------|
| `pdf_gen_pipeline.py` | **메인 파이프라인**. `CustomOCRModel` 클래스 (PaddleOCR 래퍼)와 `OCRPDFGenerator` 클래스 (이미지 → 검색 가능한 PDF 변환). 커스텀 한국어 인식 모델 로딩, CTC 디코딩으로 문자별 신뢰도 추출 |
| `ocr_engine.py` | PaddleOCR 래퍼. 이미지 전처리(노이즈 제거, 업스케일, CLAHE) 후 OCR 실행. 커스텀 인식 모델 경로를 Config에서 읽음 |
| `paddleocr_engine.py` | 순수 PaddleOCR 엔진. 레이아웃 감지 없이 텍스트 감지+인식만 수행. 라인 단위 정밀 bbox 반환 |
| `pp_structure_engine.py` | PP-StructureV3 기반 고급 엔진. 20개 이상의 레이아웃 카테고리 인식, 다단 읽기 순서 복원 |
| `layout_detector.py` | PP-DocLayout 모델로 문서 영역 감지 (제목, 본문, 표, 그림, 수식, 참고문헌 등). 첫 사용 시 모델 지연 로딩 |
| `reading_order_sorter.py` | 좌표 기반 읽기 순서 정렬. 단일/다단 자동 감지, 같은 줄 그루핑, 왼쪽→오른쪽 컬럼 순서 정렬. ML 모델 불필요 (<5ms/페이지) |
| `column_detector.py` | 다단(컬럼) 구조 감지. 텍스트 블록 좌표에서 컬럼 수와 경계를 계산 |
| `invisible_layer.py` | 투명 텍스트 레이어 PDF 생성. ReportLab으로 OCR bbox에 맞춰 거의 보이지 않는(alpha=0.01) 텍스트 배치. 한글 폰트 지원 |
| `text_scaler.py` | 텍스트 크기 정밀 계산. ReportLab 폰트 메트릭으로 bbox에 딱 맞는 폰트 크기를 이진 탐색으로 결정 |
| `pdf_processor.py` | PDF → 이미지 변환 유틸리티. PyMuPDF 또는 pdf2image 백엔드 사용 |
| `ctc_patch.py` | PaddleOCR의 CTC 디코더를 패치하여 문자별 신뢰도를 추출할 수 있도록 함. 앱 시작 시 PaddleOCR import 전에 적용 |
| `ctc_char_confidence.py` | CTC 출력에서 문자 단위 신뢰도를 디코딩하는 커스텀 디코더 |
| `config_manager.py` | config.yaml을 파싱하여 딕셔너리로 제공. `create_legacy_config()` 함수로 기존 파이프라인과의 호환 설정 생성 |


### 데이터 모델 (`backend/models/`)

| 파일 | 설명 |
|------|------|
| `job.py` | 작업(Job) 모델. `JobStatus` 열거형 (QUEUED, PROCESSING, COMPLETED, FAILED, CANCELLED), 생성/응답 모델 |
| `ocr.py` | OCR 결과 모델. 텍스트 라인(`OCRLine`: 텍스트, bbox, 신뢰도, 문자별 신뢰도, 레이아웃 타입), 페이지(`OCRPage`), 문서(`OCRResult`), 내보내기 요청 |
| `document.py` | 문서 메타데이터 모델. 페이지 수, 파일 크기, 언어 정보 |


### 유틸리티 (`backend/utils/`)

| 파일 | 설명 |
|------|------|
| `job_manager.py` | 작업 상태 관리. 메모리 + 파일 기반 이중 저장 (파일 락으로 원자적 쓰기). 프로세스 간 상태 공유 가능 |
| `file_utils.py` | 파일 유틸리티. UUID 기반 고유 ID 생성, 파일 저장, 임시 파일 정리 |
| `db_helper.py` | DB 헬퍼 함수. 작업 생성/상태 업데이트/완료 처리, 페이지별 통계 저장, OCR 결과 조회 |
| `smart_layers.py` | 사용자 편집 오버레이 적용. 텍스트, 이미지, 서명, 도형, 드로잉을 페이지 이미지에 렌더링 |


---


## 프론트엔드 구조 (`frontend/src/`)


### 페이지 (`src/app/`)

| 파일 | 경로 | 설명 |
|------|------|------|
| `layout.tsx` | — | 루트 레이아웃. 테마 프로바이더, 사이드바, 전역 스타일 |
| `page.tsx` | `/` | 대시보드. 최근 활동, 세션 목록, 파일 업로드 |
| `jobs/page.tsx` | `/jobs` | 작업 이력. 상태별 필터링, 검색, 통계 |
| `editor/[jobId]/page.tsx` | `/editor/:jobId` | OCR 편집기. PDF 뷰어 + 텍스트 편집 + 내보내기. 자동 저장 |
| `drive/page.tsx` | `/drive` | 파일 관리자. 폴더 탐색, 파일 이동/복사/삭제, PDF 병합/분할 |
| `settings/page.tsx` | `/settings` | 설정 화면. OCR/PDF/전처리 설정을 웹에서 변경 |
| `help/page.tsx` | `/help` | 도움말 |
| `logout/page.tsx` | `/logout` | 로그아웃 (홈으로 리다이렉트) |


### 컴포넌트 (`src/components/`)

| 파일 | 설명 |
|------|------|
| `Sidebar.tsx` | 좌측 내비게이션 바. 대시보드/작업/드라이브/설정/도움말 링크 |
| `Dashboard.tsx` | 대시보드 메인 영역. 세션 목록, 통계, 최근 문서 |
| `UploadZone.tsx` | 파일 업로드 영역. 드래그 앤 드롭, 클립보드 붙여넣기, 진행률 표시 |
| `UploadOverlay.tsx` | 업로드 진행 오버레이. 업로드 → 처리 → 완료 단계 표시 |
| `PDFViewer.tsx` | PDF 렌더링. 확대/축소, 페이지 맞춤, 텍스트 레이어 오버레이 |
| `TextEditor.tsx` | 텍스트 편집기. PDF 위에 텍스트 요소 추가/수정/삭제 |
| `ExportModal.tsx` | 내보내기 모달. PDF, TXT, XML, JSON, Excel 형식 선택 |
| `SessionSidebar.tsx` | 세션 사이드바. 문서 트리, 업로드 큐, 일괄 내보내기 |
| `SessionExportModal.tsx` | 세션 일괄 내보내기 모달 |
| `OCRProgressOverlay.tsx` | OCR 진행률 원형 게이지. 현재 페이지/전체 페이지 표시 |
| `RecentActivity.tsx` | 최근 작업 위젯. 상태 표시 및 다운로드 |
| `DataViewer.tsx` | OCR 결과 데이터 뷰어. JSON/XML 형식으로 복사/다운로드 |
| `ThemeToggle.tsx` | 다크/라이트 모드 전환 버튼 |


### 라이브러리 (`src/lib/`)

| 파일 | 설명 |
|------|------|
| `api.ts` | 백엔드 API 클라이언트. axios 기반. 모든 API 호출 함수 집중 관리 (업로드, 작업 조회, OCR 결과, 드라이브 조작, 내보내기 등) |


### 타입 (`src/types/`)

| 파일 | 설명 |
|------|------|
| `index.ts` | TypeScript 인터페이스 정의. Job, OCRLine, OCRPage, OCRResult, SmartToolLayer 등 |


### 컨텍스트 (`src/contexts/`)

| 파일 | 설명 |
|------|------|
| `ThemeContext.tsx` | 테마 컨텍스트. 다크/라이트 모드 상태를 localStorage에 저장하여 유지 |


---


## 멀티 GPU 병렬 처리 구조

```
ocr.py (API 라우터)
    │
    ├─ GPU 0 ─ OCR 엔진 인스턴스 ─ Lock
    ├─ GPU 1 ─ OCR 엔진 인스턴스 ─ Lock
    └─ GPU 2 ─ OCR 엔진 인스턴스 ─ Lock
         │
         └─ ThreadPoolExecutor
              페이지 1 → GPU 0
              페이지 2 → GPU 1
              페이지 3 → GPU 2
              페이지 4 → GPU 0 (순환)
              ...
```

- `config.yaml`의 `gpu.available_gpu_ids`에 지정된 GPU마다 독립적인 OCR 엔진 인스턴스 생성
- PaddleOCR이 스레드 안전하지 않으므로 GPU별 Lock으로 동시 접근 방지
- 페이지를 GPU에 라운드 로빈으로 분배하여 병렬 처리


## DB 스키마

```
users
  ├── id (PK)
  ├── username, email
  │
  ├── jobs (1:N)
  │     ├── id, job_id (UUID)
  │     ├── filename, file_path, file_size
  │     ├── status (queued/processing/completed/failed/cancelled)
  │     ├── progress_percent, current_page, total_pages
  │     ├── pdf_path, ocr_json_path
  │     ├── processing_time_seconds
  │     ├── total_text_blocks, average_confidence, is_double_column
  │     │
  │     └── ocr_pages (1:N)
  │           ├── page_number
  │           ├── text_block_count, average_confidence
  │           ├── is_double_column, column_boundary
  │           └── image_width, image_height
  │
  └── sessions (1:N)
        ├── id, name, description
        │
        └── session_documents (1:N)
              ├── job_id (FK → jobs)
              ├── display_order
              └── is_selected
```
