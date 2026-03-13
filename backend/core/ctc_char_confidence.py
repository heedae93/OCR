"""
Custom CTC Label Decoder with Character-Level Confidence
Extracts per-character confidence scores from CTC output
"""
import numpy as np
from typing import List, Tuple, Dict, Any


class CTCCharConfidenceDecoder:
    """
    CTC 디코더 - 문자별 confidence 추출

    PaddleOCR의 CTCLabelDecode를 확장하여 각 문자별 확률을 반환
    """

    def __init__(self, character_list: List[str] = None, use_space_char: bool = True):
        """
        Args:
            character_list: 문자 사전 리스트
            use_space_char: 공백 문자 사용 여부
        """
        if character_list is None:
            character_list = list("0123456789abcdefghijklmnopqrstuvwxyz")

        if use_space_char and " " not in character_list:
            character_list = list(character_list) + [" "]

        # CTC blank token을 맨 앞에 추가
        self.character = ["blank"] + list(character_list)
        self.dict = {char: i for i, char in enumerate(self.character)}

    def decode_with_char_confidence(
        self,
        preds: np.ndarray,
        return_details: bool = False
    ) -> List[Dict[str, Any]]:
        """
        CTC 출력에서 문자별 confidence 추출

        Args:
            preds: 모델 출력 (batch_size, seq_len, vocab_size)
            return_details: 상세 정보 반환 여부

        Returns:
            List of dicts with:
                - text: 인식된 텍스트
                - score: 평균 confidence (기존 호환)
                - char_confidences: 각 문자별 confidence 리스트
                - char_details: (optional) 각 문자의 상세 정보
        """
        if isinstance(preds, (list, tuple)):
            preds = np.array(preds[0])
        else:
            preds = np.array(preds)

        # Softmax가 적용되지 않은 경우 적용
        if preds.max() > 1.0 or preds.min() < 0.0:
            # Apply softmax
            preds = self._softmax(preds)

        results = []
        batch_size = preds.shape[0]

        for batch_idx in range(batch_size):
            pred = preds[batch_idx]  # (seq_len, vocab_size)

            # 각 timestep에서 최고 확률 문자와 확률
            pred_idx = pred.argmax(axis=-1)  # (seq_len,)
            pred_prob = pred.max(axis=-1)    # (seq_len,)

            # CTC 디코딩: blank 제거 및 중복 제거
            char_list = []
            conf_list = []
            char_details = []

            prev_idx = -1
            for t, (idx, prob) in enumerate(zip(pred_idx, pred_prob)):
                # blank token (index 0) 스킵
                if idx == 0:
                    prev_idx = idx
                    continue

                # 중복 문자 스킵 (CTC 디코딩)
                if idx == prev_idx:
                    continue

                # 유효한 문자 추가
                if idx < len(self.character):
                    char = self.character[idx]
                    char_list.append(char)
                    conf_list.append(float(prob))

                    if return_details:
                        # Top-3 후보와 확률
                        top_k = 3
                        top_indices = pred[t].argsort()[-top_k:][::-1]
                        alternatives = [
                            {
                                'char': self.character[i] if i < len(self.character) else '?',
                                'prob': float(pred[t][i])
                            }
                            for i in top_indices
                        ]

                        char_details.append({
                            'char': char,
                            'confidence': float(prob),
                            'timestep': t,
                            'alternatives': alternatives
                        })

                prev_idx = idx

            text = "".join(char_list)
            mean_score = float(np.mean(conf_list)) if conf_list else 0.0

            result = {
                'text': text,
                'score': mean_score,
                'char_confidences': conf_list
            }

            if return_details:
                result['char_details'] = char_details

            results.append(result)

        return results

    def _softmax(self, x: np.ndarray) -> np.ndarray:
        """Numerically stable softmax"""
        x = x - np.max(x, axis=-1, keepdims=True)
        exp_x = np.exp(x)
        return exp_x / np.sum(exp_x, axis=-1, keepdims=True)

    def __call__(self, preds) -> Tuple[List[str], List[float], List[List[float]]]:
        """
        기존 인터페이스 호환 + 문자별 confidence 추가

        Returns:
            texts: 인식된 텍스트 리스트
            scores: 평균 confidence 리스트
            char_confidences: 각 텍스트의 문자별 confidence 리스트
        """
        results = self.decode_with_char_confidence(preds)

        texts = [r['text'] for r in results]
        scores = [r['score'] for r in results]
        char_confidences = [r['char_confidences'] for r in results]

        return texts, scores, char_confidences


def patch_paddlex_ctc_decoder():
    """
    PaddleX의 CTCLabelDecode를 패치하여 문자별 confidence 반환

    주의: 이 함수는 모델 로딩 전에 호출해야 함
    """
    try:
        from paddlex.inference.models.text_recognition import processors

        # 원본 클래스 백업
        OriginalCTCLabelDecode = processors.CTCLabelDecode

        class PatchedCTCLabelDecode(OriginalCTCLabelDecode):
            """패치된 CTC 디코더 - 문자별 confidence 포함"""

            def __call__(self, pred):
                """문자별 confidence도 함께 반환"""
                preds = np.array(pred[0])
                preds_idx = preds.argmax(axis=-1)
                preds_prob = preds.max(axis=-1)

                # 수정된 decode 호출
                text_results = self.decode_with_char_conf(
                    preds_idx, preds_prob, is_remove_duplicate=True
                )

                texts = []
                scores = []
                char_confs = []

                for text, score, conf_list in text_results:
                    texts.append(text)
                    scores.append(score)
                    char_confs.append(conf_list)

                # 기존 호환성을 위해 char_confs를 별도 속성으로 저장
                self._last_char_confidences = char_confs

                return texts, scores

            def decode_with_char_conf(self, text_index, text_prob=None, is_remove_duplicate=False):
                """문자별 confidence 포함 디코딩"""
                result_list = []
                ignored_tokens = self.get_ignored_tokens()
                batch_size = len(text_index)

                for batch_idx in range(batch_size):
                    selection = np.ones(len(text_index[batch_idx]), dtype=bool)
                    if is_remove_duplicate:
                        selection[1:] = text_index[batch_idx][1:] != text_index[batch_idx][:-1]
                    for ignored_token in ignored_tokens:
                        selection &= text_index[batch_idx] != ignored_token

                    char_list = [
                        self.character[text_id]
                        for text_id in text_index[batch_idx][selection]
                    ]

                    if text_prob is not None:
                        conf_list = text_prob[batch_idx][selection].tolist()
                    else:
                        conf_list = [1.0] * len(char_list)

                    if len(conf_list) == 0:
                        conf_list = [0.0]

                    text = "".join(char_list)
                    mean_conf = float(np.mean(conf_list))

                    result_list.append((text, mean_conf, conf_list))

                return result_list

            def get_last_char_confidences(self):
                """마지막 예측의 문자별 confidence 반환"""
                return getattr(self, '_last_char_confidences', None)

        # 패치 적용
        processors.CTCLabelDecode = PatchedCTCLabelDecode

        return True
    except Exception as e:
        print(f"Failed to patch CTCLabelDecode: {e}")
        return False


class CharConfidenceExtractor:
    """
    OCR 결과에서 문자별 confidence를 추출하는 유틸리티 클래스
    PaddleOCR 파이프라인과 통합하여 사용
    """

    def __init__(self, character_dict_path: str = None):
        """
        Args:
            character_dict_path: 문자 사전 파일 경로
        """
        self.character_list = None
        if character_dict_path:
            self.load_character_dict(character_dict_path)

        self.decoder = None

    def load_character_dict(self, dict_path: str):
        """문자 사전 로드"""
        try:
            with open(dict_path, 'r', encoding='utf-8') as f:
                chars = [line.strip() for line in f if line.strip()]
            self.character_list = chars
        except Exception as e:
            print(f"Failed to load character dict: {e}")
            self.character_list = None

    def get_decoder(self) -> CTCCharConfidenceDecoder:
        """디코더 인스턴스 반환"""
        if self.decoder is None:
            self.decoder = CTCCharConfidenceDecoder(
                character_list=self.character_list
            )
        return self.decoder

    def extract_from_predictions(
        self,
        predictions: np.ndarray
    ) -> List[Dict[str, Any]]:
        """
        모델 예측값에서 문자별 confidence 추출

        Args:
            predictions: CTC 출력 (batch_size, seq_len, vocab_size)

        Returns:
            문자별 confidence가 포함된 결과 리스트
        """
        decoder = self.get_decoder()
        return decoder.decode_with_char_confidence(predictions, return_details=True)


class HeuristicCharConfidenceEstimator:
    """
    휴리스틱 기반 문자별 confidence 추정기

    라인 레벨 confidence만 있을 때 문자별 confidence를 추정
    - 문자 유형별 가중치 적용
    - 언어별 특성 반영
    - 문맥 기반 조정
    """

    # 문자 유형별 기본 가중치
    CHAR_TYPE_WEIGHTS = {
        'digit': 1.05,          # 숫자는 인식이 잘 됨
        'latin_upper': 1.02,    # 대문자
        'latin_lower': 1.0,     # 소문자
        'hangul_common': 1.0,   # 흔한 한글
        'hangul_rare': 0.90,    # 드문 한글
        'punctuation': 0.95,    # 구두점
        'space': 1.0,           # 공백
        'hanja': 0.75,          # 한자 (드물어서 오인식 많음)
        'japanese': 0.70,       # 일본어 (한국어 모델에서)
        'special': 0.85,        # 특수문자
        'unknown': 0.60,        # 알 수 없는 문자
    }

    # 흔한 한글 자모 (초성)
    COMMON_KOREAN_INITIALS = set('ㄱㄴㄷㄹㅁㅂㅅㅇㅈㅊㅋㅌㅍㅎ')

    # 의심스러운 패턴 (오인식 가능성 높음)
    SUSPICIOUS_PATTERNS = [
        (r'[ぁ-んァ-ン]', 0.5),   # 일본어 문자 in 한국어 문서
        (r'[一-龥]', 0.7),        # 한자
        (r'[А-я]', 0.6),         # 키릴 문자
        (r'[\u4e00-\u9fff]', 0.75),  # CJK 통합 한자
    ]

    def __init__(self):
        import re
        self.re = re

        # 유니코드 범위 정의
        self.korean_range = (0xAC00, 0xD7AF)  # 한글 음절
        self.korean_jamo = (0x1100, 0x11FF)   # 한글 자모
        self.hanja_ranges = [
            (0x4E00, 0x9FFF),   # CJK 통합 한자
            (0x3400, 0x4DBF),   # CJK 확장 A
        ]
        self.japanese_ranges = [
            (0x3040, 0x309F),   # 히라가나
            (0x30A0, 0x30FF),   # 가타카나
        ]

    def get_char_type(self, char: str) -> str:
        """문자 유형 판별"""
        if not char:
            return 'unknown'

        code = ord(char)

        # 숫자
        if char.isdigit():
            return 'digit'

        # 공백
        if char.isspace():
            return 'space'

        # 라틴 문자
        if char.isalpha() and ord(char) < 128:
            return 'latin_upper' if char.isupper() else 'latin_lower'

        # 한글
        if self.korean_range[0] <= code <= self.korean_range[1]:
            # 흔한 한글인지 체크 (간단한 휴리스틱)
            return 'hangul_common'

        if self.korean_jamo[0] <= code <= self.korean_jamo[1]:
            return 'hangul_common'

        # 한자
        for start, end in self.hanja_ranges:
            if start <= code <= end:
                return 'hanja'

        # 일본어
        for start, end in self.japanese_ranges:
            if start <= code <= end:
                return 'japanese'

        # 구두점
        if char in '.,;:!?\'\"()[]{}/<>-_=+*&^%$#@~`|\\':
            return 'punctuation'

        # 기타 특수문자
        if not char.isalnum():
            return 'special'

        return 'unknown'

    def estimate_char_confidences(
        self,
        text: str,
        line_confidence: float,
        context: dict = None
    ) -> List[Dict[str, Any]]:
        """
        라인 confidence로부터 문자별 confidence 추정

        Args:
            text: 인식된 텍스트
            line_confidence: 라인 레벨 confidence (0-1)
            context: 추가 컨텍스트 정보 (optional)
                - document_language: 문서 언어
                - is_title: 제목 여부
                - bbox_height: 바운딩 박스 높이

        Returns:
            문자별 confidence 정보 리스트
        """
        if not text:
            return []

        results = []

        # 기본 confidence (라인 confidence를 기반으로)
        base_conf = line_confidence

        for i, char in enumerate(text):
            char_type = self.get_char_type(char)
            weight = self.CHAR_TYPE_WEIGHTS.get(char_type, 0.8)

            # 문자별 confidence 계산
            char_conf = base_conf * weight

            # 문맥 기반 조정
            char_conf = self._apply_context_adjustment(
                char, char_conf, text, i, context
            )

            # 0-1 범위로 클리핑
            char_conf = max(0.0, min(1.0, char_conf))

            results.append({
                'char': char,
                'confidence': char_conf,
                'char_type': char_type,
                'position': i,
                'suspicious': char_conf < 0.8
            })

        return results

    def _apply_context_adjustment(
        self,
        char: str,
        base_conf: float,
        text: str,
        position: int,
        context: dict = None
    ) -> float:
        """문맥 기반 confidence 조정"""
        conf = base_conf

        # 1. 의심스러운 패턴 체크
        for pattern, penalty in self.SUSPICIOUS_PATTERNS:
            if self.re.match(pattern, char):
                conf *= penalty
                break

        # 2. 연속 같은 문자 (오인식 가능성)
        if position > 0 and text[position - 1] == char:
            # 같은 문자가 3번 이상 연속이면 의심
            if position > 1 and text[position - 2] == char:
                conf *= 0.85

        # 3. 한글 문서에서 비한글 문자 단독 출현
        if context and context.get('document_language') == 'ko':
            char_type = self.get_char_type(char)
            if char_type in ['hanja', 'japanese']:
                # 앞뒤에 한글이 없으면 더 의심
                has_korean_neighbor = False
                if position > 0:
                    prev_type = self.get_char_type(text[position - 1])
                    if prev_type.startswith('hangul'):
                        has_korean_neighbor = True
                if position < len(text) - 1:
                    next_type = self.get_char_type(text[position + 1])
                    if next_type.startswith('hangul'):
                        has_korean_neighbor = True

                if not has_korean_neighbor:
                    conf *= 0.8

        # 4. 작은 bbox에서의 문자 (인식이 어려움)
        if context and context.get('bbox_height'):
            height = context['bbox_height']
            if height < 15:  # 매우 작은 텍스트
                conf *= 0.9
            elif height < 10:
                conf *= 0.8

        return conf

    def estimate_batch(
        self,
        ocr_results: List[Dict],
        document_language: str = 'ko'
    ) -> List[Dict]:
        """
        배치 OCR 결과에 대해 문자별 confidence 추정

        Args:
            ocr_results: OCR 결과 리스트 (text, bbox, score 포함)
            document_language: 문서 언어

        Returns:
            문자별 confidence가 추가된 OCR 결과
        """
        enhanced_results = []

        for result in ocr_results:
            text = result.get('text', '')
            score = result.get('score', 0.9)
            bbox = result.get('bbox', None)

            # bbox에서 높이 추출
            bbox_height = None
            if bbox and len(bbox) == 4:
                bbox_height = bbox[3] - bbox[1]  # bottom - top

            context = {
                'document_language': document_language,
                'bbox_height': bbox_height,
            }

            char_confidences = self.estimate_char_confidences(
                text, score, context
            )

            enhanced_result = {
                **result,
                'char_confidences': char_confidences
            }
            enhanced_results.append(enhanced_result)

        return enhanced_results


def add_char_confidences_to_ocr_result(ocr_data: dict) -> dict:
    """
    OCR JSON 결과에 문자별 confidence 추가

    Args:
        ocr_data: OCR 결과 JSON (pages, lines 포함)

    Returns:
        char_confidences가 추가된 OCR 결과
    """
    estimator = HeuristicCharConfidenceEstimator()

    for page in ocr_data.get('pages', []):
        for line in page.get('lines', []):
            text = line.get('text', '')
            score = line.get('confidence', 0.9)
            bbox = line.get('bbox', [0, 0, 100, 30])

            # bbox에서 높이 추출
            bbox_height = bbox[3] - bbox[1] if len(bbox) == 4 else 30

            context = {
                'document_language': 'ko',
                'bbox_height': bbox_height,
            }

            char_confs = estimator.estimate_char_confidences(text, score, context)
            line['char_confidences'] = char_confs

    return ocr_data


# 테스트 코드
if __name__ == "__main__":
    # 휴리스틱 추정기 테스트
    estimator = HeuristicCharConfidenceEstimator()

    test_cases = [
        ("한글 테스트", 0.95),
        ("2020 , 06 , 02(기증 )", 0.87),
        ("至您", 0.14),  # 한자 - 낮은 confidence
        ("Hello World 123", 0.92),
    ]

    print("=" * 60)
    print("Heuristic Character Confidence Estimation Test")
    print("=" * 60)

    for text, line_conf in test_cases:
        print(f"\nText: '{text}' (line_conf: {line_conf})")
        char_confs = estimator.estimate_char_confidences(
            text, line_conf, {'document_language': 'ko'}
        )
        for cc in char_confs:
            suspicious = "⚠️" if cc['suspicious'] else "✓"
            print(f"  [{cc['char']}] {cc['confidence']:.2f} ({cc['char_type']}) {suspicious}")
