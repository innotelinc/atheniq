"""Unit tests for scripts/setup-wizard.py.

The wizard is what `./setup.sh` runs on a fresh clone, so its contract is
narrow and worth pinning: it writes the identity the operator typed, generates
only the secrets this stack owns, keeps every comment in the templates, and
never replaces an env file an operator already has.
"""
import contextlib
import io
import os
import tempfile
import unittest
from pathlib import Path

from _loader import ROOT, load

wizard = load("setup-wizard.py")


def answers(domain="example.edu"):
    return wizard.Answers(
        institution="Example University",
        domain=domain,
        admin_name="Ada Registrar",
        admin_email=f"registrar@{domain}",
        ai_base_url="http://127.0.0.1:20128/v1",
        signer_name="Ada Registrar",
        signer_title="Registrar",
        signer_email=f"registrar@{domain}",
    )


def quiet(function, *args, **kwargs):
    with contextlib.redirect_stdout(io.StringIO()):
        return function(*args, **kwargs)


class MergeEnvTest(unittest.TestCase):
    def test_replaces_owned_keys_and_keeps_everything_else(self):
        template = "# header\nAPP_NAME=Old Name\nLMS_HOST=old.example\n# LMS_HOST=commented\nOTHER=keep\n"
        merged = wizard.merge_env(template, {"APP_NAME": "New Name", "LMS_HOST": "learn.new.edu"})
        self.assertIn("# header", merged)
        self.assertIn("APP_NAME=\"New Name\"", merged)
        self.assertIn("LMS_HOST=learn.new.edu", merged)
        self.assertIn("# LMS_HOST=commented", merged)
        self.assertIn("OTHER=keep", merged)

    def test_appends_a_key_the_template_does_not_have(self):
        merged = wizard.merge_env("A=1\n", {"B": "2"})
        self.assertEqual(merged, "A=1\nB=2\n")


class ValuesTest(unittest.TestCase):
    def test_hosts_are_derived_from_the_domain(self):
        a = answers("university.test")
        self.assertEqual(a.lms_host, "learn.university.test")
        self.assertEqual(a.studio_host, "studio.university.test")
        self.assertEqual(a.console_host, "registrar.university.test")
        self.assertEqual(a.classroom_host, "https://class.university.test")

    def test_secrets_are_distinct_and_the_url_carries_the_db_password(self):
        generated = wizard.Generated.make()
        secrets_ = [
            generated.db_password,
            generated.persistence_token,
            generated.convex_instance_secret,
            generated.console_password,
            generated.console_secret,
        ]
        self.assertEqual(len(set(secrets_)), len(secrets_))
        values = wizard.platform_values(answers(), generated)
        self.assertIn(generated.db_password, values["OPENMAIC_DATABASE_URL"])

    def test_credentials_owned_by_another_system_are_not_invented(self):
        values = wizard.platform_values(answers(), wizard.Generated.make())
        for external in ("OIDC_CLIENT_SECRET", "SIGNARA_API_KEY", "CONVEX_SELF_HOSTED_ADMIN_KEY"):
            self.assertNotIn(external, values)

    def test_console_identity_matches_the_admin_and_domain(self):
        values = wizard.console_values(answers(), wizard.Generated.make())
        self.assertEqual(values["PUBLIC_SITE_HOSTS"], "example.edu,www.example.edu")
        self.assertEqual(values["AUTH_EMAIL"], "registrar@example.edu")
        self.assertEqual(values["STAFF_EMAIL_DOMAINS"], "example.edu")
        self.assertEqual(values["CONSOLE_ORIGIN"], "https://registrar.example.edu")


class ValidationTest(unittest.TestCase):
    def test_domain_accepts_what_operators_paste(self):
        self.assertEqual(wizard.check_domain("Example.EDU"), "example.edu")
        self.assertEqual(wizard.check_domain("https://learn.example.edu/"), "learn.example.edu")

    def test_domain_rejects_prose(self):
        with self.assertRaises(ValueError):
            wizard.check_domain("our school")

    def test_email_rejects_prose(self):
        with self.assertRaises(ValueError):
            wizard.check_email("the registrar")


class WriteTest(unittest.TestCase):
    def setUp(self):
        self.dir = Path(tempfile.mkdtemp())
        self.path = self.dir / ".env"

    def test_writes_a_private_file_once(self):
        self.assertTrue(wizard.write_env(self.path, "A=1\n", {"A": "2"}, force=False))
        self.assertEqual(self.path.stat().st_mode & 0o777, 0o600)
        self.assertIn("A=2", self.path.read_text())

        self.assertFalse(wizard.write_env(self.path, "A=1\n", {"A": "3"}, force=False))
        self.assertIn("A=2", self.path.read_text())
        self.assertTrue(wizard.write_env(self.path, "A=1\n", {"A": "3"}, force=True))
        self.assertIn("A=3", self.path.read_text())


class EndToEndTest(unittest.TestCase):
    def setUp(self):
        self.dir = Path(tempfile.mkdtemp())
        (self.dir / "console").mkdir()
        (self.dir / ".env.example").write_text((ROOT / ".env.example").read_text())
        (self.dir / "console" / ".env.example").write_text(
            (ROOT / "console" / ".env.example").read_text()
        )

    def run_wizard(self, *extra):
        return quiet(
            wizard.main,
            ["--root", str(self.dir), "--no-input", "--skip-preflight", *extra],
        )

    def test_writes_both_env_files_from_the_templates(self):
        self.assertEqual(self.run_wizard(), 0)
        platform = (self.dir / ".env").read_text()
        console = (self.dir / "console" / ".env").read_text()

        self.assertRegex(platform, r'(?m)^APP_NAME="Example University"$')
        self.assertRegex(platform, r"(?m)^LMS_HOST=learn\.example\.edu$")
        self.assertRegex(console, r"(?m)^AUTH_EMAIL=admin@example\.edu$")
        self.assertNotIn("change-me", console)

        # Only the credentials other systems own are left for their stage.
        self.assertEqual(
            wizard.placeholders(platform),
            [
                "OMNIROUTE_API_KEY",
                "OIDC_CLIENT_SECRET",
                "CONVEX_SELF_HOSTED_ADMIN_KEY",
                "SIGNARA_API_KEY",
                "CERULEAN_ADMIN_PASSWORD",
            ],
        )

    def test_dry_run_writes_nothing(self):
        self.assertEqual(self.run_wizard("--dry-run"), 0)
        self.assertFalse((self.dir / ".env").exists())
        self.assertFalse((self.dir / "console" / ".env").exists())

    def test_second_run_keeps_the_files(self):
        self.assertEqual(self.run_wizard(), 0)
        before = (self.dir / ".env").read_bytes()
        self.assertEqual(self.run_wizard(), 0)
        self.assertEqual((self.dir / ".env").read_bytes(), before)


class EntryPointTest(unittest.TestCase):
    def test_root_setup_sh_runs_the_wizard(self):
        script = (ROOT / "setup.sh").read_text()
        self.assertIn("scripts/setup-wizard.py", script)
        self.assertTrue(os.access(ROOT / "setup.sh", os.X_OK))


if __name__ == "__main__":
    unittest.main()
