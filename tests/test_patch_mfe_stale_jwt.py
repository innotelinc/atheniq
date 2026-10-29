#!/usr/bin/env python3
"""Unit tests for patch-mfe-stale-jwt.py — the shell guard against an expired JWT.

The bug is a **stuck** page, not a momentary one: with an expired token the LMS
answers the public config call with 401, the app then posts its own page
(`POST /catalog/` → 405), and the error boundary's "Try again" repeats it. Deleting
the dead credential before the app boots is what breaks the loop, so what is worth
locking here is that the delete happens **only** for a token that cannot
authenticate anything: no cookie, an expired one, an unparsable one, or a payload
with no signature beside it. A valid token must survive untouched, and the insert
must run before the app's deferred bundles.
"""
from __future__ import annotations

import importlib.util
import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
CHECK = SCRIPTS / "patch-mfe-stale-jwt.py"

SHELL = (
    '<!doctype html><html lang="en-us"><head><title></title>'
    '<script defer="defer" src="/catalog/runtime.abc.js"></script>'
    '<script defer="defer" src="/catalog/app.abc.js"></script>'
    "</head><body><div id=\"root\"></div></body></html>"
)


def _load():
    spec = importlib.util.spec_from_file_location("patch_mfe_stale_jwt", CHECK)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    import sys

    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


guard = _load()


class InsertCase(unittest.TestCase):
    def test_the_guard_lands_inside_head_and_before_the_bundles(self):
        text, changed = guard.patch_html(SHELL)
        self.assertTrue(changed)
        self.assertIn(guard.MARKER, text)
        head_end = text.index("</head>")
        self.assertLess(text.index(guard.MARKER), head_end)
        # The bundles are `defer`red, so an inline classic script in <head> runs first.
        self.assertLess(text.index(guard.MARKER), text.index("runtime.abc.js"))
        self.assertIn('<div id="root">', text, "the body is left exactly as it was")

    def test_a_second_run_is_a_no_op(self):
        once, _ = guard.patch_html(SHELL)
        twice, changed = guard.patch_html(once)
        self.assertFalse(changed)
        self.assertEqual(once, twice)
        self.assertEqual(twice.count(guard.MARKER), 1)

    def test_a_file_without_a_head_is_left_alone(self):
        text, changed = guard.patch_html("<html><body>no head</body></html>")
        self.assertFalse(changed)
        self.assertEqual(text, "<html><body>no head</body></html>")

    def test_check_mode_reports_without_writing(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "index.html"
            path.write_text(SHELL, encoding="utf-8")
            self.assertEqual(guard.main(["--check", str(path)]), 1)
            self.assertNotIn(guard.MARKER, path.read_text(encoding="utf-8"))
            self.assertEqual(guard.main([str(path)]), 0)
            self.assertEqual(guard.main(["--check", str(path)]), 0)


@unittest.skipIf(shutil.which("node") is None, "no node to run the injected script")
class BehaviourCase(unittest.TestCase):
    """Run the injected script the way a browser would, with `document.cookie` stubbed."""

    def _run(self, cookie: str) -> list[str]:
        text = guard.patch_html(SHELL)[0]
        body = text.split("<script>", 1)[1].split("</script>", 1)[0]
        with tempfile.TemporaryDirectory() as directory:
            script = Path(directory) / "guard.js"
            script.write_text(body, encoding="utf-8")
            harness = (
                "const written = [];\n"
                "global.document = { get cookie() { return process.env.COOKIE || ''; },\n"
                "  set cookie(value) { written.push(value); } };\n"
                "global.location = { hostname: 'atheniq.courses' };\n"
                "global.atob = (value) => Buffer.from(value, 'base64').toString('binary');\n"
                f"require({json.dumps(str(script))});\n"
                "console.log(JSON.stringify(written));\n"
            )
            env = {"COOKIE": cookie, "PATH": "/usr/local/bin:/usr/bin:/bin"}
            out = subprocess.run(
                ["node", "-e", harness], capture_output=True, text=True, timeout=30, env=env
            )
            self.assertEqual(out.returncode, 0, out.stderr)
            return json.loads(out.stdout)

    @staticmethod
    def _jwt(exp: int) -> str:
        import base64

        def seg(obj: dict) -> str:
            return base64.urlsafe_b64encode(json.dumps(obj).encode()).decode().rstrip("=")

        return f"{seg({'alg': 'HS256'})}.{seg({'exp': exp, 'sub': '1'})}"

    def test_a_valid_token_is_left_alone(self):
        import time

        cookie = (
            f"edx-jwt-cookie-header-payload={self._jwt(int(time.time()) + 600)}; "
            "edx-jwt-cookie-signature=abc"
        )
        self.assertEqual(self._run(cookie), [], "a live credential is never touched")

    def test_an_expired_token_is_dropped_with_its_signature(self):
        cookie = (
            f"edx-jwt-cookie-header-payload={self._jwt(1)}; edx-jwt-cookie-signature=abc"
        )
        written = self._run(cookie)
        joined = " ".join(written)
        self.assertIn("edx-jwt-cookie-header-payload=; Max-Age=0", joined)
        self.assertIn("edx-jwt-cookie-signature=; Max-Age=0", joined)
        self.assertIn("domain=.atheniq.courses", joined)

    def test_an_unparsable_token_is_dropped(self):
        written = self._run(
            "edx-jwt-cookie-header-payload=not-a-token; edx-jwt-cookie-signature=abc"
        )
        self.assertTrue(written, "an unreadable token cannot authenticate anything")
        self.assertIn("Max-Age=0", " ".join(written))

    def test_a_payload_without_its_signature_is_dropped(self):
        import time

        cookie = f"edx-jwt-cookie-header-payload={self._jwt(int(time.time()) + 600)}"
        written = self._run(cookie)
        self.assertTrue(written, "the LMS rejects a token with no signature")

    def test_no_cookie_writes_nothing(self):
        self.assertEqual(self._run(""), [])


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
