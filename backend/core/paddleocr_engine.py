"""
Pure PaddleOCR Engine for tight line-level text detection
Replaces PPStructureV3 for better line-level accuracy
"""
import logging
from pathlib import Path
from typing import List, Dict, Optional
import numpy as np
from PIL import Image

try:
    from paddleocr import PaddleOCR
    PADDLEOCR_AVAILABLE = True
except ImportError:
    PADDLEOCR_AVAILABLE = False
    logging.warning("PaddleOCR not available")

from config import Config

logger = logging.getLogger(__name__)


class PaddleOCREngine:
    """
    Pure PaddleOCR engine optimized for LINE-LEVEL text detection

    Benefits over PPStructure:
    - Tight bounding boxes (avg height ~60px vs ~85px)
    - Line-level detection (137 lines vs 83 blocks)
    - Less overlap between adjacent lines
    - Faster (no layout detection overhead)

    Trade-offs:
    - No automatic layout detection
    - No reading order for complex multi-column layouts
    - Requires manual sorting for reading order
    """

    def __init__(self, use_custom_recognition: bool = True):
        """
        Initialize PaddleOCR engine

        Args:
            use_custom_recognition: Use custom recognition model (best_0828)
        """
        if not PADDLEOCR_AVAILABLE:
            raise RuntimeError("PaddleOCR is not installed")

        self.config = Config
        self.use_custom_recognition = use_custom_recognition
        self.ocr = self._initialize_ocr()
        logger.info("PaddleOCR Engine initialized successfully")

    def _initialize_ocr(self):
        """Initialize PaddleOCR with tight line-level detection parameters"""
        try:
            ocr_params = {
                # Disable unnecessary features
                "use_textline_orientation": False,
                "lang": "korean",

                # Detection parameters - OPTIMIZED for TIGHT LINE-LEVEL boxes
                "text_det_limit_side_len": self.config.OCR_DETECTION_LIMIT,
                "text_det_thresh": 0.3,          # Default - reduce noise
                "text_det_box_thresh": 0.6,      # Default - higher quality
                "text_det_unclip_ratio": 1.1,    # TIGHT boxes (was 1.5)

                # Recognition
                "text_recognition_batch_size": self.config.OCR_REC_BATCH_NUM,

                # Device - use config setting
                "device": "gpu" if self.config.OCR_USE_GPU else "cpu",

                # CPU threads for faster processing
                "cpu_threads": self.config.OCR_CPU_THREADS
            }

            # Use custom recognition model if available
            if self.use_custom_recognition and self.config.OCR_MODEL_DIR.exists():
                ocr_params["text_recognition_model_dir"] = str(self.config.OCR_MODEL_DIR)
                logger.info(f"Using custom recognition model: {self.config.OCR_MODEL_DIR}")
            else:
                # Use default Korean model
                ocr_params["text_recognition_model_name"] = "PP-OCRv5_server_rec"
                logger.info("Using default PP-OCRv5 recognition model")

            ocr = PaddleOCR(**ocr_params)
            logger.info("PaddleOCR initialized with tight line-level detection")

            return ocr

        except Exception as e:
            logger.error(f"Failed to initialize PaddleOCR: {e}")
            raise

    def analyze(self, image_path: str) -> Dict:
        """
        Perform OCR analysis with tight line-level detection

        Args:
            image_path: Path to image file

        Returns:
            Dict with OCR results in standard format
        """
        try:
            logger.info(f"Analyzing image with PaddleOCR: {Path(image_path).name}")

            # Run PaddleOCR
            result = self.ocr.predict(image_path)

            if not result or len(result) == 0:
                logger.warning("No results from PaddleOCR")
                return {
                    "ocr_blocks": [],
                    "layout_info": {},
                    "page_info": {}
                }

            # Process results
            processed_data = self._process_results(result, image_path)

            logger.info(f"PaddleOCR analysis complete: {len(processed_data['ocr_blocks'])} blocks")
            return processed_data

        except Exception as e:
            logger.error(f"PaddleOCR analysis failed: {e}")
            raise

    def _process_results(self, results, image_path: str) -> Dict:
        """
        Convert PaddleOCR results to standard format

        Args:
            results: PaddleOCR result list
            image_path: Path to source image

        Returns:
            Dict with ocr_blocks, layout_info, page_info
        """
        try:
            # Get image dimensions
            with Image.open(image_path) as img:
                img_width, img_height = img.size

            # Extract detection results
            page_result = results[0]
            dt_polys = page_result.get('dt_polys', [])
            rec_texts = page_result.get('rec_texts', [])
            rec_scores = page_result.get('rec_scores', [])

            ocr_blocks = []

            # Process each detected line
            for idx in range(len(dt_polys)):
                poly = dt_polys[idx]
                text = rec_texts[idx] if idx < len(rec_texts) else ""
                score = rec_scores[idx] if idx < len(rec_scores) else 0.0

                # Skip empty or low-confidence results
                if not text.strip() or score < 0.5:
                    continue

                # Convert polygon to bbox
                x_coords = [p[0] for p in poly]
                y_coords = [p[1] for p in poly]
                x1, y1 = min(x_coords), min(y_coords)
                x2, y2 = max(x_coords), max(y_coords)

                # Create OCR block
                ocr_block = {
                    "text": text,
                    "bbox": [x1, y1, x2, y2],
                    "polygon": poly,
                    "confidence": float(score),
                    "block_type": "text",
                    "reading_order": idx  # Simple top-to-bottom order
                }

                ocr_blocks.append(ocr_block)

            # Sort by vertical position (top to bottom, then left to right)
            ocr_blocks.sort(key=lambda b: (b['bbox'][1], b['bbox'][0]))

            # Update reading order after sort
            for idx, block in enumerate(ocr_blocks):
                block['reading_order'] = idx

            return {
                "ocr_blocks": ocr_blocks,
                "layout_info": {
                    "regions": [],
                    "reading_order_method": "top-to-bottom"
                },
                "page_info": {
                    "width": img_width,
                    "height": img_height,
                    "total_blocks": len(ocr_blocks)
                }
            }

        except Exception as e:
            logger.error(f"Failed to process PaddleOCR results: {e}")
            raise

    def recognize(self, image_path: str) -> List[Dict]:
        """
        Recognize text from image (compatibility method for OCREngine interface)

        Args:
            image_path: Path to image file

        Returns:
            List of OCR blocks (matching OCREngine interface)
        """
        result = self.analyze(image_path)
        return result.get('ocr_blocks', [])
