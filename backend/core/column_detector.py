"""
Multi-column layout detection
"""
import logging
from typing import List, Dict, Optional
import math

logger = logging.getLogger(__name__)


class ColumnDetector:
    """Detects multi-column layout in OCR results"""

    @staticmethod
    def detect_columns(
        ocr_results: List[Dict],
        page_width: float,
        min_blocks: int = 6,
        min_gap_ratio: float = 0.12,
        min_side_ratio: float = 0.25
    ) -> Dict:
        """
        Detect if the page has multiple columns

        Args:
            ocr_results: List of OCR blocks with bbox
            page_width: Width of the page
            min_blocks: Minimum number of blocks required
            min_gap_ratio: Minimum gap ratio to consider double column
            min_side_ratio: Minimum ratio of blocks on each side

        Returns:
            Dictionary with column detection results
        """
        if not ocr_results or len(ocr_results) < min_blocks:
            return {
                'is_multi_column': False,
                'is_double_column': False,
                'column_count': 1,
                'column_boundary': None,
                'confidence': 0.0,
                'method': 'insufficient_blocks'
            }

        try:
            # Process blocks
            processed_blocks = []
            min_x = math.inf
            max_x = -math.inf
            max_width = 0.0

            for block in ocr_results:
                bbox = block.get('bbox')
                if not bbox or len(bbox) != 4:
                    continue

                x1, y1, x2, y2 = bbox
                if x2 <= x1 or y2 <= y1:
                    continue

                center_x = (x1 + x2) / 2.0
                width = x2 - x1

                processed_blocks.append({
                    'center_x': center_x,
                    'width': width,
                    'bbox': bbox
                })

                min_x = min(min_x, x1)
                max_x = max(max_x, x2)
                max_width = max(max_width, width)

            if len(processed_blocks) < min_blocks:
                return {
                    'is_multi_column': False,
                    'is_double_column': False,
                    'column_count': 1,
                    'column_boundary': None,
                    'confidence': 0.0,
                    'method': 'insufficient_valid_blocks'
                }

            # Remove overly wide blocks (e.g., centered titles)
            narrow_blocks = [b for b in processed_blocks if b['width'] <= page_width * 0.75]
            if len(narrow_blocks) >= max(min_blocks, len(processed_blocks) // 2):
                centers_source = narrow_blocks
            else:
                centers_source = processed_blocks

            # Find the largest gap between center X coordinates
            centers = sorted(b['center_x'] for b in centers_source)
            if len(centers) < 2:
                return {
                    'is_multi_column': False,
                    'is_double_column': False,
                    'column_count': 1,
                    'column_boundary': None,
                    'confidence': 0.0,
                    'method': 'insufficient_centers'
                }

            gaps = [centers[i + 1] - centers[i] for i in range(len(centers) - 1)]
            max_gap = max(gaps)
            gap_index = gaps.index(max_gap)
            boundary = (centers[gap_index] + centers[gap_index + 1]) / 2.0
            gap_ratio = max_gap / page_width if page_width > 0 else 0.0

            # Check if gap is significant enough
            if gap_ratio < min_gap_ratio:
                return {
                    'is_multi_column': False,
                    'is_double_column': False,
                    'column_count': 1,
                    'column_boundary': None,
                    'confidence': 0.0,
                    'method': 'gap_too_small',
                    'details': {'gap_ratio': round(gap_ratio, 3)}
                }

            # Split blocks by boundary
            left_blocks = [b for b in processed_blocks if b['center_x'] < boundary]
            right_blocks = [b for b in processed_blocks if b['center_x'] >= boundary]

            total_blocks = len(left_blocks) + len(right_blocks)
            if total_blocks < min_blocks:
                return {
                    'is_multi_column': False,
                    'is_double_column': False,
                    'column_count': 1,
                    'column_boundary': None,
                    'confidence': 0.0,
                    'method': 'insufficient_split_blocks'
                }

            # Check if both sides have enough blocks
            left_ratio = len(left_blocks) / total_blocks if total_blocks > 0 else 0.0
            right_ratio = len(right_blocks) / total_blocks if total_blocks > 0 else 0.0

            if left_ratio < min_side_ratio or right_ratio < min_side_ratio:
                return {
                    'is_multi_column': False,
                    'is_double_column': False,
                    'column_count': 1,
                    'column_boundary': None,
                    'confidence': 0.0,
                    'method': 'unbalanced_sides',
                    'details': {
                        'left_ratio': round(left_ratio, 3),
                        'right_ratio': round(right_ratio, 3)
                    }
                }

            # Calculate confidence
            balance_score = 1.0 - abs(left_ratio - right_ratio)
            confidence = min(0.95, max(0.4,
                gap_ratio * 0.6 +
                min(left_ratio, right_ratio) * 0.4 +
                balance_score * 0.2
            ))

            logger.info(
                f"Double-column detected: boundary={boundary:.1f}, "
                f"gap_ratio={gap_ratio:.3f}, left={len(left_blocks)}, right={len(right_blocks)}, "
                f"confidence={confidence:.3f}"
            )

            return {
                'is_multi_column': True,
                'is_double_column': True,
                'column_count': 2,
                'column_boundary': boundary,
                'confidence': round(confidence, 3),
                'method': 'gap_analysis',
                'details': {
                    'gap_ratio': round(gap_ratio, 3),
                    'left_ratio': round(left_ratio, 3),
                    'right_ratio': round(right_ratio, 3),
                    'left_blocks': len(left_blocks),
                    'right_blocks': len(right_blocks),
                    'total_blocks': total_blocks
                }
            }

        except Exception as e:
            logger.error(f"Column detection failed: {e}")
            return {
                'is_multi_column': False,
                'is_double_column': False,
                'column_count': 1,
                'column_boundary': None,
                'confidence': 0.0,
                'method': 'error',
                'error': str(e)
            }

    @staticmethod
    def assign_column_labels(ocr_results: List[Dict], column_info: Dict) -> List[Dict]:
        """
        Assign column labels to OCR results

        Args:
            ocr_results: List of OCR blocks
            column_info: Column detection result

        Returns:
            OCR results with column labels added
        """
        if not column_info.get('is_double_column'):
            # Single column - no labels needed
            for block in ocr_results:
                block['column'] = None
            return ocr_results

        boundary = column_info['column_boundary']

        for block in ocr_results:
            bbox = block.get('bbox')
            if bbox and len(bbox) == 4:
                center_x = (bbox[0] + bbox[2]) / 2.0
                block['column'] = 'left' if center_x < boundary else 'right'
            else:
                block['column'] = None

        return ocr_results

    @staticmethod
    def clamp_to_column_bounds(ocr_results: List[Dict], column_info: Dict, page_width: Optional[float] = None) -> List[Dict]:
        """Trim bbox coordinates so each block stays inside its column"""
        if not column_info or not column_info.get('is_double_column'):
            return ocr_results

        boundary = column_info.get('column_boundary')
        if boundary is None:
            return ocr_results

        for block in ocr_results:
            bbox = block.get('bbox')
            if not bbox or len(bbox) != 4:
                continue

            x1, y1, x2, y2 = bbox
            center_x = (x1 + x2) / 2.0

            if center_x < boundary and x2 > boundary:
                x2 = boundary
            elif center_x >= boundary and x1 < boundary:
                x1 = boundary

            # Clamp within page bounds if provided
            if page_width:
                x1 = max(0.0, min(x1, page_width))
                x2 = max(0.0, min(x2, page_width))

            block['bbox'] = [x1, y1, x2, y2]

        return ocr_results
