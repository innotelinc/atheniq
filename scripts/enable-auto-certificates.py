#!/usr/bin/env python3
"""Enable automatic certificate issuance on a passing grade (Open edX).

Open edX ships the full "course completion trigger" already: when a learner's
grade is recomputed and crosses the pass threshold, CourseGradeFactory emits
COURSE_GRADE_NOW_PASSED, and the certificates app enqueues a celery task that
writes a `downloadable` GeneratedCertificate — but only while the waffle switch
`certificates.auto_certificate_generation` is active (it defaults to OFF).

That switch is stored in the LMS DB, so it survives container restarts but is
lost on a fresh MySQL volume. Run this after a Tutor recreate (or point it at
any LMS shell) to re-arm the trigger:

    tutor local run lms python manage.py lms shell < scripts/enable-auto-certificates.py

or, inside the LMS container:

    cd /openedx/edx-platform && python /path/to/scripts/enable-auto-certificates.py

The certificate is then issued automatically when a learner passes, and the
AthenIQ cert bridge (scripts/cert-bridge.py) picks it up and pushes it through
Signara for signing.
"""
import os
import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "lms.envs.tutor.production")
django.setup()

from waffle.models import Switch  # noqa: E402

NAME = "certificates.auto_certificate_generation"

switch, created = Switch.objects.update_or_create(name=NAME, defaults={"active": True})
print(f"switch: {switch.name} active: {switch.active} created: {created}")

from lms.djangoapps.certificates.api import auto_certificate_generation_enabled  # noqa: E402
print("auto_certificate_generation_enabled():", auto_certificate_generation_enabled())