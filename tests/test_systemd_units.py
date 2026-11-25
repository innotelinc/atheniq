"""A unit's ExecStart must name a file this repo actually ships.

Renaming a script is invisible to systemd: the unit keeps starting the old path,
fails at the next timer tick, and nothing here notices until a host reports it.
This walks every `deploy/systemd/*.service` and resolves the paths that point
into a checkout — `/home/tutor/atheniq/` on the classroom host,
`/usr/src/projects/complete/atheniq/` on the LMS host — against the repo. The
timer half checks the other direction: every `*.timer` must name a `.service`
that is still in `deploy/systemd`, so renaming a service cannot leave a timer
pointing at nothing.

Paths outside a checkout (`/usr/bin/python3`, `/opt/node/bin/node`, the console's
`/opt/atheniq-console` install) are deployment facts a unit test cannot check and
are skipped.
"""
import pathlib
import re
import unittest

ROOT = pathlib.Path(__file__).resolve().parent.parent
SYSTEMD = ROOT / "deploy" / "systemd"

#: Where the host checkouts put this repo, as the units spell it.
CHECKOUT_ROOTS = (
    "/home/tutor/atheniq/",
    "/usr/src/projects/complete/atheniq/",
)

EXEC = re.compile(r"^ExecStart(?:Pre|Post)?\s*=\s*(.+)$")
UNIT = re.compile(r"^Unit\s*=\s*(\S+)\s*$")


def repo_paths(command):
    """Yield the checkout-relative paths an ExecStart line runs."""
    for token in command.split():
        for prefix in CHECKOUT_ROOTS:
            if token.startswith(prefix):
                yield token[len(prefix):]


class ExecStartTest(unittest.TestCase):
    def test_units_start_a_file_that_exists(self):
        units = sorted(SYSTEMD.glob("*.service"))
        self.assertTrue(units, "no service units found")

        checked = 0
        for unit in units:
            text = unit.read_text()
            commands = [m.group(1) for m in map(EXEC.match, text.splitlines()) if m]
            self.assertTrue(commands, f"{unit.name} has no ExecStart")

            for command in commands:
                for relative in repo_paths(command):
                    checked += 1
                    with self.subTest(unit=unit.name, path=relative):
                        self.assertFalse(relative.startswith("../"), relative)
                        self.assertTrue(
                            (ROOT / relative).is_file(),
                            f"{unit.name} runs {relative}, which is not in the repo",
                        )

        # If the checkout roots above ever stop matching, the loop passes
        # vacuously and guards nothing — this keeps that from happening.
        self.assertGreater(checked, 0, "no unit ExecStart resolved into the repo")


class TimerUnitTest(unittest.TestCase):
    def test_timers_name_a_service_that_exists(self):
        timers = sorted(SYSTEMD.glob("*.timer"))
        self.assertTrue(timers, "no timer units found")

        for timer in timers:
            names = [m.group(1) for m in map(UNIT.match, timer.read_text().splitlines()) if m]
            self.assertEqual(len(names), 1, f"{timer.name} needs exactly one Unit=")
            target = names[0]

            with self.subTest(timer=timer.name, unit=target):
                self.assertTrue(
                    target.endswith(".service"),
                    f"{timer.name} targets {target}, not a service unit",
                )
                self.assertTrue(
                    (SYSTEMD / target).is_file(),
                    f"{timer.name} targets {target}, which is not in deploy/systemd",
                )


if __name__ == "__main__":
    unittest.main()
