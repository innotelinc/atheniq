import Link from "next/link";
import { brandOf } from "@/lib/branding";
import { money } from "@/lib/format";
import { ADMISSIONS_EMAIL, LEGAL_EMAIL } from "@/lib/legal";
import { programTuition, publicCourses, publicPrograms } from "@/lib/public-site";
import { getDb } from "@/lib/store";

/**
 * The storefront's front page, built to the same order and voice as the
 * marketing site at atheniq.institute (web/landing on the monorepo): hero and
 * cohort card, what makes the school different, the degree plans, a week of
 * study, tuition, admissions, questions, then the closing band.
 *
 * The copy that describes the institution is here because it is the same
 * institution on both hosts. The catalog, the plans, the credit counts and the
 * prices are not: they come from the registrar's own records on every request,
 * so the site cannot drift from what the console bills.
 */
export const dynamic = "force-dynamic";

const FEATURES = [
  {
    glyph: "◎",
    title: "Live AI classrooms",
    body: "Each module runs as a facilitated session with an AI teacher, AI classmates for practice, and a faculty member who reviews the outcomes.",
  },
  {
    glyph: "◈",
    title: "Small by design",
    body: "Seminars are capped so discussion stays real. Your success coach and faculty adviser are reachable, not buried behind a portal.",
  },
  {
    glyph: "▤",
    title: "Competency, not seat time",
    body: "Every course ends in graded work and a proctored final. Pass at 60% and the credit is yours; your transcript records the grade.",
  },
  {
    glyph: "◇",
    title: "Credentials that verify",
    body: "Completion is signed through Signara and issued to your learner record, so employers and licensure boards can check it at the source.",
  },
];

const WEEK = [
  {
    title: "Attend the classroom",
    body: "A facilitated session with an AI teacher and AI classmates. Ask questions, work scenarios, leave with the week’s problem set.",
  },
  {
    title: "Work the lessons",
    body: "Short readings, worked examples and practice questions, built from the same outline your syllabus publishes.",
  },
  {
    title: "Submit graded work",
    body: "Problem sets, labs, writing and projects, marked against the published rubric — with feedback you can act on.",
  },
  {
    title: "Sit the final",
    body: "A proctored final examination at the end of each course. Pass at 60% for credit; the grade goes on your transcript.",
  },
];

const NEED = [
  "A laptop or desktop with a current browser and a reliable connection.",
  "A webcam for proctored examinations.",
  "No textbooks to buy: every reading and case is in the course.",
  "Nursing: clinical placement, immunisations and a background check before practicum.",
];

const SUPPORT = [
  "A success coach from application to conferral.",
  "Faculty office hours every week, plus a 24/7 AI study partner.",
  "Writing and quantitative support, and accessibility accommodations.",
  "Career services: résumé review, interview practice and employer introductions.",
];

const CALENDAR = [
  ["Priority application deadline", "November 1"],
  ["Final application deadline", "January 4"],
  ["Registration closes", "January 8"],
  ["Classes begin", "January 11"],
  ["Add / drop ends", "January 25"],
  ["Midterm week", "March 1–5"],
  ["Finals week", "May 3–7"],
  ["Conferral", "May 14"],
];

const FAQ = [
  {
    q: "Is AthenIQ accredited?",
    a: "AthenIQ is an online learning program of Innotel Labs. Accreditation and state-authorization disclosures, including the status of each program and any pending applications, are stated in the university catalog and provided with every offer of admission. Credits transfer at the receiving institution’s discretion.",
  },
  {
    q: "How much time should I plan for each week?",
    a: "Full-time study is 15–20 hours a week across four to five courses. A single 3-credit course is about 8–10 hours a week for a 15-week term. Most courses run every term, so you can slow down without leaving the program.",
  },
  {
    q: "Are the classes live?",
    a: "Each module has a scheduled live AI-classroom session, recorded for learners in other time zones. The rest is self-paced, with faculty office hours and asynchronous discussion. You are never required to be online at a fixed hour to pass.",
  },
  {
    q: "Can I work while I study?",
    a: "Yes. Most learners do. The part-time plan spreads a program over roughly twice the length, and your success coach maps it term by term before you register.",
  },
  {
    q: "What does the nursing program require beyond the online courses?",
    a: "Supervised clinical hours with a partner site near you, current immunisations, a background check and CPR certification before practicum. Placement is arranged with your clinical coordinator; the fee, if any, is billed at cost.",
  },
  {
    q: "What happens if I fail a course?",
    a: "You can retake it at the same tuition rate. The first attempt stays on the transcript; the retake replaces the grade in the GPA calculation according to the academic policy published in the catalog.",
  },
];

export default function SiteHome() {
  const db = getDb();
  const brand = brandOf(db.settings);
  const site = db.settings.site;
  const courses = publicCourses(db);
  const programs = publicPrograms(db);
  const rateCents = db.settings.tuitionPerCreditCents;
  const applyHref = `mailto:${ADMISSIONS_EMAIL}?subject=${encodeURIComponent("Application — Spring 2027")}`;

  if (!site.published) {
    return (
      <section className="site-section narrow">
        <div className="holding">
          <div className="holding-name">{brand.siteName}</div>
          <h1>This site is not published yet.</h1>
          <p>
            The catalog is ready, but the school has taken its public site offline. If you reached this by mistake,
            contact <a href={`mailto:${ADMISSIONS_EMAIL}`}>{ADMISSIONS_EMAIL}</a>.
          </p>
        </div>
      </section>
    );
  }

  const credits = programs.map((program) => program.totalCredits);
  const creditsRange = credits.length ? `${Math.min(...credits)}–${Math.max(...credits)}` : "—";

  return (
    <>
      {/* Hero */}
      <section className="hero">
        <div className="hero-inner">
          <div className="hero-grid">
            <div className="hero-copy">
              <p className="eyebrow">
                {brand.siteName} · Innotel Labs
              </p>
              <h1>{site.headline}</h1>
              <p className="hero-intro">{site.intro}</p>
              <div className="hero-actions">
                <Link className="btn-primary" href={site.ctaHref || "/site/courses"}>
                  {site.ctaLabel || "Explore the course catalog"}
                </Link>
                <Link className="btn-quiet" href="/site/programs">
                  Compare programs
                </Link>
              </div>
              <p className="hero-fine">No SAT or ACT. Transfer up to 90 credits. One tuition rate for every program.</p>
            </div>

            <aside className="cohort" aria-label="Spring 2027 cohort">
              <h3>
                Spring 2027 cohort <span className="pill">Open</span>
              </h3>
              <p className="date">January 11</p>
              <p className="small muted">First day of classes</p>
              <dl>
                <div>
                  <dt>Application deadline</dt>
                  <dd>January 4</dd>
                </div>
                <div>
                  <dt>Registration closes</dt>
                  <dd>January 8</dd>
                </div>
                <div>
                  <dt>Add / drop ends</dt>
                  <dd>January 25</dd>
                </div>
                <div>
                  <dt>Finals week</dt>
                  <dd>May 3–7</dd>
                </div>
              </dl>
              <p className="note">
                Applications are reviewed in the order received. Enrolled learners can begin coursework now; the
                cohort’s official first day is January 11, 2027. Nursing has a separate clinical-placement review.
              </p>
            </aside>
          </div>

          <div className="stats">
            <div className="stat">
              <b>{programs.length}</b>
              <span>Degree programs</span>
            </div>
            <div className="stat">
              <b>{courses.length}</b>
              <span>Courses in the catalog</span>
            </div>
            <div className="stat">
              <b>{creditsRange}</b>
              <span>Credits to graduate</span>
            </div>
            <div className="stat">
              <b>100%</b>
              <span>Online, live and self-paced</span>
            </div>
          </div>
        </div>
      </section>

      {/* Why */}
      <section className="site-section alt">
        <div className="section-head">
          <div>
            <p className="eyebrow">The {brand.siteName.split(" ")[0]} difference</p>
            <h2>Rigorous, personal, and built around how people actually learn.</h2>
            <p className="section-sub">
              Small cohorts. Faculty who know your name. An AI classroom that gives every learner a voice — and never
              replaces the person grading the work.
            </p>
          </div>
        </div>
        <div className="grid-4">
          {FEATURES.map((feature) => (
            <div className="feature" key={feature.title}>
              <span className="glyph" aria-hidden="true">
                {feature.glyph}
              </span>
              <h3>{feature.title}</h3>
              <p>{feature.body}</p>
            </div>
          ))}
        </div>
      </section>

      {/* Programs */}
      {site.showPrograms && programs.length > 0 ? (
        <section className="site-section" id="programs">
          <div className="section-head">
            <div>
              <p className="eyebrow">Degree programs</p>
              <h2>{programs.length === 1 ? "One program. One standard." : `${programs.length} programs. One standard.`}</h2>
              <p className="section-sub">
                Each program is a fixed sequence of semesters, built from courses you can read in the catalog before
                you apply. Outlines below are the plans the registrar publishes for the Spring 2027 cohort.
              </p>
            </div>
            <Link className="btn-quiet" href="/site/courses">
              Browse all {courses.length} courses
            </Link>
          </div>

          <div className="programs">
            {programs.map((program) => (
              <article className="program" key={program.id}>
                <div className="program-top">
                  <div>
                    <p className="level">{program.credential}</p>
                    <h3>{program.name}</h3>
                    <p className="desc">{program.summary}</p>
                  </div>
                  <div className="facts">
                    <div className="fact">
                      <b>{program.totalCredits}</b>
                      <span>Credits</span>
                    </div>
                    <div className="fact">
                      <b>{program.semesters.length}</b>
                      <span>Semesters</span>
                    </div>
                    <div className="fact">
                      <b>{program.credentialType === "Associate" ? "2.5 yrs" : `${Math.round(program.semesters.length / 2) || "—"} yrs`}</b>
                      <span>Full time</span>
                    </div>
                  </div>
                </div>

                {program.semesters.length > 0 && (
                  <details>
                    <summary>Program outline</summary>
                    <div className="outline">
                      <table>
                        <thead>
                          <tr>
                            <th>Semester</th>
                            <th>Focus</th>
                            <th>Credits</th>
                            <th>Sample courses</th>
                          </tr>
                        </thead>
                        <tbody>
                          {program.semesters.map((semester) => (
                            <tr key={semester.number}>
                              <td>{semester.number}</td>
                              <td>{semester.focus}</td>
                              <td>{semester.credits}</td>
                              <td>
                                {semester.courses.map((course) => (
                                  <span key={course.code}>
                                    <span className="code">{course.code}</span> {course.title}
                                    {" · "}
                                  </span>
                                ))}
                              </td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  </details>
                )}
              </article>
            ))}
          </div>
        </section>
      ) : null}

      {/* Experience */}
      <section className="site-section alt" id="experience">
        <div className="section-head">
          <div>
            <p className="eyebrow">What to expect</p>
            <h2>A week at {brand.siteName.split(" ")[0]}.</h2>
            <p className="section-sub">
              Full-time study is about 15–20 hours a week: one live classroom session per course, self-paced lessons,
              practice with immediate feedback, and graded work. Part-time is possible — most courses run every term.
            </p>
          </div>
        </div>
        <div className="flow">
          {WEEK.map((step) => (
            <div className="step" key={step.title}>
              <h3>{step.title}</h3>
              <p>{step.body}</p>
            </div>
          ))}
        </div>
        <div className="rhythm">
          <div className="panel">
            <h3>What you need</h3>
            <ul className="checks">
              {NEED.map((item) => (
                <li key={item}>{item}</li>
              ))}
            </ul>
          </div>
          <div className="panel">
            <h3>How you’re supported</h3>
            <ul className="checks">
              {SUPPORT.map((item) => (
                <li key={item}>{item}</li>
              ))}
            </ul>
          </div>
        </div>
      </section>

      {/* Tuition */}
      <section className="site-section" id="tuition">
        <div className="section-head">
          <div>
            <p className="eyebrow">Tuition and aid</p>
            <h2>One rate. No surprises.</h2>
            <p className="section-sub">
              Every program is charged per credit at the same rate, whether you study full or part time. Course
              materials are included, and there is no out-of-state premium.
            </p>
          </div>
        </div>
        <div className="tuition-grid">
          <div>
            {site.showPrices ? (
              <table className="price-table">
                <thead>
                  <tr>
                    <th>Program</th>
                    <th>Credits</th>
                    <th>Tuition</th>
                  </tr>
                </thead>
                <tbody>
                  {programs.map((program) => (
                    <tr key={program.id}>
                      <td>{program.credential}</td>
                      <td>{program.totalCredits}</td>
                      <td className="num">{programTuition(program)}</td>
                    </tr>
                  ))}
                  <tr>
                    <td>Per credit</td>
                    <td>1</td>
                    <td className="num">{money(rateCents)}</td>
                  </tr>
                  <tr>
                    <td>Typical 3-credit course</td>
                    <td>3</td>
                    <td className="num">{money(rateCents * 3)}</td>
                  </tr>
                </tbody>
              </table>
            ) : (
              <p className="empty-line">Tuition is quoted by the admissions office for this cohort.</p>
            )}
            <div className="aid">
              <div className="feature">
                <h3>Monthly plan</h3>
                <p>Pay per course, or spread the term across monthly payments with no interest and no fee.</p>
              </div>
              <div className="feature">
                <h3>Employer billing</h3>
                <p>We invoice employers directly and defer payment while tuition assistance is approved.</p>
              </div>
              <div className="feature">
                <h3>Scholarships</h3>
                <p>Merit awards up to 20%, a 10% military and veteran discount, and need-based support up to 25%.</p>
              </div>
            </div>
            <p className="fine-print">
              Tuition is locked for the cohort you enter. Fees: {money(db.settings.applicationFeeCents)} application
              (waived for Spring 2027) and a graduation fee. Nursing clinical placement fees, where a partner charges
              them, are billed at cost.
            </p>
          </div>
          <aside className="price-card">
            <p className="small muted">Your first course</p>
            <p className="big">
              {money(rateCents * 3)}
              <small> / 3 credits</small>
            </p>
            <p className="small muted">Or {money(rateCents)} per credit, paid course by course.</p>
            <ul className="checks" style={{ marginTop: 16 }}>
              <li>All readings and course materials</li>
              <li>Live AI classroom and faculty office hours</li>
              <li>Graded assessments and proctored final</li>
              <li>Transcript and verified credential</li>
            </ul>
            <p className="fine-print">
              Ask <a href={`mailto:${ADMISSIONS_EMAIL}`}>{ADMISSIONS_EMAIL}</a> about a plan before you commit.
            </p>
          </aside>
        </div>
      </section>

      {/* Admissions */}
      <section className="site-section alt" id="admissions">
        <div className="section-head">
          <div>
            <p className="eyebrow">Admissions</p>
            <h2>Apply in about twenty minutes.</h2>
            <p className="section-sub">
              We read every application. There is no SAT or ACT requirement; what matters is that you are ready for
              college-level work and can show it.
            </p>
          </div>
          <a className="btn-primary" href={applyHref}>
            Start your application
          </a>
        </div>
        <div className="two-col">
          <div className="panel">
            <h3>What you need</h3>
            <ul className="checks">
              <li>High school diploma or equivalency (GED, HiSET).</li>
              <li>Official transcripts from every institution you have attended.</li>
              <li>English proficiency, if your schooling was not in English.</li>
              <li>
                Nursing: prerequisite sciences, immunisations and a background check before clinical placement.
              </li>
            </ul>
            <div className="flow" style={{ marginTop: 20 }}>
              <div className="step">
                <h3>Apply</h3>
                <p>Tell us the program and term. No essay; a short goals statement for nursing.</p>
              </div>
              <div className="step">
                <h3>Send transcripts</h3>
                <p>We evaluate transfer credit and send you a degree audit before you commit.</p>
              </div>
              <div className="step">
                <h3>Talk to a coach</h3>
                <p>A 20-minute call about pace, cost and start date.</p>
              </div>
              <div className="step">
                <h3>Register</h3>
                <p>Confirm your plan, register for the first term and meet your adviser.</p>
              </div>
            </div>
          </div>
          <div className="panel">
            <h3>Spring 2027 calendar</h3>
            <table className="dates">
              <tbody>
                {CALENDAR.map(([label, date]) => (
                  <tr key={label}>
                    <td>{label}</td>
                    <td>{date}</td>
                  </tr>
                ))}
              </tbody>
            </table>
            <h3 style={{ marginTop: 22 }}>Transfer credit</h3>
            <p className="small muted">
              Up to 90 credits toward a bachelor’s and up to 45 toward the associate degree, from regionally
              accredited institutions. Military training and approved industry certifications are evaluated against
              the same standard.
            </p>
            <h3 style={{ marginTop: 22 }}>International learners</h3>
            <p className="small muted">
              {brand.siteName} is online and borderless, but some programs lead to licensure. Check the requirements
              of the state or country where you intend to practise before enrolling.
            </p>
            <p className="small muted" style={{ marginTop: 18 }}>
              Questions: <a href={`mailto:${ADMISSIONS_EMAIL}`}>{ADMISSIONS_EMAIL}</a>. The registrar’s office
              reaches at <a href={`mailto:${LEGAL_EMAIL}`}>{LEGAL_EMAIL}</a>.
            </p>
          </div>
        </div>
      </section>

      {/* FAQ */}
      <section className="site-section" id="faq">
        <div className="section-head">
          <div>
            <p className="eyebrow">Questions</p>
            <h2>Before you apply.</h2>
          </div>
        </div>
        <div className="faq">
          {FAQ.map((item) => (
            <details key={item.q}>
              <summary>{item.q}</summary>
              <p>{item.a}</p>
            </details>
          ))}
        </div>
      </section>

      {/* Closing band */}
      <section className="cta-band" id="apply">
        <div className="cta-band-inner">
          <p className="eyebrow">Spring 2027 · Apply by January 4</p>
          <h2>Start with a course. Finish with a degree.</h2>
          <p>
            Read the catalog first. Every syllabus, every course and every assessment is published before you pay a
            cent — then apply to a program when you know the plan is the one you want.
          </p>
          <div className="actions">
            <Link className="btn-primary" href="/site/courses">
              See the catalog
            </Link>
            <a className="btn-quiet" href={applyHref}>
              Ask about admission
            </a>
            {site.showVerify && (
              <Link className="btn-quiet" href="/verify">
                Verify a credential
              </Link>
            )}
          </div>
        </div>
      </section>
    </>
  );
}
