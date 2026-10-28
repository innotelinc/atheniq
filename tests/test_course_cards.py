"""Per-course cards: one image per course, carrying its own program and title.

The catalog used to show photographs from a subject pool, so two courses of one
program could share a picture and no card said which course it was. These tests
pin the renderer's contract: every program course becomes one 1600x900 JPEG, the
title always fits the copy column, and the photo resolver prefers the rendered
card over the pool. They also pin the join that makes the workforce runs cards:
a course a track carries is read from the track, and a code no track owns keeps
its program plan's name.
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


TRACKS = {
    "version": 1,
    "tracks": [
        {
            "id": "test-track",
            "title": "Test Workforce Track",
            "status": "active",
            "credential": {"type": "certificate",
                           "title": "Test Track — Certification"},
            "courses": ["course-v1:TestOrg+ITSP101+2026_T1",
                        "course-v1:TestOrg+BUS101+2026_T1"],
        },
        {
            "id": "draft-track",
            "title": "Draft Track",
            "status": "draft",
            "courses": ["course-v1:TestOrg+OLD101+2026_T1"],
        },
    ],
}

PRICES = {
    "courses": {
        "course-v1:TestOrg+ITSP101+2026_T1": {"name": "ITSP101 — IT Support Foundations"},
        "course-v1:TestOrg+BUS101+2026_T1": {"name": "BUS101 - Introduction to Business"},
        "course-v1:TestOrg+TEST101+2026_T1": {"name": "TEST101 — Introduction"},
    },
}


def _config_files():
    """A temp tracks catalog and course sheet, so no test reads the real ones."""
    directory = tempfile.mkdtemp(prefix="atheniq-cards-config-")
    tracks = os.path.join(directory, "workforce-tracks.json")
    prices = os.path.join(directory, "course-prices.json")
    with open(tracks, "w", encoding="utf-8") as fh:
        json.dump(TRACKS, fh)
    with open(prices, "w", encoding="utf-8") as fh:
        json.dump(PRICES, fh)
    return tracks, prices


class Tracks(unittest.TestCase):
    def setUp(self):
        self.tracks, self.prices = _config_files()

    def test_a_track_course_carries_the_track_and_its_credential(self):
        entries = {entry["code"]: entry
                   for entry, _photo in CARDS.track_entries(self.tracks, self.prices)}
        self.assertEqual(sorted(entries), ["BUS101", "ITSP101"])
        course = entries["ITSP101"]
        self.assertEqual(course["program"], "Test Workforce Track")
        self.assertEqual(course["credential"], "Test Track — Certification")
        self.assertEqual(course["semester"], "")
        self.assertIsNone(course["credits"])

    def test_the_headline_is_the_name_after_the_code(self):
        entries = {entry["code"]: entry
                   for entry, _photo in CARDS.track_entries(self.tracks, self.prices)}
        # An em dash and a plain hyphen both name the course after the chip.
        self.assertEqual(entries["ITSP101"]["title"], "IT Support Foundations")
        self.assertEqual(entries["BUS101"]["title"], "Introduction to Business")

    def test_the_term_is_the_run_the_sheet_lists(self):
        entries = {entry["code"]: entry
                   for entry, _photo in CARDS.track_entries(self.tracks, self.prices)}
        self.assertEqual(entries["ITSP101"]["term"], "2026 T1")
        overridden = CARDS.track_entries(self.tracks, self.prices, term="2027_T2")
        self.assertEqual({entry["term"] for entry, _ in overridden}, {"2027_T2"})

    def test_a_draft_track_publishes_nothing(self):
        codes = [entry["code"] for entry, _ in CARDS.track_entries(self.tracks, self.prices)]
        self.assertNotIn("OLD101", codes)

    def test_a_track_owns_the_course_it_sells(self):
        entries = {entry["code"]: entry
                   for entry, _photo in CARDS.course_entries(
                       _programs_dir(), tracks_path=self.tracks,
                       prices_path=self.prices)}
        # BUS101 is in both: the track is the ladder the catalog sells, so its
        # title is the eyebrow and its credential the footer, while BUS110 —
        # which the track does not carry — stays the plan's card.
        self.assertEqual(entries["BUS101"]["program"], "Test Workforce Track")
        self.assertEqual(entries["BUS110"]["program"], "Test Business Administration")
        self.assertEqual(entries["ITSP101"]["program"], "Test Workforce Track")

    def test_a_catalog_course_with_no_credential_is_badged_as_the_platform(self):
        entries = {entry["code"]: entry
                   for entry, _photo in CARDS.course_entries(
                       _programs_dir(), tracks_path=self.tracks,
                       prices_path=self.prices)}
        self.assertEqual(entries["TEST101"]["program"], "AthenIQ")
        self.assertEqual(entries["TEST101"]["credential"], "")

    def test_a_missing_catalog_is_skipped_rather_than_fatal(self):
        entries = CARDS.course_entries(_programs_dir(),
                                       tracks_path="/nonexistent/tracks.json",
                                       prices_path="/nonexistent/prices.json")
        self.assertEqual([entry["code"] for entry, _ in entries], ["BUS101", "BUS110"])


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

    def test_a_publish_renders_only_the_courses_it_imported(self):
        # Publishing passes the codes it created; a two-course publish must not
        # cost a catalog-wide render.
        tracks, prices = _config_files()
        manifest = CARDS.build(self.programs, self.out, term="2026_T4",
                               tracks_path=tracks, prices_path=prices,
                               only=["ITSP101"])
        self.assertEqual([card["code"] for card in manifest["cards"]], ["ITSP101"])

    def test_the_whole_catalog_renders_once_each_with_its_own_program(self):
        tracks, prices = _config_files()
        manifest = CARDS.build(self.programs, self.out, term="2026_T4",
                               tracks_path=tracks, prices_path=prices)
        codes = [card["code"] for card in manifest["cards"]]
        self.assertEqual(sorted(codes), ["BUS101", "BUS110", "ITSP101", "TEST101"])
        self.assertEqual(len(codes), len(set(codes)), "a course is one card")
        programs = {card["code"]: card["program"] for card in manifest["cards"]}
        # BUS101 is both: the track it is sold in names it, and BUS110 stays the plan's.
        self.assertEqual(programs["BUS101"], "Test Workforce Track")
        self.assertEqual(programs["BUS110"], "Test Business Administration")
        self.assertEqual(programs["ITSP101"], "Test Workforce Track")
        self.assertEqual(programs["TEST101"], "AthenIQ")
        for card in manifest["cards"]:
            with CARDS.Image.open(os.path.join(self.out, card["file"])) as image:
                self.assertEqual(image.size, (1600, 900), card["code"])


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

    def test_the_renderer_reads_the_pool_not_the_card_it_wrote_last_time(self):
        # The renderer writes its cards into the directory this resolver reads, so a
        # second run must take the photograph from the pool again — taking its own
        # last output would nest one card inside the next, which is not idle drift.
        directory = tempfile.mkdtemp(prefix="atheniq-photos-")
        path = os.path.join(directory, "ZZZ999.jpg")
        open(path, "wb").close()
        original = PHOTOS.PHOTO_DIR
        PHOTOS.PHOTO_DIR = directory
        try:
            photo = PHOTOS.resolve("ZZZ999", "Something Entirely New",
                                   allow_rendered=False)
        finally:
            PHOTOS.PHOTO_DIR = original
        self.assertNotEqual(photo["file"], "ZZZ999.jpg")

    def test_a_course_without_its_own_card_still_gets_a_pool_photo(self):
        photo = PHOTOS.resolve("NUR101", "Nursing Fundamentals")
        self.assertTrue((ROOT / "contrib" / "atheniq-theme" / "lms" / "static"
                         / "images" / "courses" / photo["file"]).is_file())
