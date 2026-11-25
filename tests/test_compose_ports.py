"""The console's port and the retired classroom front must not drift back.

Two edits in this repo pull 8090 back into service on the reference host: giving
the `generation` service a default profile again (so `deploy.sh`'s untargeted
`docker compose up --remove-orphans` starts it), or moving the console's
published port off 8094 (where `generation-sso` and the uptime probe expect it).
Neither shows up as a failing unit test anywhere else, so this file pins both.

The compose file is read as text, like `test_sso_doors.py`: the repo runs its
tests with the system `python3` and no PyYAML dependency.
"""
import pathlib
import re
import unittest

ROOT = pathlib.Path(__file__).resolve().parent.parent
COMPOSE = ROOT / "docker-compose.yml"
ENV_EXAMPLE = ROOT / ".env.example"

SERVICE = re.compile(r"^  ([a-z][a-z0-9-]*):\s*$")

#: The retired Python classroom front. Its unit is gone and the Next console
#: serves the staff screen; this service may only run when asked for by name.
LEGACY_SERVICE = "generation"
LEGACY_PORT = "8090"

#: The console's published port: `generation-sso` forwards here and the uptime
#: probe reads `/api/health` here.
CONSOLE_PORT = "8094"


def services(text):
    """Map each top-level compose service to its own config lines (no YAML).

    Comment lines are dropped: a service's comment block sits above its key, so
    keeping them would attribute the next service's prose to the previous one.
    """
    out = {"": []}
    current = ""
    for line in text.splitlines():
        match = SERVICE.match(line)
        if match:
            current = match.group(1)
            out[current] = []
            continue
        if line.lstrip().startswith("#"):
            continue
        out.setdefault(current, []).append(line)
    return out


class ComposePortTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.services = services(COMPOSE.read_text())

    def test_generation_is_behind_its_profile(self):
        self.assertIn(LEGACY_SERVICE, self.services)
        lines = "\n".join(self.services[LEGACY_SERVICE])
        profile = re.search(r"^\s+profiles:\s*(.+)$", lines, re.MULTILINE)
        self.assertIsNotNone(
            profile,
            "the generation service must stay behind a profile, or a plain "
            "`docker compose up` (and deploy.sh) starts it on 8090 again",
        )
        self.assertIn(LEGACY_SERVICE, profile.group(1))

    def test_no_other_service_names_8090(self):
        offenders = [
            name
            for name, lines in self.services.items()
            if name and name != LEGACY_SERVICE and LEGACY_PORT in "\n".join(lines)
        ]
        self.assertEqual(
            offenders,
            [],
            f"only the profiled {LEGACY_SERVICE} front may name {LEGACY_PORT}",
        )

    def test_console_publishes_8094(self):
        ports = [line for line in self.services["console"] if "CONSOLE_PORT" in line]
        self.assertEqual(len(ports), 1, "the console needs one published port")
        self.assertIn(f"${{CONSOLE_PORT:-{CONSOLE_PORT}}}", ports[0])

    def test_env_example_matches_the_console_default(self):
        match = re.search(r"^CONSOLE_PORT=(\S+)$", ENV_EXAMPLE.read_text(), re.MULTILINE)
        self.assertIsNotNone(match, "CONSOLE_PORT must be listed in .env.example")
        self.assertEqual(match.group(1), CONSOLE_PORT)


if __name__ == "__main__":
    unittest.main()
