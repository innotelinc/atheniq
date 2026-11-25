#!/usr/bin/env python3
"""AthenIQ — guided setup wizard for a fresh install.

`./setup.sh` runs this. It asks for the few values that cannot be guessed from
the templates — who the institution is, what domain it answers on, which
administrator account bootstraps the console, and where the model gateway
lives — then writes `.env` and `console/.env` with generated secrets for the
services this stack owns.

It is deliberately conservative:

- existing env files are left untouched unless `--force` is given;
- credentials that belong to another system (Authentik, Cerulean, Signara,
  Magnate, the Convex admin key) are never invented here — the templates keep
  their placeholders and the checklist names the step that mints the real one;
- generated secrets are written, never printed.

`--check` preflights only, `--no-input` accepts every default, `--dry-run`
prints the plan without touching disk, and `--root` points it at a checkout
other than the one holding this script.
"""
from __future__ import annotations

import argparse
import os
import re
import secrets
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

KEY = re.compile(r"^([A-Z][A-Z0-9_]*)=(.*)$")
DOMAIN = re.compile(r"^(?=.{1,253}$)([a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,63}$", re.I)
EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
SAFE = re.compile(r"^[A-Za-z0-9_./:@,+%=-]+$")

REQUIRED_TOOLS = (
    ("git", ("git", "--version")),
    ("docker", ("docker", "--version")),
    ("docker compose", ("docker", "compose", "version")),
    ("python3", (sys.executable, "--version")),
    ("openssl", ("openssl", "version")),
    ("curl", ("curl", "--version")),
)


@dataclass(frozen=True)
class Answers:
    institution: str
    domain: str
    admin_name: str
    admin_email: str
    ai_base_url: str
    signer_name: str
    signer_title: str
    signer_email: str

    @classmethod
    def defaults(cls) -> "Answers":
        return cls(
            institution="Example University",
            domain="example.edu",
            admin_name="Registrar",
            admin_email="admin@example.edu",
            ai_base_url="http://127.0.0.1:20128/v1",
            signer_name="Registrar",
            signer_title="Registrar",
            signer_email="admin@example.edu",
        )

    @property
    def lms_host(self) -> str:
        return f"learn.{self.domain}"

    @property
    def studio_host(self) -> str:
        return f"studio.{self.domain}"

    @property
    def console_host(self) -> str:
        return f"registrar.{self.domain}"

    @property
    def classroom_host(self) -> str:
        return f"https://class.{self.domain}"


@dataclass(frozen=True)
class Generated:
    db_password: str
    persistence_token: str
    convex_instance_secret: str
    console_password: str
    console_secret: str

    @classmethod
    def make(cls) -> "Generated":
        return cls(
            db_password=secrets.token_hex(18),
            persistence_token=secrets.token_hex(24),
            convex_instance_secret=secrets.token_hex(32),
            console_password=secrets.token_urlsafe(18),
            console_secret=secrets.token_hex(32),
        )


def env_value(value: str) -> str:
    """Quote a value only when dotenv needs it."""
    if value and SAFE.match(value):
        return value
    escaped = value.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


def merge_env(template: str, values: dict[str, str]) -> str:
    """Replace the keys we own, keep every comment and unknown line."""
    lines: list[str] = []
    written: set[str] = set()
    for line in template.splitlines():
        match = KEY.match(line)
        if match and match.group(1) in values:
            key = match.group(1)
            lines.append(f"{key}={env_value(values[key])}")
            written.add(key)
        else:
            lines.append(line)
    for key, value in values.items():
        if key not in written:
            lines.append(f"{key}={env_value(value)}")
    return "\n".join(lines) + "\n"


def platform_values(answers: Answers, generated: Generated) -> dict[str, str]:
    return {
        "APP_NAME": answers.institution,
        "BASE_DOMAIN": answers.domain,
        "LMS_HOST": answers.lms_host,
        "CMS_HOST": answers.studio_host,
        "CLASSROOM_HOST": answers.classroom_host,
        "CERULEAN_BASE_DOMAIN": answers.lms_host,
        "CERULEAN_ZONE": answers.domain,
        "OPENMAIC_DB_PASSWORD": generated.db_password,
        "OPENMAIC_DATABASE_URL": (
            f"postgres://openmaic:{generated.db_password}@127.0.0.1:5433/openmaic"
        ),
        "PERSISTENCE_DEV_TOKEN": generated.persistence_token,
        "CONVEX_INSTANCE_SECRET": generated.convex_instance_secret,
        "OMNIROUTE_BASE_URL": answers.ai_base_url,
        "CERT_SIGNER_NAME": answers.signer_name,
        "CERT_SIGNER_TITLE": answers.signer_title,
        "CERT_SIGNER_EMAIL": answers.signer_email,
        "SMTP_FROM": f"{answers.institution} <no-reply@{answers.domain}>",
    }


def console_values(answers: Answers, generated: Generated) -> dict[str, str]:
    return {
        "PUBLIC_SITE_HOSTS": f"{answers.domain},www.{answers.domain}",
        "PUBLIC_SITE_DOMAIN": answers.domain,
        "CONSOLE_ORIGIN": f"https://{answers.console_host}",
        "AUTH_EMAIL": answers.admin_email,
        "AUTH_NAME": answers.admin_name,
        "AUTH_TITLE": f"Registrar, {answers.institution}",
        "AUTH_PASSWORD": generated.console_password,
        "AUTH_SECRET": generated.console_secret,
        "STAFF_EMAIL_DOMAINS": answers.domain,
        "DIGEST_TO": answers.admin_email,
        "MAIL_SMTP_HOST": "",
        "MAIL_FROM": f"noreply@{answers.domain}",
        "CERT_SIGNER_NAME": answers.signer_name,
        "CERT_SIGNER_TITLE": answers.signer_title,
        "CERT_SIGNER_EMAIL": answers.signer_email,
    }


def check_domain(value: str) -> str:
    value = value.strip().lower().removeprefix("https://").removeprefix("http://").strip("/")
    if not DOMAIN.match(value):
        raise ValueError("enter a bare domain such as example.edu")
    return value


def check_email(value: str) -> str:
    value = value.strip()
    if not EMAIL.match(value):
        raise ValueError("enter an email address such as registrar@example.edu")
    return value


def check_url(value: str) -> str:
    value = value.strip()
    if value and not value.startswith(("http://", "https://")):
        raise ValueError("enter an http(s) URL, or leave it blank")
    return value


def ask(label: str, default: str, check=None) -> str:
    while True:
        try:
            raw = input(f"{label} [{default}]: ").strip()
        except EOFError:
            return default
        value = raw or default
        if check is None:
            return value
        try:
            return check(value)
        except ValueError as error:
            print(f"  {error}")


def preflight() -> int:
    missing = []
    for name, command in REQUIRED_TOOLS:
        if shutil.which(command[0]) is None and command[0] != sys.executable:
            missing.append(name)
            continue
        result = subprocess.run(command, capture_output=True, text=True, check=False)
        if result.returncode != 0:
            missing.append(name)
    if missing:
        print("Missing required tools: " + ", ".join(missing), file=sys.stderr)
        return 1
    print("Preflight ok: " + ", ".join(name for name, _ in REQUIRED_TOOLS))
    return 0


def placeholders(text: str) -> list[str]:
    """Keys still holding a template placeholder, in file order."""
    names = []
    for line in text.splitlines():
        match = KEY.match(line)
        if match and match.group(2).strip().startswith("change-me"):
            names.append(match.group(1))
    return names


def write_env(path: Path, template: str, values: dict[str, str], force: bool) -> bool:
    """Write one env file; False when an existing file was kept."""
    if path.exists() and not force:
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(merge_env(template, values))
    os.chmod(path, 0o600)
    return True


def parse_args(argv=None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="./setup.sh",
        description="Guided first-install wizard for AthenIQ.",
    )
    parser.add_argument("--root", default=str(ROOT), help="checkout holding .env.example")
    parser.add_argument("--check", action="store_true", help="preflight the tools and exit")
    parser.add_argument("--no-input", action="store_true", help="accept every default")
    parser.add_argument("--yes", action="store_true", help="do not ask for confirmation")
    parser.add_argument("--dry-run", action="store_true", help="print the plan, write nothing")
    parser.add_argument("--force", action="store_true", help="replace existing env files")
    parser.add_argument("--skip-preflight", action="store_true", help=argparse.SUPPRESS)
    return parser.parse_args(argv)


def main(argv=None) -> int:
    args = parse_args(argv)
    root = Path(args.root).resolve()

    if args.check:
        return preflight()
    if not args.skip_preflight:
        result = preflight()
        if result:
            return result

    if args.no_input:
        answers = Answers.defaults()
    else:
        defaults = Answers.defaults()
        print()
        print("Institution")
        institution = ask("  Name", defaults.institution)
        domain = ask("  Primary domain", defaults.domain, check_domain)
        print()
        print("Administrator (bootstraps the registrar console)")
        admin_name = ask("  Name", defaults.admin_name)
        admin_email = ask("  Email", f"admin@{domain}", check_email)
        print()
        print("Integrations")
        ai_base_url = ask("  Model gateway base URL", defaults.ai_base_url, check_url)
        print()
        print("Certificate signatory")
        signer_name = ask("  Name", admin_name)
        signer_title = ask("  Title", defaults.signer_title)
        answers = Answers(
            institution=institution,
            domain=domain,
            admin_name=admin_name,
            admin_email=admin_email,
            ai_base_url=ai_base_url,
            signer_name=signer_name,
            signer_title=signer_title,
            signer_email=admin_email,
        )

    generated = Generated.make()
    platform = platform_values(answers, generated)
    console = console_values(answers, generated)

    print()
    print("Plan")
    print(f"  Institution     {answers.institution}")
    print(f"  LMS             https://{answers.lms_host}")
    print(f"  Studio          https://{answers.studio_host}")
    print(f"  Console         https://{answers.console_host}")
    print(f"  Administrator   {answers.admin_name} <{answers.admin_email}>")
    print(f"  Model gateway   {answers.ai_base_url or '(left unset)'}")
    print("  Secrets         generated locally; written to the env files, not printed")

    if args.dry_run:
        print()
        print("Dry run — no files written.")
        return 0

    if not (args.yes or args.no_input) and sys.stdin.isatty():
        reply = input("\nWrite these settings? [Y/n]: ").strip().lower()
        if reply not in ("", "y", "yes"):
            print("Nothing written.")
            return 1

    templates = [root / ".env.example", root / "console" / ".env.example"]
    missing = [str(path) for path in templates if not path.exists()]
    if missing:
        print(
            "Not a checkout with env templates: missing " + ", ".join(missing),
            file=sys.stderr,
        )
        return 1

    platform_template = templates[0].read_text()
    console_template = templates[1].read_text()

    print()
    if write_env(root / ".env", platform_template, platform, args.force):
        print(f"Wrote {root / '.env'} (mode 600)")
    else:
        print(f"Kept existing {root / '.env'} — pass --force to replace it")
    if write_env(root / "console" / ".env", console_template, console, args.force):
        print(f"Wrote {root / 'console' / '.env'} (mode 600)")
    else:
        print(f"Kept existing {root / 'console' / '.env'} — pass --force to replace it")

    if (root / ".git").exists():
        subprocess.run(("git", "config", "core.hooksPath", ".githooks"), cwd=root, check=False)

    remaining = placeholders((root / ".env").read_text()) if (root / ".env").exists() else []
    if remaining:
        print()
        print("Still placeholders, by design: " + ", ".join(remaining))
        print("  They belong to Authentik, Cerulean, Signara or the gateway, or are")
        print("  minted with `make convex-key` — set each when its stage is wired.")

    print()
    print("Next steps")
    print("  1. Tutor LMS:      pip install tutor && make tutor-quickstart")
    print("  2. Identity:       register the OIDC client (docs/Deployment.md — Stage 2)")
    print("  3. AI + realtime:  make up (openmaic + convex profiles)")
    print("  4. Console:        make convex-key, then start console/ with its .env")
    print("  5. Certificates:   docs/Deployment.md — Stage 7 (Signara)")
    print("  6. Media/storage:  make onyx-check && make onyx-buckets (optional)")
    print("  7. Verify:         make test && make check-compose")
    print("  Console administrator password: console/.env (AUTH_PASSWORD)")
    print("  Full runbook: docs/Deployment.md")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
