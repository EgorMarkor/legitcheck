from io import BytesIO
from pathlib import Path

from django.conf import settings
from django.contrib.staticfiles import finders
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from PIL import Image, ImageOps, UnidentifiedImageError


WATERMARK_STATIC_NAME = "my_watermark.png"
WATERMARK_OPACITY = 0.28
WATERMARK_WIDTH_RATIO = 0.56


def _watermark_path():
    found_path = finders.find(WATERMARK_STATIC_NAME)
    if found_path:
        return found_path

    fallback_path = Path(settings.BASE_DIR) / "webapp" / "static" / WATERMARK_STATIC_NAME
    if fallback_path.exists():
        return str(fallback_path)

    return None


def apply_verdict_photo_watermark(uploaded_file):
    uploaded_size = getattr(uploaded_file, "size", None)
    max_bytes = int(getattr(settings, "MAX_UPLOAD_IMAGE_BYTES", 15 * 1024 * 1024))
    if uploaded_size is not None and uploaded_size > max_bytes:
        raise ValidationError("Изображение превышает допустимый размер.")

    watermark_path = _watermark_path()
    if not watermark_path:
        return uploaded_file

    try:
        uploaded_file.seek(0)
    except (AttributeError, OSError):
        pass

    try:
        with Image.open(uploaded_file) as source_image:
            if source_image.format not in {"JPEG", "PNG", "WEBP", "GIF", "HEIC", "HEIF"}:
                raise ValidationError("Неподдерживаемый формат изображения.")
            max_pixels = int(getattr(settings, "MAX_UPLOAD_IMAGE_PIXELS", 40_000_000))
            if source_image.width * source_image.height > max_pixels:
                raise ValidationError("Слишком большое разрешение изображения.")
            base_image = ImageOps.exif_transpose(source_image).convert("RGBA")
    except ValidationError:
        raise
    except (Image.DecompressionBombError, UnidentifiedImageError, OSError, ValueError) as exc:
        raise ValidationError("Файл не является допустимым изображением.") from exc

    try:
        with Image.open(watermark_path) as watermark_image:
            watermark = watermark_image.convert("RGBA")
    except (UnidentifiedImageError, OSError, ValueError):
        return uploaded_file

    base_width, base_height = base_image.size
    watermark_width = max(56, int(min(base_width, base_height) * WATERMARK_WIDTH_RATIO))
    watermark_ratio = watermark.height / watermark.width
    watermark_size = (watermark_width, max(1, int(watermark_width * watermark_ratio)))
    watermark = watermark.resize(watermark_size, Image.Resampling.LANCZOS)

    alpha = watermark.getchannel("A")
    alpha = alpha.point(lambda value: int(value * WATERMARK_OPACITY))
    watermark.putalpha(alpha)

    position = (
        (base_width - watermark.width) // 2,
        (base_height - watermark.height) // 2,
    )
    base_image.alpha_composite(watermark, position)

    output = BytesIO()
    base_image.convert("RGB").save(output, format="JPEG", quality=90, optimize=True)
    output.seek(0)

    original_name = Path(getattr(uploaded_file, "name", "") or "photo").stem or "photo"
    return SimpleUploadedFile(
        f"{original_name}.jpg",
        output.getvalue(),
        content_type="image/jpeg",
    )
