#!/usr/bin/env python3
"""AthenIQ — report a finished classroom lesson to OnTrak ITS.

The classroom (OpenMAIC) knows what a learner did in a lesson. It is not,
however, the record of record: OnTrak ITS holds the training ledger, and a
classroom's own progress screen is a view of the lesson rather than evidence
anybody can hand an auditor. This is the one-way door between them — the last
step of OnTrak Class 2.1:

    classroom (this host)  ──POST──▶  ITS /api/v1/classroom/completions
                                      └─ training record + verifiable certificate

Three decisions make the report safe to run from a sweep or a webhook:

  * **The completion id is derived, not invented.** `openmaic:<classroom>:
    <learner>:<lesson>` is the same string on every retry, and ITS stores it as
    a unique key. A classroom that retries after a timeout therefore gets the
    record it already has rather than a second one — the same shape the lab's
    completion door uses.
  * **A refusal is the server's, quoted.** ITS re-validates every field (the two
    products deploy independently), so a 422 comes back with the list of what is
    wrong. This tool prints that list and exits non-zero; it never rewrites a
    body into something the server might accept.
  * **Dry run dials nothing.** `--dry-run` prints the exact JSON that would be
    sent, which is what an operator checks before pointing a webhook at a
    production ITS. It also works without a token, because a rehearsal is not a
    report.

Usage
-----
    python3 scripts/report-classroom-completion.py \\
        --classroom cls-1042 --learner ada@acme.test \\
        --course-ref ITSP101 --course-title "IT Support Foundations" \\
        --lesson-ref chapter-3 --lesson-title "Accounts and access" \\
        --score 8 --max-score 10

    # What the body a JSON file (or another tool) already built would look like
    python3 scripts/report-classroom-completion.py --json completion.json --dry-run

Environment
-----------
    ITS_BASE_URL       origin of the training app (default https://its.ontrak.technology)
    ONTRAK_API_TOKEN   the deployment's shared API token — required to send
    CLASSROOM_HOST     only used to explain where this ran, never sent
"""
import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from datetime import datetime, timezone

#: The body format ITS accepts. Named so a wrong door is refused by the server
#: with a sentence rather than by a KeyError here.
FORMAT = "ontrak.classroom.completion/v1"

DEFAULT_ITS_BASE = "https://its.ontrak.technology"
PATH = "/api/v1/classroom/completions"
TIMEOUT_SECONDS = 15

#: Bounds mirrored from the door's rulebook. They are checked here as well so a
#: typo fails before the round trip, not because this end distrusts the door.
MAX_REF = 200
MAX_TITLE = 300
MAX_SCORE = 100_000
MAX_CHECKS = 200


class CompletionError(ValueError):
    """A body this tool will not send. The message is the reason."""


@dataclass
class SendResult:
    """What the door answered, or why nothing was sent."""

    ok: bool
    status: int = 0
    record_id: str = ""
    created: bool = False
    #: The verifiable record's short code, when the lesson passed. ITS stores the
    #: record and returns this so the learner can be handed something to check at
    #: `/verify`; a failing lesson carries neither.
    code: str = ""
    error: str = ""
    issues: list = field(default_factory=list)


# ---------------------------------------------------------------------------
# the body (pure — no environment, no socket)
# ---------------------------------------------------------------------------

def _text(value, label, limit=MAX_REF):
    text = str(value or "").strip()
    if not text:
        raise CompletionError(f"{label} is empty")
    if len(text) > limit:
        raise CompletionError(f"{label} is longer than {limit} characters")
    return text


def _whole(value, label, *, minimum=0, maximum=MAX_SCORE):
    try:
        number = int(value)
    except (TypeError, ValueError):
        raise CompletionError(f"{label} must be a whole number") from None
    if number < minimum or number > maximum:
        raise CompletionError(f"{label} must be between {minimum} and {maximum}")
    return number


def _instant(value, label):
    """One ISO-8601 instant, normalised to UTC with a `Z`.

    ITS parses with `Date`, so `2026-10-05T09:20:00Z` and a `+00:00` offset are
    the same instant. Normalising here makes two retries byte-identical, which is
    what makes the derived completion id the whole idempotency story.
    """
    text = str(value or "").strip()
    if not text:
        raise CompletionError(f"{label} is empty")
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        raise CompletionError(f"{label} is not an ISO-8601 date-time: {text!r}") from None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _after(later, earlier):
    """Is the normalised instant `later` after `earlier`? Both end in `Z`.

    Compared as instants rather than as strings, because the format they are
    normalised to happens to sort correctly and relying on that would hide a
    change to it.
    """
    def parse(value):
        return datetime.fromisoformat(value.replace("Z", "+00:00"))

    return parse(later) > parse(earlier)


def completion_key(classroom, learner, lesson):
    """The idempotency key: one lesson, one learner, one classroom.

    Deliberately built from the three ids rather than a timestamp or a random
    value — a retry must be the *same* fact, or ITS would store it twice.
    """
    parts = [
        _text(classroom, "classroom"),
        # The address is part of the key *folded*, exactly as `learnerEmail` is:
        # a directory that changes only the case of an address must not turn one
        # completion into two records.
        _text(learner, "learner").lower(),
        _text(lesson, "lesson"),
    ]
    return "openmaic:" + ":".join(parts)


def _checks(raw):
    checks = []
    for index, entry in enumerate(raw or []):
        if not isinstance(entry, dict):
            raise CompletionError(f"check {index} is not an object")
        points = _whole(entry.get("points", 0), f"check {index} points")
        max_points = _whole(entry.get("maxPoints", 0), f"check {index} maxPoints")
        if points > max_points:
            raise CompletionError(
                f"check {index} awards {points} of {max_points}; points cannot exceed maxPoints")
        checks.append({
            "checkId": _text(entry.get("checkId"), f"check {index} checkId"),
            "label": _text(entry.get("label"), f"check {index} label", MAX_TITLE),
            "passed": bool(entry.get("passed")),
            "points": points,
            "maxPoints": max_points,
        })
    if len(checks) > MAX_CHECKS:
        raise CompletionError(f"at most {MAX_CHECKS} checks are accepted")
    return checks


def build_body(*, classroom, learner, lesson, course_ref, course_title,
               lesson_ref=None, lesson_title=None, score, max_score,
               pass_score=None, started_at=None, completed_at=None,
               checks=(), skills=()):
    """One completion, in the shape ITS accepts, or `CompletionError`.

    `score`/`maxScore` are points; `passScore` is a percentage, which is the same
    split the lab's completion door uses and the reason a raw `score >= passScore`
    comparison would call 8/10 a failure against a 70% mark.
    """
    learner_email = _text(learner, "learner email")
    if "@" not in learner_email:
        raise CompletionError(f"{learner_email!r} is not an email address")

    body = {
        "format": FORMAT,
        "completionId": completion_key(classroom, learner_email, lesson),
        "learnerEmail": learner_email.lower(),
        "course": {
            "ref": _text(course_ref, "course ref"),
            "title": _text(course_title, "course title", MAX_TITLE),
        },
        "lesson": {
            "ref": _text(lesson_ref or lesson, "lesson ref"),
            "title": _text(lesson_title or (lesson_ref or lesson), "lesson title", MAX_TITLE),
        },
        "score": _whole(score, "score"),
        "maxScore": _whole(max_score, "maxScore", minimum=1),
        "completedAt": _instant(completed_at or datetime.now(timezone.utc).isoformat(),
                                "completedAt"),
        "checks": _checks(checks),
        "skills": [_text(skill, "skill") for skill in (skills or [])],
    }
    if body["score"] > body["maxScore"]:
        raise CompletionError(
            f"score {body['score']} is greater than maxScore {body['maxScore']}")
    if pass_score is not None:
        body["passScore"] = _whole(pass_score, "passScore", minimum=0, maximum=100)
    if started_at:
        body["startedAt"] = _instant(started_at, "startedAt")
        if _after(body["startedAt"], body["completedAt"]):
            raise CompletionError("startedAt is after completedAt")
    return body


def body_from_json(data):
    """Re-validate a body somebody else built, without rewriting its meaning.

    `--json` exists so the classroom host can hand this tool the object it
    already has. The check here is the same one `build_body` makes, in the same
    order, so a body that passes this and fails at ITS has one cause: the two
    sides disagree, which the server's `issues` list will name.
    """
    if not isinstance(data, dict):
        raise CompletionError("the JSON body is not an object")
    if data.get("format") not in (None, FORMAT):
        raise CompletionError(f"format must be {FORMAT!r}")
    key = _text(data.get("completionId"), "completionId")
    course = data.get("course") or {}
    lesson = data.get("lesson") or {}
    if not isinstance(course, dict) or not isinstance(lesson, dict):
        raise CompletionError("course and lesson must be objects")

    body = {
        "format": FORMAT,
        "completionId": key,
        "learnerEmail": _text(data.get("learnerEmail"), "learnerEmail").lower(),
        "course": {
            "ref": _text(course.get("ref"), "course ref"),
            "title": _text(course.get("title"), "course title", MAX_TITLE),
        },
        "lesson": {
            "ref": _text(lesson.get("ref"), "lesson ref"),
            "title": _text(lesson.get("title"), "lesson title", MAX_TITLE),
        },
        "score": _whole(data.get("score"), "score"),
        "maxScore": _whole(data.get("maxScore"), "maxScore", minimum=1),
        "completedAt": _instant(data.get("completedAt"), "completedAt"),
        "checks": _checks(data.get("checks")),
        "skills": [_text(skill, "skill") for skill in (data.get("skills") or [])],
    }
    if body["score"] > body["maxScore"]:
        raise CompletionError("score is greater than maxScore")
    if data.get("passScore") is not None:
        body["passScore"] = _whole(data["passScore"], "passScore", minimum=0, maximum=100)
    if data.get("startedAt"):
        body["startedAt"] = _instant(data["startedAt"], "startedAt")
        if _after(body["startedAt"], body["completedAt"]):
            raise CompletionError("startedAt is after completedAt")
    return body


# ---------------------------------------------------------------------------
# the door (the only part that dials)
# ---------------------------------------------------------------------------

def endpoint(base):
    return (base or DEFAULT_ITS_BASE).rstrip("/") + PATH


def post(body, *, base=None, token="", transport=None, timeout=TIMEOUT_SECONDS):
    """Send one completion and return the door's answer as a value.

    The transport is injectable so the tests never open a socket; it is called
    as `transport(request, timeout=...)`, which is `urllib.request.urlopen`'s
    own shape.
    """
    url = endpoint(base)
    payload = json.dumps(body, sort_keys=False).encode()
    request = urllib.request.Request(
        url, data=payload, method="POST",
        headers={
            "content-type": "application/json",
            "authorization": f"Bearer {token}",
            "accept": "application/json",
        })
    opener = transport or urllib.request.urlopen
    try:
        with opener(request, timeout=timeout) as response:
            status = int(getattr(response, "status", 0) or response.getcode() or 0)
            text = response.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as error:
        text = error.read().decode("utf-8", "replace")
        answer = _parse(text)
        return SendResult(ok=False, status=error.code,
                          error=answer.get("error") or f"ITS answered {error.code}",
                          issues=answer.get("issues") or [])
    except (urllib.error.URLError, TimeoutError, OSError) as error:
        return SendResult(ok=False, error=f"ITS unreachable: {error}")

    answer = _parse(text)
    if status >= 300:
        return SendResult(ok=False, status=status,
                          error=answer.get("error") or f"ITS answered {status}",
                          issues=answer.get("issues") or [])
    return SendResult(ok=True, status=status,
                      record_id=str(answer.get("id") or ""),
                      created=bool(answer.get("created")),
                      code=str(answer.get("code") or ""))


def _parse(text):
    try:
        value = json.loads(text) if text.strip() else {}
    except ValueError:
        return {}
    return value if isinstance(value, dict) else {}


def send(body, *, base=None, token="", dry_run=False, transport=None,
         timeout=TIMEOUT_SECONDS):
    """Check the configuration, then either print or post.

    A token is required to *send* and not to rehearse, because a dry run dials
    nothing — requiring the credential there would make the safe path harder than
    the real one.
    """
    if dry_run:
        return SendResult(ok=True, status=0, created=False)
    if not str(token or "").strip():
        return SendResult(ok=False, error="ONTRAK_API_TOKEN is not set — see docs/Integrations.md.")
    return post(body, base=base, token=token, transport=transport, timeout=timeout)


# ---------------------------------------------------------------------------
# the operator surface
# ---------------------------------------------------------------------------

def main(argv=None):
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--classroom", help="classroom / stage id (the idempotency key's first part)")
    parser.add_argument("--learner", help="the learner's email")
    parser.add_argument("--lesson", help="lesson / chapter id")
    parser.add_argument("--course-ref", help="course key or slug, e.g. ITSP101")
    parser.add_argument("--course-title", help="the course as a person reads it")
    parser.add_argument("--lesson-ref", help="lesson id, when it differs from --lesson")
    parser.add_argument("--lesson-title", help="the lesson as a person reads it")
    parser.add_argument("--score", type=int, help="points earned")
    parser.add_argument("--max-score", type=int, help="points available")
    parser.add_argument("--pass-score", type=int, help="the pass mark, as a percentage")
    parser.add_argument("--started-at", help="ISO-8601 instant the lesson was entered")
    parser.add_argument("--completed-at", help="ISO-8601 instant the lesson was finished")
    parser.add_argument("--check", action="append", default=[],
                        help='JSON check object, repeatable: {"checkId":…,"label":…,"passed":true,"points":1,"maxPoints":1}')
    parser.add_argument("--skill", action="append", default=[],
                        help="a competency the lesson demonstrated, repeatable")
    parser.add_argument("--json", metavar="FILE",
                        help="a complete body to re-validate and send (instead of flags)")
    parser.add_argument("--dry-run", action="store_true", help="print the body; dial nothing")
    args = parser.parse_args(argv)

    try:
        if args.json:
            with open(args.json, "r", encoding="utf-8") as handle:
                body = body_from_json(json.load(handle))
        else:
            missing = [name for name, value in (
                ("--classroom", args.classroom), ("--learner", args.learner),
                ("--lesson", args.lesson), ("--course-ref", args.course_ref),
                ("--course-title", args.course_title),
                ("--score", args.score), ("--max-score", args.max_score)) if value in (None, "")]
            if missing:
                raise CompletionError(f"missing {', '.join(missing)}")
            checks = []
            for raw in args.check:
                try:
                    checks.append(json.loads(raw))
                except ValueError:
                    raise CompletionError(f"--check is not JSON: {raw!r}") from None
            body = build_body(
                classroom=args.classroom, learner=args.learner, lesson=args.lesson,
                course_ref=args.course_ref, course_title=args.course_title,
                lesson_ref=args.lesson_ref, lesson_title=args.lesson_title,
                score=args.score, max_score=args.max_score,
                pass_score=args.pass_score, started_at=args.started_at,
                completed_at=args.completed_at, checks=checks, skills=args.skill)
    except CompletionError as error:
        print(f"refused: {error}", file=sys.stderr)
        return 2

    base = os.environ.get("ITS_BASE_URL") or DEFAULT_ITS_BASE
    token = os.environ.get("ONTRAK_API_TOKEN", "")

    if args.dry_run:
        print(json.dumps(body, indent=2))
        print(f"\n(dry run — would POST {endpoint(base)})", file=sys.stderr)
        return 0

    result = send(body, base=base, token=token)
    if not result.ok:
        print(f"ITS refused the completion: {result.error}", file=sys.stderr)
        for issue in result.issues:
            print(f"  - {issue}", file=sys.stderr)
        return 1

    verb = "recorded" if result.created else "already recorded"
    check = f" — verify code {result.code}" if result.code else ""
    print(f"{verb}: {result.record_id or '(no id returned)'} "
          f"(http {result.status}, {body['completionId']}){check}")
    if result.code:
        print("Give the learner the record JSON and this code; either can be checked "
              "at ITS /verify.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
