"""
PDF Processing utilities
"""
import logging
from pathlib import Path
from typing import List, Tuple, Optional
import tempfile

try:
    import fitz  # PyMuPDF
    PYMUPDF_AVAILABLE = True
except ImportError:
    PYMUPDF_AVAILABLE = False

try:
    from pdf2image import convert_from_path
    PDF2IMAGE_AVAILABLE = True
except ImportError:
    PDF2IMAGE_AVAILABLE = False

from PIL import Image

logger = logging.getLogger(__name__)


class PDFProcessor:
    """PDF processing utilities"""

    @staticmethod
    def get_page_count(pdf_path: str) -> int:
        """Get the number of pages in a PDF"""
        try:
            if PYMUPDF_AVAILABLE:
                doc = fitz.open(pdf_path)
                page_count = len(doc)
                doc.close()
                return page_count
            elif PDF2IMAGE_AVAILABLE:
                from pdf2image import pdfinfo_from_path
                info = pdfinfo_from_path(pdf_path)
                return info.get('Pages', 0)
            else:
                raise RuntimeError("No PDF library available (PyMuPDF or pdf2image)")
        except Exception as e:
            logger.error(f"Failed to get page count: {e}")
            raise

    @staticmethod
    def pdf_to_images(pdf_path: str, output_dir: Optional[Path] = None, dpi: int = 300, progress_callback=None) -> List[Tuple[str, int, int]]:
        """
        Convert PDF pages to images

        Args:
            pdf_path: Path to PDF file
            output_dir: Directory to save images (if None, use temp directory)
            dpi: Resolution for image conversion
            progress_callback: Optional callback(current_page, total_pages) for progress updates

        Returns:
            List of tuples: (image_path, width, height) for each page
        """
        pdf_path = Path(pdf_path)

        if output_dir is None:
            output_dir = Path(tempfile.mkdtemp(prefix='pdf_'))
        else:
            output_dir = Path(output_dir)
            output_dir.mkdir(parents=True, exist_ok=True)

        logger.info(f"Converting PDF to images: {pdf_path.name} (DPI: {dpi})")

        try:
            # Try PyMuPDF first (faster and better quality)
            if PYMUPDF_AVAILABLE:
                return PDFProcessor._pdf_to_images_pymupdf(pdf_path, output_dir, dpi, progress_callback)
            # Fallback to pdf2image
            elif PDF2IMAGE_AVAILABLE:
                return PDFProcessor._pdf_to_images_pdf2image(pdf_path, output_dir, dpi, progress_callback)
            else:
                raise RuntimeError("No PDF library available (PyMuPDF or pdf2image)")

        except Exception as e:
            logger.error(f"Failed to convert PDF to images: {e}")
            raise

    @staticmethod
    def _pdf_to_images_pymupdf(pdf_path: Path, output_dir: Path, dpi: int, progress_callback=None) -> List[Tuple[str, int, int]]:
        """Convert PDF to images using PyMuPDF"""
        doc = fitz.open(str(pdf_path))
        image_paths = []
        total_pages = len(doc)

        for page_num in range(total_pages):
            page = doc[page_num]

            # Get PDF page size in points
            page_width_pt = page.rect.width
            page_height_pt = page.rect.height

            # Check if PDF is already high-resolution (likely from scanned image)
            # Standard A4 is 595x842 pt, Letter is 612x792 pt
            # If page is much larger (e.g., > 1000 pt), it's likely already high-res
            is_high_res_pdf = page_width_pt > 1000 or page_height_pt > 1000

            if is_high_res_pdf:
                # PDF is already high-resolution, render at 1:1 (72 DPI)
                # This preserves the original quality without upscaling
                zoom = 1.0
                logger.debug(f"Page {page_num + 1}: High-res PDF ({page_width_pt:.0f}x{page_height_pt:.0f} pt), using 1:1 scale")
            else:
                # Normal PDF, scale to target DPI
                zoom = dpi / 72
                logger.debug(f"Page {page_num + 1}: Standard PDF ({page_width_pt:.0f}x{page_height_pt:.0f} pt), scaling to {dpi} DPI")

            mat = fitz.Matrix(zoom, zoom)
            pix = page.get_pixmap(matrix=mat)

            image_path = output_dir / f"page_{page_num + 1:04d}.png"
            pix.save(str(image_path))

            image_paths.append((str(image_path), pix.width, pix.height))
            logger.debug(f"Converted page {page_num + 1}/{total_pages}: {pix.width}x{pix.height} px")

            # Call progress callback
            if progress_callback:
                progress_callback(page_num + 1, total_pages)

        doc.close()
        logger.info(f"PDF conversion completed: {len(image_paths)} pages")
        return image_paths

    @staticmethod
    def _pdf_to_images_pdf2image(pdf_path: Path, output_dir: Path, dpi: int, progress_callback=None) -> List[Tuple[str, int, int]]:
        """Convert PDF to images using pdf2image"""
        images = convert_from_path(str(pdf_path), dpi=dpi)
        image_paths = []
        total_pages = len(images)

        for page_num, image in enumerate(images):
            image_path = output_dir / f"page_{page_num + 1:04d}.png"
            image.save(str(image_path), 'PNG')

            image_paths.append((str(image_path), image.width, image.height))
            logger.debug(f"Converted page {page_num + 1}/{total_pages}")

            # Call progress callback
            if progress_callback:
                progress_callback(page_num + 1, total_pages)

        logger.info(f"PDF conversion completed: {len(image_paths)} pages")
        return image_paths

    @staticmethod
    def is_pdf(file_path: str) -> bool:
        """Check if file is a PDF"""
        try:
            path = Path(file_path)
            if not path.exists():
                return False

            # Check file extension
            if path.suffix.lower() != '.pdf':
                return False

            # Check magic bytes
            with open(path, 'rb') as f:
                header = f.read(4)
                return header == b'%PDF'

        except Exception:
            return False

    @staticmethod
    def is_image(file_path: str) -> bool:
        """Check if file is an image"""
        try:
            path = Path(file_path)
            if not path.exists():
                return False

            # Check by opening with PIL
            with Image.open(path) as img:
                img.verify()
            return True

        except Exception:
            return False
