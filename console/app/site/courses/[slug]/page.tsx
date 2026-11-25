import Link from "next/link";
import type { Metadata } from "next";
import { notFound } from "next/navigation";
import { brandOf } from "@/lib/branding";
import { ADMISSIONS_EMAIL } from "@/lib/legal";
import { getDb } from "@/lib/store";
import { priceLabel } from "@/lib/public-site";

export const dynamic = "force-dynamic";

/** A course page in a search result should say which course it is. */
export async function generateMetadata({ params }: { params: Promise<{ slug: string }> }): Promise<Metadata> {
  const { slug } = await params;
  const db = getDb();
  const brand = brandOf(db.settings);
  const course = db.courses.find(
    (item) => item.status === "published" && (item.slug === slug || item.id === slug),
  );
  // A missing course goes to not-found, which brings its own title.
  if (!course) return {};
  return { title: `${course.title.replace(`${course.code} — `, "")} — ${brand.siteName}` };
}

export default async function PublicCoursePage({ params }: { params: Promise<{ slug: string }> }) {
  const { slug } = await params;
  const db = getDb();
  const brand = brandOf(db.settings);
  const site = db.settings.site;
  const course = db.courses.find(
    (item) => item.status === "published" && (item.slug === slug || item.id === slug),
  );
  if (!course) notFound();

  const track = db.tracks.find((item) => item.courses.includes(course.key));
  const lessons = course.modules.reduce((total, module) => total + module.lessons.length, 0);

  return (
    <section className="site-section narrow">
      <div className="crumbs-line">
        <Link href="/site/courses">Catalog</Link> / {course.code}
      </div>

      <header className="course-hero">
        <div>
          <div className="eyebrow">
            {course.department} · {course.credits} credits · level {course.level}
          </div>
          <h1>{course.title.replace(`${course.code} — `, "")}</h1>
          <p className="section-sub">{course.summary}</p>
          <div className="row-tags">
            <span className="tag">{course.modules.length} modules</span>
            <span className="tag">{lessons} lessons</span>
            {track && <span className="tag">{track.credential.title}</span>}
          </div>
        </div>
        <aside className="enroll-card">
          {site.showPrices && <div className="enroll-price">{priceLabel(course)}</div>}
          <div className="enroll-meta">
            {course.term.replace("_", " ")} · {course.credits} credits
          </div>
          <a className="btn-primary block" href={`mailto:${ADMISSIONS_EMAIL}?subject=${encodeURIComponent(`Enrollment — ${course.code}`)}`}>
            Ask about enrollment
          </a>
          <span className="tiny">
            Taught through {brand.siteName}. Credential offered on completion, signed at the source.
          </span>
        </aside>
      </header>

      <div className="prose">
        <h2>What this course covers</h2>
        <p>{course.description}</p>

        {course.outcomes.length > 0 && (
          <>
            <h2>By the end you can</h2>
            <ul>
              {course.outcomes.map((outcome) => (
                <li key={outcome}>{outcome}</li>
              ))}
            </ul>
          </>
        )}

        <h2>Curriculum</h2>
        <div className="module-list">
          {course.modules.map((module, index) => (
            <details key={module.id} className="module" open={index === 0}>
              <summary>
                <span>
                  Module {index + 1} — {module.title}
                </span>
                <span className="tiny">{module.lessons.length} lessons</span>
              </summary>
              <p>{module.summary}</p>
              <ul>
                {module.lessons.map((lesson) => (
                  <li key={lesson.id}>
                    {lesson.title} <span className="tiny">· {lesson.type} · {lesson.minutes} min</span>
                  </li>
                ))}
              </ul>
              <div className="tiny">Assessment: {module.assessment}</div>
            </details>
          ))}
        </div>

        {course.prerequisites.length > 0 && (
          <>
            <h2>Before you start</h2>
            <ul>
              {course.prerequisites.map((item) => (
                <li key={item}>{item}</li>
              ))}
            </ul>
          </>
        )}

        {course.grading.length > 0 && (
          <>
            <h2>How you are graded</h2>
            <ul>
              {course.grading.map((component) => (
                <li key={component.component}>
                  {component.component} — {component.weight}%
                </li>
              ))}
            </ul>
          </>
        )}

        <p className="tiny">
          {course.audience && <>Designed for {course.audience}. </>}
          {site.showVerify && (
            <>
              Certificates are verifiable at <Link href="/verify">the credential register</Link>.
            </>
          )}
        </p>
      </div>
    </section>
  );
}
