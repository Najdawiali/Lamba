"""
app/services/image_sanitize.py: every stored product photo is a new, metadata-free JPEG.

Needs Pillow (skipped without it). The fixtures are built here, with real EXIF/GPS/ICC/comment
segments, and the tests first prove the fixture really carries them, then that the output does not.
"""

import io
import os
import sys
import unittest

BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BACKEND)

try:
    from PIL import Image, ImageCms
    HAVE_PILLOW = True
except ImportError:  # pragma: no cover - depends on the interpreter
    HAVE_PILLOW = False

if HAVE_PILLOW:
    from app.services.image_sanitize import InvalidImage, MAX_EDGE, MAX_PIXELS, sanitize_image

APP1_EXIF_XMP, APP2_ICC, APP13_IPTC, COM = 0xE1, 0xE2, 0xED, 0xFE
# The only segments a clean output may have before the image data: JFIF header, quantisation and
# Huffman tables, start of frame (baseline / progressive), restart interval, start of scan.
ALLOWED_MARKERS = {0xE0, 0xDB, 0xC4, 0xC0, 0xC2, 0xDD, 0xDA}

GPS_IFD = 0x8825


def jpeg_markers(data: bytes) -> list:
    """Marker codes of the segments in front of the image data of a JPEG."""
    assert data[:2] == b"\xff\xd8", "not a JPEG"
    markers, i = [], 2
    while i + 4 <= len(data):
        assert data[i] == 0xFF, f"bad marker at {i}"
        marker = data[i + 1]
        markers.append(marker)
        if marker == 0xDA:
            break
        i += 2 + int.from_bytes(data[i + 2:i + 4], "big")
    return markers


def srgb_icc() -> bytes:
    return ImageCms.ImageCmsProfile(ImageCms.createProfile("sRGB")).tobytes()


XMP_PACKET = (
    b'<x:xmpmeta xmlns:x="adobe:ns:meta/"><rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#">'
    b'<rdf:Description xmlns:xmp="http://ns.adobe.com/xap/1.0/" xmp:CreatorTool="OwnerPhoneApp"/></rdf:RDF></x:xmpmeta>'
)


def add_xmp(jpeg: bytes) -> bytes:
    """Insert an XMP packet (APP1) right after the start-of-image marker."""
    payload = b"http://ns.adobe.com/xap/1.0/\x00" + XMP_PACKET
    segment = b"\xff\xe1" + (len(payload) + 2).to_bytes(2, "big") + payload
    return jpeg[:2] + segment + jpeg[2:]


def jpeg_with_metadata(size=(400, 200), orientation=None, icc=True, comment=True, xmp=True, quality=95) -> bytes:
    """A phone-like JPEG: make/model, GPS position, optional orientation, ICC profile, comment, XMP."""
    img = Image.new("RGB", size, (200, 30, 30))
    exif = Image.Exif()
    exif[0x010F] = "SamsungTestMake"
    exif[0x0110] = "SM-TEST"
    if orientation:
        exif[0x0112] = orientation
    exif[GPS_IFD] = {1: "N", 2: (31.0, 57.0, 0.0), 3: "E", 4: (35.0, 55.0, 0.0)}
    extra = {}
    if icc:
        extra["icc_profile"] = srgb_icc()
    if comment:
        extra["comment"] = b"owner: Ali, shop at home"
    out = io.BytesIO()
    img.save(out, "JPEG", quality=quality, exif=exif, **extra)
    data = out.getvalue()
    return add_xmp(data) if xmp else data


def encode(img, fmt, **kwargs) -> bytes:
    out = io.BytesIO()
    img.save(out, fmt, **kwargs)
    return out.getvalue()


@unittest.skipUnless(HAVE_PILLOW, "Pillow is not installed")
class FixtureTests(unittest.TestCase):
    def test_the_fixture_really_carries_metadata(self):
        data = jpeg_with_metadata(orientation=6)
        markers = jpeg_markers(data)
        for expected in (APP1_EXIF_XMP, APP2_ICC, COM):
            self.assertIn(expected, markers)
        exif = Image.open(io.BytesIO(data)).getexif()
        self.assertTrue(exif.get_ifd(GPS_IFD), "fixture has no GPS block")
        self.assertEqual(exif.get(0x0112), 6)
        for needle in (b"SamsungTestMake", b"OwnerPhoneApp", b"owner: Ali"):
            self.assertIn(needle, data)

    def test_pillow_reads_the_xmp_and_comment_into_info_where_its_jpeg_writer_would_reuse_them(self):
        # This is why sanitize_image must clear img.info: with Pillow 11.0 (the pinned version) saving a JPEG
        # without any metadata argument still writes info["xmp"] and info["comment"] back.
        info = Image.open(io.BytesIO(jpeg_with_metadata())).info
        self.assertIn("comment", info)
        self.assertIn("xmp", info)


class _MetadataBase:
    """Every metadata kind must be gone whether or not an ICC profile is present: converting a profile
    returns a fresh image, which once hid the metadata that a plain image kept."""
    ICC = True

    def setUp(self):
        self.source = jpeg_with_metadata(orientation=6, icc=self.ICC)
        self.out = sanitize_image(self.source)

    def test_output_is_a_plain_rgb_jpeg(self):
        img = Image.open(io.BytesIO(self.out))
        self.assertEqual((img.format, img.mode), ("JPEG", "RGB"))

    def test_no_metadata_segment_is_left(self):
        markers = jpeg_markers(self.out)
        for banned in (APP1_EXIF_XMP, APP2_ICC, APP13_IPTC, COM):
            self.assertNotIn(banned, markers)
        self.assertTrue(set(markers) <= ALLOWED_MARKERS, f"unexpected segments: {[hex(m) for m in markers]}")

    def test_no_exif_gps_or_text_survives_anywhere_in_the_bytes(self):
        exif = Image.open(io.BytesIO(self.out)).getexif()
        self.assertEqual(len(exif), 0)
        self.assertFalse(exif.get_ifd(GPS_IFD))
        for needle in (b"Exif", b"SamsungTestMake", b"SM-TEST", b"owner", b"ICC_PROFILE", b"http://ns.adobe.com",
                       b"OwnerPhoneApp"):
            self.assertNotIn(needle, self.out)

    def test_orientation_is_applied_to_the_pixels_before_the_tag_is_dropped(self):
        # 400x200 with orientation 6 (rotate 90 clockwise to view) is upright as 200x400
        self.assertEqual(Image.open(io.BytesIO(self.out)).size, (200, 400))

    def test_the_input_bytes_are_not_returned_as_they_came(self):
        self.assertNotEqual(self.out, self.source)

    def test_a_broken_colour_profile_does_not_lose_the_photo_or_leak_the_comment(self):
        # The profile cannot be converted, so the pixels are kept as they are: this is the path where no
        # fresh image is made, and a comment or XMP packet would have gone straight back into the output.
        img = Image.new("RGB", (64, 64), (10, 120, 200))
        data = add_xmp(encode(img, "JPEG", icc_profile=b"this is not a colour profile", comment=b"home address"))
        out = sanitize_image(data)
        markers = jpeg_markers(out)
        for banned in (APP1_EXIF_XMP, APP2_ICC, COM):
            self.assertNotIn(banned, markers)
        for needle in (b"home address", b"OwnerPhoneApp", b"http://ns.adobe.com"):
            self.assertNotIn(needle, out)
        self.assertEqual(Image.open(io.BytesIO(out)).size, (64, 64))


@unittest.skipUnless(HAVE_PILLOW, "Pillow is not installed")
class MetadataWithIccProfileTests(_MetadataBase, unittest.TestCase):
    ICC = True


@unittest.skipUnless(HAVE_PILLOW, "Pillow is not installed")
class MetadataWithoutIccProfileTests(_MetadataBase, unittest.TestCase):
    ICC = False


@unittest.skipUnless(HAVE_PILLOW, "Pillow is not installed")
class SizeTests(unittest.TestCase):
    def size_of(self, data):
        return Image.open(io.BytesIO(sanitize_image(data))).size

    def test_a_big_landscape_photo_is_scaled_to_the_max_edge(self):
        self.assertEqual(self.size_of(encode(Image.new("RGB", (4000, 3000), "gray"), "JPEG")), (MAX_EDGE, 1200))

    def test_a_big_portrait_photo_is_scaled_to_the_max_edge(self):
        self.assertEqual(self.size_of(encode(Image.new("RGB", (3000, 4000), "gray"), "JPEG")), (1200, MAX_EDGE))

    def test_a_small_photo_is_never_enlarged(self):
        self.assertEqual(self.size_of(encode(Image.new("RGB", (800, 600), "gray"), "JPEG")), (800, 600))

    def test_a_photo_of_exactly_the_max_edge_is_kept(self):
        self.assertEqual(self.size_of(encode(Image.new("RGB", (MAX_EDGE, 900), "gray"), "JPEG")), (MAX_EDGE, 900))

    def test_a_big_noisy_photo_gets_smaller(self):
        noise = Image.effect_noise((3000, 2000), 60).convert("RGB")
        source = encode(noise, "JPEG", quality=95)
        self.assertLess(len(sanitize_image(source)), len(source))


@unittest.skipUnless(HAVE_PILLOW, "Pillow is not installed")
class FormatTests(unittest.TestCase):
    def test_png_with_a_transparent_background_becomes_white_not_black(self):
        img = Image.new("RGBA", (100, 100), (0, 0, 0, 0))     # fully transparent black
        for x in range(40, 60):
            for y in range(40, 60):
                img.putpixel((x, y), (255, 0, 0, 255))        # an opaque red square
        out = Image.open(io.BytesIO(sanitize_image(encode(img, "PNG")))).convert("RGB")
        self.assertTrue(all(c >= 250 for c in out.getpixel((5, 5))), out.getpixel((5, 5)))
        r, g, b = out.getpixel((50, 50))
        self.assertGreater(r, 200)
        self.assertLess(g, 60)

    def test_palette_png_with_transparency(self):
        img = Image.new("P", (20, 20), 0)
        img.putpalette([0, 0, 0, 255, 0, 0] + [0] * 756)
        img.info["transparency"] = 0
        out = Image.open(io.BytesIO(sanitize_image(encode(img, "PNG", transparency=0)))).convert("RGB")
        self.assertTrue(all(c >= 250 for c in out.getpixel((2, 2))))

    def test_webp_and_png_photos_are_accepted(self):
        photo = Image.new("RGB", (300, 200), (40, 90, 160))
        for fmt in ("WEBP", "PNG"):
            out = sanitize_image(encode(photo, fmt))
            self.assertEqual(Image.open(io.BytesIO(out)).format, "JPEG", fmt)

    def test_grayscale_and_cmyk_photos_come_out_rgb(self):
        for mode in ("L", "CMYK"):
            out = Image.open(io.BytesIO(sanitize_image(encode(Image.new(mode, (50, 50)), "JPEG"))))
            self.assertEqual(out.mode, "RGB", mode)


@unittest.skipUnless(HAVE_PILLOW, "Pillow is not installed")
class RefusalTests(unittest.TestCase):
    def assert_refused(self, data, why):
        with self.assertRaises(InvalidImage, msg=why):
            sanitize_image(data)

    def test_empty(self):
        self.assert_refused(b"", "empty")

    def test_svg_even_if_the_client_says_it_is_a_jpeg(self):
        self.assert_refused(b'<svg xmlns="http://www.w3.org/2000/svg"><script>alert(1)</script></svg>', "svg")

    def test_html_and_plain_text(self):
        self.assert_refused(b"<html><body>hello</body></html>", "html")
        self.assert_refused(b"just some text, not a photo", "text")

    def test_random_bytes(self):
        self.assert_refused(bytes(range(256)) * 20, "random")

    def test_a_truncated_jpeg(self):
        data = encode(Image.effect_noise((600, 400), 80).convert("RGB"), "JPEG", quality=90)
        self.assert_refused(data[: len(data) // 2], "truncated jpeg")

    def test_formats_that_are_not_photos_we_accept(self):
        img = Image.new("RGB", (40, 40), "red")
        self.assert_refused(encode(img, "GIF"), "gif")
        self.assert_refused(encode(img, "BMP"), "bmp")

    def test_a_small_file_with_a_huge_canvas_is_refused_before_it_is_decoded(self):
        side = int(MAX_PIXELS ** 0.5) + 200
        bomb = encode(Image.new("1", (side, side)), "PNG")      # a few KB on disk, ~65 MP when decoded
        self.assertLess(len(bomb), 200_000)
        self.assert_refused(bomb, "decompression bomb")


if __name__ == "__main__":
    unittest.main()
