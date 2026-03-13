"""
Precision Text Scaler for Searchable PDF Generation

Core principle: Scale text to EXACTLY fit the OCR detected bbox,
ensuring perfect alignment between invisible text layer and visible image.
"""
import logging
from typing import Tuple, Optional
from reportlab.pdfbase import pdfmetrics

logger = logging.getLogger(__name__)


class PrecisionTextScaler:
    """
    텍스트를 bbox 크기에 정확히 맞추는 스케일러

    핵심 로직:
    1. ReportLab의 실제 폰트 메트릭을 사용하여 텍스트 크기 측정
    2. 이진 탐색으로 bbox width에 정확히 맞는 폰트 사이즈 계산
    3. bbox height 제약 조건 검증
    4. 최소한의 보정만 수행
    """

    def __init__(self):
        self.measurement_cache = {}
        logger.info("PrecisionTextScaler initialized")

    def calculate_font_size(
        self,
        text: str,
        bbox: Tuple[float, float, float, float],
        font_name: str = "Helvetica",
        min_size: float = 6.0,
        max_size: float = 90.0,
        target_fill_ratio: float = 1.0,
        width_overshoot_ratio: float = 1.0
    ) -> float:
        """
        Calculate optimal font size to fit text EXACTLY within bbox

        Core principle: OCR detection bbox already encodes the desired
        line height/width. We scale text until it fills the bbox to the
        requested ratio without hard-coded fudge factors.

        Args:
            text: Text to fit
            bbox: (x1, y1, x2, y2) bounding box from OCR detection
            font_name: ReportLab font name
            min_size: Minimum font size
            max_size: Maximum font size
            target_fill_ratio: Portion of bbox width the text should cover
            width_overshoot_ratio: Maximum allowed width relative to bbox

        Returns:
            Optimal font size that fits text within bbox
        """
        x1, y1, x2, y2 = bbox
        bbox_width = x2 - x1
        bbox_height = y2 - y1

        if not text or bbox_width <= 0 or bbox_height <= 0:
            return min_size

        # Cache key
        # Clamp ratios to sane ranges (avoid zero/negative targets)
        target_fill_ratio = max(target_fill_ratio, 0.1)
        width_overshoot_ratio = max(width_overshoot_ratio, target_fill_ratio)

        cache_key = (
            text,
            bbox_width,
            bbox_height,
            font_name,
            target_fill_ratio,
            width_overshoot_ratio,
        )
        if cache_key in self.measurement_cache:
            return self.measurement_cache[cache_key]

        # Target dimensions: use EXACT bbox dimensions
        # No artificial scaling - bbox from detection is already correct
        target_width = bbox_width * target_fill_ratio
        max_allowed_width = bbox_width * width_overshoot_ratio
        target_height = bbox_height

        if max_allowed_width <= 0:
            return min_size

        # Binary search for optimal font size
        low = min_size
        high = max_size
        best_size = min_size
        iterations = 0
        max_iterations = 20
        tolerance = 0.5  # 0.5pt tolerance

        while iterations < max_iterations and (high - low) > tolerance:
            mid = (low + high) / 2.0

            # Measure text at this font size
            text_width = self._measure_text_width(text, mid, font_name)
            text_height = self._estimate_text_height(mid, font_name)

            # Check if it fits
            width_fits = text_width <= max_allowed_width
            height_fits = text_height <= target_height

            if width_fits and height_fits:
                # Text fits, try larger size
                best_size = mid
                low = mid
            else:
                # Text too large, try smaller size
                high = mid

            iterations += 1

        # Final validation: ensure text fills bbox as much as possible
        final_width = self._measure_text_width(text, best_size, font_name)
        if final_width > 0 and final_width < target_width * 0.995:
            # Scale up to reach target width but clamp to allowed overshoot
            desired_scale = target_width / final_width
            max_scale = max_allowed_width / final_width
            scale_factor = min(desired_scale, max_scale)
            candidate_size = min(best_size * scale_factor, max_size)

            final_height = self._estimate_text_height(candidate_size, font_name)
            if final_height <= target_height:
                best_size = candidate_size
            else:
                # Fit height by proportional scaling
                height_scale = target_height / final_height
                best_size = max(min_size, candidate_size * height_scale)

        # Clamp to min/max
        best_size = max(min_size, min(best_size, max_size))

        # Cache result
        self.measurement_cache[cache_key] = best_size

        return best_size

    def _measure_text_width(self, text: str, font_size: float, font_name: str) -> float:
        """
        Measure actual text width using ReportLab font metrics

        This is the GROUND TRUTH for PDF text rendering
        """
        try:
            width = pdfmetrics.stringWidth(text, font_name, font_size)
            return width
        except Exception as e:
            logger.warning(f"Failed to measure text width with ReportLab: {e}")
            # Fallback to estimation
            return self._estimate_text_width(text, font_size)

    def _estimate_text_height(self, font_size: float, font_name: str) -> float:
        """
        Estimate text height based on font metrics
        """
        try:
            font = pdfmetrics.getFont(font_name)
            if font and hasattr(font, 'face'):
                face = font.face
                ascent = getattr(face, 'ascent', 1000)
                descent = getattr(face, 'descent', -200)
                height = ((ascent - descent) / 1000.0) * font_size
                return height if height > 0 else font_size * 1.2
        except Exception:
            pass

        # Fallback: use typical height multiplier
        return font_size * 1.2

    def _estimate_text_width(self, text: str, font_size: float) -> float:
        """
        Fallback estimation when ReportLab metrics fail
        """
        # Count Korean vs ASCII characters
        korean_count = sum(1 for ch in text if '\uac00' <= ch <= '\ud7a3')
        ascii_count = len(text) - korean_count

        # Korean characters are roughly square (0.9 * font_size wide)
        # ASCII characters are roughly 0.6 * font_size wide
        korean_width = korean_count * font_size * 0.9
        ascii_width = ascii_count * font_size * 0.6

        return korean_width + ascii_width

    def calculate_text_position(
        self,
        text: str,
        bbox: Tuple[float, float, float, float],
        font_size: float,
        font_name: str,
        img_height: float
    ) -> Tuple[float, float]:
        """
        Calculate (x, y) position for text to be centered in bbox

        PDF coordinate system: origin at bottom-left
        Image coordinate system: origin at top-left

        Args:
            text: Text to position
            bbox: (x1, y1, x2, y2) in image coordinates
            font_size: Font size to use
            font_name: ReportLab font name
            img_height: Total image/PDF height for coordinate conversion

        Returns:
            (x, y) in PDF coordinates for drawString
        """
        x1, y1, x2, y2 = bbox
        bbox_width = x2 - x1
        bbox_height = y2 - y1

        # Horizontally anchor at bbox left; scaling will handle width fitting
        x = x1

        # Vertical baseline: align to bbox bottom, adding descent to keep glyphs inside
        pdf_bbox_bottom = img_height - y2

        try:
            font = pdfmetrics.getFont(font_name)
            if font and hasattr(font, 'face'):
                face = font.face
                descent = getattr(face, 'descent', -200)
                actual_descent = abs((descent / 1000.0) * font_size)
                y = pdf_bbox_bottom + actual_descent
            else:
                # Fallback: descent ≈ 0.2 * font_size
                y = pdf_bbox_bottom + font_size * 0.2
        except Exception as e:
            logger.debug(f"Failed to get font metrics for baseline calculation: {e}")
            y = pdf_bbox_bottom + font_size * 0.2

        return (x, y)

    def get_metrics(
        self,
        text: str,
        font_size: float,
        font_name: str
    ) -> Tuple[float, float]:
        """
        Get text width and height for given font size

        Returns:
            (width, height) in points
        """
        width = self._measure_text_width(text, font_size, font_name)
        height = self._estimate_text_height(font_size, font_name)
        return (width, height)
