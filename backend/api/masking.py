"""
Masking api - PII 감지 및 마스킹 pdf 다운로드
"""
import json
import logging
import io
from pathlib import Path
from typing import Optional, Dict

import fitz 
from fastapi import APIRouter,HTTPException
from fastapi.responses import StreamingResponse
from config import Config

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/masking", tags=["Masking"])

def _load_ocr(job_id:str) -> Optional[Dict]:
    """OCR 결과 JSON 로드"""
    json_path = Config.PROCESSED_DIR / f"{job_id}_ocr.json"
    if not json_path.exists():
        return None
    with open(json_path,"r",encoding="utf-8") as f:
        return json.load(f)
    

# ============================================================
# 1. PII 감지 엔드포인트
# ============================================================

def _ensure_masked_pdf(job_id: str, pii_data: dict) -> None:
    """마스킹 PDF 파일이 없으면 생성해서 저장한다."""
    masked_pdf_path = Config.PROCESSED_DIR / f"{job_id}_masked.pdf"
    if masked_pdf_path.exists():
        return

    pdf_path = Config.PROCESSED_DIR / f"{job_id}.pdf"
    if not pdf_path.exists():
        logger.warning(f"원본 PDF 없음, 마스킹 PDF 생성 스킵: {job_id}")
        return

    boxes_with_bbox = [
        b for b in pii_data.get("masked_boxes", [])
        if b.get("bbox") and b.get("masked_value", b.get("value")) != b.get("value")
    ]

    ocr_data = _load_ocr(job_id) or {}
    try:
        pdf_bytes = _apply_masking(pdf_path, boxes_with_bbox, ocr_data)
        with open(masked_pdf_path, "wb") as f:
            f.write(pdf_bytes)
        logger.info(f"마스킹 PDF 저장 완료: {masked_pdf_path}")
    except Exception as e:
        logger.error(f"마스킹 PDF 생성 실패 ({job_id}): {e}")


@router.get("/{job_id}/detect")
async def detect_pii(job_id: str):
    pii_path = Config.PROCESSED_DIR / f"{job_id}_pii.json"

    # 저장된 파일 있으면 필터링 후 반환
    if pii_path.exists():
        with open(pii_path, "r", encoding="utf-8") as f:
            cached = json.load(f)
        # 마스킹이 실제로 변경되지 않은 항목(라벨 단어 등) 제외
        cached["masked_boxes"] = [
            b for b in cached.get("masked_boxes", [])
            if b.get("masked_value") != b.get("value")
        ]
        cached["pii_items"] = [
            item for item in cached.get("pii_items", [])
            if item.get("masked_value") != item.get("value")
        ]
        # 마스킹 PDF가 없으면 생성
        _ensure_masked_pdf(job_id, cached)
        return cached

    # 없으면 실시간 추출 (fallback)
    from core.pii_extractor import extract_pii_from_pages, mask_value
    ocr_data = _load_ocr(job_id)
    if not ocr_data:
        raise HTTPException(status_code=404, detail="OCR 결과를 찾을 수 없습니다. OCR을 먼저 실행하세요.")

    pages = ocr_data.get("pages", [])

    # 라인별 bbox와 함께 PII 추출 (1차 정규식 → 2차 병합 → 3차 LLM 보조)
    pii_boxes = extract_pii_from_pages(pages)

    for box in pii_boxes:
        box["masked_value"] = mask_value(box["type"], box["value"])

    # 실제 마스킹이 일어나지 않은 항목 제거
    pii_boxes = [b for b in pii_boxes if b.get("masked_value") != b.get("value")]

    pii_items = [
        {"type": b["type"], "value": b["value"], "masked_value": b["masked_value"]}
        for b in pii_boxes
    ]

    result = {"job_id": job_id, "pii_items": pii_items, "masked_boxes": pii_boxes}

    # 결과 저장
    with open(pii_path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    # 마스킹 PDF 생성 및 저장
    _ensure_masked_pdf(job_id, result)

    return result


# ============================================================
# 2. 마스킹 PDF 다운로드 엔드포인트
# ============================================================

@router.get("/{job_id}/download")
async def download_masked_pdf(job_id:str):
    # 저장된 PII 결과 로드
    pii_path = Config.PROCESSED_DIR / f"{job_id}_pii.json"
    if not pii_path.exists():
        raise HTTPException(status_code=404, detail="PII 결과를 찾을 수 없습니다. OCR을 먼저 실행하세요.")
    with open(pii_path, "r", encoding="utf-8") as f:
        pii_data = json.load(f)

    # 원본 PDF 경로 확인
    pdf_path = Config.PROCESSED_DIR / f"{job_id}.pdf"
    if not pdf_path.exists():
        raise HTTPException(status_code=404, detail="PDF 파일을 찾을 수 없습니다.")
    
    # bbox 있고 실제 마스킹이 적용된 항목만 추출
    # (masked_value == value 이면 마스킹이 안 된 것 → 흰박스 제외)
    boxes_with_bbox = [
        b for b in pii_data.get("masked_boxes", [])
        if b.get("bbox") and b.get("masked_value", b.get("value")) != b.get("value")
    ]

    # OCR 데이터(좌표 변환용)
    ocr_data = _load_ocr(job_id)

    masked_pdf_bytes = _apply_masking(pdf_path, boxes_with_bbox, ocr_data)

    return StreamingResponse(
        io.BytesIO(masked_pdf_bytes),
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="masked_{job_id}.pdf"'}
    )


# def _apply_masking(pdf_path: Path, boxes: list, ocr_data: dict) -> bytes:
#     """
#     텍스트를 물리적으로 파괴하고 안전하게 저장합니다.
#     """
#     doc = fitz.open(str(pdf_path))
#     # ocr_data 구조에 따라 page_number 혹은 page 키를 유연하게 처리
#     ocr_pages = {p.get("page_number") or p.get("page"): p for p in ocr_data.get("pages", [])}

#     for page_index in range(len(doc)):
#         page_num = page_index + 1
#         page_boxes = [b for b in boxes if b.get("page") == page_num]
#         if not page_boxes:
#             continue

#         pdf_page = doc[page_index]
#         ocr_p = ocr_pages.get(page_num, {})
        
#         # 스케일 계산
#         ocr_w = ocr_p.get("width") or pdf_page.rect.width
#         ocr_h = ocr_p.get("height") or pdf_page.rect.height
        
#         scale_x = pdf_page.rect.width / ocr_w
#         scale_y = pdf_page.rect.height / ocr_h

#         for item in page_boxes:
#             x1, y1, x2, y2 = item["bbox"]
            
#             # PDF 좌표 변환 및 여유값(Padding) 부여
#             rect = fitz.Rect(
#                 x1 * scale_x - 2, 
#                 y1 * scale_y - 2, 
#                 x2 * scale_x + 2, 
#                 y2 * scale_y + 2
#             )
            
#             # 교정 영역 지정 (흰색 박스)
#             pdf_page.add_redact_annot(rect, fill=(1, 1, 1))

#         # 페이지별 즉시 적용
#         pdf_page.apply_redactions(images=fitz.PDF_REDACT_IMAGE_NONE)

#     # [수정] 문제가 된 linear=True 옵션을 제거하고 안정적인 옵션만 사용
#     pdf_bytes = doc.tobytes(
#         garbage=3, 
#         deflate=True, 
#         clean=True
#     )
#     doc.close()
#     return pdf_bytes

import fitz
from pathlib import Path


def _get_partial_mask_bbox(value: str, masked_value: str, bbox: list):
    """
    value와 masked_value를 비교해 * 에 해당하는 부분의 sub-bbox만 반환.
    예: value="박채연", masked_value="박**" → "채연" 부분의 bbox 반환.
    실패 시 None 반환 (호출부에서 원본 bbox로 fallback).
    """
    if not value or not masked_value or len(value) != len(masked_value):
        return None

    first_star = masked_value.find('*')
    last_star = masked_value.rfind('*')
    if first_star == -1:
        return None

    masked_substr = value[first_star:last_star + 1]
    if not masked_substr:
        return None

    from core.pii_extractor import _estimate_sub_bbox
    return _estimate_sub_bbox(masked_substr, value, bbox)


def _sample_background_color(pdf_page, rect: fitz.Rect) -> tuple:
    """
    rect 주변(상하좌우) 픽셀을 샘플링해 배경색을 추정한다.
    반환값: fitz fill 용 (r, g, b) — 각 0.0~1.0 범위.
    """
    pad = 6  # 샘플링 여백 (pt)
    pr = pdf_page.rect

    zones = [
        fitz.Rect(rect.x0, max(pr.y0, rect.y0 - pad), rect.x1, rect.y0),       # 위
        fitz.Rect(rect.x0, rect.y1, rect.x1, min(pr.y1, rect.y1 + pad)),         # 아래
        fitz.Rect(max(pr.x0, rect.x0 - pad), rect.y0, rect.x0, rect.y1),         # 왼쪽
        fitz.Rect(rect.x1, rect.y0, min(pr.x1, rect.x1 + pad), rect.y1),         # 오른쪽
    ]

    total_r = total_g = total_b = count = 0
    for zone in zones:
        if zone.is_empty or zone.width < 1 or zone.height < 1:
            continue
        try:
            pix = pdf_page.get_pixmap(clip=zone, matrix=fitz.Matrix(1, 1))
            data = pix.samples
            n = pix.n  # 채널 수 (RGB=3, RGBA=4 등)
            for i in range(0, len(data) - 2, n):
                total_r += data[i]
                total_g += data[i + 1]
                total_b += data[i + 2]
                count += 1
        except Exception:
            pass

    if count == 0:
        return (1.0, 1.0, 1.0)  # 샘플 실패 시 흰색 fallback
    return (total_r / count / 255, total_g / count / 255, total_b / count / 255)


# 한글 지원 폰트 경로 (없으면 None — 기본 폰트로 fallback)
import os as _os
_KOREAN_FONT_PATH = next(
    (p for p in [
        r"C:\Windows\Fonts\malgun.ttf",      # Windows Malgun Gothic
        r"C:\Windows\Fonts\gulim.ttc",
        "/usr/share/fonts/truetype/nanum/NanumGothic.ttf",  # Linux NanumGothic
    ] if _os.path.exists(p)),
    None
)


def _apply_masking(pdf_path: Path, boxes: list, ocr_data: dict) -> bytes:
    """
    마스킹 영역 주변 픽셀을 샘플링해 배경색으로 채우고,
    그 위에 마스킹된 * 텍스트를 덧씌운다.
    (예: 박채연 → "채연" 영역을 배경색으로 덮고 "**" 표시)
    """
    try:
        doc = fitz.open(str(pdf_path))
        pages_list = ocr_data.get("pages", [])
        ocr_pages = {p.get("page_number") or p.get("page"): p for p in pages_list}

        for page_index in range(len(doc)):
            page_num = page_index + 1
            page_boxes = [b for b in boxes if str(b.get("page")) == str(page_num)]
            if not page_boxes:
                continue

            pdf_page = doc[page_index]
            ocr_p = ocr_pages.get(page_num, {})
            ocr_w = ocr_p.get("width") or pdf_page.rect.width
            ocr_h = ocr_p.get("height") or pdf_page.rect.height
            scale_x = pdf_page.rect.width / ocr_w
            scale_y = pdf_page.rect.height / ocr_h

            # ── 1단계: redaction 등록 + 배경색 샘플링 (삭제 전에 해야 함) ──────
            pending: list[tuple[fitz.Rect, str]] = []  # (rect, star_text)

            for item in page_boxes:
                bbox = item.get("bbox")
                if not bbox:
                    continue

                value = item.get("value", "")
                masked_value = item.get("masked_value", "")

                # * 부분만 좁혀서 처리
                partial_bbox = _get_partial_mask_bbox(value, masked_value, bbox)
                x1, y1, x2, y2 = partial_bbox if partial_bbox else bbox

                rect = fitz.Rect(
                    x1 * scale_x - 1,
                    y1 * scale_y - 1,
                    x2 * scale_x + 1,
                    y2 * scale_y + 1,
                )

                # 주변 픽셀로 배경색 추정 (삭제 전 샘플링)
                fill_color = _sample_background_color(pdf_page, rect)
                pdf_page.add_redact_annot(rect, fill=fill_color)

                # masked_value 에서 * 부분만 추출 (예: "박**" → "**")
                first_star = masked_value.find('*')
                last_star  = masked_value.rfind('*')
                star_text  = masked_value[first_star:last_star + 1] if first_star != -1 else ""
                pending.append((rect, star_text))

            # ── 2단계: redaction 적용 (텍스트 물리적 제거) ────────────────────
            pdf_page.apply_redactions(images=fitz.PDF_REDACT_IMAGE_NONE)

            # ── 3단계: * 텍스트 덧씌우기 ─────────────────────────────────────
            for rect, star_text in pending:
                if not star_text:
                    continue
                font_size = max(6.0, rect.height * 0.62)
                try:
                    kwargs = dict(
                        rect=rect,
                        text=star_text,
                        fontsize=font_size,
                        color=(0.2, 0.2, 0.2),
                        align=fitz.TEXT_ALIGN_LEFT,
                    )
                    if _KOREAN_FONT_PATH:
                        kwargs["fontfile"] = _KOREAN_FONT_PATH
                        kwargs["fontname"] = "korean"
                    pdf_page.insert_textbox(**kwargs)
                except Exception as te:
                    logger.debug(f"텍스트 삽입 실패 (무시): {te}")

        pdf_bytes = doc.tobytes(garbage=3, deflate=True)
        doc.close()

        if not pdf_bytes:
            raise ValueError("생성된 PDF 데이터가 비어있습니다.")
        return pdf_bytes

    except Exception as e:
        logger.error(f"CRITICAL ERROR in _apply_masking: {e}")
        with open(pdf_path, "rb") as f:
            return f.read()