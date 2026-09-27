"""Unit tests for scripts/build-course-images.py."""
import json
import os
import unittest
import xml.etree.ElementTree as ET

from _loader import ROOT, load

images = load("build-course-images.py")

try:
    from PIL import Image
    HAVE_PIL = True
except ImportError:  # pragma: no cover - CI installs Pillow
    HAVE_PIL = False


class PlannedOutputs(unittest.TestCase):
    def test_covers_every_shipped_course(self):
        courses = images.course_models()
        self.assertTrue(courses, "no courses discovered")
        planned = {os.path.relpath(p, ROOT) for p, _ in images.planned_outputs()}
        for course in courses:
            self.assertIn(
                os.path.join("courses", course["slug"], "olx", "static",
                             f"{course['slug']}-course-card.png"),
                planned)

    def test_includes_the_brand_rasters(self):
        planned = {os.path.relpath(p, ROOT) for p, _ in images.planned_outputs()}
        for name in ("favicon-32.png", "apple-touch-icon.png", "atheniq-og.png"):
            self.assertIn(os.path.join("web", "landing", "assets", name), planned)

    def test_every_card_is_sixteen_by_nine(self):
        for path, size in images.planned_outputs():
            if path.endswith("-course-card.png"):
                self.assertEqual(size, images.CARD_SIZE)


class ShippedRasters(unittest.TestCase):
    def test_every_raster_exists_and_matches_its_spec(self):
        for path, size in images.planned_outputs():
            self.assertTrue(os.path.isfile(path), f"{path} missing (run make images)")
            if HAVE_PIL:
                with Image.open(path) as img:
                    self.assertEqual(img.size, size, path)

    def test_every_policy_course_image_is_a_committed_raster(self):
        for course in images.course_models():
            run = ET.parse(os.path.join(course["olx"], "course.xml")).getroot().get("url_name")
            with open(os.path.join(course["olx"], "policies", run, "policy.json")) as fh:
                policy = json.load(fh)
            image = policy[f"course/{run}"]["course_image"]
            self.assertTrue(image.endswith(".png"), image)
            self.assertTrue(os.path.isfile(os.path.join(course["olx"], "static", image)), image)


class InlineFavicon(unittest.TestCase):
    """The stack's conformity audit wants a self-contained SVG favicon."""

    def test_landing_page_embeds_the_current_favicon(self):
        page = (ROOT / "web" / "landing" / "index.html").read_text()
        self.assertIn(images.inline_favicon(), page)

    def test_generated_pages_embed_the_current_favicon(self):
        data_uri = images.inline_favicon()
        for rel in ("web/landing/catalog/index.html",
                    "web/landing/courses/it-support-certification/index.html"):
            self.assertIn(data_uri, (ROOT / rel).read_text(), rel)


@unittest.skipUnless(HAVE_PIL, "Pillow not installed")
class Rendering(unittest.TestCase):
    def test_course_card_is_sized_and_not_blank(self):
        card = images.render_course_card("ITSP101", "IT Support Foundations",
                                         "Innotel Labs · IT Support Specialist track")
        self.assertEqual(card.size, images.CARD_SIZE)
        colours = card.getcolors(maxcolors=1_000_000)
        self.assertGreater(len(colours), 8, "card looks blank")

    def test_mark_tile_is_square_with_transparent_corners(self):
        tile = images.render_mark_tile(180)
        self.assertEqual(tile.size, (180, 180))
        self.assertEqual(tile.convert("RGBA").getpixel((0, 0))[3], 0)
        self.assertEqual(tile.convert("RGBA").getpixel((90, 90))[3], 255)

    def test_mark_tile_stays_open_at_favicon_size(self):
        """The pupil must not fuse with the eye ring at 20px (Brand.md minimum)."""
        size = 20
        px = images.render_mark_tile(size).convert("RGBA").load()
        x0, y0, x1, y1 = images.mark_bounds()
        scale = size * images.FAVICON_MARK_HEIGHT / (y1 - y0)
        ox = size / 2 - (x0 + x1) / 2 * scale
        oy = size / 2 - (y0 + y1) / 2 * scale
        ex = ox + images.EYE_RINGS[0][0] * scale
        ey = oy + images.EYE_RINGS[0][1] * scale
        inner = images.EYE_R - images.EYE_STROKE / 2
        gap = 0
        for i in range(8):
            t = images.PUPIL_R + (i + 0.5) / 8 * (inner - images.PUPIL_R)
            x, y = int(round(ex + t * scale)), int(round(ey))
            if 0 <= x < size and 0 <= y < size and px[x, y][:3] == images.TILE_BG:
                gap += 1
        self.assertGreater(gap, 0, "pupil and eye ring fuse at 20px")

    def test_check_passes_on_the_committed_assets(self):
        self.assertEqual(images.check(), [])


if __name__ == "__main__":
    unittest.main()
