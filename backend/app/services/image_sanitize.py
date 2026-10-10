"""
Re-encode an uploaded photo before it is stored on images.lambajo.com.

The server used to store the uploaded bytes as they came: any EXIF block (a phone camera writes the
GPS position of the shop or the merchant's home, the time, the phone model, the owner's name on some
phones) went public with the photo, and the stored extension and Content-Type came from the client's
file name, so a file called x.svg was served as image/svg+xml.

What comes out of sanitize_image() is always a new JPEG:
  - decoded by Pillow, so anything that is not a real JPEG / PNG / WebP photo is refused (SVG, HTML,
    a renamed text file, a truncated file);
  - rotated the way EXIF said, THEN stripped of all metadata (EXIF, GPS, XMP, IPTC, comments, thumbnails,
    the ICC profile after converting the colours to sRGB, so a wide-gamut iPhone photo keeps its look);
  - at most MAX_EDGE pixels on the long side (never enlarged);
  - flattened to RGB on white (a PNG with a transparent background has no black box around the product).
"""

import io
import logging
from typing import Optional

from PIL import Image, ImageCms, ImageOps, UnidentifiedImageError

logger = logging.getLogger(__name__)

MAX_EDGE = 1600          # px, long side. Cards show a product at well under 800 px; 1600 allows a zoom.
JPEG_QUALITY = 82
# Refused before decoding: a small file can declare a huge canvas (decompression bomb). 64 MP covers
# every phone camera at full resolution (a 50 MP sensor is 8192 x 6144).
MAX_PIXELS = 64_000_000
ALLOWED_FORMATS = {"JPEG", "MPO", "PNG", "WEBP"}   # MPO is a JPEG with extra frames (some phones)

_SRGB = None


class InvalidImage(ValueError):
    """The bytes are not a photo we accept (not an image, damaged, or too large a canvas)."""


def _srgb_profile():
    global _SRGB
    if _SRGB is None:
        _SRGB = ImageCms.createProfile("sRGB")
    return _SRGB


def _to_srgb(img: Image.Image, icc_profile: Optional[bytes]) -> Image.Image:
    """Convert from the photo's own colour profile to sRGB. Any trouble with the profile: keep the pixels."""
    if not icc_profile or img.mode != "RGB":
        return img
    try:
        source = ImageCms.ImageCmsProfile(io.BytesIO(icc_profile))
        return ImageCms.profileToProfile(img, source, _srgb_profile(), outputMode="RGB")
    except Exception as exc:  # a broken or unsupported profile must not lose the photo
        logger.info("[IMAGE] colour profile ignored: %r", exc)
        return img


def _flatten_to_rgb(img: Image.Image) -> Image.Image:
    has_alpha = img.mode in ("RGBA", "LA", "PA") or (img.mode == "P" and "transparency" in img.info)
    if has_alpha:
        rgba = img.convert("RGBA")
        flat = Image.new("RGB", rgba.size, (255, 255, 255))
        flat.paste(rgba, mask=rgba.getchannel("A"))
        return flat
    return img if img.mode == "RGB" else img.convert("RGB")


def sanitize_image(data: bytes) -> bytes:
    """The photo as a metadata-free JPEG of at most MAX_EDGE px. Raises InvalidImage."""
    if not data:
        raise InvalidImage("empty")
    try:
        img = Image.open(io.BytesIO(data))
        if img.format not in ALLOWED_FORMATS:
            raise InvalidImage(f"format {img.format!r} is not accepted")
        width, height = img.size
        if width < 1 or height < 1 or width * height > MAX_PIXELS:
            raise InvalidImage(f"{width}x{height} is not an accepted size")

        icc_profile = img.info.get("icc_profile")
        img.getexif()                        # read the orientation now: thumbnail() works in place
        img.thumbnail((MAX_EDGE, MAX_EDGE), Image.Resampling.LANCZOS)   # JPEGs are decoded at reduced size
        img = ImageOps.exif_transpose(img)   # turn the pixels upright; the tag itself is dropped below
        img = _to_srgb(_flatten_to_rgb(img), icc_profile)

        # Pillow's JPEG writer falls back to img.info for the XMP packet (11.0, the pinned version) and the
        # comment (every version), so passing no exif=/xmp=/comment= is not enough: the info dict has to go.
        # Whether a previous step happened to return a fresh image must not decide whether they leak.
        img.info = {}

        out = io.BytesIO()
        img.save(out, "JPEG", quality=JPEG_QUALITY, optimize=True, progressive=True)
        return out.getvalue()
    except InvalidImage:
        raise
    except (UnidentifiedImageError, Image.DecompressionBombError, OSError, ValueError, SyntaxError) as exc:
        # OSError: truncated or damaged data; ValueError / SyntaxError: malformed headers
        raise InvalidImage(f"cannot be decoded: {exc!r}") from exc
