"""Unit tests for scripts/check-brand-mark.py."""
import os
import shutil
import tempfile
import unittest

from _loader import ROOT, load

brand = load("check-brand-mark.py")


class Fragments(unittest.TestCase):
    def test_fragments_track_the_geometry(self):
        joined = " | ".join(brand.expected_fragments())
        im = brand.IMAGES
        # Every stroke is one path, point for point.
        for path in im.MARK_STROKES:
            self.assertIn("M" + " L".join(f"{brand._num(x)} {brand._num(y)}"
                                           for x, y in path), joined)
        # The spark and the tassel's knot are the solid pass.
        self.assertIn("M" + " L".join(f"{brand._num(x)} {brand._num(y)}"
                                      for x, y in im.SPARK) + " Z", joined)
        self.assertIn(f'r="{brand._num(im.KNOT_R)}"', joined)
        # Stroke width is the geometry's, not a copy.
        self.assertIn(f'stroke-width="{brand._num(im.MARK_STROKE)}"', joined)

    def test_favicon_transform_is_derived(self):
        attr = brand.IMAGES.favicon_transform_attr()
        self.assertRegex(attr, r"^translate\(-?\d+(\.\d+)? -?\d+(\.\d+)?\) scale\(\d+(\.\d+)?\)$")

    def test_normalize_ignores_paint(self):
        a = brand.normalize('stroke="url(#atheniq-mark)"')
        b = brand.normalize('stroke="url(#g)"')
        self.assertEqual(a, b)


class Repository(unittest.TestCase):
    def test_shipped_svgs_are_in_sync(self):
        self.assertEqual(brand.check(), [])

    def test_detects_drift_in_a_copy(self):
        tmp = tempfile.mkdtemp()
        try:
            for rel in ("web/landing/assets", "courses/capstone/olx/static"):
                os.makedirs(os.path.join(tmp, rel), exist_ok=True)
            for rel in ("web/landing/assets/atheniq-mark.svg",
                        "web/landing/assets/atheniq-logo.svg",
                        "web/landing/assets/favicon.svg",
                        "courses/capstone/olx/static/capstone-course-card.svg"):
                shutil.copy(os.path.join(ROOT, rel), os.path.join(tmp, rel))
            # Mutate the card's stroke so it no longer matches the geometry.
            card = os.path.join(tmp, "courses/capstone/olx/static/capstone-course-card.svg")
            real = f'stroke-width="{brand._num(brand.IMAGES.MARK_STROKE)}"'
            body = open(card).read().replace(real, 'stroke-width="3.5"')
            open(card, "w").write(body)
            problems = brand.check(repo=tmp)
            self.assertTrue(any("stroke-width" in p for p in problems), problems)
        finally:
            shutil.rmtree(tmp)


if __name__ == "__main__":
    unittest.main()
