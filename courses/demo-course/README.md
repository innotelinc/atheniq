# TEST101 — AthenIQ Demo Course

The platform's **reference course**. It is short, public, and deliberately exercises
every part of the stack a real course depends on, so an operator can validate a
deployment by running one learner through it and watching a signed certificate come
out the other end.

| | |
| --- | --- |
| Course key | `course-v1:InnotelLabs+TEST101+2026_T1` |
| Grading | Homework 40% · Final Exam 60% · pass at 50% |
| Certificate | Open edX certificate, signed through Signara |
| Used by | The certificate bridge / paid-course examples in the runbook |

## What it demonstrates

| Chapter | Components |
| --- | --- |
| Welcome to the Demo Course | Rich text orientation |
| Text, Images & Video | HTML5 `<video>` embed, images, links |
| Problem Types *(graded)* | Multiple choice, checkbox, dropdown, numerical, text input, math expression |
| Grading & Certificates | How a passing grade becomes a signed certificate |
| Final Assessment *(graded)* | Final exam spanning the platform |

## Import

Same as any OLX package:

```bash
cd courses/demo-course
tar -czf /tmp/TEST101-2026_T1.tar.gz olx
docker cp /tmp/TEST101-2026_T1.tar.gz tutor_local-cms-1:/tmp/
docker exec tutor_local-cms-1 sh -c \
  'cd /openedx/edx-platform && ./manage.py cms import /openedx/data \
     course-v1:InnotelLabs+TEST101+2026_T1 /tmp/TEST101-2026_T1.tar.gz'
```

Then publish the course and confirm the certificate block is active. A learner who
answers the graded problems and the final exam correctly clears the 50% pass and
receives a certificate automatically.
