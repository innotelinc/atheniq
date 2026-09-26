# ITSP101 — IT Support Foundations

The IT Support Specialist certification course for **Innotel Labs**. Seven chapters
take a new technician from hardware fundamentals to running a help desk, with graded
homework, applied labs, and a final exam.

| | |
| --- | --- |
| Course key | `course-v1:InnotelLabs+ITSP101+2026_T1` |
| Track | `it-support` — *IT Support Specialist* (see [`config/workforce-tracks.json`](../../config/workforce-tracks.json)) |
| Org / course / run | `Innotel` / `ITSP101` / `2026_T1` |
| Grading | Homework 35% · Lab 25% · Final Exam 40% · pass at 70% |
| Certificate | Open edX certificate, signed through Signara (`course-completion`) |
| Classroom | OpenMAIC generative classroom spec in [`openmaic/`](openmaic/classrooms.json) |

## Contents

```
it-support-certification/
├── README.md                # this file
├── olx/                     # Open edX OLX — the importable course
│   ├── course.xml           # root index (url_name, org, course)
│   ├── course/2026_T1.xml   # the course block: settings + chapter refs
│   ├── chapter/             # 7 sections
│   ├── sequential/          # 14 subsections (7 ungraded lessons + 7 graded)
│   ├── vertical/            # 21 units
│   ├── html/                # 14 text components (.xml pointer + .html content)
│   ├── problem/             # 7 graded problems
│   ├── policies/            # course run policy + grading policy + assets
│   ├── about/               # overview + short description
│   ├── info/                # handouts + updates
│   └── assets/assets.xml
└── openmaic/
    └── classrooms.json      # per-chapter generative-classroom specification
```

## Course outline

| # | Chapter | Lessons | Graded work |
| --- | --- | --- | --- |
| 1 | Welcome to IT Support | How this course works · The IT support role | Knowledge check (Homework) |
| 2 | Hardware & Devices | Hardware basics · Peripherals & mobile | Homework: Hardware |
| 3 | Operating Systems & Software | Operating systems · Accounts & software | Lab: OS troubleshooting |
| 4 | Networking Fundamentals | Networking basics · IP, DNS & DHCP | Homework: Networking |
| 5 | Security Essentials | Security fundamentals · Passwords, MFA & phishing | Lab: Security response |
| 6 | Help Desk Operations | Help desk operations · Ticketing & SLAs | Lab: Ticket triage |
| 7 | Troubleshooting & Certification Prep | Troubleshooting methodology · Certification & next steps | Final Exam |

The OLX is written in the exact layout Open edX Studio exports, including the
chapter → sequential → vertical containment that the Studio outline requires
(a vertical directly under a chapter crashes the authoring MFE).

## Validate

```bash
make check-courses                                  # human summary
python3 scripts/check-course-olx.py --json           # machine output
python3 scripts/check-course-olx.py --markdown       # outline table
```

`scripts/check-course-olx.py` is a lint: it parses every XML file, verifies that
each container reference resolves to a file of the right type, that html components
point at real `.html` content, that the containment chain is well-formed, and that a
course key matches `course-v1:<org>+<course>+<run>`. It never touches the LMS.

## Import into Open edX Studio

The `olx/` directory is the course data directory (it contains `course.xml`). Bundle
it and import it — no server access is needed from CI.

```bash
cd courses/it-support-certification
tar -czf /tmp/ITSP101-2026_T1.tar.gz olx
```

Then either:

- **Studio UI:** Tools → Import, and upload the `.tar.gz`; or
- **CLI (Tutor):**
  ```bash
  docker cp /tmp/ITSP101-2026_T1.tar.gz tutor_local-cms-1:/tmp/
  docker exec tutor_local-cms-1 sh -c \
    'cd /openedx/edx-platform && ./manage.py cms import /openedx/data \
       course-v1:InnotelLabs+ITSP101+2026_T1 /tmp/ITSP101-2026_T1.tar.gz'
  ```

After import, confirm the certificate block is active and publish the course. The
completion → Signara signing leg is automatic once a learner passes (see
[`docs/Deployment.md`](../../docs/Deployment.md)).

## OpenMAIC classroom

[`openmaic/classrooms.json`](openmaic/classrooms.json) describes one generative
classroom per chapter — prompt, objectives, agent roles, and activities. Feed it to
OpenMAIC (directly or through the OpenClaw OpenMAIC skill) to generate interactive
lessons, then link the resulting classroom from the matching Open edX unit. See
[`openmaic/README.md`](openmaic/README.md).
