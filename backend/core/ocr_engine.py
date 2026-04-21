"""
OCR Engine using PaddleOCR
"""
import logging
import os
from pathlib import Path
from typing import List, Dict, Optional
import tempfile
import cv2
import numpy as np

# cuDNN preloading is handled by main.py via config.yaml settings

try:
    from paddleocr import PaddleOCR
    PADDLEOCR_AVAILABLE = True
except ImportError:
    PADDLEOCR_AVAILABLE = False
    logging.warning("PaddleOCR not available")

from config import Config

logger = logging.getLogger(__name__)


class OCREngine:
    """OCR Engine wrapper for PaddleOCR"""

    def __init__(self):
        if not PADDLEOCR_AVAILABLE:
            raise RuntimeError("PaddleOCR is not installed")

        self.config = Config
        self.ocr = self._initialize_ocr()
        logger.info("OCR Engine initialized successfully")

    def _initialize_ocr(self):
        """Initialize PaddleOCR model"""
        try:
            import os

            # CRITICAL: Use Chinese detection + custom recognition (pdf_gen method)
            # Chinese detection model (ch_PP-OCRv4_det) provides LINE-LEVEL detection
            # Custom recognition model handles Korean text properly
            ocr_params = {
                "use_angle_cls": False,                    # Disable for speed
                "det_limit_side_len": 2000,                # Higher resolution for better line detection
                "det_db_thresh": 0.25,                     # Binarization threshold (낮출수록 더 많은 텍스트 감지)
                "det_db_box_thresh": 0.25,                 # Box confidence threshold (낮출수록 더 많은 박스 유지)
                "det_db_unclip_ratio": 2.0,                # CRITICAL: Higher value merges chars into lines (글자 분리 방지)
                "rec_batch_num": self.config.OCR_REC_BATCH_NUM,
            }

            logger.info(f"Using device: {'GPU' if self.config.OCR_USE_GPU else 'CPU'}")

            # Use custom recognition model if available
            if self.config.OCR_MODEL_DIR.exists():
                ocr_params["text_recognition_model_dir"] = str(self.config.OCR_MODEL_DIR)
                logger.info(f"Using custom recognition model: {self.config.OCR_MODEL_DIR}")
                logger.info("Using Chinese detection + custom recognition (Korean support)")

                # CRITICAL: DO NOT set rec_char_dict_path (same as pdf_gen)
                # Let PaddleOCR use the model's internal character mapping
                # This allows the model to use its learned multilingual capabilities
                logger.info("NOT setting rec_char_dict_path - model uses internal char mapping")
            else:
                # No custom model: use default Chinese model
                ocr_params["lang"] = "ch"
                logger.info("Using default Chinese model (no custom model found)")

            ocr = PaddleOCR(**ocr_params)
            logger.info("PaddleOCR API initialized")
            logger.info("PaddleOCR model loaded successfully")
            return ocr

        except Exception as e:
            logger.error(f"Failed to initialize OCR model: {e}")
            raise

    def _preprocess_image(self, image_path: str) -> tuple[str, tuple[int, int]]:
        """
        Apply preprocessing to improve OCR accuracy

        IMPORTANT: Always preserves original image dimensions for coordinate consistency

        Returns:
            tuple: (preprocessed_image_path, original_size)
                   original_size is (width, height) of the original image
        """
        if not self.config.DENOISE_ENABLED and not self.config.UPSCALE_ENABLED and not self.config.CLAHE_ENABLED: 
            # Get original size even if no preprocessing
            img = cv2.imread(image_path)
            if img is not None:
                h, w = img.shape[:2]
                return image_path, (w, h)
            return image_path, (0, 0)

        try:
            image = cv2.imread(image_path, cv2.IMREAD_COLOR)
            if image is None:
                logger.warning(f"Failed to load image for preprocessing: {image_path}")
                return image_path, (0, 0)

            processed = image
            original_shape = image.shape[:2]  # (height, width)
            modified = False

            # Denoise
            if self.config.DENOISE_ENABLED:
                try:
                    processed = cv2.fastNlMeansDenoisingColored(
                        processed, None,
                        h=self.config.DENOISE_H,
                        hColor=self.config.DENOISE_H,
                        templateWindowSize=7,
                        searchWindowSize=21
                    )
                    modified = True
                    logger.debug("Applied denoising")
                except Exception as e:
                    logger.warning(f"Denoising failed: {e}")

            # Upscale
            if self.config.UPSCALE_ENABLED:
                try:
                    height, width = processed.shape[:2]
                    short_edge = min(height, width)

                    if short_edge < self.config.UPSCALE_MIN_EDGE:
                        scale = min(
                            self.config.UPSCALE_MAX_SCALE,
                            self.config.UPSCALE_MIN_EDGE / short_edge
                        )
                        if scale > 1.01:
                            new_size = (int(width * scale), int(height * scale))
                            processed = cv2.resize(processed, new_size, interpolation=cv2.INTER_CUBIC)
                            modified = True
                            logger.debug(f"Applied upscaling: scale={scale:.2f}")
                except Exception as e:
                    logger.warning(f"Upscaling failed: {e}")

            # CLAHE
            if self.config.CLAHE_ENABLED:
                try:
                    clahe = cv2.createCLAHE(
                        clipLimit=self.config.CLAHE_CLIP_LIMIT,
                        tileGridSize=self.config.CLAHE_TILE_GRID
                    )
                    lab = cv2.cvtColor(processed, cv2.COLOR_BGR2LAB)
                    l, a, b = cv2.split(lab)
                    l = clahe.apply(l)
                    lab = cv2.merge((l, a, b))
                    processed = cv2.cvtColor(lab, cv2.COLOR_LAB2BGR)
                    modified = True
                    logger.debug("Applied CLAHE")
                except Exception as e:
                    logger.warning(f"CLAHE failed: {e}")

            if not modified:
                orig_h, orig_w = original_shape
                return image_path, (orig_w, orig_h)

            # CRITICAL: Restore to original size for coordinate consistency
            # This ensures OCR bbox coordinates match the original image dimensions
            if processed.shape[:2] != original_shape:
                orig_h, orig_w = original_shape
                logger.debug(f"Restoring to original size: {orig_w}x{orig_h}")
                processed = cv2.resize(processed, (orig_w, orig_h), interpolation=cv2.INTER_LINEAR)

            # Save preprocessed image
            temp_file = tempfile.NamedTemporaryFile(suffix='.png', delete=False)
            temp_path = temp_file.name
            temp_file.close()

            cv2.imwrite(temp_path, processed)
            orig_h, orig_w = original_shape
            logger.info(f"Preprocessing completed: {Path(image_path).name} (restored to {orig_w}x{orig_h})")
            return temp_path, (orig_w, orig_h)

        except Exception as e:
            logger.warning(f"Preprocessing failed: {e}")
            # Try to get original size even on error
            try:
                img = cv2.imread(image_path)
                if img is not None:
                    h, w = img.shape[:2]
                    return image_path, (w, h)
            except:
                pass
            return image_path, (0, 0)

    def recognize(self, image_path: str) -> Optional[List[Dict]]:
        """
        Perform OCR using PaddleOCR's ocr() method

        Args:
            image_path: Path to image file

        Returns:
            List of OCR results with bbox, text, and confidence
            bbox coordinates match original image dimensions
        """
        temp_path = None
        try:
            # Preprocess image (will be resized back to original dimensions)
            preprocessed_path, original_size = self._preprocess_image(image_path)
            if preprocessed_path != image_path:
                temp_path = preprocessed_path

            logger.info(f"Performing OCR on: {Path(image_path).name}")

            # Perform OCR using the ocr() method (PaddleOCR 3.x - no cls parameter)
            # This returns: List[List[Tuple[bbox_4points, Tuple[text, confidence]]]]
            results = self.ocr.ocr(preprocessed_path)

            if not results or len(results) == 0:
                logger.info("No text detected")
                return None

            # PaddleOCR 3.x returns OCRResult object with json attribute
            ocr_result = results[0]
            if not ocr_result:
                logger.info("No text detected on page")
                return None

            # Extract data from OCRResult.json
            # PaddleOCR 3.x wraps the result in a 'res' key
            result_data = ocr_result.json if hasattr(ocr_result, 'json') else {}

            # DEBUG: Log raw result structure
            logger.debug(f"RAW OCR RESULT TYPE: {type(ocr_result)}")
            logger.debug(f"RAW OCR RESULT JSON KEYS: {result_data.keys() if isinstance(result_data, dict) else 'NOT A DICT'}")

            # Check if data is wrapped in 'res' key
            if 'res' in result_data and isinstance(result_data['res'], dict):
                result_data = result_data['res']

            rec_texts = result_data.get('rec_texts', [])
            rec_scores = result_data.get('rec_scores', [])
            rec_boxes = result_data.get('rec_boxes', [])
            dt_polys = result_data.get('dt_polys', [])

            # DEBUG: Log first few items
            if rec_texts and dt_polys:
                logger.debug(f"FIRST TEXT: '{rec_texts[0]}'")
                logger.debug(f"FIRST DT_POLY: {dt_polys[0]}")
                logger.debug(f"FIRST REC_BOX: {rec_boxes[0] if rec_boxes else 'NONE'}")

            if not rec_texts:
                logger.info("No text detected")
                return None

            logger.info(f"Detected {len(rec_texts)} text regions")

            # Convert to standard format
            ocr_blocks = []
            for i in range(len(rec_texts)):
                try:
                    text = rec_texts[i]
                    score = rec_scores[i] if i < len(rec_scores) else 0.0
                    polygon = dt_polys[i] if i < len(dt_polys) else None
                    bbox = self._polygon_to_bbox(polygon)

                    # Fallback to rec_boxes if polygon data unavailable
                    if not bbox and i < len(rec_boxes):
                        bbox = rec_boxes[i]

                    # DEBUG: Log raw OCR output to check if spaces are present
                    logger.debug(f"RAW OCR OUTPUT [{i}]: '{text}' (len={len(text)}, has_space={' ' in text})")

                    if not text or not text.strip():
                        continue

                    if not bbox or len(bbox) < 4:
                        logger.warning(f"Invalid bbox at index {i}: {bbox}")
                        continue

                    ocr_blocks.append({
                        'bbox': bbox,
                        'text': text.strip(),  # Only strip leading/trailing spaces, not internal ones
                        'score': float(score)
                    })

                except Exception as e:
                    logger.warning(f"Failed to parse result at index {i}: {e}")
                    continue

            logger.info(f"OCR completed: {len(ocr_blocks)} text blocks found")

            # 인접 문자 블록 병합: 같은 줄에서 너무 잘게 쪼개진 블록을 하나로 합침
            # (예: "주"+"소" → "주소", "서울시"+"강남구" → "서울시강남구")
            ocr_blocks = self._merge_fragmented_blocks(ocr_blocks)
            logger.info(f"After merge: {len(ocr_blocks)} text blocks")

            return ocr_blocks if ocr_blocks else None

        except Exception as e:
            logger.error(f"OCR failed: {e}")
            raise

        finally:
            # Clean up temporary preprocessed image
            if temp_path and os.path.exists(temp_path):
                try:
                    os.unlink(temp_path)
                except Exception as e:
                    logger.debug(f"Failed to clean up temp file: {e}")

    @staticmethod
    def _merge_fragmented_blocks(blocks: List[Dict]) -> List[Dict]:
        """
        같은 줄에 있는 인접 텍스트 블록을 병합한다.

        OCR이 "주소"를 "주"+"소"처럼 글자 단위로 쪼개는 문제를 해결.
        기준:
          - y 중심 차이 < 블록 높이의 60% → 같은 줄로 판단
          - 수평 간격 < 글자 높이의 1.2배 → 병합 대상
        병합 시 텍스트는 공백 없이 이어 붙이고, bbox는 합집합으로 확장.
        """
        if len(blocks) <= 1:
            return blocks

        def y_center(b):
            return (b['bbox'][1] + b['bbox'][3]) / 2

        # y 중심 → x 시작 순으로 정렬
        sorted_blocks = sorted(blocks, key=lambda b: (y_center(b), b['bbox'][0]))

        merged = []
        used = [False] * len(sorted_blocks)

        for i, blk in enumerate(sorted_blocks):
            if used[i]:
                continue

            cur_bbox = list(blk['bbox'])
            cur_text = blk['text']
            cur_score = blk['score']
            h_i = cur_bbox[3] - cur_bbox[1]
            yc_i = y_center(blk)

            for j in range(i + 1, len(sorted_blocks)):
                if used[j]:
                    continue
                cand = sorted_blocks[j]
                c_bbox = cand['bbox']
                h_j = c_bbox[3] - c_bbox[1]
                yc_j = y_center(cand)

                h_ref = max(h_i, h_j, 1)

                # 같은 줄 판단: y 중심 거리 < 블록 높이 60%
                if abs(yc_i - yc_j) > h_ref * 0.6:
                    break  # y 기준 정렬이므로 이후 블록은 더 멀다

                # 수평 간격: 현재 블록 오른쪽 끝 ~ 후보 블록 왼쪽 시작
                gap = c_bbox[0] - cur_bbox[2]

                # 간격이 음수(겹침)이거나 글자 높이 1.2배 이내일 때 병합
                if -h_ref * 0.3 <= gap <= h_ref * 1.2:
                    # 두 블록 사이에 의미 있는 공백이 있으면 스페이스 삽입
                    sep = ' ' if gap > h_ref * 0.3 else ''
                    cur_text = cur_text + sep + cand['text']
                    cur_bbox[2] = max(cur_bbox[2], c_bbox[2])
                    cur_bbox[1] = min(cur_bbox[1], c_bbox[1])
                    cur_bbox[3] = max(cur_bbox[3], c_bbox[3])
                    cur_score = min(cur_score, cand['score'])
                    used[j] = True

            merged.append({'bbox': cur_bbox, 'text': cur_text, 'score': cur_score})

        return merged

    @staticmethod
    def _polygon_to_bbox(polygon):
        """Convert PaddleOCR polygon output to [x1, y1, x2, y2] bbox"""
        if not polygon:
            return None

        try:
            if isinstance(polygon[0], (list, tuple)):
                xs = [float(pt[0]) for pt in polygon if pt and len(pt) >= 2]
                ys = [float(pt[1]) for pt in polygon if pt and len(pt) >= 2]
            else:
                # Flattened list [x1, y1, ..., x4, y4]
                xs = [float(polygon[i]) for i in range(0, len(polygon), 2)]
                ys = [float(polygon[i]) for i in range(1, len(polygon), 2)]

            if not xs or not ys:
                return None

            return [min(xs), min(ys), max(xs), max(ys)]
        except Exception:
            return None
