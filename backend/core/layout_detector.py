"""
Layout Detection Module - PP-DocLayout-L with object_detection pipeline
Detects semantic layout regions (title, text, list, figure, table, etc.)
"""
import logging
from typing import List, Dict, Optional
import numpy as np

logger = logging.getLogger(__name__)

try:
    from paddlex import create_pipeline
    PADDLEX_AVAILABLE = True
except ImportError:
    PADDLEX_AVAILABLE = False
    logger.warning("PaddleX not available, layout detection will be disabled")


class LayoutDetector:
    """
    Layout detector using PP-DocLayout-L with object_detection pipeline (lightweight)

    Detects semantic regions:
    - title: Document titles, headings
    - text: Body text paragraphs
    - list: Bullet/numbered lists
    - figure: Images, diagrams
    - table: Tables
    - equation: Mathematical formulas
    - reference: Citations, references
    """

    # Layout type priority for reading order (higher = earlier)
    LAYOUT_PRIORITY = {
        'title': 100,
        'text': 50,
        'list': 40,
        'table': 30,
        'figure': 20,
        'equation': 10,
        'reference': 5,
    }

    def __init__(self, model_name: str = "PP-DocLayout-L", device: str = "cpu"):
        if not PADDLEX_AVAILABLE:
            raise RuntimeError("PaddleX is required for layout detection")

        self.model_name = model_name
        self.device = device
        self.model = None

        logger.info(f"Initializing LayoutDetector with {model_name}")

    def _lazy_load(self):
        """Lazy load model on first use"""
        if self.model is None:
            logger.info(f"Loading layout detection model: {self.model_name}")
            try:
                # Import create_model instead of create_pipeline for direct model loading
                from paddlex import create_model

                # Load PP-DocLayout-L model directly (not through pipeline)
                self.model = create_model(
                    model_name=self.model_name,
                    device=self.device
                )
                logger.info(f"Layout detection model {self.model_name} loaded successfully")
                logger.debug(f"Loaded model: {self.model_name} on {self.device}")
            except Exception as e:
                logger.error(f"Failed to load layout detection model: {e}")
                raise

    def detect(self, image_path: str) -> List[Dict]:
        """
        Detect layout regions in image using PP-DocLayout-L

        Args:
            image_path: Path to image file

        Returns:
            List of layout regions with:
            - bbox: [x1, y1, x2, y2]
            - type: Layout type (title, text, list, figure, table, etc.)
            - score: Confidence score
        """
        self._lazy_load()

        try:
            # Run layout detection
            results = list(self.model.predict(image_path))

            if not results:
                logger.warning("Layout detection returned no results")
                return []

            result = results[0]  # Get first result

            logger.debug(f"Layout result type: {type(result)}")

            layout_regions = []

            # object_detection pipeline returns dict with 'boxes' as list of dicts
            if isinstance(result, dict):
                boxes = result.get('boxes', [])

                logger.debug(f"Layout boxes count: {len(boxes) if boxes else 0}")

                for i, box_dict in enumerate(boxes):
                    if not isinstance(box_dict, dict):
                        logger.warning(f"Box {i} is not a dict: {box_dict}, skipping")
                        continue

                    # Extract label from dict
                    label = box_dict.get('label', 'text')
                    score = box_dict.get('score', 1.0)
                    coordinate = box_dict.get('coordinate', None)

                    if coordinate is None:
                        logger.warning(f"Box {i} has no coordinate, skipping")
                        continue

                    # Normalize label name (lowercase)
                    if isinstance(label, str):
                        label = label.lower()
                    else:
                        label = 'text'

                    # Convert coordinate to list of floats
                    if hasattr(coordinate, 'tolist'):
                        coordinate = coordinate.tolist()

                    bbox = [float(x) for x in coordinate[:4]]  # [x1, y1, x2, y2]

                    logger.debug(f"Layout box {i}: label={label}, score={score:.2f}")

                    layout_regions.append({
                        'bbox': bbox,  # [x1, y1, x2, y2]
                        'type': label,
                        'score': float(score),
                        'priority': self.LAYOUT_PRIORITY.get(label, 0)
                    })

            logger.info(f"Detected {len(layout_regions)} layout regions")
            return layout_regions

        except Exception as e:
            logger.error(f"Layout detection failed: {e}", exc_info=True)
            return []

    def _get_label_name(self, cls_id: int) -> str:
        """Map class ID to label name"""
        # PP-DocLayout-L class mapping
        LABEL_MAP = {
            0: 'title',
            1: 'text',
            2: 'list',
            3: 'figure',
            4: 'table',
            5: 'equation',
            6: 'reference',
        }
        return LABEL_MAP.get(cls_id, 'text')

    def match_ocr_to_layout(
        self,
        ocr_blocks: List[Dict],
        page_width: int,
        page_height: int,
        layout_regions: List[Dict] = None,
        iou_threshold: float = 0.5
    ) -> List[Dict]:
        """
        Match OCR blocks to layout regions by containment

        Strategy: If an OCR bbox is contained within a layout region,
        assign that region's type to the OCR block.

        Args:
            ocr_blocks: List of OCR results with bbox
            page_width: Page width (unused, kept for compatibility)
            page_height: Page height (unused, kept for compatibility)
            layout_regions: List of layout regions (if None, detect first)
            iou_threshold: Unused (kept for API compatibility)

        Returns:
            OCR blocks with added 'layout_type' and 'layout_priority' fields
        """
        # If no layout regions provided, we need image path to detect
        # In this case, layout_regions should be pre-detected
        if not layout_regions:
            logger.warning("No layout regions provided, cannot match OCR blocks")
            # Assign default 'text' to all blocks
            for ocr_block in ocr_blocks:
                ocr_block['layout_type'] = 'text'
                ocr_block['layout_priority'] = self.LAYOUT_PRIORITY['text']
                ocr_block['layout_score'] = 1.0
            return ocr_blocks

        logger.debug(f"Matching {len(ocr_blocks)} OCR blocks to {len(layout_regions)} layout regions")

        # Sort layout regions by area (largest first) to prioritize more specific regions
        layout_regions_sorted = sorted(layout_regions, key=lambda r: self._calculate_area(r['bbox']), reverse=True)

        matched_count = 0
        for ocr_block in ocr_blocks:
            ocr_bbox = ocr_block['bbox']

            # Find the smallest layout region that contains this OCR block
            best_match = None
            best_area = float('inf')

            for region in layout_regions_sorted:
                layout_bbox = region['bbox']

                # Check if OCR bbox is contained within layout region
                if self._is_contained(ocr_bbox, layout_bbox):
                    area = self._calculate_area(layout_bbox)
                    # Choose the smallest containing region (most specific)
                    if area < best_area:
                        best_area = area
                        best_match = region

            # Assign layout type
            if best_match:
                ocr_block['layout_type'] = best_match['type']
                ocr_block['layout_priority'] = best_match['priority']
                ocr_block['layout_score'] = best_match['score']
                matched_count += 1
            else:
                # Default to text if no containing region found
                ocr_block['layout_type'] = 'text'
                ocr_block['layout_priority'] = self.LAYOUT_PRIORITY['text']
                ocr_block['layout_score'] = 1.0

        logger.debug(f"Matched {matched_count}/{len(ocr_blocks)} OCR blocks to layout regions")
        return ocr_blocks

    def _is_contained(self, bbox1: List[float], bbox2: List[float]) -> bool:
        """
        Check if bbox1 is contained within bbox2

        Args:
            bbox1: [x1, y1, x2, y2] - smaller bbox (OCR text)
            bbox2: [x1, y1, x2, y2] - larger bbox (layout region)

        Returns:
            True if bbox1 is fully contained within bbox2
        """
        x1_min, y1_min, x1_max, y1_max = bbox1
        x2_min, y2_min, x2_max, y2_max = bbox2

        # Check if all corners of bbox1 are inside bbox2
        return (x1_min >= x2_min and x1_max <= x2_max and
                y1_min >= y2_min and y1_max <= y2_max)

    def _calculate_area(self, bbox: List[float]) -> float:
        """Calculate area of a bbox"""
        x1, y1, x2, y2 = bbox
        return (x2 - x1) * (y2 - y1)

    def _calculate_iou(self, bbox1: List[float], bbox2: List[float]) -> float:
        """Calculate Intersection over Union between two bboxes"""
        x1_min, y1_min, x1_max, y1_max = bbox1
        x2_min, y2_min, x2_max, y2_max = bbox2

        # Calculate intersection
        x_left = max(x1_min, x2_min)
        y_top = max(y1_min, y2_min)
        x_right = min(x1_max, x2_max)
        y_bottom = min(y1_max, y2_max)

        if x_right < x_left or y_bottom < y_top:
            return 0.0

        intersection = (x_right - x_left) * (y_bottom - y_top)

        # Calculate union
        area1 = (x1_max - x1_min) * (y1_max - y1_min)
        area2 = (x2_max - x2_min) * (y2_max - y2_min)
        union = area1 + area2 - intersection

        if union == 0:
            return 0.0

        return intersection / union


def create_layout_detector(model_name: str = "PP-DocLayout-L", device: str = "cpu") -> LayoutDetector:
    """Factory function to create layout detector"""
    return LayoutDetector(model_name=model_name, device=device)
