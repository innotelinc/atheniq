from openedx.core.djangoapps.content.course_overviews.models import CourseOverview as C

row = C.objects.filter(id="course-v1:InnotelLabs+BIO201+2026_T4").values(
    "course_image_url", "banner_image_url").first()
print(row)
