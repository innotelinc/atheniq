from openedx.core.djangoapps.content.course_overviews.models import CourseOverview as C

rows = list(C.objects.values_list("id", "course_image_url", "display_name"))
mapped = [r for r in rows if "/static/atheniq/images/courses/" in (r[1] or "")]
print("TOTAL", len(rows), "MAPPED", len(mapped))
for row in mapped[:8]:
    print("ROW", row)
unmapped = [r for r in rows if "/static/atheniq/images/courses/" not in (r[1] or "")]
print("UNMAPPED", len(unmapped), unmapped[:3])
