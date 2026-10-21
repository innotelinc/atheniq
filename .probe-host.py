import glob
import json
import sys

sys.path.insert(0, "/home/tutor/atheniq/scripts")
import importlib.util

spec = importlib.util.spec_from_file_location("photos", "/home/tutor/atheniq/scripts/course-photos.py")
photos = importlib.util.module_from_spec(spec)
spec.loader.exec_module(photos)

for path in glob.glob("/home/tutor/atheniq-generation/programs/*.json"):
    doc = json.load(open(path))
    for semester in doc.get("semesters") or []:
        for course in semester.get("courses") or []:
            if course.get("code") in ("BIO201", "BUS110", "CJ310"):
                print(path.split("/")[-1], course.get("code"), repr(course.get("title")),
                      repr(course.get("description"))[:200])
                print("   ->", photos.resolve(course.get("code"), course.get("title"), course.get("description") or ""))
