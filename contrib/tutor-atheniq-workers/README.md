# tutor-atheniq-workers

Caps the AthenIQ LMS and CMS Celery worker pools.

Tutor starts both workers without `--concurrency`, so Celery defaults to the
number of CPUs it can see. On i2 that was **8 worker processes per container**,
and the two containers together held ~3.3 GiB — the largest consumers on a
13.4 GiB host that also carries the capstone stack.

This plugin appends `--concurrency=<WORKER_CONCURRENCY>` to
`Filters.LMS_WORKER_COMMAND` and `Filters.CMS_WORKER_COMMAND`, which is what
Tutor 22 renders `local/docker-compose.prod.yml` from. Because the change is
part of the rendered env rather than an edit to a generated file, it survives
`tutor config save`.

## Install

```bash
cd /home/tutor/atheniq/contrib/tutor-atheniq-workers
/home/tutor/tutor-venv/bin/pip install -e .
/home/tutor/tutor-venv/bin/tutor plugins enable atheniqworkers
/home/tutor/tutor-venv/bin/tutor config save
/home/tutor/tutor-venv/bin/tutor local restart lms-worker cms-worker
```

## Change the cap

Edit `WORKER_CONCURRENCY` in `atheniqworkers/plugin.py`, then re-run
`tutor config save` and restart the two workers. The value is a module constant
on purpose: Tutor loads plugins before the config, and these filters are called
with no config argument, so a `CONFIG_DEFAULTS` key cannot reach this call site
without changing the filter signature.

## Notes

- The queues are Open edX's own (grading, course publication, bulk email). A
  smaller pool makes those slower under load, never incorrect — tasks queue and
  drain in order.
- `pip list` should show `tutor-atheniq-workers` alongside `tutor-atheniq-mfe`,
  `tutor-ceruleansso`, `tutor-indigo` and `tutor-mfe`. All five must be present
  for `tutor config save` to reproduce this deployment's env; a save run without
  them silently drops their contributions from every rendered file.
