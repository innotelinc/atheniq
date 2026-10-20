"""AthenIQ — cap the LMS and CMS Celery worker pools.

Tutor starts both workers as ``celery worker`` with no ``--concurrency``, so
Celery picks its default, which is the number of CPUs the container can see.
On this box both worker containers were running **8** worker processes each
(``ps --ppid 1`` on the lms-worker/cms-worker containers showed 8 children
plus the parent), and the two containers together held ~3.3 GiB — the single
largest consumers on a host that has 13.4 GiB in total and holds a second
large stack beside it.

Tutor 22 exposes the worker command as a first-class filter,
``Filters.LMS_WORKER_COMMAND`` / ``Filters.CMS_WORKER_COMMAND``, and renders
``local/docker-compose.prod.yml`` from it (``iter_lms_celery_parameters()`` /
``iter_cms_celery_parameters()``). Appending ``--concurrency`` there is the
supported way to pin it: it is part of the env Tutor renders, not an edit to a
generated file, so ``tutor config save`` reproduces it instead of dropping it.

The value is deliberately a module constant. Tutor loads plugins before it
loads the config, and these filters are evaluated with no config argument, so
a ``CONFIG_DEFAULTS``-style key could not reach this call site without
threading the config through the filter signature. ``contrib/tutor-ceruleansso``
makes the same call for its Cerulean endpoint, which is also
deployment-specific. To change the cap, edit ``WORKER_CONCURRENCY`` and re-run
``tutor config save``; the compose file and the two worker containers are
regenerated from it.

    tutor plugins enable atheniqworkers
    tutor config save
    tutor local restart lms-worker cms-worker

The queues these workers serve are Open edX's own (grading, course
publication, bulk email). A smaller pool makes those *slower* under load, never
incorrect — the tasks queue and drain in order — which is why trading
throughput for resident memory is the right direction on a host this size.
"""

from tutor import hooks as _tutor_hooks

#: Worker processes per Celery container. Tutor's implicit default here was 8.
WORKER_CONCURRENCY = 2

_tutor_hooks.Filters.LMS_WORKER_COMMAND.add_items(
    [f"--concurrency={WORKER_CONCURRENCY}"]
)
_tutor_hooks.Filters.CMS_WORKER_COMMAND.add_items(
    [f"--concurrency={WORKER_CONCURRENCY}"]
)
