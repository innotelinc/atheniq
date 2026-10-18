# tutor-atheniq-hosts

Keeps the platform answering for hostnames other than the canonical one — the
aliases a rename leaves behind, so every link, bookmark and course email written
before the rename still lands on the same application.

Two lists, both empty by default:

| List | What it names | What the plugin adds |
| --- | --- | --- |
| `ATHENIQ_LEGACY_LMS_HOSTS` | another LMS hostname | `ALLOWED_HOSTS`, `CSRF_TRUSTED_ORIGINS`, `CORS_ORIGIN_WHITELIST`, `LOGIN_REDIRECT_WHITELIST`, and a caddy block proxying to `lms:8000` |
| `ATHENIQ_LEGACY_MFE_HOSTS` | another learner-MFE hostname | the same trust lines minus `ALLOWED_HOSTS` (Django never serves the MFE), and a caddy block proxying to `mfe:8002` |

The canonical names (`LMS_HOST` and `apps.<LMS_HOST>`) are emitted by Tutor and
its MFE plugin, so they must not be listed here.

Set the names in `config.yml` (a list, so removing one turns it off) and
re-apply:

```bash
# this deployment: learn.<domain> is canonical, lms.<domain> is the alias
tutor config save \
  --set 'ATHENIQ_LEGACY_LMS_HOSTS=["lms.innotel.us"]' \
  --set 'ATHENIQ_LEGACY_MFE_HOSTS=["apps.lms.innotel.us"]'
tutor local restart caddy lms lms-worker cms cms-worker mfe
```

Each name also needs its own edge host (DNS record, certificate, NPM proxy host)
before anyone outside the LAN can reach it — see
[`scripts/provision-edge.sh`](../../scripts/provision-edge.sh).

Install: `pip install -e contrib/tutor-atheniq-hosts && tutor plugins enable atheniqhosts`.
