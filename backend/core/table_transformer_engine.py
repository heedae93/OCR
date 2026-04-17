"""
Table detection and structure recognition using Microsoft Table Transformer (DETR-based).

Detection model  : microsoft/table-transformer-detection
Structure model  : microsoft/table-transformer-structure-recognition-v1.1-all

Usage modes (OCR_TABLE_BACKEND in config.yaml):
  slanet            – default PaddleX SLANet/SLANet+ (no Table Transformer)
  table_transformer – Table Transformer for detection + structure (replaces SLANet)
  hybrid            – PP-Structure layout detects table regions, Table Transformer
                      recognises structure (recommended)
"""

import logging
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

TABLE_TRANSFORMER_AVAILABLE = False
_import_error_msg: Optional[str] = None

try:
    import torch
    from transformers import AutoImageProcessor, TableTransformerForObjectDetection
    from PIL import Image as _PILImage
    TABLE_TRANSFORMER_AVAILABLE = True
except ImportError as _e:
    _import_error_msg = str(_e)
    logger.warning(
        "Table Transformer not available (%s). "
        "Install: pip install transformers timm torch",
        _e,
    )


class TableTransformerEngine:
    """
    Wraps the two Microsoft Table Transformer models:
      1. table-transformer-detection        – locates tables in a page image
      2. table-transformer-structure-recognition – finds rows / columns / cells

    Both models are based on DETR and loaded from HuggingFace Hub on first init
    (cached locally afterward).
    """

    # HuggingFace model identifiers (overridable via config)
    DEFAULT_DETECTION_MODEL = "microsoft/table-transformer-detection"
    DEFAULT_STRUCTURE_MODEL = (
        "microsoft/table-transformer-structure-recognition-v1.1-all"
    )

    # Label maps used by the two models
    DETECTION_LABELS: Dict[int, str] = {0: "table", 1: "table rotated"}
    STRUCTURE_LABELS: Dict[int, str] = {
        0: "table",
        1: "table column",
        2: "table row",
        3: "table column header",
        4: "table projected row header",
        5: "table spanning cell",
        6: "no object",
    }

    def __init__(
        self,
        use_gpu: bool = True,
        detection_model: str = DEFAULT_DETECTION_MODEL,
        structure_model: str = DEFAULT_STRUCTURE_MODEL,
        detection_threshold: float = 0.9,
        structure_threshold: float = 0.6,
    ) -> None:
        if not TABLE_TRANSFORMER_AVAILABLE:
            raise RuntimeError(
                "Table Transformer not available. "
                "Run: pip install transformers timm torch\n"
                f"Import error: {_import_error_msg}"
            )

        self.detection_model_name = detection_model
        self.structure_model_name = structure_model
        self.detection_threshold = detection_threshold
        self.structure_threshold = structure_threshold
        self.device = (
            "cuda" if (use_gpu and torch.cuda.is_available()) else "cpu"
        )

        logger.info("Initializing Table Transformer on device: %s", self.device)
        self._load_models()

    # ------------------------------------------------------------------
    # Model loading
    # ------------------------------------------------------------------

    def _load_models(self) -> None:
        logger.info("Loading detection model: %s", self.detection_model_name)
        self._det_processor = AutoImageProcessor.from_pretrained(
            self.detection_model_name
        )
        self._det_model = TableTransformerForObjectDetection.from_pretrained(
            self.detection_model_name
        )
        self._det_model.to(self.device)
        self._det_model.eval()

        logger.info("Loading structure model: %s", self.structure_model_name)
        self._str_processor = AutoImageProcessor.from_pretrained(
            self.structure_model_name
        )
        self._str_model = TableTransformerForObjectDetection.from_pretrained(
            self.structure_model_name
        )
        self._str_model.to(self.device)
        self._str_model.eval()

        logger.info("Table Transformer models ready")

    # ------------------------------------------------------------------
    # Table detection
    # ------------------------------------------------------------------

    def detect_tables(self, image: "_PILImage.Image") -> List[Dict]:
        """
        Detect table bounding boxes in a page image.

        Returns:
            List of dicts: {bbox, score, label, model}
        """
        inputs = self._det_processor(
            images=image, return_tensors="pt"
        ).to(self.device)

        with torch.no_grad():
            outputs = self._det_model(**inputs)

        target_sizes = torch.tensor([image.size[::-1]])  # (H, W)
        post = self._det_processor.post_process_object_detection(
            outputs,
            threshold=self.detection_threshold,
            target_sizes=target_sizes,
        )[0]

        tables = []
        for score, label, box in zip(
            post["scores"], post["labels"], post["boxes"]
        ):
            label_id = label.item()
            if label_id not in self.DETECTION_LABELS:
                continue
            tables.append(
                {
                    "bbox": [round(x) for x in box.tolist()],
                    "score": round(score.item(), 4),
                    "label": self.DETECTION_LABELS[label_id],
                    "model": "table-transformer-detection",
                }
            )
        return tables

    # ------------------------------------------------------------------
    # Structure recognition
    # ------------------------------------------------------------------

    def recognize_structure(
        self,
        image: "_PILImage.Image",
        table_bbox: List,
        bbox_offset: Tuple[int, int] = (0, 0),
    ) -> Dict:
        """
        Recognise rows, columns, and spanning cells within a detected table.

        Args:
            image:       Full-page PIL image.
            table_bbox:  [x1, y1, x2, y2] in image coordinates.
            bbox_offset: (ox, oy) added to all returned coordinates
                         (useful when `image` is already a crop).

        Returns:
            Dict with keys: rows, columns, cells, spanning_cells, structure_model
        """
        ox, oy = bbox_offset
        img_w, img_h = image.size
        pad = 10

        x1, y1, x2, y2 = [int(v) for v in table_bbox]
        cx1 = max(0, x1 - pad)
        cy1 = max(0, y1 - pad)
        cx2 = min(img_w, x2 + pad)
        cy2 = min(img_h, y2 + pad)
        table_crop = image.crop((cx1, cy1, cx2, cy2))

        inputs = self._str_processor(
            images=table_crop, return_tensors="pt"
        ).to(self.device)

        with torch.no_grad():
            outputs = self._str_model(**inputs)

        target_sizes = torch.tensor([table_crop.size[::-1]])
        post = self._str_processor.post_process_object_detection(
            outputs,
            threshold=self.structure_threshold,
            target_sizes=target_sizes,
        )[0]

        rows: List[Dict] = []
        columns: List[Dict] = []
        spanning_cells: List[Dict] = []

        for score, label, box in zip(
            post["scores"], post["labels"], post["boxes"]
        ):
            label_name = self.STRUCTURE_LABELS.get(label.item(), "unknown")
            if label_name in ("no object", "table", "unknown"):
                continue

            b = box.tolist()
            # Translate crop-relative coords → original image + any outer offset
            bbox = [
                round(b[0] + cx1 + ox),
                round(b[1] + cy1 + oy),
                round(b[2] + cx1 + ox),
                round(b[3] + cy1 + oy),
            ]
            entry = {
                "bbox": bbox,
                "score": round(score.item(), 4),
                "label": label_name,
            }

            if label_name in (
                "table row",
                "table column header",
                "table projected row header",
            ):
                rows.append(entry)
            elif label_name == "table column":
                columns.append(entry)
            elif label_name == "table spanning cell":
                spanning_cells.append(entry)

        cells = self._build_cell_grid(rows, columns)

        return {
            "rows": rows,
            "columns": columns,
            "cells": cells,
            "spanning_cells": spanning_cells,
            "structure_model": "table-transformer-structure",
        }

    # ------------------------------------------------------------------
    # Cell grid builder
    # ------------------------------------------------------------------

    def _build_cell_grid(
        self, rows: List[Dict], columns: List[Dict]
    ) -> List[Dict]:
        """Compute cell bounding boxes from row × column intersections."""
        cells: List[Dict] = []
        sorted_rows = sorted(rows, key=lambda r: r["bbox"][1])
        sorted_cols = sorted(columns, key=lambda c: c["bbox"][0])

        for ri, row in enumerate(sorted_rows):
            for ci, col in enumerate(sorted_cols):
                ix1 = max(row["bbox"][0], col["bbox"][0])
                iy1 = max(row["bbox"][1], col["bbox"][1])
                ix2 = min(row["bbox"][2], col["bbox"][2])
                iy2 = min(row["bbox"][3], col["bbox"][3])
                if ix2 > ix1 and iy2 > iy1:
                    cells.append(
                        {"bbox": [ix1, iy1, ix2, iy2], "row": ri, "col": ci}
                    )
        return cells

    # ------------------------------------------------------------------
    # HTML generator
    # ------------------------------------------------------------------

    def build_html(
        self, cells: List[Dict], ocr_blocks: List[Dict]
    ) -> str:
        """
        Generate an HTML <table> by mapping OCR text blocks into cells.

        Each OCR block whose centre point falls inside a cell's bbox is
        assigned to that cell.
        """
        if not cells:
            return ""

        num_rows = max(c["row"] for c in cells) + 1
        num_cols = max(c["col"] for c in cells) + 1

        # Build a 2-D grid
        grid: List[List[Optional[Dict]]] = [
            [None] * num_cols for _ in range(num_rows)
        ]
        for cell in cells:
            r, c = cell["row"], cell["col"]
            if grid[r][c] is None:
                grid[r][c] = {"bbox": cell["bbox"], "text": ""}

        # Fill text from OCR blocks using centre-point containment
        for row_cells in grid:
            for cell in row_cells:
                if cell is None:
                    continue
                cx1, cy1, cx2, cy2 = cell["bbox"]
                texts = []
                for block in ocr_blocks:
                    bx1, by1, bx2, by2 = block.get("bbox", [0, 0, 0, 0])
                    bcx = (bx1 + bx2) / 2
                    bcy = (by1 + by2) / 2
                    if cx1 <= bcx <= cx2 and cy1 <= bcy <= cy2:
                        text = block.get("text", "")
                        if text:
                            texts.append(text)
                cell["text"] = " ".join(texts)

        rows_html = []
        for row_cells in grid:
            cols_html = "".join(
                f"<td>{cell['text'] if cell else ''}</td>"
                for cell in row_cells
            )
            rows_html.append(f"<tr>{cols_html}</tr>")
        return "<table>" + "".join(rows_html) + "</table>"

    # ------------------------------------------------------------------
    # High-level API
    # ------------------------------------------------------------------

    def analyze_image(
        self,
        image_path: str,
        existing_table_bboxes: Optional[List[List]] = None,
        ocr_blocks: Optional[List[Dict]] = None,
    ) -> List[Dict]:
        """
        Full Table Transformer pipeline for one page image.

        Args:
            image_path:            Path to the page image file.
            existing_table_bboxes: Pre-detected table bbox list from PP-Structure
                                   layout detection.  When supplied, the detection
                                   step is skipped and these bboxes are used directly.
            ocr_blocks:            OCR text blocks (list of {bbox, text, …}) used
                                   to fill cell HTML.

        Returns:
            List of table dicts, each containing:
              bbox, score, label, model,
              rows, columns, cells, spanning_cells, html, structure_model
        """
        from PIL import Image  # local to avoid polluting module namespace

        image = Image.open(image_path).convert("RGB")
        ocr_blocks = ocr_blocks or []

        # --- Detection step ---
        if existing_table_bboxes is not None:
            tables = [
                {
                    "bbox": bbox,
                    "score": 1.0,
                    "label": "table",
                    "model": "pp-structure-layout",
                }
                for bbox in existing_table_bboxes
            ]
            logger.info(
                "Table Transformer: using %d table bbox(es) from PP-Structure layout",
                len(tables),
            )
        else:
            tables = self.detect_tables(image)
            logger.info(
                "Table Transformer: detected %d table(s) independently",
                len(tables),
            )

        if not tables:
            return []

        # --- Structure recognition step ---
        enriched: List[Dict] = []
        for table in tables:
            try:
                structure = self.recognize_structure(image, table["bbox"])
                html = self.build_html(structure["cells"], ocr_blocks)
                enriched.append(
                    {
                        "bbox": table["bbox"],
                        "score": table["score"],
                        "label": table.get("label", "table"),
                        "model": table.get("model", "table-transformer-detection"),
                        "rows": structure["rows"],
                        "columns": structure["columns"],
                        "cells": structure["cells"],
                        "spanning_cells": structure["spanning_cells"],
                        "html": html,
                        "structure_model": structure["structure_model"],
                    }
                )
            except Exception as exc:
                logger.warning(
                    "Table structure recognition failed for bbox %s: %s",
                    table["bbox"],
                    exc,
                )
                # Still return the detection result even without structure
                enriched.append(
                    {
                        "bbox": table["bbox"],
                        "score": table.get("score", 0.0),
                        "model": table.get("model", ""),
                        "error": str(exc),
                    }
                )

        return enriched
