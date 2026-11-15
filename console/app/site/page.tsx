import Link from "next/link";
import { brandOf } from "@/lib/branding";
import { getDb } from "@/lib/store";
import { issuedCredentials, priceLabel, programTuition, publicCourses, publicPrograms, publicTracks } from "@/lib/public-site";
import { money } from "@/lib/format";

export const dynamic = "force-dynamic";

export default function SiteHome() {
  const db = getDb();
  const brand = brandOf(db.settings);
  const site = db.settings.site;
  const courses = publicCourses(db);
  const programs = publicPrograms(db);
  const tracks = publicTracks(db);
  const credentials = issuedCredentials(db);

  if (!site.published) {
    return (
      <section className="site-section narrow">
        <div className="holding">
          <div className="holding-name">{brand.siteName}</div>
          <h1>This site is not published yet.</h1>
          <p>
            The catalog is ready, but the school has taken its public site offline. If you reached this by mistake,
            contact <a href={`mailto:${brand.supportEmail}`}>{brand.supportEmail}</a>.
          </p>
        </div>
      </section>
    );
  }

  return (
    <>
      <section className="hero">
        <div className="hero-inner">
          <div className="hero-copy">
            <div className="eyebrow">{brand.tagline}</div>
            <h1>{site.headline}</h1>
            <p className="hero-intro">{site.intro}</p>
            <div className="hero-actions">
              <Link className="btn-primary" href={site.ctaHref || "/site/courses"}>
                {site.ctaLabel || "Explore the catalog"}
              </Link>
              {site.showVerify && (
                <Link className="btn-quiet" href="/verify">
                  Verify a credential
                </Link>
              )}
            </div>
            <dl className="hero-stats">
              <div>
                <dt>Published courses</dt>
                <dd>{courses.length}</dd>
              </div>
              {site.showPrograms && (
                <div>
                  <dt>Degree programs</dt>
                  <dd>{programs.length}</dd>
                </div>
              )}
              <div>
                <dt>Credentials issued</dt>
                <dd>{credentials.length}</dd>
              </div>
              <div>
                <dt>Tuition</dt>
                <dd>{money(db.settings.tuitionPerCreditCents)}<small>/credit</small></dd>
              </div>
            </dl>
          </div>
        </div>
      </section>

      <section className="site-section">
        <header className="section-head">
          <div>
            <div className="eyebrow">Catalog</div>
            <h2>Courses you can start now</h2>
          </div>
          <Link className="link-arrow" href="/site/courses">
            All {courses.length} courses →
          </Link>
        </header>
        <div className="course-grid">
          {courses.slice(0, 6).map((course) => (
            <Link key={course.id} href={`/site/courses/${course.slug}`} className="course-card">
              <div className="course-code">
                {course.code} · {course.credits} credits
              </div>
              <h3>{course.title.replace(`${course.code} — `, "")}</h3>
              <p>{course.summary}</p>
              <div className="course-foot">
                <span className="tag">{course.department}</span>
                {site.showPrices && <span className="price">{priceLabel(course)}</span>}
              </div>
            </Link>
          ))}
        </div>
        {courses.length === 0 && (
          <p className="empty-line">No courses are published yet. The catalog is being prepared.</p>
        )}
      </section>

      {site.showPrograms && programs.length > 0 && (
        <section className="site-section alt">
          <header className="section-head">
            <div>
              <div className="eyebrow">Degrees</div>
              <h2>Programs with a clear credit path</h2>
            </div>
            <Link className="link-arrow" href="/site/programs">
              All programs →
            </Link>
          </header>
          <div className="program-grid">
            {programs.slice(0, 3).map((program) => (
              <article key={program.id} className="program-card">
                <div className="course-code">{program.credentialType} · {program.totalCredits} credits</div>
                <h3>{program.name}</h3>
                <p>{program.summary}</p>
                <div className="course-foot">
                  <span className="tag">{program.semesters.length} semesters</span>
                  {site.showPrices && <span className="price">{programTuition(program)}</span>}
                </div>
              </article>
            ))}
          </div>
        </section>
      )}

      {tracks.length > 0 && (
        <section className="site-section">
          <header className="section-head">
            <div>
              <div className="eyebrow">Workforce</div>
              <h2>Ladders built with employers</h2>
            </div>
          </header>
          <div className="track-list">
            {tracks.slice(0, 4).map((track) => (
              <article key={track.id} className="track-row">
                <div>
                  <h3>{track.title}</h3>
                  <p>{track.summary}</p>
                </div>
                <div className="track-meta">
                  <span className="tag">{track.courses.length} courses</span>
                  <span className="tag">{track.credential.title}</span>
                </div>
              </article>
            ))}
          </div>
        </section>
      )}

      <section className="verify-strip">
        <div>
          <h2>Every credential is signed at the source</h2>
          <p>
            Certificates and degree conferrals are signed through Signara. An employer checks the verification id
            printed on the document and sees the award record it was signed over.
          </p>
        </div>
        {site.showVerify && (
          <Link className="btn-primary" href="/verify">
            Verify a credential
          </Link>
        )}
      </section>
    </>
  );
}
