"""
OCR 텍스트에서 메타데이터를 추출하는 유틸리티 (외부 API 없음)
- 언어 감지, 문서 유형 분류, 키워드 추출, 날짜 추출, 청크 분할
"""
import re
import math
import logging
from collections import Counter
from typing import Dict, Any, List, Tuple

logger = logging.getLogger(__name__)

# ─── 한국어 불용어 ─────────────────────────────────────────────────────────────
KO_STOPWORDS = {
    "이", "가", "을", "를", "은", "는", "의", "에", "에서", "로", "으로",
    "와", "과", "도", "만", "에게", "께", "한", "하는", "하여", "하고",
    "그", "이", "저", "것", "수", "등", "및", "또", "더", "그리고",
    "하지만", "그러나", "따라", "대한", "위한", "관한", "통해", "위해",
    "있는", "없는", "있다", "없다", "된다", "한다", "됩니다", "합니다",
    "있습니다", "없습니다", "입니다", "습니다", "니다", "시", "년", "월", "일",
    "제", "조", "항", "호", "본", "각", "동", "해당", "관련", "경우",
}

# ─── 문서 유형 키워드 패턴 ─────────────────────────────────────────────────────
DOC_TYPE_PATTERNS = [
    ("공문서",   ["공문", "시행", "수신", "발신", "담당", "결재", "기안", "문서번호", "행정"]),
    ("계약서",   ["계약", "갑", "을", "계약서", "서명", "날인", "계약기간", "계약금액", "위약금"]),
    ("보고서",   ["보고", "현황", "분석", "결과", "요약", "검토", "평가", "제언", "결론"]),
    ("학술논문", ["abstract", "참고문헌", "서론", "결론", "연구", "논문", "학술", "방법론", "실험"]),
    ("법령문서", ["법률", "조례", "시행령", "규정", "제정", "개정", "시행일", "부칙", "조항"]),
    ("회의록",   ["회의", "의결", "안건", "참석", "회의록", "토의", "의사록"]),
    ("영수증",   ["영수증", "합계", "부가세", "VAT", "공급가액", "영수", "금액"]),
    ("기타",     []),
]


def extract_full_text(ocr_data: Dict[str, Any]) -> str:
    """OCR 데이터에서 전체 텍스트 추출"""
    lines = []
    for page in ocr_data.get("pages", []):
        for line in page.get("lines", []):
            text = line.get("text", "").strip() if isinstance(line, dict) else str(line).strip()
            if text:
                lines.append(text)
    return "\n".join(lines)


def detect_language(text: str) -> str:
    """ko / en / mixed 감지"""
    if not text:
        return "unknown"
    ko_count = len(re.findall(r'[가-힣]', text))
    en_count = len(re.findall(r'[a-zA-Z]', text))
    total = ko_count + en_count
    if total == 0:
        return "unknown"
    ko_ratio = ko_count / total
    if ko_ratio >= 0.8:
        return "ko"
    elif ko_ratio <= 0.2:
        return "en"
    else:
        return "mixed"


def detect_doc_type(text: str) -> str:
    """키워드 패턴으로 문서 유형 분류"""
    text_lower = text.lower()
    scores = {}
    for doc_type, keywords in DOC_TYPE_PATTERNS:
        if not keywords:
            continue
        score = sum(1 for kw in keywords if kw in text_lower)
        if score > 0:
            scores[doc_type] = score
    if not scores:
        return "기타"
    return max(scores, key=scores.get)


def extract_keywords(text: str, top_n: int = 20) -> List[str]:
    """TF-IDF 기반 키워드 추출 (단일 문서이므로 빈도 + 길이 기반)"""
    # 한국어 어절/영어 단어 토크나이징
    ko_tokens = re.findall(r'[가-힣]{2,}', text)
    en_tokens = re.findall(r'[a-zA-Z]{3,}', text)
    tokens = ko_tokens + [t.lower() for t in en_tokens]

    # 불용어 제거
    tokens = [t for t in tokens if t not in KO_STOPWORDS and len(t) >= 2]

    if not tokens:
        return []

    # 빈도 계산
    freq = Counter(tokens)
    total = len(tokens)

    # TF 점수 (빈도 * 단어 길이 보정)
    scored = {
        word: (count / total) * math.log(1 + len(word))
        for word, count in freq.items()
        if count >= 2  # 최소 2회 이상 등장
    }

    top = sorted(scored, key=scored.get, reverse=True)[:top_n]
    return top


def extract_dates(text: str) -> List[str]:
    """텍스트에서 날짜 패턴 추출"""
    patterns = [
        r'\d{4}년\s*\d{1,2}월\s*\d{1,2}일',   # 2026년 4월 10일
        r'\d{4}년\s*\d{1,2}월',                 # 2026년 4월
        r'\d{4}[-./]\d{1,2}[-./]\d{1,2}',      # 2026-04-10, 2026.04.10
        r'\d{2}[-./]\d{1,2}[-./]\d{1,2}',      # 26-04-10
    ]
    found = set()
    for pattern in patterns:
        matches = re.findall(pattern, text)
        found.update(m.strip() for m in matches)
    return sorted(found)


def split_into_chunks(
    ocr_data: Dict[str, Any],
    chunk_size: int = 500,
    overlap: int = 50
) -> List[Dict[str, Any]]:
    """
    RAG용 청크 분할
    - 페이지 경계를 최대한 유지
    - chunk_size: 청크당 최대 문자 수
    - overlap: 청크 간 겹치는 문자 수
    """
    chunks = []
    chunk_index = 0

    for page in ocr_data.get("pages", []):
        page_num = page.get("page_number", 1)
        page_lines = []
        for line in page.get("lines", []):
            text = line.get("text", "").strip() if isinstance(line, dict) else str(line).strip()
            if text:
                page_lines.append(text)

        page_text = "\n".join(page_lines)
        if not page_text:
            continue

        # 페이지 텍스트를 chunk_size 단위로 분할
        start = 0
        while start < len(page_text):
            end = start + chunk_size
            chunk_text = page_text[start:end]
            if chunk_text.strip():
                chunks.append({
                    "chunk_index": chunk_index,
                    "text": chunk_text,
                    "page_number": page_num,
                    "char_start": start,
                    "char_end": min(end, len(page_text)),
                })
                chunk_index += 1
            start = end - overlap  # overlap 적용
            if start >= len(page_text):
                break

    return chunks


def extract_all_metadata(
    ocr_data: Dict[str, Any],
    chunk_size: int = 500,
    chunk_overlap: int = 50,
    keywords_top_n: int = 20,
) -> Dict[str, Any]:
    """OCR 결과에서 모든 메타데이터 추출"""
    full_text = extract_full_text(ocr_data)

    keywords = extract_keywords(full_text, top_n=keywords_top_n)
    dates = extract_dates(full_text)
    language = detect_language(full_text)
    doc_type = detect_doc_type(full_text)
    chunks = split_into_chunks(ocr_data, chunk_size=chunk_size, overlap=chunk_overlap)

    # 단어/문자 수
    char_count = len(full_text.replace("\n", "").replace(" ", ""))
    word_count = len(re.findall(r'[가-힣]+|[a-zA-Z]+', full_text))

    return {
        "full_text": full_text,
        "detected_language": language,
        "doc_type": doc_type,
        "keywords": keywords,          # List[str]
        "detected_dates": dates,       # List[str]
        "char_count": char_count,
        "word_count": word_count,
        "chunks": chunks,              # List[Dict]
    }
