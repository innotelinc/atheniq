import re
from django.test import Client

c = Client(SERVER_NAME="studio.innotel.us")
page = c.get("/this-page-does-not-exist").content.decode("utf-8", "replace")
for line in page.splitlines():
    if "stylesheet" in line or "unity" in line or "data-scheme" in line:
        print(line.strip()[:240])
