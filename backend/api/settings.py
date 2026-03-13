"""
Settings API for config.yaml management
"""
import yaml
from pathlib import Path
from typing import Any, Dict, Optional
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter(prefix="/api/settings", tags=["settings"])

CONFIG_PATH = Path(__file__).parent.parent.parent / "config.yaml"


class OCRSettings(BaseModel):
    use_gpu: bool = True
    rec_batch_num: int = 1
    detection_limit_side_len: int = 1200
    use_smart_reading_order: bool = True


class PDFSettings(BaseModel):
    dpi: int = 400
    fast_mode: bool = True


class PreprocessingSettings(BaseModel):
    enable: bool = False
    denoise_enabled: bool = True
    upscale_enabled: bool = True
    clahe_enabled: bool = True


class PerformanceSettings(BaseModel):
    gc_interval_pages: int = 8
    enable_memory_cleanup: bool = True


class SettingsResponse(BaseModel):
    ocr: OCRSettings
    pdf_processing: PDFSettings
    preprocessing: PreprocessingSettings
    performance: PerformanceSettings


def load_config() -> Dict[str, Any]:
    """Load config.yaml"""
    if not CONFIG_PATH.exists():
        raise HTTPException(status_code=404, detail="Config file not found")

    with open(CONFIG_PATH, 'r', encoding='utf-8') as f:
        return yaml.safe_load(f)


def save_config(config: Dict[str, Any]) -> None:
    """Save config.yaml"""
    with open(CONFIG_PATH, 'w', encoding='utf-8') as f:
        yaml.dump(config, f, allow_unicode=True, default_flow_style=False, sort_keys=False)


@router.get("", response_model=SettingsResponse)
async def get_settings():
    """Get current settings from config.yaml"""
    config = load_config()

    ocr_config = config.get('ocr', {})
    pdf_config = config.get('pdf_processing', {})
    prep_config = config.get('preprocessing', {})
    perf_config = config.get('performance', {})

    return SettingsResponse(
        ocr=OCRSettings(
            use_gpu=ocr_config.get('use_gpu', True),
            rec_batch_num=ocr_config.get('rec_batch_num', 1),
            detection_limit_side_len=ocr_config.get('detection_limit_side_len', 1200),
            use_smart_reading_order=ocr_config.get('use_smart_reading_order', True),
        ),
        pdf_processing=PDFSettings(
            dpi=pdf_config.get('dpi') or 400,
            fast_mode=pdf_config.get('fast_mode', True),
        ),
        preprocessing=PreprocessingSettings(
            enable=prep_config.get('enable', False),
            denoise_enabled=prep_config.get('denoise', {}).get('enabled', True),
            upscale_enabled=prep_config.get('upscale', {}).get('enabled', True),
            clahe_enabled=prep_config.get('clahe', {}).get('enabled', True),
        ),
        performance=PerformanceSettings(
            gc_interval_pages=perf_config.get('gc_interval_pages', 8),
            enable_memory_cleanup=perf_config.get('enable_memory_cleanup', True),
        ),
    )


class UpdateSettingsRequest(BaseModel):
    ocr: Optional[OCRSettings] = None
    pdf_processing: Optional[PDFSettings] = None
    preprocessing: Optional[PreprocessingSettings] = None
    performance: Optional[PerformanceSettings] = None


@router.put("")
async def update_settings(request: UpdateSettingsRequest):
    """Update settings in config.yaml"""
    config = load_config()

    if request.ocr:
        if 'ocr' not in config:
            config['ocr'] = {}
        config['ocr']['use_gpu'] = request.ocr.use_gpu
        config['ocr']['rec_batch_num'] = request.ocr.rec_batch_num
        config['ocr']['detection_limit_side_len'] = request.ocr.detection_limit_side_len
        config['ocr']['use_smart_reading_order'] = request.ocr.use_smart_reading_order

    if request.pdf_processing:
        if 'pdf_processing' not in config:
            config['pdf_processing'] = {}
        config['pdf_processing']['dpi'] = request.pdf_processing.dpi
        config['pdf_processing']['fast_mode'] = request.pdf_processing.fast_mode

    if request.preprocessing:
        if 'preprocessing' not in config:
            config['preprocessing'] = {}
        config['preprocessing']['enable'] = request.preprocessing.enable
        if 'denoise' not in config['preprocessing']:
            config['preprocessing']['denoise'] = {}
        config['preprocessing']['denoise']['enabled'] = request.preprocessing.denoise_enabled
        if 'upscale' not in config['preprocessing']:
            config['preprocessing']['upscale'] = {}
        config['preprocessing']['upscale']['enabled'] = request.preprocessing.upscale_enabled
        if 'clahe' not in config['preprocessing']:
            config['preprocessing']['clahe'] = {}
        config['preprocessing']['clahe']['enabled'] = request.preprocessing.clahe_enabled

    if request.performance:
        if 'performance' not in config:
            config['performance'] = {}
        config['performance']['gc_interval_pages'] = request.performance.gc_interval_pages
        config['performance']['enable_memory_cleanup'] = request.performance.enable_memory_cleanup

    save_config(config)

    return {"status": "success", "message": "Settings updated. Restart server to apply changes."}


@router.post("/reset")
async def reset_settings():
    """Reset settings to defaults (requires manual backup)"""
    return {"status": "info", "message": "Manual reset required. Please restore from backup."}
