"""Filenames the deploy instructions tell an operator to run must exist.

A rename lands in the units first and the docs second, or not at all: the last
console-uptime rename left `docs/Deployment.md` copy-pasting a timer and script
that no longer existed. Anything a doc names as a repo path (`scripts/…`,
`deploy/…`) or as a unit (`atheniq-*.timer`/`.service`) is resolved here.

Paths are tried from the repo root and from the doc's own directory, because
`console/README.md` writes `deploy/rebuild-on-host.sh` for a command run inside
`console/`. Absolute paths into an LMS or Open edX checkout (`manage.py`,
`cms/…`), `/tmp` copies and `/path/to` placeholders name other machines' files,
so they are not this repo's to verify. Bare script names (`deploy.sh` in prose)
are skipped too; only qualified script paths and unit filenames are in scope.
"""
import pathlib
import re
import unittest

ROOT = pathlib.Path(__file__).resolve().parent.parent
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


def docs():
    """Every Markdown file that ships with the repo."""
    return [
        path
        for path in sorted(ROOT.rglob("*.md"))
        if not {".git", "node_modules"} & set(path.parts)
    ]


def mentions(text):
    """Yield the raw paths and unit filenames a doc names."""
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
                yield raw, name
        elif name.endswith((".service", ".timer")):
            yield raw, name


def targets(doc, raw, name):
    """Where a named path may live, given how the doc writes it."""
    if "/" not in name:
        return [SYSTEMD / name]
    candidates = [ROOT / name, (doc.parent / raw).resolve()]
    return [path for path in candidates if path.is_relative_to(ROOT)]


class DeploymentDocTest(unittest.TestCase):
    def test_named_scripts_and_units_exist(self):
        markdown = docs()
        self.assertTrue(markdown, "no Markdown files found")

        found = 0
        for doc in markdown:
            for raw, name in sorted(set(mentions(doc.read_text()))):
                if name in RETIRED_UNITS:
                    continue
                found += 1
                with self.subTest(doc=str(doc.relative_to(ROOT)), name=name):
                    self.assertTrue(
                        any(path.is_file() for path in targets(doc, raw, name)),
                        f"{doc.relative_to(ROOT)} names {name}, which is not in the repo",
                    )

        # If the patterns ever stop matching, the loop passes vacuously.
        self.assertGreater(found, 0, "no filenames found in the docs")

    def test_retired_units_are_not_described_as_current(self):
        deployment = ROOT / "docs" / "Deployment.md"
        text = deployment.read_text()
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
