"""
Korean NER helper for OCR text.

This version avoids the Hugging Face pipeline aggregation bug for models that
use labels like PER-B / PER-I instead of B-PER / I-PER by reading token labels
directly and merging spans ourselves.
"""
import logging
import os
import re
from contextlib import contextmanager
from pathlib import Path
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

_PROXY_ENV_KEYS = [
    "HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "NO_PROXY",
    "http_proxy", "https_proxy", "all_proxy", "no_proxy",
]
_NER_CACHE_DIR = Path(__file__).resolve().parents[2] / "data" / "hf_cache"


@contextmanager
def _temporarily_disable_broken_proxies():
    """
    Temporarily disable obviously broken local proxy settings during model load.
    This environment currently exports 127.0.0.1:9, which rejects connections.
    """
    saved = {key: os.environ.get(key) for key in _PROXY_ENV_KEYS}
    try:
        for key, value in saved.items():
            if value and "127.0.0.1:9" in value:
                os.environ.pop(key, None)
        yield
    finally:
        for key, value in saved.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


@contextmanager
def _temporary_hf_cache_dir():
    """Use a workspace-local Hugging Face cache to avoid user-profile lock issues."""
    saved = {
        "HF_HOME": os.environ.get("HF_HOME"),
        "HUGGINGFACE_HUB_CACHE": os.environ.get("HUGGINGFACE_HUB_CACHE"),
        "TRANSFORMERS_CACHE": os.environ.get("TRANSFORMERS_CACHE"),
    }
    _NER_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    try:
        os.environ["HF_HOME"] = str(_NER_CACHE_DIR)
        os.environ["HUGGINGFACE_HUB_CACHE"] = str(_NER_CACHE_DIR / "hub")
        os.environ["TRANSFORMERS_CACHE"] = str(_NER_CACHE_DIR / "transformers")
        yield
    finally:
        for key, value in saved.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


MODEL_ENTITY_TYPE_MAP = {
    "PER": "PERSON",
    "PS": "PERSON",
    "LOC": "LOCATION",
    "LC": "LOCATION",
    "ORG": "ORGANIZATION",
    "OG": "ORGANIZATION",
    "DAT": "DATE",
    "DT": "DATE",
    "TIM": "TIME",
    "TI": "TIME",
    "NUM": "QUANTITY",
    "QT": "QUANTITY",
    "FLD": "FIELD",
    "FD": "FIELD",
    "EVT": "EVENT",
    "EV": "EVENT",
    "AFW": "PRODUCT",
    "PT": "PRODUCT",
    "CVL": "CIVILIZATION",
    "CV": "CIVILIZATION",
    "TRM": "THEORY",
    "TR": "THEORY",
    "ANM": "ANIMAL",
    "AM": "ANIMAL",
    "PLT": "PRODUCT",
    "MAT": "FIELD",
}

ENTITY_TYPE_KO = {
    "PERSON": "이름",
    "LOCATION": "장소",
    "ORGANIZATION": "기관",
    "DATE": "날짜",
    "TIME": "시간",
    "QUANTITY": "수량",
    "FIELD": "분야",
    "EVENT": "사건",
    "PRODUCT": "제품",
    "CIVILIZATION": "문명/문화",
    "THEORY": "이론",
    "ANIMAL": "동물",
    "UNKNOWN": "미분류",
}

_KV_SPLIT = re.compile(r"\s*[:：=]\s*")
_KOREAN_NAME_RE = re.compile(r"^[가-힣]{2,4}$")


class KoreanNERExtractor:
    """Korean NER extractor for OCR lines."""

    MODEL_NAME = "monologg/koelectra-base-finetuned-naver-ner"

    def __init__(self):
        self._tokenizer = None
        self._model = None
        self._torch = None
        self._device = "cpu"
        self._load_failed = False

    def _load(self) -> bool:
        if self._load_failed:
            return False
        try:
            with _temporarily_disable_broken_proxies(), _temporary_hf_cache_dir():
                from transformers import AutoModelForTokenClassification, AutoTokenizer
                import torch

                self._torch = torch
                self._device = "cuda:0" if torch.cuda.is_available() else "cpu"
                self._tokenizer = AutoTokenizer.from_pretrained(self.MODEL_NAME)
                self._model = AutoModelForTokenClassification.from_pretrained(self.MODEL_NAME)
                self._model.to(self._device)
                self._model.eval()

            logger.info(
                "[NER] Model loaded: %s (device=%s)",
                self.MODEL_NAME,
                "GPU" if self._device != "cpu" else "CPU",
            )
            return True
        except Exception as e:
            logger.error("[NER] Model load failed: %s", e)
            self._load_failed = True
            return False

    @property
    def is_available(self) -> bool:
        if self._model is not None and self._tokenizer is not None:
            return True
        return self._load()

    @staticmethod
    def _parse_label(label: str) -> Tuple[Optional[str], Optional[str]]:
        """
        Normalize labels like PER-B or B-PER into (prefix, entity_code).
        Returns (None, None) for O or unsupported labels.
        """
        if not label or label == "O":
            return None, None
        if "-" not in label:
            return None, label

        left, right = label.split("-", 1)
        if left in {"B", "I"}:
            return left, right
        if right in {"B", "I"}:
            return right, left
        return None, label

    @staticmethod
    def _map_entity_code(entity_code: Optional[str]) -> str:
        if not entity_code:
            return "UNKNOWN"
        return MODEL_ENTITY_TYPE_MAP.get(entity_code, entity_code)

    def extract_entities(self, text: str) -> List[Dict]:
        """
        Extract entities from text.
        Returns: [{"entity_type": "PERSON", "value": "홍길동", "score": 0.99, ...}]
        """
        if not text.strip() or not self.is_available:
            return []

        try:
            encoded = self._tokenizer(
                text,
                return_tensors="pt",
                return_offsets_mapping=True,
                truncation=True,
            )
            offsets = encoded.pop("offset_mapping")[0].tolist()
            encoded = {k: v.to(self._device) for k, v in encoded.items()}

            with self._torch.no_grad():
                outputs = self._model(**encoded)

            probs = self._torch.softmax(outputs.logits, dim=-1)[0]
            pred_ids = outputs.logits.argmax(dim=-1)[0].tolist()
            id2label = self._model.config.id2label

            merged: List[Dict] = []
            current = None

            for token_idx, pred_id in enumerate(pred_ids):
                start, end = offsets[token_idx]
                if start == end:
                    continue

                label = id2label[int(pred_id)]
                prefix, entity_code = self._parse_label(label)
                if prefix is None or entity_code is None:
                    if current:
                        merged.append(current)
                        current = None
                    continue

                entity_type = self._map_entity_code(entity_code)
                score = float(probs[token_idx][pred_id])

                gap_text = ""
                if current is not None:
                    gap_text = text[current["end"]:start]

                should_start_new = (
                    current is None
                    or current["entity_type"] != entity_type
                    or gap_text.strip() != ""
                )

                if should_start_new:
                    if current:
                        merged.append(current)
                    current = {
                        "entity_type": entity_type,
                        "start": start,
                        "end": end,
                        "scores": [score],
                    }
                else:
                    current["end"] = end
                    current["scores"].append(score)

            if current:
                merged.append(current)

            results = []
            for ent in merged:
                value = text[ent["start"]:ent["end"]].strip()
                if not value:
                    continue
                results.append({
                    "entity_type": ent["entity_type"],
                    "value": value,
                    "score": round(sum(ent["scores"]) / len(ent["scores"]), 3),
                    "start": ent["start"],
                    "end": ent["end"],
                })
            return self._apply_name_heuristics(text, results)
        except Exception as e:
            logger.error("[NER] Extraction failed: %s", e)
            return []

    @staticmethod
    def _apply_name_heuristics(text: str, results: List[Dict]) -> List[Dict]:
        """
        Expand likely Korean personal names when the model only tags part of them.
        Example: 황유빈 -> 황유 (PERSON)  =>  황유빈 (PERSON)
        """
        stripped = text.strip()
        if not _KOREAN_NAME_RE.fullmatch(stripped):
            return results

        person_spans = [r for r in results if r["entity_type"] == "PERSON"]
        if not person_spans:
            return results

        if len(stripped) == 3:
            best = max(person_spans, key=lambda r: r["score"])
            return [{
                "entity_type": "PERSON",
                "value": stripped,
                "score": best["score"],
                "start": 0,
                "end": len(stripped),
            }]

        return results

    def extract_kv_from_lines(self, lines: List[Dict]) -> List[Dict]:
        """
        Extract key-value style entities from OCR lines.

        Input line format: {"text": "성명 : 홍길동", "bbox": [...]}
        """
        results = []

        for line in lines:
            text = line.get("text", "").strip()
            if not text:
                continue

            parts = _KV_SPLIT.split(text, maxsplit=1)

            if len(parts) == 2:
                key_text = parts[0].strip()
                val_text = parts[1].strip()
                if not val_text:
                    continue

                entities = self.extract_entities(val_text)
                if (
                    key_text.replace(" ", "") in {"성명", "이름", "성명(한글)", "성명(한자)"}
                    and _KOREAN_NAME_RE.fullmatch(val_text)
                ):
                    entities = [{
                        "entity_type": "PERSON",
                        "value": val_text,
                        "score": max((e["score"] for e in entities), default=1.0),
                        "start": 0,
                        "end": len(val_text),
                    }]
                if entities:
                    best = max(entities, key=lambda e: e["score"])
                    entity_type = best["entity_type"]
                    score = best["score"]
                else:
                    entity_type = "UNKNOWN"
                    score = None

                results.append({
                    "key": key_text,
                    "value": val_text,
                    "entity_type": entity_type,
                    "entity_type_ko": ENTITY_TYPE_KO.get(entity_type, entity_type),
                    "score": score,
                    "raw_entities": entities,
                    "bbox": line.get("bbox"),
                })
            else:
                entities = self.extract_entities(text)
                for ent in entities:
                    results.append({
                        "key": None,
                        "value": ent["value"],
                        "entity_type": ent["entity_type"],
                        "entity_type_ko": ENTITY_TYPE_KO.get(ent["entity_type"], ent["entity_type"]),
                        "score": ent["score"],
                        "raw_entities": [ent],
                        "bbox": line.get("bbox"),
                    })

        return results

    def extract_from_ocr_pages(self, ocr_pages: List[Dict]) -> List[Dict]:
        """Extract entities from OCR pages."""
        all_results = []
        for page in ocr_pages:
            page_num = page.get("page_number", 1)
            lines = page.get("lines", [])
            kv_items = self.extract_kv_from_lines(lines)
            for item in kv_items:
                item["page"] = page_num
                all_results.append(item)

        logger.info("[NER] Extracted %s items from OCR pages", len(all_results))
        return all_results


_extractor: Optional[KoreanNERExtractor] = None


def get_ner_extractor() -> KoreanNERExtractor:
    global _extractor
    if _extractor is None:
        _extractor = KoreanNERExtractor()
    return _extractor
