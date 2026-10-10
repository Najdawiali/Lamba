"""
POST /api/v1/merchant/items/{id}/photos and POST /items/new: what reaches storage.

HTTP-level tests of the real app with the database and the signed-in user replaced by mocks (same
style as test_merchant_market_location_api.py), and storage_service.upload captured, so the bytes
and the file name that would be published on images.lambajo.com can be checked.

Needs the full backend dependencies (it imports app.main) and Pillow.
"""

import ast
import io
import os
import sys
import unittest
import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from httpx import AsyncClient, ASGITransport
from PIL import Image

BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BACKEND)
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")

from app.main import app
from app.api import merchant_v1
from app.api.auth import get_current_user
from app.database import get_db
from app.models.product_image import ProductImage
from app.models.user import User

URL = "https://images.lambajo.com/products/new.jpg"
GPS_IFD = 0x8825


def jpeg_with_gps(size=(400, 200)) -> bytes:
    exif = Image.Exif()
    exif[0x0110] = "SM-TEST"
    exif[GPS_IFD] = {1: "N", 2: (31.0, 57.0, 0.0), 3: "E", 4: (35.0, 55.0, 0.0)}
    out = io.BytesIO()
    Image.new("RGB", size, (30, 120, 60)).save(out, "JPEG", exif=exif, comment=b"home address")
    return out.getvalue()


def is_two_lines(detail) -> bool:
    return isinstance(detail, str) and len(detail.split("\n")) == 2


class PhotoApiCase(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.item_id = uuid.uuid4()
        self.user = User(id=uuid.uuid4(), email="merchant@test.com", user_type="merchant")
        self.item = SimpleNamespace(id=self.item_id, moderation_status="approved")
        self.db = AsyncMock()
        self.db.add = MagicMock()  # Session.add is synchronous
        self.result = MagicMock()
        self.result.scalar_one_or_none.return_value = uuid.uuid4()                 # the merchant stocks it
        self.result.unique.return_value.scalar_one_or_none.return_value = self.item  # the catalog item
        self.result.scalar_one.side_effect = [0, 0]                                 # photos so far, primary photos
        self.db.execute.return_value = self.result
        app.dependency_overrides[get_current_user] = lambda: self.user
        app.dependency_overrides[get_db] = lambda: self.db
        self.upload = AsyncMock(return_value=URL)
        patcher = patch.object(merchant_v1.storage_service, "upload", self.upload)
        patcher.start()
        self.addCleanup(patcher.stop)

    def tearDown(self):
        app.dependency_overrides.clear()

    async def post_photo(self, content, filename="photo.jpg", content_type="image/jpeg"):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            return await client.post(
                f"/api/v1/merchant/items/{self.item_id}/photos",
                files={"image": (filename, content, content_type)},
            )


class TestStoredPhoto(PhotoApiCase):
    async def test_a_photo_with_gps_is_published_without_it(self):
        source = jpeg_with_gps()
        self.assertTrue(Image.open(io.BytesIO(source)).getexif().get_ifd(GPS_IFD), "fixture has no GPS")

        res = await self.post_photo(source)

        self.assertEqual(res.status_code, 200, res.text)
        self.upload.assert_awaited_once()
        stored = self.upload.await_args.kwargs["file_bytes"]
        img = Image.open(io.BytesIO(stored))
        self.assertEqual(img.format, "JPEG")
        self.assertEqual(len(img.getexif()), 0)
        for needle in (b"Exif", b"SM-TEST", b"home address"):
            self.assertNotIn(needle, stored)

    async def test_the_response_and_the_row_are_as_before(self):
        res = await self.post_photo(jpeg_with_gps())
        self.assertEqual(res.json(), {"image_url": URL, "is_primary": True})
        ((row,), _) = self.db.add.call_args
        self.assertIsInstance(row, ProductImage)
        self.assertEqual((row.global_item_id, row.image_url, row.is_primary), (self.item_id, URL, True))
        self.db.commit.assert_awaited_once()

    async def test_a_big_photo_is_resized(self):
        out = io.BytesIO()
        Image.new("RGB", (4000, 3000), "gray").save(out, "JPEG")
        res = await self.post_photo(out.getvalue())
        self.assertEqual(res.status_code, 200, res.text)
        size = Image.open(io.BytesIO(self.upload.await_args.kwargs["file_bytes"])).size
        self.assertEqual(size, (1600, 1200))

    async def test_the_stored_name_does_not_come_from_the_client(self):
        for client_name in ("evil.svg", "x.html", "photo.png", "../../etc/passwd", ""):
            self.upload.reset_mock()
            self.result.scalar_one.side_effect = [0, 0]
            res = await self.post_photo(jpeg_with_gps(), filename=client_name or "blob")
            self.assertEqual(res.status_code, 200, f"{client_name}: {res.text}")
            self.assertEqual(self.upload.await_args.kwargs["original_filename"], "photo.jpg", client_name)

    async def test_a_png_is_stored_as_a_jpeg(self):
        out = io.BytesIO()
        Image.new("RGBA", (200, 200), (255, 0, 0, 128)).save(out, "PNG")
        res = await self.post_photo(out.getvalue(), filename="shot.png", content_type="image/png")
        self.assertEqual(res.status_code, 200, res.text)
        self.assertEqual(Image.open(io.BytesIO(self.upload.await_args.kwargs["file_bytes"])).format, "JPEG")


class TestRefusedUploads(PhotoApiCase):
    async def assert_refused(self, res, status_code):
        self.assertEqual(res.status_code, status_code, res.text)
        self.assertTrue(is_two_lines(res.json()["detail"]), res.json()["detail"])  # Arabic line, English line
        self.upload.assert_not_awaited()
        self.db.commit.assert_not_awaited()

    async def test_svg_is_refused(self):
        svg = b'<svg xmlns="http://www.w3.org/2000/svg"><script>alert(1)</script></svg>'
        await self.assert_refused(await self.post_photo(svg, "logo.svg", "image/svg+xml"), 415)

    async def test_svg_claiming_to_be_a_jpeg_is_refused(self):
        svg = b'<svg xmlns="http://www.w3.org/2000/svg"><script>alert(1)</script></svg>'
        await self.assert_refused(await self.post_photo(svg, "photo.jpg", "image/jpeg"), 415)

    async def test_a_text_file_claiming_to_be_an_image_is_refused(self):
        await self.assert_refused(await self.post_photo(b"not a photo", "a.jpg", "image/jpeg"), 415)

    async def test_a_non_image_content_type_is_refused(self):
        await self.assert_refused(await self.post_photo(jpeg_with_gps(), "a.pdf", "application/pdf"), 415)

    async def test_an_empty_file_is_refused(self):
        await self.assert_refused(await self.post_photo(b""), 422)

    async def test_a_too_large_upload_is_refused(self):
        with patch.object(merchant_v1, "MAX_PHOTO_BYTES", 1000):
            res = await self.post_photo(jpeg_with_gps())
        await self.assert_refused(res, 413)

    async def test_a_product_the_merchant_does_not_stock_is_refused(self):
        self.result.scalar_one_or_none.return_value = None
        await self.assert_refused(await self.post_photo(jpeg_with_gps()), 403)

    async def test_an_unknown_or_blocked_product_is_404(self):
        self.item.moderation_status = "blocked"
        await self.assert_refused(await self.post_photo(jpeg_with_gps()), 404)

    async def test_a_product_with_enough_photos_is_409(self):
        self.result.scalar_one.side_effect = [merchant_v1.MAX_PHOTOS_PER_ITEM, 1]
        await self.assert_refused(await self.post_photo(jpeg_with_gps()), 409)


class TestEveryUploadSite(unittest.TestCase):
    def test_every_storage_upload_in_merchant_v1_gets_cleaned_bytes_and_a_fixed_name(self):
        # POST /items/new has a primary and secondary photos with the same rules as the photo endpoint, and no
        # HTTP test here (it needs the classifier, the category and the embedding mocked). Instead: no
        # storage_service.upload call may take the client's bytes or the client's file name.
        path = os.path.join(BACKEND, "app", "api", "merchant_v1.py")
        with open(path, encoding="utf-8") as f:
            tree = ast.parse(f.read())
        calls = [
            n for n in ast.walk(tree)
            if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute) and n.func.attr == "upload"
            and isinstance(n.func.value, ast.Name) and n.func.value.id == "storage_service"
        ]
        self.assertGreaterEqual(len(calls), 3, "expected the photo endpoint and /items/new (primary + secondary)")
        for call in calls:
            kw = {k.arg: k.value for k in call.keywords}
            name = kw.get("original_filename")
            self.assertTrue(isinstance(name, ast.Constant) and name.value == "photo.jpg",
                            f"line {call.lineno}: the stored file name must be the constant photo.jpg")
            self.assertFalse(
                any(isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute) and n.func.attr == "read"
                    for n in ast.walk(kw["file_bytes"])),
                f"line {call.lineno}: file_bytes must be the cleaned bytes, not a raw .read() of an upload",
            )

    def test_the_new_item_endpoint_cleans_every_image_it_stores(self):
        path = os.path.join(BACKEND, "app", "api", "merchant_v1.py")
        with open(path, encoding="utf-8") as f:
            tree = ast.parse(f.read())
        fn = next(n for n in ast.walk(tree) if isinstance(n, ast.AsyncFunctionDef) and n.name == "create_new_item")
        cleaned = [
            n for n in ast.walk(fn)
            if isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id == "_clean_image_upload"
        ]
        self.assertEqual(len(cleaned), 2, "primary image and the secondary images")


if __name__ == "__main__":
    unittest.main()
