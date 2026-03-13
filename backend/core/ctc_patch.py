"""
PaddleX CTC Decoder Patch - 실제 문자별 confidence 추출

이 모듈은 PaddleX의 CTCLabelDecode를 패치하여
각 문자별 실제 CTC 확률을 추출합니다.
"""
import numpy as np
import logging
from typing import List, Tuple, Dict, Any, Optional

logger = logging.getLogger(__name__)

# 전역 저장소: 예측의 (텍스트, 문자별 confidence) 쌍 (누적)
_text_conf_pairs: List[Tuple[str, List[float]]] = []
_is_accumulating: bool = False  # 누적 모드 플래그


def start_accumulating():
    """누적 모드 시작 - OCR 처리 시작 전 호출"""
    global _text_conf_pairs, _is_accumulating
    _text_conf_pairs = []
    _is_accumulating = True


def stop_accumulating() -> List[Tuple[str, List[float]]]:
    """누적 모드 종료 및 결과 반환 - OCR 처리 완료 후 호출"""
    global _text_conf_pairs, _is_accumulating
    result = _text_conf_pairs.copy()
    _text_conf_pairs = []
    _is_accumulating = False
    return result


def get_char_confidences_for_texts(final_texts: List[str],
                                    pairs: List[Tuple[str, List[float]]] = None) -> List[List[float]]:
    """
    최종 텍스트 목록에 대한 문자별 confidence 매칭

    디코딩 순서와 최종 결과 순서가 다를 수 있으므로
    텍스트 내용으로 매칭합니다.

    Args:
        final_texts: 최종 인식된 텍스트 목록
        pairs: (텍스트, confidence) 쌍 목록 (없으면 전역 저장소 사용)
    """
    global _text_conf_pairs

    source_pairs = pairs if pairs is not None else _text_conf_pairs

    # 텍스트별 confidence 딕셔너리 생성 (중복 텍스트 처리를 위해 리스트 사용)
    text_to_confs: Dict[str, List[List[float]]] = {}
    for text, confs in source_pairs:
        if text not in text_to_confs:
            text_to_confs[text] = []
        text_to_confs[text].append(confs)

    # 각 텍스트에 대해 confidence 찾기
    result = []
    used_indices: Dict[str, int] = {}  # 같은 텍스트가 여러 번 나올 때 순서대로 사용

    for text in final_texts:
        if text in text_to_confs:
            idx = used_indices.get(text, 0)
            confs_list = text_to_confs[text]
            if idx < len(confs_list):
                result.append(confs_list[idx])
                used_indices[text] = idx + 1
            else:
                # 더 이상 매칭할 confidence가 없음
                result.append([])
        else:
            result.append([])

    return result


def get_last_char_confidences() -> List[List[float]]:
    """저장된 문자별 confidence 반환 (하위 호환성)"""
    global _text_conf_pairs
    return [confs for _, confs in _text_conf_pairs]


def clear_char_confidences():
    """저장된 confidence 초기화"""
    global _text_conf_pairs
    _text_conf_pairs = []


def _append_text_conf_pairs(pairs: List[Tuple[str, List[float]]]):
    """(텍스트, confidence) 쌍 추가 (내부 사용)"""
    global _text_conf_pairs, _is_accumulating
    if _is_accumulating:
        _text_conf_pairs.extend(pairs)
    else:
        _text_conf_pairs = pairs


def patch_ctc_decoder():
    """
    PaddleX의 CTCLabelDecode를 패치하여 문자별 confidence 추출

    Returns:
        True if patching succeeded, False otherwise
    """
    global _last_char_confidences

    try:
        from paddlex.inference.models.text_recognition import processors

        # 원본 클래스 백업
        OriginalCTCLabelDecode = processors.CTCLabelDecode
        OriginalBaseRecLabelDecode = processors.BaseRecLabelDecode

        class PatchedBaseRecLabelDecode(OriginalBaseRecLabelDecode):
            """패치된 Base 디코더 - 문자별 confidence 반환"""

            def decode(self, text_index, text_prob=None, is_remove_duplicate=False):
                """문자별 confidence를 포함하여 디코딩"""
                result_list = []
                char_conf_list = []  # 문자별 confidence 저장
                ignored_tokens = self.get_ignored_tokens()
                batch_size = len(text_index)


                for batch_idx in range(batch_size):
                    selection = np.ones(len(text_index[batch_idx]), dtype=bool)
                    if is_remove_duplicate:
                        selection[1:] = text_index[batch_idx][1:] != text_index[batch_idx][:-1]
                    for ignored_token in ignored_tokens:
                        selection &= text_index[batch_idx] != ignored_token

                    char_list = [
                        self.character[text_id] for text_id in text_index[batch_idx][selection]
                    ]

                    if text_prob is not None:
                        conf_list = text_prob[batch_idx][selection].tolist()
                    else:
                        conf_list = [1.0] * np.sum(selection)  # Fix: use sum of selection

                    if len(conf_list) == 0:
                        conf_list = [0.0]

                    text = "".join(char_list)

                    if self.reverse:  # for arabic rec
                        text = self.pred_reverse(text)
                        conf_list = conf_list[::-1]  # reverse confidence too

                    mean_conf = float(np.mean(conf_list))
                    result_list.append((text, mean_conf))
                    char_conf_list.append((text, conf_list))  # 텍스트와 함께 저장

                # 전역 저장소에 추가 (누적) - 텍스트와 함께
                _append_text_conf_pairs(char_conf_list)

                return result_list

        class PatchedCTCLabelDecode(PatchedBaseRecLabelDecode):
            """패치된 CTC 디코더"""

            def __init__(self, character_list=None, use_space_char=True):
                super().__init__(character_list, use_space_char=use_space_char)

            def __call__(self, pred):
                """apply - 문자별 confidence도 저장"""
                preds = np.array(pred[0])
                preds_idx = preds.argmax(axis=-1)
                preds_prob = preds.max(axis=-1)
                text = self.decode(preds_idx, preds_prob, is_remove_duplicate=True)
                texts = []
                scores = []
                for t in text:
                    texts.append(t[0])
                    scores.append(t[1])
                return texts, scores

            def add_special_char(self, character_list):
                """add_special_char"""
                character_list = ["blank"] + character_list
                return character_list

        # 패치 적용 - processors 모듈
        processors.BaseRecLabelDecode = PatchedBaseRecLabelDecode
        processors.CTCLabelDecode = PatchedCTCLabelDecode

        # 패치 적용 - predictor 모듈의 build_postprocess 메서드
        try:
            from paddlex.inference.models.text_recognition import predictor

            # 원본 build_postprocess 백업
            original_build_postprocess = predictor.TextRecPredictor.build_postprocess

            def patched_build_postprocess(self, **kwargs):
                """패치된 build_postprocess - PatchedCTCLabelDecode 사용"""
                if kwargs.get("name") == "CTCLabelDecode":
                    return PatchedCTCLabelDecode(
                        character_list=kwargs.get("character_dict"),
                    )
                else:
                    raise Exception(f"Unknown postprocess: {kwargs.get('name')}")

            predictor.TextRecPredictor.build_postprocess = patched_build_postprocess
            logger.info("TextRecPredictor.build_postprocess 패치 완료")
        except ImportError as e:
            logger.warning(f"predictor 모듈 패치 실패: {e}")
        except Exception as e:
            logger.warning(f"build_postprocess 패치 실패: {e}")

        logger.info("CTCLabelDecode 패치 성공 - 문자별 confidence 추출 활성화")
        return True

    except Exception as e:
        logger.error(f"CTCLabelDecode 패치 실패: {e}")
        return False


class CharConfidenceStore:
    """
    OCR 결과와 함께 문자별 confidence를 저장하는 클래스

    OCR 파이프라인에서 사용:
    1. OCR 수행 전: store.clear()
    2. OCR 수행 후: char_confs = store.get_confidences()
    3. 결과에 추가: result['char_confidences'] = char_confs
    """

    def __init__(self):
        self._confidences: List[List[float]] = []

    def clear(self):
        """저장된 confidence 초기화"""
        self._confidences = []
        clear_char_confidences()

    def capture(self):
        """전역 저장소에서 confidence 캡처"""
        self._confidences = get_last_char_confidences().copy()

    def get_confidences(self) -> List[List[float]]:
        """저장된 confidence 반환"""
        return self._confidences

    def get_confidence_for_text(self, text_index: int) -> List[float]:
        """특정 텍스트의 문자별 confidence 반환"""
        if text_index < len(self._confidences):
            return self._confidences[text_index]
        return []


# 모듈 로드 시 자동 패치
_patch_applied = False

def ensure_patched():
    """패치가 적용되었는지 확인하고, 안되어 있으면 적용"""
    global _patch_applied
    if not _patch_applied:
        _patch_applied = patch_ctc_decoder()
    return _patch_applied


def extract_char_confidences_from_ocr_result(
    texts: List[str],
    store: CharConfidenceStore = None
) -> List[Dict[str, Any]]:
    """
    OCR 결과에서 문자별 confidence 추출

    Args:
        texts: OCR 인식 텍스트 리스트
        store: CharConfidenceStore 인스턴스 (없으면 전역 사용)

    Returns:
        각 텍스트의 문자별 confidence 정보
    """
    if store:
        char_confs = store.get_confidences()
    else:
        char_confs = get_last_char_confidences()

    results = []
    for i, text in enumerate(texts):
        if i < len(char_confs):
            confs = char_confs[i]
            # 텍스트 길이와 confidence 길이 맞추기
            if len(confs) < len(text):
                confs = confs + [0.0] * (len(text) - len(confs))
            elif len(confs) > len(text):
                confs = confs[:len(text)]

            char_details = []
            for j, (char, conf) in enumerate(zip(text, confs)):
                char_details.append({
                    'char': char,
                    'confidence': conf,
                    'position': j,
                    'suspicious': conf < 0.8
                })

            results.append({
                'text': text,
                'mean_confidence': float(np.mean(confs)) if confs else 0.0,
                'char_confidences': confs,
                'char_details': char_details
            })
        else:
            results.append({
                'text': text,
                'mean_confidence': 0.0,
                'char_confidences': [],
                'char_details': []
            })

    return results


# 테스트
if __name__ == "__main__":
    print("Testing CTC Patch...")

    # 패치 적용
    success = patch_ctc_decoder()
    print(f"Patch applied: {success}")

    if success:
        # 간단한 테스트
        from paddlex.inference.models.text_recognition.processors import CTCLabelDecode

        # 가짜 예측 생성
        vocab_size = 100
        seq_len = 20
        batch_size = 2

        fake_preds = [np.random.randn(batch_size, seq_len, vocab_size)]

        decoder = CTCLabelDecode(character_list=list("가나다라마바사아자차카타파하0123456789"))
        texts, scores = decoder(fake_preds)

        print(f"\nDecoded texts: {texts}")
        print(f"Mean scores: {scores}")

        char_confs = get_last_char_confidences()
        print(f"\nChar confidences per text:")
        for i, (text, confs) in enumerate(zip(texts, char_confs)):
            print(f"  [{i}] '{text}'")
            for j, (c, conf) in enumerate(zip(text, confs)):
                print(f"      {c}: {conf:.4f}")
