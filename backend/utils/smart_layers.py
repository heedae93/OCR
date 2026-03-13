"""Utility helpers for applying Smart Tool layers onto page images."""
from __future__ import annotations

import base64
import io
import logging
from pathlib import Path
from typing import List, Tuple

from PIL import Image, ImageDraw, ImageFont

from models.ocr import SmartToolElement

logger = logging.getLogger(__name__)

DEFAULT_FONT_CANDIDATES = [
    "/usr/share/fonts/truetype/nanum/NanumGothic.ttf",
    "/System/Library/Fonts/AppleGothic.ttf",
    "C:/Windows/Fonts/malgun.ttf",
    "C:/Windows/Fonts/gulim.ttc",
]


def _hex_to_rgba(value: str | None, alpha: float = 1.0) -> Tuple[int, int, int, int]:
    if not value:
        return (0, 0, 0, int(255 * alpha))

    value = value.strip()
    if value.startswith('#'):
        value = value[1:]

    if len(value) == 3:
        value = ''.join(ch * 2 for ch in value)

    try:
        r = int(value[0:2], 16)
        g = int(value[2:4], 16)
        b = int(value[4:6], 16)
    except ValueError:
        logger.debug("Invalid hex color %s, fallback to black", value)
        return (0, 0, 0, int(255 * alpha))

    return (r, g, b, int(255 * alpha))


def _load_font(font_family: str | None, font_size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    if font_size <= 0:
        font_size = 12

    candidates = []
    if font_family:
        normalized = font_family.lower()
        if 'nanum' in normalized:
            candidates.append("/usr/share/fonts/truetype/nanum/NanumGothic.ttf")
        elif 'apple' in normalized:
            candidates.append("/System/Library/Fonts/AppleGothic.ttf")
        elif 'malgun' in normalized:
            candidates.append("C:/Windows/Fonts/malgun.ttf")
        elif 'gulim' in normalized:
            candidates.append("C:/Windows/Fonts/gulim.ttc")

    candidates.extend(DEFAULT_FONT_CANDIDATES)

    for candidate in candidates:
        try:
            path = Path(candidate)
            if path.exists():
                return ImageFont.truetype(str(path), font_size)
        except Exception:
            continue

    try:
        return ImageFont.load_default()
    except Exception:
        return ImageFont.truetype(DEFAULT_FONT_CANDIDATES[0], font_size) if Path(DEFAULT_FONT_CANDIDATES[0]).exists() else ImageFont.load_default()


def _load_image_from_data(data_str: str | None) -> Image.Image | None:
    """Decode data URL/base64 string into a PIL image."""
    if not data_str:
        return None

    try:
        if data_str.startswith('data:'):
            _, encoded = data_str.split(',', 1)
        else:
            encoded = data_str
        image_bytes = base64.b64decode(encoded)
        buffer = io.BytesIO(image_bytes)
        return Image.open(buffer).convert('RGBA')
    except Exception as exc:
        logger.warning(f"Failed to decode smart layer image: {exc}")
        return None


def apply_smart_layers_to_image(
    image_path: str,
    elements: List[SmartToolElement],
    output_path: Path,
) -> str:
    """Apply Smart Tool overlays to an image and return the new path."""
    if not elements:
        return image_path

    try:
        base = Image.open(image_path).convert('RGBA')
    except Exception as exc:
        logger.error(f"Failed to open base image for smart layers: {exc}")
        return image_path

    overlay = Image.new('RGBA', base.size)
    draw = ImageDraw.Draw(overlay)

    for element in elements:
        bbox = element.bbox or [0, 0, 0, 0]
        if len(bbox) != 4:
            continue
        x1, y1, x2, y2 = bbox
        width = max(1, int(round(x2 - x1)))
        height = max(1, int(round(y2 - y1)))
        position = (int(round(x1)), int(round(y1)))

        etype = element.type.lower()
        data = element.data or {}

        if etype in {'text', 'sticker'}:
            text = data.get('text', '').strip()
            if not text:
                continue
            font_size = int(round(data.get('fontSize', data.get('size', 24))))
            font = _load_font(data.get('fontFamily'), font_size)
            color = _hex_to_rgba(data.get('color', '#000000'), alpha=float(data.get('opacity', 1.0)))
            draw.text(position, text, font=font, fill=color)

        elif etype in {'image', 'signature'}:
            img = _load_image_from_data(data.get('imageData') or data.get('src'))
            if not img:
                continue
            img_resized = img.resize((width, height))
            overlay.alpha_composite(img_resized, dest=position)

        elif etype == 'shape':
            fill_color = data.get('fillColor') or data.get('color')
            stroke_color = data.get('strokeColor') or fill_color or '#000000'
            opacity = float(data.get('opacity', 1.0))
            stroke_width = max(1, int(round(data.get('strokeWidth', 2))))
            fill_rgba = _hex_to_rgba(fill_color, alpha=opacity) if fill_color else None
            outline_rgba = _hex_to_rgba(stroke_color, alpha=opacity)
            draw.rectangle([x1, y1, x2, y2], fill=fill_rgba, outline=outline_rgba, width=stroke_width)

        elif etype == 'draw':
            points = data.get('points') or []
            if len(points) < 2:
                continue
            stroke_color = _hex_to_rgba(data.get('strokeColor', '#000000'), alpha=float(data.get('opacity', 1.0)))
            stroke_width = max(1, int(round(data.get('strokeWidth', 3))))
            # Flatten points as tuples
            path = [(int(round(pt[0])), int(round(pt[1]))) for pt in points if isinstance(pt, (list, tuple)) and len(pt) == 2]
            if len(path) >= 2:
                draw.line(path, fill=stroke_color, width=stroke_width, joint='curve')

    composed = Image.alpha_composite(base, overlay).convert('RGB')
    output_path.parent.mkdir(parents=True, exist_ok=True)
    composed.save(output_path, format='PNG')

    logger.info("Smart layers applied: %s", output_path.name)
    return str(output_path)
