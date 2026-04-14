
import re
import json
import logging
import requests

logger = logging.getLogger(__name__)

PII_PATTERNS = {
    "PHONE": [
        r"\b01[016789]-?\d{3,4}-?\d{4}\b",
        r"\b02-?\d{3,4}-?\d{4}\b",
        r"\b0[3-6][1-5]-?\d{3,4}-?\d{4}\b",
        r"\b070-?\d{3,4}-?\d{4}\b",
        # 전국대표번호 (1544, 1588, 1600, 1800 등)
        r"\b1[0-9]{3}-\d{4}\b",
        # 국번 없는 7자리 지역번호 (예: 305-3311, 376-5555)
        r"\b[2-9]\d{2}-\d{4}\b",
    ],
    "EMAIL": [
        r"\b[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}\b"
    ],
    "RRN": [
        r"\b\d{6}-?[1-4]\d{6}\b"
    ],
    "FOREIGNER_REG_NO": [
        r"\b\d{6}-?[5-8]\d{6}\b"
    ],
    "BUSINESS_REG_NO": [
        r"\b\d{3}-\d{2}-\d{5}\b"
    ],
    "ACCOUNT_NO": [
        r"\b(?!01[016789]|02-|070)\d{4,6}-\d{2,6}-\d{4,7}\b",
        r"\b\d{3,4}-\d{3,4}-\d{4}-\d{2}\b",
        # 은행명 + 하이픈 없는 숫자 계좌번호 (예: 케이뱅크 1001 33370105, 기업 21302612001120)
        r"(?:케이뱅크|국민|신한|우리|하나|기업|농협|씨티|SC제일|카카오뱅크|토스뱅크|수협|우체국|새마을|부산|경남|대구|전북|광주|제주|산업|기술|외환)[\s]*(\d[\d\s]{7,19}\d)",
    ],
    "HEALTH_INSURANCE_NO": [
        r"\b\d{1,2}-\d{7,10}\b"
    ],
    "CREDIT_CARD": [
        r"\b\d{4}[-\s]\d{4}[-\s]\d{4}[-\s]\d{4}\b",
    ],
    "PASSPORT_NO": [
        r"\b[A-Z]{1,2}\d{7,8}\b",
        r"\b[MSROD]\d{8}\b"
    ],
    "IP_ADDRESS": [
        r"\b(?:(?:25[0-5]|2[0-4]\d|1\d\d|[1-9]?\d)\.){3}(?:25[0-5]|2[0-4]\d|1\d\d|[1-9]?\d)\b"
    ],
    "CAR_NO": [
        r"\b\d{2,3}\s?[가-힣]\s?\d{4}\b",
        r"\b[가-힣]{1,2}\s?\d{2,3}\s?[가-힣]\s?\d{4}\b",
    ],
    "ROAD_ADDRESS": [
        # [ \t] → \s? 로 변경: 인접 라인 병합 시 로/길 뒤 번지가 다음 줄에 있어도 매칭
        # 단, 앞쪽 주소 prefix는 [ \t] 유지 (줄바꿈 포함 시 다른 줄로 번지는 탐욕적 매칭 방지)
        r"\b[가-힣0-9·\-[ \t]]+(?:로|길)\s?\d+(?:-\d+)?(?:\s?\d+[동층호실]*)?\b"
    ],
    "NAME": [
        # 레이블 뒤 이름
        r"(?:성\s*명|이\s*름|대\s*표\s*이\s*사|대표자|원\s*장|사\s*장|담당자|신청인|보호자|환\s*자|예\s*금\s*주|배\s*통\s*자|수\s*취\s*인|송\s*금\s*인|본\s*인|세\s*대\s*주)[\s\n:：]*([가-힣]{2,4})\b",
    ],
}

TYPE_NORMALIZE_MAP = {
    "전화번호": "PHONE", "휴대폰": "PHONE", "휴대전화": "PHONE", "핸드폰": "PHONE",
    "이메일": "EMAIL", "이메일주소": "EMAIL", "email": "EMAIL",
    "주민등록번호": "RRN", "주민번호": "RRN",
    "외국인등록번호": "FOREIGNER_REG_NO",
    "사업자등록번호": "BUSINESS_REG_NO",
    "계좌번호": "ACCOUNT_NO", "은행계좌": "ACCOUNT_NO",
    "건강보험번호": "HEALTH_INSURANCE_NO", "건강보험": "HEALTH_INSURANCE_NO",
    "신용카드번호": "CREDIT_CARD", "카드번호": "CREDIT_CARD",
    "여권번호": "PASSPORT_NO",
    "ip주소": "IP_ADDRESS", "ip": "IP_ADDRESS",
    "차량번호": "CAR_NO", "자동차번호": "CAR_NO", "차량번호판": "CAR_NO", "번호판": "CAR_NO",
    "도로명주소": "ROAD_ADDRESS", "주소": "ROAD_ADDRESS",
    "이름": "NAME", "성명": "NAME",
}

ALLOWED_TYPES = {
    "PHONE", "EMAIL", "RRN", "FOREIGNER_REG_NO", "BUSINESS_REG_NO",
    "ACCOUNT_NO", "HEALTH_INSURANCE_NO", "CREDIT_CARD", "PASSPORT_NO",
    "IP_ADDRESS", "CAR_NO", "ROAD_ADDRESS", "NAME"
}

# NAME 오탐 방지: 이름처럼 생겼지만 이름이 아닌 단어 블랙리스트
NAME_BLACKLIST = {
    # 레이블/키워드
    "성명", "이름", "전화", "이메일", "주소", "직위", "직책", "부서", "팀명",
    "담당자", "대표자", "대표이사", "원장", "사장", "담당", "신청인", "보호자",
    "예금주", "수취인", "송금인", "본인", "세대주", "환자",
    # 일반 조사/어미/단어
    "이나", "와의", "에서", "으로", "에게", "한국", "서울", "부산", "대구",
    "인천", "광주", "대전", "울산", "세종", "경기", "강원", "충북", "충남",
    "전북", "전남", "경북", "경남", "제주", "이하", "여백", "확인", "내용",
    "관계", "번호", "등록", "등본", "초본", "발급", "신청", "용도", "목적",
    "정보", "처리", "동의", "거부", "철회", "권리", "의무", "책임", "규정",
}

# LLM 보조 프롬프트: NAME + ROAD_ADDRESS, 원문 그대로 추출 (교정 금지)
AI_AUXILIARY_PROMPT = """아래 텍스트에서 다음 두 유형의 개인정보를 빠짐없이 찾아 JSON 배열로만 출력하라.
type은 반드시 NAME 또는 ROAD_ADDRESS 중 하나만 사용하라.
value는 원문 텍스트에 있는 그대로 추출하라. 절대 교정하거나 변형하지 마라.
같은 값이 여러 번 나와도 각각 별도 항목으로 추출하라.

NAME 규칙:
- 성명/이름/대표이사/대표자/원장/사장/담당자/신청인/보호자/환자/예금주/수취인/송금인 등 레이블 뒤 2~4글자 한글 이름
- 레이블 없이 단독으로 줄에 나오는 2~4글자 한글 이름도 추출 (이체확인증의 박채연, 배통자 같은 예금주/수취인 이름)
- 일반 명사, 회사명, 기관명, 지명은 제외
- 동일 이름이 여러 줄에 반복되면 각각 추출

ROAD_ADDRESS 규칙:
- 개인 주소, 회사 주소 모두 추출
- 로/길 포함 도로명 주소 (예: 경인로71길70, 동호로17길300)
- 건물명+호수 포함 주소도 추출 (예: 벽산디지털밸리 1102, 스마일원룸 106호)
- 한 줄에 여러 주소가 있으면 각각 별도 항목으로 추출
- OCR 오인식으로 글자가 심하게 깨진 경우에도 현주소/주소/거주지 등 레이블 뒤 내용이면 원문 그대로 추출
- 주소가 여러 줄에 걸쳐 있으면 각 줄을 각각 별도 항목으로 추출 (예: "서울특별시 중구 동호로17길 300,"과 "106호 (신당동, 스마일원룸)"을 각각 추출)

결과 없으면 [] 출력.
출력 예: [{{"type":"NAME","value":"홍길동"}},{{"type":"NAME","value":"홍길동"}},{{"type":"ROAD_ADDRESS","value":"서울 영등포구 경인로71길70"}}]

텍스트:
{text}"""

# LLM 보조가 담당하는 타입
AUXILIARY_TYPES = {"NAME", "ROAD_ADDRESS"}


# ============================================================
# 메인 함수: OCR pages → PII + bbox 한 번에 반환
# ============================================================

def extract_pii_from_pages(ocr_pages: list) -> list:
    """
    1차: 라인별 정규식 추출 → bbox 즉시 확정
    2차: 인접 라인 병합 후 정규식 (줄 걸침 PII 대응)
    3차: LLM 보조 추출 (NAME 등 문맥 의존형)

    반환: [{"type", "value", "page", "bbox"}, ...]
    """
    results = []

    # ── 1차: 라인별 정규식 ──────────────────────────────────
    for page in ocr_pages:
        page_num = page["page_number"]
        for line in page.get("lines", []):
            text = line.get("text", "")
            bbox = line.get("bbox")
            if not text or not bbox:
                continue

            processed = _preprocess_for_regex(text)

            for pii_type, patterns in PII_PATTERNS.items():
                for pattern in patterns:
                    for m in re.finditer(pattern, processed):
                        value = _get_match_value(m)
                        if not value:
                            continue
                        # NAME 블랙리스트: 라벨 단어 오탐 방지 (OCR 공백 포함 대응)
                        if pii_type == "NAME" and re.sub(r'\s+', '', value) in NAME_BLACKLIST:
                            continue
                        sub_bbox = _estimate_sub_bbox(value, text, bbox)
                        results.append({
                            "type": pii_type,
                            "value": value,
                            "page": page_num,
                            "bbox": sub_bbox or bbox,
                            "_context": text,  # LLM 검증용 임시 필드
                        })

    results = _deduplicate(results)
    logger.info(f"[1차 라인별 정규식] {len(results)}개 추출")

    # ── 2차: 인접 라인 병합 ─────────────────────────────────
    for page in ocr_pages:
        page_num = page["page_number"]
        lines = [l for l in page.get("lines", []) if l.get("text") and l.get("bbox")]

        for i in range(len(lines) - 1):
            l1, l2 = lines[i], lines[i + 1]
            # \n 구분자 사용: _preprocess_for_regex가 줄별로 처리하므로
            # 줄 경계 숫자끼리 합쳐지는 오탐 방지 (예: "84" + "123" → "84123")
            merged_text = l1["text"] + "\n" + l2["text"]
            processed = _preprocess_for_regex(merged_text)

            for pii_type, patterns in PII_PATTERNS.items():
                for pattern in patterns:
                    for m in re.finditer(pattern, processed):
                        value = _get_match_value(m)
                        if not value or _is_covered(value, pii_type, results):
                            continue
                        # NAME 블랙리스트: 라벨 단어 오탐 방지 (OCR 공백 포함 대응)
                        if pii_type == "NAME" and re.sub(r'\s+', '', value) in NAME_BLACKLIST:
                            continue
                        # 값이 어느 라인에 속하는지 먼저 확인 후 tight bbox 사용
                        # → 레이블(l1)까지 마스킹하는 문제 방지
                        # _estimate_sub_bbox는 라인 전체와 동일하면 None 반환하므로
                        # "값이 해당 라인에 존재하는가"를 별도로 판단해야 함
                        def _normalize_for_match(s):
                            s = re.sub(r'[\s\-\u2013\u2014\u2015\u2212.,]', '', str(s))
                            return s.replace('O','0').replace('o','0').replace('l','1').replace('I','1')

                        norm_val = _normalize_for_match(value)
                        if norm_val in _normalize_for_match(l1["text"]):
                            sub_bbox = _estimate_sub_bbox(value, l1["text"], l1["bbox"]) or l1["bbox"]
                        elif norm_val in _normalize_for_match(l2["text"]):
                            sub_bbox = _estimate_sub_bbox(value, l2["text"], l2["bbox"]) or l2["bbox"]
                        else:
                            # 정말 두 줄에 걸친 경우 fallback
                            sub_bbox = _merge_bboxes(l1["bbox"], l2["bbox"])
                        results.append({
                            "type": pii_type,
                            "value": value,
                            "page": page_num,
                            "bbox": sub_bbox,
                            "_context": l1["text"] + " " + l2["text"],  # LLM 검증용 임시 필드
                        })

    results = _deduplicate(results)
    logger.info(f"[2차 인접 라인 병합] 누적 {len(results)}개")

    # ── 정규식 추출 NAME LLM 검증 ────────────────────────────
    # 정규식은 레이블 뒤 한글을 기계적으로 잡기 때문에 조사/어미 오탐 가능성이 있음.
    # LLM으로 문맥 기반 검증 후 실제 이름이 아닌 항목 제거.
    results = _validate_regex_names(results)
    logger.info(f"[NAME LLM 검증] 완료 후 {len(results)}개")

    # ── 3차: LLM 보조 (NAME) ────────────────────────────────
    for page in ocr_pages:
        page_num = page["page_number"]
        lines = page.get("lines", [])
        page_text = "\n".join(l.get("text", "") for l in lines if l.get("text"))
        if not page_text.strip():
            continue

        ai_items = _extract_auxiliary_with_ai(page_text)

        for item in ai_items:
            # NAME 블랙리스트 필터: 레이블/일반단어 오탐 제거 (공백 제거 후 비교로 OCR 공백 오인식 대응)
            if item["type"] == "NAME" and re.sub(r'\s+', '', item["value"]) in NAME_BLACKLIST:
                logger.debug(f"[LLM 블랙리스트] NAME 오탐 제거: {item['value']}")
                continue
            # 2글자 한글이 조사/어미인 경우 제거 (받침 없는 2글자 중 한국어 일상어 패턴)
            if item["type"] == "NAME" and len(item["value"]) == 2:
                # 일반명사/동사어간 등 이름이 아닌 것들 추가 필터
                if re.search(r'[하되어이의을를은는가나]$', item["value"]):
                    logger.debug(f"[LLM 블랙리스트] 조사/어미 패턴 제거: {item['value']}")
                    continue

            # 해당 value가 등장하는 모든 bbox 찾기
            bboxes = _find_all_value_bboxes(item["value"], lines)
            if not bboxes:
                # bbox를 못 찾아도 pii_items 목록에는 포함 (bbox=None)
                if not _is_covered(item["value"], item["type"], results):
                    results.append({
                        "type": item["type"],
                        "value": item["value"],
                        "page": page_num,
                        "bbox": None,
                    })
            else:
                for bbox in bboxes:
                    # 이미 동일 bbox로 등록된 항목은 건너뜀
                    already = any(
                        r["type"] == item["type"]
                        and r["value"] == item["value"]
                        and r.get("bbox") == bbox
                        for r in results
                    )
                    if not already:
                        results.append({
                            "type": item["type"],
                            "value": item["value"],
                            "page": page_num,
                            "bbox": bbox,
                        })

    # 3차에서는 value+bbox 기준 중복 제거 (같은 이름이 다른 위치에 있으면 유지)
    seen = set()
    deduped_results = []
    for r in results:
        key = (r["type"], r["value"], str(r.get("bbox")))
        if key not in seen:
            seen.add(key)
            deduped_results.append(r)
    results = deduped_results

    logger.info(f"[3차 LLM 보조] 최종 {len(results)}개: {results}")

    return results


# ============================================================
# 유틸리티
# ============================================================

def _get_match_value(m: re.Match) -> str:
    """캡처 그룹이 있으면 group(1), 없으면 group(0) 반환."""
    if m.lastindex and m.lastindex >= 1:
        return m.group(1).strip()
    return m.group(0).strip()


def _is_covered(value: str, pii_type: str, existing: list) -> bool:
    """이미 추출된 목록에 같은 타입으로 포함되어 있는지 확인."""
    def sc(s):
        return re.sub(r'[\s\-\n\r\t]', '', str(s))

    val = sc(value)
    for item in existing:
        if item["type"] != pii_type:
            continue
        ex = sc(item["value"])
        if val in ex or ex in val:
            return True
        if pii_type == "ROAD_ADDRESS" and len(val) >= 10 and len(ex) >= 10:
            if val[:10] in ex or ex[:10] in val:
                return True
    return False


def _merge_bboxes(bbox1: list, bbox2: list) -> list:
    """두 bbox를 감싸는 최소 bbox 반환."""
    if not bbox1:
        return bbox2
    if not bbox2:
        return bbox1
    return [
        min(bbox1[0], bbox2[0]),
        min(bbox1[1], bbox2[1]),
        max(bbox1[2], bbox2[2]),
        max(bbox1[3], bbox2[3]),
    ]


def _find_all_value_bboxes(value: str, lines: list) -> list:
    """LLM이 반환한 value가 등장하는 모든 라인의 bbox를 반환 (중복 위치 대응)."""
    def normalize(s):
        s = re.sub(r'[\s\-\u2013\u2014\u2015\u2212.,]', '', str(s))
        return s.replace('O', '0').replace('o', '0').replace('l', '1').replace('I', '1')

    norm_val = normalize(value)
    found = []
    for line in lines:
        norm_line = normalize(line.get("text", ""))
        bbox = line.get("bbox")
        if bbox and norm_val in norm_line:
            sub_bbox = _estimate_sub_bbox(value, line.get("text", ""), bbox)
            found.append(sub_bbox or bbox)
    return found


def _deduplicate(results: list) -> list:
    """type 내에서 value가 부분 문자열 관계인 경우 중복 제거."""
    def sc(s):
        return re.sub(r'[\s\-\n\r\t]', '', str(s))

    deduped = []
    for item in results:
        val = sc(item["value"])
        is_dup = False
        for existing in deduped:
            if existing["type"] != item["type"]:
                continue
            ex = sc(existing["value"])
            if val == ex or val in ex or ex in val:
                is_dup = True
                break
        if not is_dup:
            deduped.append(item)
    return deduped


def _validate_regex_names(results: list) -> list:
    """
    정규식으로 추출된 NAME 항목을 LLM으로 검증.
    실제 이름이 아닌 항목(조사, 어미, 일반 단어 등)을 제거하고
    _context 임시 필드도 함께 정리.
    NAME이 아닌 타입은 그대로 통과.
    """
    name_items = [(i, r) for i, r in enumerate(results) if r["type"] == "NAME"]

    if not name_items:
        # _context 필드만 정리
        for r in results:
            r.pop("_context", None)
        return results

    candidates = [
        {"idx": i, "value": r["value"], "context": r.get("_context", r["value"])}
        for i, r in name_items
    ]

    items_text = "\n".join(
        f'{n+1}. 문장: "{c["context"]}" | 추출값: "{c["value"]}"'
        for n, c in enumerate(candidates)
    )
    prompt = f"""아래 각 항목에서 '추출값'이 실제 사람 이름인지 판단하라.
레이블(본인/세대주/담당자 등) 바로 뒤에 붙은 조사·어미이거나 일반 단어이면 NO.
실제 사람 이름(2~4글자 한글)이면 YES.
JSON 배열로만 출력. 형식: [{{"i":1,"name":true}},{{"i":2,"name":false}}]

{items_text}"""

    try:
        raw = call_exaone(prompt)
        cleaned = re.sub(r'```(?:json)?', '', raw).strip().rstrip('`')
        m = re.search(r'\[.*\]', cleaned, re.DOTALL)
        if not m:
            logger.warning("[NAME 검증 LLM] JSON 파싱 실패, 전부 통과")
            valid_result_indices = {c["idx"] for c in candidates}
        else:
            parsed = json.loads(m.group(0))
            # YES인 항목의 원본 results 인덱스
            valid_result_indices = set()
            for item in parsed:
                n = item.get("i", 0) - 1  # 0-based
                if 0 <= n < len(candidates) and item.get("name") is True:
                    valid_result_indices.add(candidates[n]["idx"])
        logger.info(f"[NAME 검증 LLM] {len(name_items)}개 중 {len(valid_result_indices)}개 실제 이름으로 확인")
    except Exception as e:
        logger.warning(f"[NAME 검증 LLM] 오류: {e}, 전부 통과")
        valid_result_indices = {c["idx"] for c in candidates}

    # 검증 통과 여부 반영 + _context 필드 제거
    filtered = []
    for i, r in enumerate(results):
        r.pop("_context", None)
        if r["type"] == "NAME" and i in {c["idx"] for c in candidates}:
            if i in valid_result_indices:
                filtered.append(r)
        else:
            filtered.append(r)
    return filtered


def _extract_auxiliary_with_ai(page_text: str) -> list:
    """LLM으로 NAME + ROAD_ADDRESS 추출 (2회 호출 후 합집합). 원문 그대로 반환."""
    prompt = AI_AUXILIARY_PROMPT.format(text=page_text)
    all_items = []
    for attempt in range(2):
        raw = call_exaone(prompt)
        parsed = _parse_ai_response(raw)
        aux_items = [i for i in parsed if i.get("type") in AUXILIARY_TYPES]
        logger.info(f"[LLM 보조] 시도 {attempt + 1}: {aux_items}")
        all_items.extend(aux_items)

    seen = set()
    deduped = []
    for item in all_items:
        if item["value"] not in seen:
            seen.add(item["value"])
            deduped.append(item)
    return deduped


# ============================================================
# 정규식 전처리
# ============================================================

def _fix_ocr_ip(text: str) -> str:
    """OCR로 망가진 IP 주소 복원."""
    octet_pat = r'(?:\d{1,2}\s\d{1,2}|\d{1,3})'
    sep_pat   = r'[\s.,]+'
    full_pat  = rf'\b({octet_pat}){sep_pat}({octet_pat}){sep_pat}({octet_pat}){sep_pat}({octet_pat})\b'

    def _normalize(m: re.Match) -> str:
        full = m.group(0)
        if not re.search(r'[.,]', full):
            return full
        parts = [re.sub(r'\s+', '', m.group(i)) for i in range(1, 5)]
        try:
            if all(p.isdigit() and 0 <= int(p) <= 255 for p in parts):
                return '.'.join(parts)
        except ValueError:
            pass
        return full

    return re.sub(full_pat, _normalize, text)


def _preprocess_for_regex(text: str) -> str:
    """OCR 오인식 보정. 줄바꿈은 절대 제거하지 않는다."""
    processed_lines = []
    for line in text.split('\n'):
        line = _fix_ocr_ip(line)
        # en/em-dash → 일반 하이픈 (예: "980115–2823649" → "980115-2823649")
        line = re.sub(r'[\u2013\u2014\u2015\u2212]', '-', line)
        # 숫자 문맥에서 OCR 오인식 보정: 숫자/하이픈 인접한 O→0, l/I→1
        # 예: "07O-7829-5335" → "070-7829-5335"
        line = re.sub(r'(?<=[\d\-])[Oo](?=[\d\-])', '0', line)
        line = re.sub(r'(?<=\d)[Oo](?=[\d\-])', '0', line)
        line = re.sub(r'(?<=[\d\-])[lI](?=[\d\-])', '1', line)
        line = re.sub(r'(?<=\d)[lI](?=[\d\-])', '1', line)
        # 숫자-숫자/하이픈 사이 공백 제거
        line = re.sub(r'(?<=\d)[ \t]+(?=[\d\-])', '', line)
        line = re.sub(r'(?<=[\d\-])[ \t]+(?=\d)', '', line)
        processed_lines.append(line)
    return '\n'.join(processed_lines)


# ============================================================
# Sub-bbox 추정 (라인 일부에 PII가 있는 경우)
# ============================================================

def _char_visual_width(c: str) -> float:
    """문자 시각적 너비 추정. 한글/한자 등 전각 문자는 2, 나머지는 1."""
    cp = ord(c)
    if (0x1100 <= cp <= 0x11FF   # 한글 자모
            or 0x3000 <= cp <= 0x9FFF   # CJK 기호/한자
            or 0xAC00 <= cp <= 0xD7A3   # 한글 완성형
            or 0xF900 <= cp <= 0xFAFF   # CJK 호환 한자
            or 0xFF01 <= cp <= 0xFF60): # 전각 ASCII
        return 2.0
    return 1.0


def _text_visual_width(text: str) -> float:
    return sum(_char_visual_width(c) for c in text)


def _estimate_sub_bbox(pii_value: str, line_text_orig: str, line_bbox: list):
    """
    PII 값이 라인의 일부일 때 해당 부분의 bbox 추정.
    OCR 오인식(O↔0, l↔1)을 허용하는 regex로 위치를 찾고
    문자별 시각적 너비 비율로 x좌표를 보간한다 (한글은 2배 너비).
    라인 전체와 동일하거나 위치를 못 찾으면 None 반환.
    """
    if not line_text_orig or not pii_value:
        return None

    ocr_map = {'0': '[0Oo]', '1': '[1lI]', 'O': '[0Oo]', 'o': '[0Oo]',
               'l': '[1lI]', 'I': '[1lI]'}
    pattern_parts = []
    for orig_c in pii_value:
        if orig_c in ocr_map:
            pattern_parts.append(ocr_map[orig_c])
        else:
            pattern_parts.append(re.escape(orig_c))

    pii_pattern = r'[\s\-]*'.join(pattern_parts)

    match = re.search(pii_pattern, line_text_orig)
    if not match:
        return None

    start_char = match.start()
    end_char   = match.end()
    total_len  = len(line_text_orig)

    if start_char == 0 and end_char >= total_len:
        return None

    # 시각적 너비 기준으로 비율 계산 (한글 2x, ASCII 1x)
    total_visual = _text_visual_width(line_text_orig)
    if total_visual == 0:
        return None
    start_visual = _text_visual_width(line_text_orig[:start_char])
    end_visual   = _text_visual_width(line_text_orig[:end_char])

    x1, y1, x2, y2 = line_bbox
    line_width   = x2 - x1
    start_ratio  = start_visual / total_visual
    end_ratio    = end_visual   / total_visual

    sub_x1 = x1 + start_ratio * line_width
    sub_x2 = x1 + end_ratio * line_width

    return [sub_x1, y1, sub_x2, y2]


# ============================================================
# AI 응답 파싱
# ============================================================

def _parse_ai_response(raw: str) -> list:
    """AI 응답에서 JSON 배열을 파싱해 정규화된 item 목록 반환."""
    try:
        cleaned = raw.strip()
        cleaned = re.sub(r"```json", "", cleaned)
        cleaned = re.sub(r"```", "", cleaned)
        cleaned = re.sub(r",\s*([}\]])", r"\1", cleaned)

        match = re.search(r"\[.*\]", cleaned, re.DOTALL)
        if not match:
            logger.warning("[AI] JSON 배열 없음")
            return []

        items = json.loads(match.group(0))
        result = []
        for item in items:
            if not isinstance(item, dict):
                continue
            if "type" not in item or "value" not in item:
                continue
            value = str(item["value"]).strip()
            if not value:
                continue
            normalized = normalize_type(item["type"])
            if normalized not in ALLOWED_TYPES:
                logger.debug(f"[AI] 알 수 없는 type 버림: {normalized}")
                continue
            result.append({"type": normalized, "value": value})
        return result

    except Exception as e:
        logger.warning(f"[AI] 파싱 실패: {e}")
        return []


def normalize_type(raw_type: str) -> str:
    key = raw_type.strip().lower().replace(" ", "")
    return TYPE_NORMALIZE_MAP.get(key, raw_type.strip().upper())


# ============================================================
# 마스킹 값 생성
# ============================================================

def mask_value(pii_type: str, value: str) -> str:
    """
    기준:
      NAME            성 제외 나머지 *               홍**
      ENGLISH_NAME    앞 4자리 노출, 나머지 *         SEO ******
      PHONE           뒤 4자리 ****                  010-1234-****
      RRN             뒤 7자리 *******               980115-*******
      FOREIGNER_REG_NO 뒤 7자리 *******              800101-*******
      PASSPORT_NO     뒤 4자리 ****                  12345****
      ROAD_ADDRESS    도로명 번호·동·층·호 숫자 *       주안로 * , ****동 ****호
      EMAIL           @ 앞 3번째 자리부터 *           sy******@naver.com
      CREDIT_CARD     PCI-DSS: 중간 4+4자리 ****     9430-2000-****-2391
      ACCOUNT_NO      뒤 5자리 *                     430-20-1*****
      IP_ADDRESS      첫 옥텟 ***                    ***.8.7.12
      BUSINESS_REG_NO 앞 3자리 제외 **-*****          123-**-*****
      HEALTH_INSURANCE_NO 뒤 4자리 ****              123456****
      CAR_NO          한글+뒤 4자리 마스킹             19*****
    """
    v = value.strip()

    if pii_type == "NAME":
        if len(v) >= 2:
            return v[0] + '*' * (len(v) - 1)
        return v

    elif pii_type == "ENGLISH_NAME":
        visible = min(4, len(v))
        return v[:visible] + '*' * max(0, len(v) - visible)

    elif pii_type == "PHONE":
        digits_pos = [i for i, c in enumerate(v) if c.isdigit()]
        if len(digits_pos) >= 4:
            result = list(v)
            for pos in digits_pos[-4:]:
                result[pos] = '*'
            return ''.join(result)
        return v

    elif pii_type in ("RRN", "FOREIGNER_REG_NO"):
        digits_pos = [i for i, c in enumerate(v) if c.isdigit()]
        if len(digits_pos) >= 7:
            result = list(v)
            for pos in digits_pos[-7:]:
                result[pos] = '*'
            return ''.join(result)
        return v

    elif pii_type == "PASSPORT_NO":
        if len(v) >= 4:
            return v[:-4] + '****'
        return v

    elif pii_type == "ROAD_ADDRESS":
        # 1. 괄호 안 상세정보 전체 마스킹 (예: (신당동, 스마일원룸) → (***))
        result = re.sub(r'\([^)]+\)', '(***)', v)
        # 2. 주소 내 모든 숫자 그룹 마스킹
        #    - OCR 오인식("길"→"긴")에 무관하게 번지/동/층/호/건물호수 전체 처리
        result = re.sub(r'\d+', lambda m: '*' * len(m.group()), result)
        return result

    elif pii_type == "EMAIL":
        if '@' in v:
            local, domain = v.split('@', 1)
            if len(local) > 2:
                return local[:2] + '*' * (len(local) - 2) + '@' + domain
            return v
        return v

    elif pii_type == "CREDIT_CARD":
        digits = re.sub(r'[\s\-]', '', v)
        if len(digits) == 16:
            return f"{digits[:4]}-{digits[4:8]}-****-{digits[12:]}"
        return re.sub(r'(?<=\d{4}[\-\s])\d{4}[\-\s]\d{4}(?=[\-\s]\d)', '****-****', v)

    elif pii_type == "ACCOUNT_NO":
        digits_pos = [i for i, c in enumerate(v) if c.isdigit()]
        if len(digits_pos) >= 5:
            result = list(v)
            for pos in digits_pos[-5:]:
                result[pos] = '*'
            return ''.join(result)
        return v

    elif pii_type == "IP_ADDRESS":
        return re.sub(r'^\d+', '***', v)

    elif pii_type == "BUSINESS_REG_NO":
        return re.sub(r'(\d{3})-\d{2}-\d{5}', r'\1-**-*****', v)

    elif pii_type == "HEALTH_INSURANCE_NO":
        digits_pos = [i for i, c in enumerate(v) if c.isdigit()]
        if len(digits_pos) >= 4:
            result = list(v)
            for pos in digits_pos[-4:]:
                result[pos] = '*'
            return ''.join(result)
        return v

    elif pii_type == "CAR_NO":
        return re.sub(r'(\d{2,3})\s?[가-힣]\s?\d{4}', lambda m: m.group(1) + '*****', v)

    half = max(1, len(v) // 2)
    return v[:half] + '*' * (len(v) - half)


# ============================================================
# EXAONE LLM 호출
# ============================================================

def call_exaone(prompt, temperature=0.3):
    url = "http://211.233.58.220:8079/api/generate"
    model_name = "exaone3.5:32b"

    payload = {
        "model": model_name,
        "prompt": prompt,
        "stream": False,
        "options": {
            "temperature": temperature,
            "top_p": 0.9,
            "num_predict": 2048
        }
    }

    try:
        res = requests.post(url, json=payload, timeout=60)
        res.raise_for_status()
        data = res.json()
        logger.info("[EXAONE] 응답 수신 완료")
        return data.get("response", "")

    except requests.exceptions.Timeout:
        logger.error("[EXAONE] timeout")
        return ""

    except requests.exceptions.RequestException as e:
        logger.error(f"[EXAONE] 요청 실패: {e}")
        return ""
