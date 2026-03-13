"""
PP-Structure Engine for advanced layout analysis and reading order detection
"""
import logging
from pathlib import Path
from typing import List, Dict, Optional, Tuple
import tempfile
import os

try:
    from paddleocr import PPStructureV3
    PPSTRUCTURE_AVAILABLE = True
except ImportError:
    PPSTRUCTURE_AVAILABLE = False
    logging.warning("PPStructureV3 not available")

from config import Config

logger = logging.getLogger(__name__)


class PPStructureEngine:
    """
    Advanced OCR engine using PP-StructureV3 for:
    - Accurate layout detection (20+ categories)
    - Multi-column reading order recovery
    - Support for complex layouts (news, vertical text, etc.)
    - Integration with custom recognition models (best_0828)
    """

    def __init__(self, use_custom_recognition: bool = True):
        """
        Initialize PP-Structure engine

        Args:
            use_custom_recognition: Use custom recognition model (best_0828)
        """
        if not PPSTRUCTURE_AVAILABLE:
            raise RuntimeError("PPStructureV3 is not installed")

        self.config = Config
        self.use_custom_recognition = use_custom_recognition
        self.pipeline = self._initialize_pipeline()
        logger.info("PP-Structure Engine initialized successfully")

    def _initialize_pipeline(self):
        """Initialize PP-StructureV3 pipeline with optimal settings"""
        try:
            # Pipeline parameters
            pipeline_params = {
                # Layout detection - use high-accuracy model
                "layout_detection_model_name": "PP-DocLayout-L",  # 90.4% mAP
                "layout_threshold": 0.5,  # Confidence threshold for layout detection

                # Text detection - use server model for better accuracy
                "text_detection_model_name": "PP-OCRv5_server_det",
                "text_det_limit_side_len": self.config.OCR_DETECTION_LIMIT,
                "text_det_thresh": 0.3,
                "text_det_box_thresh": 0.6,

                # Text recognition - use custom model if available
                "text_recognition_batch_size": self.config.OCR_REC_BATCH_NUM,
                "text_rec_score_thresh": 0.5,

                # Feature flags - disable unnecessary modules for speed
                "use_doc_orientation_classify": False,  # Skip if images are pre-oriented
                "use_doc_unwarping": False,  # Skip for clean scans
                "use_textline_orientation": False,  # Skip for horizontal text
                "use_table_recognition": False,  # Disable if not needed
                "use_formula_recognition": False,  # Disable if not needed
                "use_chart_recognition": False,  # Disable if not needed
                "use_seal_recognition": False,  # Disable if not needed

                # Device - use config setting
                "device": "gpu" if self.config.OCR_USE_GPU else "cpu",

                # CPU threads for faster processing
                "cpu_threads": self.config.OCR_CPU_THREADS
            }

            # Use custom recognition model if available
            if self.use_custom_recognition and self.config.OCR_MODEL_DIR.exists():
                pipeline_params["text_recognition_model_dir"] = str(self.config.OCR_MODEL_DIR)
                logger.info(f"Using custom recognition model: {self.config.OCR_MODEL_DIR}")
            else:
                # Use default model with Korean support
                pipeline_params["text_recognition_model_name"] = "PP-OCRv5_server_rec"
                logger.info("Using default PP-OCRv5 recognition model")

            pipeline = PPStructureV3(**pipeline_params)
            logger.info("PP-StructureV3 pipeline initialized")

            return pipeline

        except Exception as e:
            logger.error(f"Failed to initialize PP-Structure pipeline: {e}")
            raise

    def analyze(self, image_path: str) -> Dict:
        """
        Perform complete document analysis with layout and reading order

        Args:
            image_path: Path to image file

        Returns:
            Dictionary with:
            - ocr_blocks: List of text blocks in correct reading order
            - layout_info: Layout detection results
            - page_info: Page dimensions and metadata
        """
        try:
            logger.info(f"Analyzing document with PP-Structure: {Path(image_path).name}")

            # Run PP-Structure pipeline with minimal modules
            # CRITICAL: Disable unnecessary modules in predict() call
            results = self.pipeline.predict(
                image_path,
                use_doc_orientation_classify=False,  # Disable orientation classification
                use_doc_unwarping=False,             # Disable document unwarping
                use_textline_orientation=False,      # Disable textline orientation
                use_seal_recognition=False,          # Disable seal recognition
                use_table_recognition=False,         # Disable table recognition
                use_formula_recognition=False,       # Disable formula recognition
                use_chart_recognition=False,         # Disable chart recognition
                use_region_detection=False           # Disable region detection
            )

            if not results or len(list(results)) == 0:
                logger.warning("No results from PP-Structure")
                return {
                    "ocr_blocks": [],
                    "layout_info": {},
                    "page_info": {}
                }

            # Process results
            processed_data = self._process_results(results, image_path)
            logger.info(f"PP-Structure analysis complete: {len(processed_data['ocr_blocks'])} blocks")
            return processed_data

        except Exception as e:
            logger.error(f"PP-Structure analysis failed: {e}")
            raise

    def _process_results(self, results, image_path: str) -> Dict:
        """
        Convert PP-Structure results to our standard format

        PP-Structure automatically handles:
        - Layout detection (text, title, table, figure, etc.)
        - Reading order recovery (multi-column, complex layouts)
        - Coordinate normalization
        """
        try:
            # Get image dimensions
            from PIL import Image
            with Image.open(image_path) as img:
                img_width, img_height = img.size

            logger.info(f"Image dimensions: {img_width}x{img_height}px")

            ocr_blocks = []
            layout_regions = []

            results_list = list(results) if results else []
            logger.debug(f"Processing {len(results_list)} pages")

            # Process each result (PP-Structure returns list of page results)
            for page_idx, page_result in enumerate(results_list):

                # PPStructureV3 returns LayoutParsingResultV2 objects
                # Access overall_ocr_res for text detection results
                # LayoutParsingResultV2 is dict-like - access overall_ocr_res as dict key
                if 'overall_ocr_res' in page_result:
                    ocr_res = page_result['overall_ocr_res']

                    # OCRResult is dict-like - access data via keys
                    dt_polys = ocr_res.get('dt_polys', [])
                    rec_texts = ocr_res.get('rec_texts', [])
                    rec_scores = ocr_res.get('rec_scores', [])

                    logger.info(f"PPStructure detected {len(dt_polys)} text regions on page {page_idx}")

                    # Log Y coordinates of last few boxes to check if bottom is detected
                    if len(dt_polys) > 0:
                        last_boxes = []
                        for i in range(max(0, len(dt_polys) - 5), len(dt_polys)):
                            if i < len(dt_polys):
                                poly = dt_polys[i]
                                y_coords = [p[1] for p in poly] if poly is not None and len(poly) > 0 else []
                                if y_coords:
                                    max_y = max(y_coords)
                                    last_boxes.append(f"box{i}:y={max_y:.0f}")
                        logger.info(f"Last 5 boxes Y coords: {', '.join(last_boxes)}")

                    filtered_count = 0
                    # Process each detected text region
                    for idx in range(len(dt_polys)):
                        poly = dt_polys[idx]
                        text = rec_texts[idx] if idx < len(rec_texts) else ""
                        score = rec_scores[idx] if idx < len(rec_scores) else 0.0

                        # Skip empty or low-confidence results
                        # Lowered threshold from 0.5 to 0.3 to capture more bottom text
                        if not text or not text.strip() or score < 0.3:
                            filtered_count += 1
                            if filtered_count <= 5 or idx >= len(dt_polys) - 5:
                                logger.debug(f"Filtered box {idx}: score={score:.3f}, text='{text[:30]}'")
                            continue

                        # Convert polygon to bbox
                        if poly is not None and len(poly) >= 4:
                            x_coords = [p[0] for p in poly]
                            y_coords = [p[1] for p in poly]
                            x1, y1 = min(x_coords), min(y_coords)
                            x2, y2 = max(x_coords), max(y_coords)

                            # Create OCR block
                            ocr_block = {
                                "text": text,
                                "bbox": [x1, y1, x2, y2],
                                "confidence": float(score),
                                "score": float(score),  # For compatibility with OCREngine interface
                                "block_type": "text",
                                "reading_order": len(ocr_blocks)
                            }
                            ocr_blocks.append(ocr_block)

                    if filtered_count > 0:
                        logger.info(f"Filtered {filtered_count}/{len(dt_polys)} low-confidence boxes (threshold=0.3)")

            # Sort blocks by reading order (top-to-bottom, left-to-right)
            ocr_blocks.sort(key=lambda b: (b['bbox'][1], b['bbox'][0]))

            # Update reading order after sort
            for idx, block in enumerate(ocr_blocks):
                block['reading_order'] = idx

            # Log coverage statistics
            if ocr_blocks:
                max_y = max(b['bbox'][3] for b in ocr_blocks)
                coverage = (max_y / img_height) * 100
                logger.info(f"Final OCR coverage: {max_y:.0f}/{img_height}px ({coverage:.1f}%)")
                if coverage < 95:
                    logger.warning(f"Low coverage detected! Missing bottom {img_height - max_y:.0f}px ({100 - coverage:.1f}%)")
            else:
                logger.warning("No OCR blocks extracted!")

            return {
                "ocr_blocks": ocr_blocks,
                "layout_info": {
                    "regions": layout_regions
                },
                "page_info": {
                    "width": img_width,
                    "height": img_height
                }
            }

        except Exception as e:
            logger.error(f"Failed to process PP-Structure results: {e}")
            logger.exception(e)
            # Return empty result instead of failing
            return {
                "ocr_blocks": [],
                "layout_info": {},
                "page_info": {}
            }

    def _normalize_bbox(self, bbox) -> List[float]:
        """
        Normalize bbox to [x1, y1, x2, y2] format

        PP-Structure may return:
        - [x1, y1, x2, y2] (already normalized)
        - [[x1, y1], [x2, y2], [x3, y3], [x4, y4]] (4-point polygon)
        """
        if not bbox:
            return [0, 0, 0, 0]

        # Already in [x1, y1, x2, y2] format
        if len(bbox) == 4 and all(isinstance(x, (int, float)) for x in bbox):
            return [float(x) for x in bbox]

        # 4-point polygon format
        if len(bbox) == 4 and all(isinstance(pt, (list, tuple)) for pt in bbox):
            xs = [pt[0] for pt in bbox]
            ys = [pt[1] for pt in bbox]
            return [min(xs), min(ys), max(xs), max(ys)]

        # Fallback
        logger.warning(f"Unexpected bbox format: {bbox}")
        return [0, 0, 0, 0]

    def _analyze_column_layout(self, layout_regions: List[Dict], page_width: float) -> Dict:
        """
        Analyze column layout from detected regions

        PP-Structure already handles reading order, but we still need
        column info for downstream processing (e.g., UI display)
        """
        if not layout_regions or page_width == 0:
            return {
                'is_multi_column': False,
                'column_count': 1,
                'column_boundary': None
            }

        # Count text regions on left vs right half
        mid_x = page_width / 2
        left_count = 0
        right_count = 0

        for region in layout_regions:
            if region['type'] not in ['text', 'paragraph', 'title']:
                continue

            bbox = region['bbox']
            center_x = (bbox[0] + bbox[2]) / 2

            if center_x < mid_x:
                left_count += 1
            else:
                right_count += 1

        # If both sides have substantial content, it's multi-column
        total = left_count + right_count
        if total > 0:
            left_ratio = left_count / total
            is_multi_column = (0.3 < left_ratio < 0.7) and total >= 6
        else:
            is_multi_column = False

        return {
            'is_multi_column': is_multi_column,
            'is_double_column': is_multi_column,
            'column_count': 2 if is_multi_column else 1,
            'column_boundary': mid_x if is_multi_column else None,
            'method': 'pp_structure_analysis'
        }

    def recognize(self, image_path: str) -> List[Dict]:
        """
        Convenience method matching OCREngine interface

        Returns:
            List of OCR blocks (matching OCREngine interface)
        """
        result = self.analyze(image_path)
        return result.get('ocr_blocks', [])
