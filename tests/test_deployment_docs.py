"""Filenames the deploy instructions tell an operator to run must exist.

A rename lands in the units first and the docs second, or not at all: the last
console-uptime rename left `docs/Deployment.md` copy-pasting a timer and script
that no longer existed. Anything the doc names as a repo path (`scripts/…`,
`deploy/…`) or as a unit (`atheniq-*.timer`/`.service`) is resolved here.

Absolute paths into an LMS or Open edX checkout (`manage.py`, `cms/…`), `/tmp`
copies and `/path/to` placeholders name other machines' files, so they are not
this repo's to verify. Bare script names (`deploy.sh` in prose) are skipped too;
only qualified script paths and unit filenames are in scope.
"""
import pathlib
import re
import unittest

ROOT = pathlib.Path(__file__).resolve().parent.parent
DOC = ROOT / "docs" / "Deployment.md"
SYSTEMD = ROOT / "deploy" / "systemd"

NAME = re.compile(
    r"(?<![\w./-])((?:\.{1,2}/)?(?:[\w.-]+/)*[\w.-]+\.(?:py|sh|service|timer))"
)
REPO_DIRS = {"scripts", "deploy", "tests", "contrib"}
CHECKOUT_ROOTS = ("/home/tutor/atheniq/", "/usr/src/projects/complete/atheniq/")

#: Deleted units the retirement section still names on purpose, so operators can
#: disable and remove what an older install left behind.
RETIRED_UNITS = {
    "atheniq-generation.service",
    "atheniq-generation-uptime.service",
    "atheniq-generation-uptime.timer",
    "atheniq-student.service",
}


def mentions(text):
    """Yield repo-relative paths and unit filenames the doc names."""
    for raw in NAME.findall(text):
        name = raw
        changed = True
        while changed:
            changed = False
            for prefix in ("./", "../"):
                if name.startswith(prefix):
                    name = name[len(prefix):]
                    changed = True
        for prefix in CHECKOUT_ROOTS:
            if name.startswith(prefix):
                name = name[len(prefix):]
        if "/" in name:
            if name.split("/")[0] in REPO_DIRS:
                yield name
        elif name.endswith((".service", ".timer")):
            yield name


class DeploymentDocTest(unittest.TestCase):
    def test_named_scripts_and_units_exist(self):
        named = sorted(set(mentions(DOC.read_text())))
        self.assertTrue(named, "no filenames found in Deployment.md")

        for name in named:
            if "/" in name:
                target = ROOT / name
            else:
                if name in RETIRED_UNITS:
                    continue
                target = SYSTEMD / name
            with self.subTest(name=name):
                self.assertTrue(
                    target.is_file(),
                    f"Deployment.md names {name}, which is not in the repo",
                )

    def test_retired_units_are_not_described_as_current(self):
        text = DOC.read_text()
        for name in RETIRED_UNITS:
            if name not in text:
                continue
            with self.subTest(name=name):
                self.assertNotIn(
                    f"sudo cp deploy/systemd/{name}",
                    text,
                    f"Deployment.md installs retired unit {name}",
                )


if __name__ == "__main__":
    unittest.main()
