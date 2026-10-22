# Assign the Unity theme to the deployment's sites.
#
# `tutor local do settheme unity` is the supported way to change the running
# site's theme; this init task is what a fresh database gets on `tutor local
# launch`, before an operator has run anything. Both point at the same theme
# directory, `themes/unity`.
./manage.py lms shell -c "
from django.contrib.sites.models import Site


def assign_theme(domain):
    site, _ = Site.objects.get_or_create(domain=domain)
    if not site.themes.exists():
        site.themes.create(theme_dir_name='unity')


for domain in ('learn.innotel.us', 'atheniq.innotel.us', 'studio.learn.innotel.us'):
    assign_theme(domain)
"
