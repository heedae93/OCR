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


def _apply_masking(pdf_path: Path, boxes: list, ocr_data: dict) -> bytes:
    """
    PyMuPDF redaction 방식으로 마스킹 적용.

    흰 사각형 overlay 대신 add_redact_annot → apply_redactions 를 사용해
    PDF 텍스트 레이어 자체를 제거한 뒤 masked_value 텍스트를 삽입한다.
    OCR bbox는 이미지 픽셀 좌표 [x1, y1, x2, y2].
    """
    doc = fitz.open(str(pdf_path))

    from collections import defaultdict
    boxes_by_page = defaultdict(list)
    for box in boxes:
        page_num = box.get("page")
        if page_num is not None:
            boxes_by_page[page_num].append({
                "bbox": box["bbox"],
                "masked_value": box.get("masked_value", "***"),
            })

    ocr_pages = {p["page_number"]: p for p in ocr_data.get("pages", [])}

    for page_index in range(len(doc)):
        page_num = page_index + 1
        if page_num not in boxes_by_page:
            continue

        pdf_page = doc[page_index]
        pdf_w = pdf_page.rect.width
        pdf_h = pdf_page.rect.height

        ocr_page = ocr_pages.get(page_num, {})
        ocr_w = ocr_page.get("width", pdf_w)
        ocr_h = ocr_page.get("height", pdf_h)

        scale_x = pdf_w / ocr_w
        scale_y = pdf_h / ocr_h

        # 좌표 변환 결과를 저장해두고 redaction 후 텍스트 삽입에 재사용
        converted = []
        for item in boxes_by_page[page_num]:
            x1, y1, x2, y2 = item["bbox"]
            rx1 = x1 * scale_x
            ry1 = y1 * scale_y
            rx2 = x2 * scale_x
            ry2 = y2 * scale_y

            # 왼쪽 14px 여유 확보 (OCR bbox 오차로 첫 글자 노출 방지)
            rect = fitz.Rect(rx1 - 14.0, ry1, rx2 + 2.0, ry2)

            # redaction 어노테이션 추가 (흰 배경으로 텍스트 레이어까지 완전 제거)
            pdf_page.add_redact_annot(rect, fill=(1, 1, 1))
            converted.append({
                "rect": rect,
                "rx1": rx1,
                "ry1": ry1,
                "ry2": ry2,
                "masked_value": item["masked_value"],
            })

        # 페이지 단위로 redaction 적용 (원본 텍스트 레이어 제거)
        pdf_page.apply_redactions()

        # redaction 후 마스킹 텍스트 삽입
        for c in converted:
            rect = c["rect"]
            masked_text = c["masked_value"]
            box_h = c["ry2"] - c["ry1"]
            box_w = rect.width

            fontsize = max(6, box_h * 0.6)
            try:
                text_w = fitz.get_text_length(masked_text, fontname="helv", fontsize=fontsize)
                if text_w > box_w and text_w > 0:
                    fontsize = fontsize * (box_w / text_w) * 0.95
                    fontsize = max(5, fontsize)
            except Exception:
                pass

            pdf_page.insert_text(
                (rect.x0 + 1, c["ry1"] + fontsize),
                masked_text,
                fontname="helv",
                fontsize=fontsize,
                color=(0, 0, 0),
            )

    pdf_bytes = doc.tobytes()
    doc.close()
    return pdf_bytes