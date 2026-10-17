# tutor-atheniq-hosts

Keeps the LMS answering for the hostnames it carried before a rename.

Set the names in `config.yml` (a list, so removing one turns it off) and
re-apply:

```bash
tutor config save --set 'ATHENIQ_LEGACY_LMS_HOSTS=["learn.example.com"]'
tutor local restart caddy lms
```

Each host is appended to `ALLOWED_HOSTS` and `CSRF_TRUSTED_ORIGINS` and gets a
caddy site block proxying to `lms:8000`. The canonical `LMS_HOST` is emitted by
Tutor itself and must not be listed here.

Install: `pip install -e contrib/tutor-atheniq-hosts && tutor plugins enable atheniqhosts`.
