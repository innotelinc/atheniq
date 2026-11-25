import Link from "next/link";
import type { Metadata } from "next";
import { getDb } from "@/lib/store";
import { programTuition, publicPrograms } from "@/lib/public-site";
import { brandOf } from "@/lib/branding";

export const dynamic = "force-dynamic";

/** A tab in someone's browser should say which plan page they are on. */
export async function generateMetadata(): Promise<Metadata> {
  const brand = brandOf(getDb().settings);
  return { title: `Degree programs — ${brand.siteName}` };
}

export default function SiteProgramsPage() {
  const db = getDb();
  const brand = brandOf(db.settings);
  const site = db.settings.site;
  const programs = publicPrograms(db);

  return (
    <section className="site-section">
      <header className="section-head">
        <div>
          <div className="eyebrow">{brand.siteName}</div>
          <h1>Degree programs</h1>
          <p className="section-sub">
            Every plan lists its semesters and credits. Tuition is quoted in US dollars at{" "}
            {(db.settings.tuitionPerCreditCents / 100).toFixed(0)} USD per credit, with a{" "}
            {(db.settings.applicationFeeCents / 100).toFixed(0)} USD application fee.
          </p>
        </div>
      </header>

      {programs.length === 0 && <p className="empty-line">No programs are open for enrollment right now.</p>}

      <div className="program-grid wide">
        {programs.map((program) => (
          <article key={program.id} className="program-card">
            <div className="course-code">
              {program.credentialType} · {program.totalCredits} credits
            </div>
            <h2>{program.credential}</h2>
            <p>{program.summary}</p>

            <details className="module">
              <summary>
                <span>Semester plan</span>
                <span className="tiny">{program.semesters.length} semesters</span>
              </summary>
              {program.semesters.map((semester) => (
                <div key={semester.number} className="semester">
                  <div className="strong small">
                    Semester {semester.number} — {semester.focus} · {semester.credits} credits
                  </div>
                  <ul>
                    {semester.courses.map((course) => (
                      <li key={course.code}>
                        {course.code} — {course.title}
                      </li>
                    ))}
                  </ul>
                </div>
              ))}
            </details>

            <div className="course-foot">
              <span className="tag">{program.accreditation || "Institutional"}</span>
              {site.showPrices && <span className="price">{programTuition(program)}</span>}
            </div>
            <Link className="link-arrow" href="/site/courses">
              Courses in this plan →
            </Link>
          </article>
        ))}
      </div>
    </section>
  );
}
