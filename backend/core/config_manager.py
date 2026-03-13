#!/usr/bin/env python3
"""
설정 관리자 모듈 - config.yaml 파일을 읽어서 전역 설정을 관리
"""

import os
import yaml
from pathlib import Path
from typing import Dict, Any, List
import logging

class ConfigManager:
    """설정 관리자 클래스"""
    
    def __init__(self, config_path: str = None):
        """
        설정 관리자 초기화

        Args:
            config_path: config.yaml 파일 경로 (기본값: 프로젝트 루트의 config.yaml)
        """
        if config_path is None:
            # 현재 파일 기준으로 프로젝트 루트 찾기
            # core/config_manager.py -> backend/core -> backend -> project root
            current_dir = Path(__file__).parent  # core
            backend_dir = current_dir.parent  # backend
            project_root = backend_dir.parent  # project root
            config_path = project_root / "config.yaml"

        self.config_path = Path(config_path)
        self.config = self._load_config()
        self._validate_config()
        
    def _load_config(self) -> Dict[str, Any]:
        """config.yaml 파일 로드"""
        try:
            if not self.config_path.exists():
                raise FileNotFoundError(f"설정 파일을 찾을 수 없습니다: {self.config_path}")
            
            with open(self.config_path, 'r', encoding='utf-8') as file:
                config = yaml.safe_load(file)
            
            logging.info(f"Config loaded: {self.config_path}")
            return config
            
        except Exception as e:
            logging.error(f"Failed to load config: {e}")
            # 기본 설정으로 폴백
            return self._get_default_config()
    
    def _get_default_config(self) -> Dict[str, Any]:
        """기본 설정 반환 (config.yaml 로드 실패시 사용)"""
        return {
            "ocr": {
                "recognition_model_dir": "data/models/best_0828",
                "custom_models": {
                    "best_0828": "data/models/best_0828",
                },
                "use_gpu": True,
                "cpu_threads": 8,
                "batch_size": 32,
                "detection_limit_side_len": 1200,
                "gpu_id": 0,
            },
            "directories": {
                "input_image_dir": "",
                "upload_dir": "data/raw",
                "output_pdf_dir": "data/processed",
                "log_dir": "data/logs",
                "debug_dir": "data/debug"
            },
            "fonts": {
                "candidates": [
                    {"path": "/usr/share/fonts/truetype/nanum/NanumGothic.ttf", "name": "NanumGothic"},
                    {"path": "/System/Library/Fonts/AppleGothic.ttf", "name": "AppleGothic"},
                    {"path": "C:/Windows/Fonts/malgun.ttf", "name": "MalgunGothic"},
                    {"path": "C:/Windows/Fonts/gulim.ttc", "name": "Gulim"}
                ],
                "max_font_size": 90,
                "korean_min_size": 7,
                "english_min_size": 6
            },
            "column_detection": {
                "enable_debug_output": False,
                "confidence_threshold": 0.05,
                "min_blocks_for_detection": 4
            },
            "text_coverage": {
                "expand_click_area": True,
                "multi_layer_rendering": False,
                "low_confidence_threshold": 0.3,
                "bbox_expansion_pixels": 0,
                "font_size_boost": 1.0,
                "coverage_fill_ratio": 1.0,
                "width_overshoot_ratio": 1.02,
                "enable_text_recovery": False
            },
            "pdf_processing": {
                "dpi": 400,
                "fast_mode": True
            },
            "performance": {
                "text_alpha": 0.01,
                "gc_interval_pages": 8,
                "enable_memory_cleanup": True
            },
            "preprocessing": {
                "enable": False,
                "denoise": {
                    "enabled": True,
                    "h": 6,
                    "h_color": 6,
                    "template_window_size": 7,
                    "search_window_size": 21
                },
                "upscale": {
                    "enabled": True,
                    "min_edge": 1600,
                    "max_scale": 2.0
                },
                "clahe": {
                    "enabled": True,
                    "clip_limit": 3.0,
                    "tile_grid_size": [8, 8]
                },
                "preserve_size": True
            },
            "file_processing": {
                "supported_image_extensions": ["*.png", "*.jpg", "*.jpeg", "*.bmp", "*.tiff", "*.tif"],
                "supported_pdf_extensions": ["*.pdf"],
                "max_file_size_mb": 50
            },
            "server": {
                "backend": {
                    "host": "0.0.0.0",
                    "port": 5015
                },
                "frontend": {
                    "host": "0.0.0.0",
                    "port": 5017
                },
                "debug": False,
                "log_level": "INFO",
                "cors_origins": ["http://localhost:5017", "http://127.0.0.1:5017"]
            }
        }
    
    def _validate_config(self):
        """설정 값 검증 및 디렉토리 생성"""
        try:
            # 필수 디렉토리 생성
            directories = self.config.get('directories', {})
            for dir_key, dir_path in directories.items():
                if dir_path:
                    Path(dir_path).mkdir(parents=True, exist_ok=True)
                    
            logging.info("Config validated and directories created")
            
        except Exception as e:
            logging.warning(f"Config validation error: {e}")
    
    def get(self, key: str, default=None):
        """
        설정값 가져오기 (점 표기법 지원)
        
        Args:
            key: 설정 키 (예: "ocr.use_gpu", "directories.output_pdf_dir")
            default: 기본값
        
        Returns:
            설정값
        """
        try:
            keys = key.split('.')
            value = self.config
            
            for k in keys:
                value = value[k]
            
            return value
            
        except (KeyError, TypeError):
            return default
    
    def get_ocr_config(self) -> Dict[str, Any]:
        """OCR 관련 설정 반환"""
        return self.config.get('ocr', {})
    
    def get_directories_config(self) -> Dict[str, str]:
        """디렉토리 관련 설정 반환"""
        return self.config.get('directories', {})
    
    def get_server_config(self) -> Dict[str, Any]:
        """서버 관련 설정 반환"""
        return self.config.get('server', {})
    
    def get_backend_config(self) -> Dict[str, Any]:
        """백엔드 서버 설정 반환"""
        return self.config.get('server', {}).get('backend', {})
    
    def get_frontend_config(self) -> Dict[str, Any]:
        """프론트엔드 서버 설정 반환"""
        return self.config.get('server', {}).get('frontend', {})
    
    def get_font_config(self) -> Dict[str, Any]:
        """폰트 관련 설정 반환"""
        return self.config.get('fonts', {})
    
    def get_column_detection_config(self) -> Dict[str, Any]:
        """다단 감지 관련 설정 반환"""
        return self.config.get('column_detection', {})
    
    def get_text_coverage_config(self) -> Dict[str, Any]:
        """텍스트 커버리지 관련 설정 반환"""
        return self.config.get('text_coverage', {})

    def get_pdf_processing_config(self) -> Dict[str, Any]:
        """PDF 처리 관련 설정 반환"""
        return self.config.get('pdf_processing', {})

    def get_performance_config(self) -> Dict[str, Any]:
        """성능 관련 설정 반환"""
        return self.config.get('performance', {})

    def get_preprocessing_config(self) -> Dict[str, Any]:
        """이미지 전처리 관련 설정 반환"""
        return self.config.get('preprocessing', {})

    def get_file_processing_config(self) -> Dict[str, Any]:
        """파일 처리 관련 설정 반환"""
        return self.config.get('file_processing', {})
    
    def is_gpu_enabled(self) -> bool:
        """GPU 사용 여부 반환"""
        return self.get('ocr.use_gpu', True)
    
    def get_gpu_id(self):
        """선호 GPU ID 반환"""
        return self.get('ocr.gpu_id')
    
    def is_debug_enabled(self) -> bool:
        """디버그 모드 여부 반환"""
        return self.get('column_detection.enable_debug_output', True)
    
    def resolve_path(self, path_str: str) -> str:
        """상대 경로를 프로젝트 루트 기준 절대 경로로 변환"""
        if not path_str:
            return path_str
        p = Path(path_str)
        if p.is_absolute():
            return str(p)
        return str(self.config_path.parent / p)

    def get_model_directory(self) -> str:
        """모델 디렉토리 경로 반환"""
        return self.get('ocr.recognition_model_dir', '')
    
    def print_config_summary(self):
        """설정 요약 출력"""
        print("\n" + "="*80)
        print("📋 OCR PDF Generator 설정 요약")
        print("="*80)
        
        # OCR 설정
        ocr_config = self.get_ocr_config()
        print(f"🔧 OCR 설정:")
        print(f"   모델 디렉토리: {ocr_config.get('recognition_model_dir', 'N/A')}")
        gpu_enabled = ocr_config.get('use_gpu', False)
        gpu_device = ocr_config.get('gpu_id', 'auto')
        gpu_device_label = gpu_device if gpu_device not in (None, '') else 'auto'
        print(f"   GPU 사용: {'✅ 활성화' if gpu_enabled else '❌ 비활성화'} (GPU ID: {gpu_device_label})")
        print(f"   CPU 스레드: {ocr_config.get('cpu_threads', 'N/A')}개")
        print(f"   배치 크기: {ocr_config.get('batch_size', 'N/A')}")
        
        # 디렉토리 설정
        dirs_config = self.get_directories_config()
        print(f"\n📁 디렉토리 설정:")
        print(f"   업로드: {dirs_config.get('upload_dir', 'N/A')}")
        print(f"   출력: {dirs_config.get('output_pdf_dir', 'N/A')}")
        print(f"   디버그: {dirs_config.get('debug_dir', 'N/A')}")
        
        # 서버 설정
        server_config = self.get_server_config()
        print(f"\n🌐 서버 설정:")
        print(f"   주소: {server_config.get('host', 'N/A')}:{server_config.get('port', 'N/A')}")
        print(f"   디버그 모드: {'✅ 활성화' if server_config.get('debug', False) else '❌ 비활성화'}")
        
        # 디버그 설정
        debug_config = self.get_column_detection_config()
        print(f"   디버그 이미지: {'✅ 활성화' if debug_config.get('enable_debug_output', False) else '❌ 비활성화'}")
        
        print("="*80 + "\n")

# 전역 설정 관리자 인스턴스
config_manager = ConfigManager()

# 편의 함수들
def get_config(key: str, default=None):
    """전역 설정값 가져오기"""
    return config_manager.get(key, default)

def is_gpu_enabled() -> bool:
    """GPU 사용 여부"""
    return config_manager.is_gpu_enabled()

def get_gpu_id():
    """GPU ID"""
    return config_manager.get_gpu_id()

def is_debug_enabled() -> bool:
    """디버그 모드 여부"""
    return config_manager.is_debug_enabled()

def get_model_directory() -> str:
    """모델 디렉토리"""
    return config_manager.get_model_directory()

# 하위 호환성을 위한 CONFIG 딕셔너리 생성
def create_legacy_config() -> Dict[str, Any]:
    """기존 pipeline.py와의 호환성을 위한 CONFIG 딕셔너리 생성"""
    ocr_config = config_manager.get_ocr_config()
    dirs_config = config_manager.get_directories_config()
    font_config = config_manager.get_font_config()
    column_config = config_manager.get_column_detection_config()
    text_config = config_manager.get_text_coverage_config()
    perf_config = config_manager.get_performance_config()
    file_config = config_manager.get_file_processing_config()
    preprocessing_config = config_manager.get_preprocessing_config()
    
    # 폰트 후보 변환
    font_candidates = []
    for font in font_config.get('candidates', []):
        font_candidates.append((font.get('path', ''), font.get('name', '')))
    
    # 상대 경로를 프로젝트 루트 기준 절대 경로로 변환
    resolve = config_manager.resolve_path

    return {
        'RECOGNITION_MODEL_DIR': resolve(ocr_config.get('recognition_model_dir', '')),
        'INPUT_IMAGE_DIR': resolve(dirs_config.get('input_image_dir', '')),
        'OUTPUT_PDF_DIR': resolve(dirs_config.get('output_pdf_dir', '')),
        'LOG_DIR': resolve(dirs_config.get('log_dir', '')),
        'USE_GPU': ocr_config.get('use_gpu', True),
        'GPU_DEVICE_ID': ocr_config.get('gpu_id'),
        'SUPPORTED_EXTENSIONS': file_config.get('supported_image_extensions', []),
        'MAX_FONT_SIZE': font_config.get('max_font_size', 90),
        'KOREAN_MIN_SIZE': font_config.get('korean_min_size', 7),
        'ENGLISH_MIN_SIZE': font_config.get('english_min_size', 6),
        'TEXT_ALPHA': perf_config.get('text_alpha', 0.01),
        'FONT_CANDIDATES': font_candidates,
        'COLUMN_DETECTION': {
            'ENABLE_DEBUG_OUTPUT': column_config.get('enable_debug_output', True),
            'DEBUG_OUTPUT_DIR': resolve(dirs_config.get('debug_dir', '')),
            'CONFIDENCE_THRESHOLD': column_config.get('confidence_threshold', 0.15),
            'MIN_BLOCKS_FOR_DETECTION': column_config.get('min_blocks_for_detection', 2),
        },
        'TEXT_COVERAGE': {
            'EXPAND_CLICK_AREA': text_config.get('expand_click_area', True),
            'MULTI_LAYER_RENDERING': text_config.get('multi_layer_rendering', False),
            'LOW_CONFIDENCE_THRESHOLD': text_config.get('low_confidence_threshold', 0.3),
            'BBOX_EXPANSION_PIXELS': text_config.get('bbox_expansion_pixels', 1),
            'FONT_SIZE_BOOST': text_config.get('font_size_boost', 1.05),
            'COVERAGE_FILL_RATIO': text_config.get('coverage_fill_ratio', 0.90),
            'WIDTH_OVERSHOOT_RATIO': text_config.get('width_overshoot_ratio', 1.0),
            'ENABLE_TEXT_RECOVERY': text_config.get('enable_text_recovery', False),
        },
        'PREPROCESSING': preprocessing_config,
    }

if __name__ == "__main__":
    # 설정 테스트
    config_manager.print_config_summary()
    
    # 샘플 설정값 출력
    print("🧪 설정값 테스트:")
    print(f"GPU 사용: {is_gpu_enabled()}")
    print(f"모델 디렉토리: {get_model_directory()}")
    print(f"디버그 활성화: {is_debug_enabled()}")
    print(f"서버 포트: {get_config('server.port')}")
