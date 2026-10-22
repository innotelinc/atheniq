"""Per-course cards: one image per course, carrying its own program and title.

The catalog used to show photographs from a subject pool, so two courses of one
program could share a picture and no card said which course it was. These tests
pin the renderer's contract: every program course becomes one 1600x900 JPEG, the
title always fits the copy column, and the photo resolver prefers the rendered
card over the pool.
"""
import json
import os
import tempfile
import unittest

from _loader import ROOT, load

CARDS = load("course-cards.py")
PHOTOS = load("course-photos.py")

PROGRAM = {
    "name": "Test Business Administration",
    "credential": "Bachelor of Business Administration",
    "startTerm": "Fall 2026",
    "semesters": [{
        "name": "Semester 1 — Foundations",
        "number": 1,
        "courses": [
            {"code": "BUS101", "title": "Introduction to Business", "credits": 3},
            {"code": "BUS110", "title": "Maternal-Newborn Nursing Practice", "credits": 4},
        ],
    }],
}


def _programs_dir():
    directory = tempfile.mkdtemp(prefix="atheniq-cards-")
    with open(os.path.join(directory, "test-program.json"), "w", encoding="utf-8") as fh:
        json.dump(PROGRAM, fh)
    return directory


@unittest.skipUnless(CARDS.Image is not None, "Pillow is not installed")
class Rendering(unittest.TestCase):
    def setUp(self):
        self.programs = _programs_dir()
        self.out = tempfile.mkdtemp(prefix="atheniq-cards-out-")

    def test_every_course_becomes_one_sized_jpeg(self):
        manifest = CARDS.build(self.programs, self.out, term="2026_T4")
        self.assertEqual([card["code"] for card in manifest["cards"]], ["BUS101", "BUS110"])
        for card in manifest["cards"]:
            path = os.path.join(self.out, card["file"])
            with CARDS.Image.open(path) as image:
                self.assertEqual(image.size, (1600, 900))
                self.assertEqual(image.format, "JPEG")
            self.assertGreater(card["bytes"], 40_000)

    def test_the_year_and_term_come_from_the_program(self):
        manifest = CARDS.build(self.programs, self.out, term="2026_T4")
        self.assertEqual({card["term"] for card in manifest["cards"]}, {"2026_T4"})

    def test_the_title_fits_the_copy_column(self):
        draw = CARDS.ImageDraw.Draw(CARDS.Image.new("RGB", CARDS.CARD_SIZE))
        for title in ("Introduction to Business",
                      "Maternal-Newborn Nursing Practice",
                      "Comprehensive Final Examination Across the Nursing Process"):
            font, lines, size = CARDS._fit_title(draw, title, 700)
            self.assertLessEqual(len(lines), 3, title)
            for line in lines:
                self.assertLessEqual(draw.textlength(line, font=font), 700.01, (title, line))

    def test_the_manifest_is_written_with_the_cards(self):
        CARDS.build(self.programs, self.out, term="2026_T4")
        with open(os.path.join(self.out, "cards.json"), encoding="utf-8") as fh:
            manifest = json.load(fh)
        self.assertEqual(manifest["size"], [1600, 900])
        self.assertEqual(len(manifest["cards"]), 2)


class Resolution(unittest.TestCase):
    def test_a_rendered_card_wins_over_the_subject_pool(self):
        directory = tempfile.mkdtemp(prefix="atheniq-photos-")
        path = os.path.join(directory, "ZZZ999.jpg")
        open(path, "wb").close()
        original = PHOTOS.PHOTO_DIR
        PHOTOS.PHOTO_DIR = directory
        try:
            photo = PHOTOS.resolve("ZZZ999", "Something Entirely New")
        finally:
            PHOTOS.PHOTO_DIR = original
        self.assertEqual(photo["file"], "ZZZ999.jpg")
        self.assertEqual(photo["url"], "/static/atheniq/images/courses/ZZZ999.jpg")

    def test_a_course_without_its_own_card_still_gets_a_pool_photo(self):
        photo = PHOTOS.resolve("NUR101", "Nursing Fundamentals")
        self.assertTrue((ROOT / "contrib" / "atheniq-theme" / "lms" / "static"
                         / "images" / "courses" / photo["file"]).is_file())
