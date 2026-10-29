"""The SSO doors may only name groups Authentik actually has.

A door's `--allowed-group` is a membership test against the `groups` claim. If the
name is wrong the claim never matches, the proxy has already accepted a perfectly
good sign-in, and the browser is answered with a **403 on `/oauth2/callback`** —
which is what `--allowed-group=AthenIQ` did on `ai.atheniq.courses`: no group of
that name has ever existed, so only the two admins could enter and every other
AthenIQ account was refused after Authentik had authenticated it.

There is no live Authentik to ask from a unit test, so the roster below is the
list of group names as Authentik held it, checked in beside the doors. It is not
a permission list — it says nothing about who is in a group, only that the name
can be held. Refresh it when a group is created or renamed:

    incus exec proxy -- docker exec cerulean printenv AUTHENTIK_BOOTSTRAP_TOKEN
    curl -H "Authorization: Bearer $TOKEN" \\
         'https://auth.cerulean.innotel.us/api/v3/core/groups/?page_size=200'

The other half of the check is the audience each door names, and the staff lists
the apps behind them keep (`PORTAL_ADMIN_GROUPS`, `GENERATION_ALLOWED_GROUPS`):
a staff list has to be a subset of the audience that can reach it, or the app
denies somebody the door just admitted.
"""
import pathlib
import re
import unittest

ROOT = pathlib.Path(__file__).resolve().parent.parent
COMPOSE = ROOT / "deploy" / "compose" / "atheniq-sso.yml"
SYSTEMD = ROOT / "deploy" / "systemd"
ROOT_SCRIPT = ROOT.parent / "atheniq-generation-sso.sh"

#: Every group Authentik held when this list was taken (2026-10-29, 44 groups).
AUTHENTIK_GROUPS = {
    "AthenIQ LMS", "Atlas Chef", "Capstone", "Cerulean", "Incus", "Jellyfin",
    "Magnate", "Mail", "Monarch", "Monit", "Oasis", "Olympus", "Onyx", "PLUTUS",
    "PM3", "PM4", "Rizz Aura", "Signara", "ZapIt", "Zeus",
    "atheniq-admins", "authentik Admins", "authentik Agent-Users",
    "authentik Read-only", "cerulean-platform", "default", "distro-users",
    "genesis-admins", "instructors", "jellyfin_admins", "learners",
    "ontrak-admins", "ontrak-analysts", "ontrak-desk", "ontrak-instructors",
    "ontrak-students", "ontrak-sysadmins", "orion-users", "paid_pro",
    "paid_users", "plutus-admins", "range-instructors", "rizz-aura-admins",
    "signara-admins",
}

#: The group every AthenIQ account is enrolled in — the audience a door has to
#: include for a learner's sign-in to end anywhere but a 403.
LEARNER_GROUP = "AthenIQ LMS"
STAFF_GROUP = "atheniq-admins"

SERVICE = re.compile(r"^  ([a-z][a-z0-9-]*):\s*$")


def services(text):
    """Map each compose service to its own lines (the file is small; no YAML)."""
    out = {"": []}
    current = ""
    for line in text.splitlines():
        match = SERVICE.match(line)
        if match:
            current = match.group(1)
            out[current] = []
            continue
        out.setdefault(current, []).append(line)
    return out


def allowed_groups(lines):
    """Every `--allowed-group` value, to end of line.

    Not `\S+`: half the estate's groups have a space in the name (`AthenIQ LMS`,
    `authentik Admins`), and a word-only match would silently test the first word
    of a name — which is how a check like this can pass while the door refuses
    everybody. The trailing `\\` of a shell continuation and the quotes that keep
    a spaced name together are stripped; a name cannot contain `#`.
    """
    found = []
    for line in lines:
        line = line.split("#", 1)[0].rstrip()
        match = re.search(r"--allowed-group=(.+)$", line)
        if match:
            value = match.group(1).rstrip("\\").strip().strip("'\"")
            if value:
                found.append(value)
    return found


def env_groups(path, variable):
    """The value of one `Environment=NAME=a,b` line in a unit file."""
    text = pathlib.Path(path).read_text(encoding="utf-8")
    match = re.search(rf"^Environment={variable}=(.*)$", text, re.MULTILINE)
    if not match:
        return None
    return [name.strip() for name in match.group(1).split(",") if name.strip()]


class Doors(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.text = COMPOSE.read_text(encoding="utf-8")
        cls.blocks = services(cls.text)

    def test_compose_defines_both_doors(self):
        self.assertIn("classroom-sso", self.blocks)
        self.assertIn("generation-sso", self.blocks)

    def test_every_allowed_group_exists(self):
        for door in ("classroom-sso", "generation-sso"):
            named = allowed_groups(self.blocks.get(door, []))
            self.assertTrue(named, f"{door} names no --allowed-group at all")
            unknown = [name for name in named if name not in AUTHENTIK_GROUPS]
            self.assertEqual(unknown, [],
                             f"{door} allows group(s) Authentik does not have: {unknown}")

    def test_both_doors_admit_the_same_audience(self):
        classroom = set(allowed_groups(self.blocks["classroom-sso"]))
        generation = set(allowed_groups(self.blocks["generation-sso"]))
        self.assertEqual(classroom, generation,
                         "the doors guard two halves of one product; an account "
                         "that may work in the classroom must reach the portal")

    def test_the_learner_group_is_admitted(self):
        classroom = set(allowed_groups(self.blocks["classroom-sso"]))
        self.assertIn(LEARNER_GROUP, classroom)
        self.assertIn(STAFF_GROUP, classroom)

    def test_the_pair_asks_for_one_prompt(self):
        for door in ("classroom-sso", "generation-sso"):
            body = self.blocks[door]
            prompt = [re.search(r"--approval-prompt=(\S+)", line).group(1)
                      for line in body if "--approval-prompt=" in line]
            self.assertEqual(prompt, ["auto"],
                             f"{door} must not re-prompt for consent on the identity "
                             "the other door already approved")


class StaffLists(unittest.TestCase):
    """The apps behind the doors keep their own, narrower list."""

    @classmethod
    def setUpClass(cls):
        blocks = services(COMPOSE.read_text(encoding="utf-8"))
        cls.audience = set(allowed_groups(blocks["generation-sso"]))

    def test_portal_default_is_inside_the_door(self):
        # The portal's unit lives on the host, so what the repo can hold to the
        # rule is the default the code falls back to when no unit sets one.
        source = (ROOT / "scripts" / "atheniq-portal.py").read_text(encoding="utf-8")
        match = re.search(r'PORTAL_ADMIN_GROUPS"?\)\s*or\s*"([^"]+)"', source)
        self.assertIsNotNone(match, "the portal's default staff list moved")
        names = [name.strip() for name in match.group(1).split(",") if name.strip()]
        self.assertEqual(set(names) - self.audience, set(),
                         "the portal's default staff group cannot reach the door")
        self.assertEqual(set(names) - AUTHENTIK_GROUPS, set())

    def test_generation_unit(self):
        names = env_groups(SYSTEMD / "atheniq-generation.service",
                           "GENERATION_ALLOWED_GROUPS")
        self.assertIsNotNone(names, "the unit sets no GENERATION_ALLOWED_GROUPS")
        self.assertTrue(names)
        self.assertEqual([n for n in names if n not in AUTHENTIK_GROUPS], [],
                         "GENERATION_ALLOWED_GROUPS names a group Authentik does not have")
        self.assertEqual(set(names) - self.audience, set(),
                         "the console allows a group the door in front of it refuses")

    def test_root_script_matches_the_door(self):
        if not ROOT_SCRIPT.exists():
            self.skipTest(f"{ROOT_SCRIPT.name} is not in this checkout")
        lines = ROOT_SCRIPT.read_text(encoding="utf-8").splitlines()
        named = allowed_groups(lines)
        self.assertEqual([n for n in named if n not in AUTHENTIK_GROUPS], [])
        self.assertEqual(set(named), self.audience,
                         "the ad-hoc proxy script has drifted from the compose file")


if __name__ == "__main__":
    unittest.main()
