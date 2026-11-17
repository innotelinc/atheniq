import Link from "next/link";
import type { Metadata } from "next";
import { getDb } from "@/lib/store";
import { priceLabel, publicCourses } from "@/lib/public-site";
import { brandOf } from "@/lib/branding";

export const dynamic = "force-dynamic";

/** The shop window for the catalog, not the landing headline in the layout. */
export async function generateMetadata(): Promise<Metadata> {
  const brand = brandOf(getDb().settings);
  return { title: `Course catalog — ${brand.siteName}` };
}

export default function SiteCoursesPage() {
  const db = getDb();
  const site = db.settings.site;
  const brand = brandOf(db.settings);
  const courses = publicCourses(db);
  const byDepartment = new Map<string, typeof courses>();
  for (const course of courses) {
    byDepartment.set(course.department, [...(byDepartment.get(course.department) ?? []), course]);
  }

  return (
    <section className="site-section">
      <header className="section-head">
        <div>
          <div className="eyebrow">{brand.siteName}</div>
          <h1>Course catalog</h1>
          <p className="section-sub">
            {courses.length} published courses. Prices are in US dollars; credits transfer into the degree plans.
          </p>
        </div>
      </header>

      {courses.length === 0 && <p className="empty-line">Nothing is published yet.</p>}

      {[...byDepartment.entries()].map(([department, list]) => (
        <div key={department} className="dept-block">
          <h2 className="dept-title">{department}</h2>
          <div className="course-grid">
            {list.map((course) => (
              <Link key={course.id} href={`/site/courses/${course.slug}`} className="course-card">
                <div className="course-code">
                  {course.code} · {course.credits} credits · level {course.level}
                </div>
                <h3>{course.title.replace(`${course.code} — `, "")}</h3>
                <p>{course.summary}</p>
                <div className="course-foot">
                  <span className="tag">{course.term.replace("_", " ")}</span>
                  {site.showPrices && <span className="price">{priceLabel(course)}</span>}
                </div>
              </Link>
            ))}
          </div>
        </div>
      ))}
    </section>
  );
}
