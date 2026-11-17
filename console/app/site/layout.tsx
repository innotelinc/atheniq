import Link from "next/link";
import type { Metadata } from "next";
import "./site.css";
import { BrandMark } from "@/components/BrandMark";
import { brandOf, brandVars } from "@/lib/branding";
import { ADMISSIONS_EMAIL, LEGAL_EMAIL } from "@/lib/legal";
import { getDb } from "@/lib/store";

/**
 * The storefront wears the same face as the marketing site at atheniq.institute
 * (web/landing on the monorepo): one utility bar, one masthead, one footer, one
 * palette. It is the same institution on two hosts, so it should not read as
 * two different schools.
 *
 * Admissions questions go to admissions@atheniq.institute and the registrar's
 * own address is registrar@atheniq.institute — both published on the marketing
 * site, both kept here rather than in a settings field that can drift.
 */
export const dynamic = "force-dynamic";

export async function generateMetadata(): Promise<Metadata> {
  const db = getDb();
  const brand = brandOf(db.settings);
  return {
    title: `${brand.siteName} — Degrees for the age of AI`,
    description: db.settings.site.intro.slice(0, 180),
  };
}

const NAV = [
  { href: "/site/programs", label: "Programs" },
  { href: "/site#experience", label: "Experience" },
  { href: "/site#tuition", label: "Tuition" },
  { href: "/site#admissions", label: "Admissions" },
  { href: "/site#faq", label: "FAQ" },
  { href: "/site/courses", label: "Course catalog" },
];

export default function SiteLayout({ children }: { children: React.ReactNode }) {
  const db = getDb();
  const brand = brandOf(db.settings);
  const site = db.settings.site;
  const applyHref = `mailto:${ADMISSIONS_EMAIL}?subject=${encodeURIComponent("Application — Spring 2027")}`;
  // The registrar console is staff-only, so it is not a door a learner is ever
  // sent through: "Student login" points at the classroom, where a student's
  // account lives. Admissions is the address above.
  const loginHref = `${db.settings.lms.baseUrl.replace(/\/+$/, "")}/login`;

  return (
    <div className="site" style={brandVars(brand) as React.CSSProperties} data-placement={brand.logoPlacement}>
      <a className="skip" href="#main">
        Skip to content
      </a>

      <div className="utility">
        <div className="wrap">
          <span>
            <strong>Spring 2027 applications are open — early access now</strong>
          </span>
          <span className="hide-mobile">Classes begin January 11, 2027 · Apply by January 4</span>
          <span className="spacer" />
          <a href={loginHref}>Student login</a>
          <a href={applyHref}>Apply</a>
        </div>
      </div>

      <header className={`site-head ${brand.logoPlacement}`}>
        <Link href="/site" className="site-brand">
          <BrandMark brand={brand} size={34} />
          <span className="site-brand-text">
            <strong>{brand.siteName}</strong>
            <em>{brand.tagline}</em>
          </span>
        </Link>
        <nav className="site-nav" aria-label="Main">
          {NAV.map((item) => (
            <Link key={item.href} href={item.href}>
              {item.label}
            </Link>
          ))}
        </nav>
        <div className="site-actions">
          <a className="site-link-quiet" href={loginHref}>
            Sign in
          </a>
          <a className="site-cta" href={applyHref}>
            Apply now
          </a>
        </div>
      </header>

      <main id="main">{children}</main>

      <footer className="site-foot">
        <div className="foot-inner">
          <div className="foot-grid">
            <div>
              <Link href="/site" className="site-brand" style={{ marginBottom: 10 }}>
                <BrandMark brand={brand} size={32} />
                <span className="site-brand-text">
                  <strong>{brand.siteName}</strong>
                  <em>{brand.tagline}</em>
                </span>
              </Link>
              <p className="small">An online university from Innotel Labs.</p>
              <p className="small" style={{ marginTop: 8 }}>
                <a href={`mailto:${ADMISSIONS_EMAIL}`}>{ADMISSIONS_EMAIL}</a>
              </p>
            </div>
            <div>
              <h4>Study</h4>
              <ul>
                <li>
                  <Link href="/site/programs">Degree programs</Link>
                </li>
                <li>
                  <Link href="/site/courses">Course catalog</Link>
                </li>
                <li>
                  <Link href="/site#tuition">Tuition and aid</Link>
                </li>
                <li>
                  <Link href="/site#experience">What to expect</Link>
                </li>
              </ul>
            </div>
            <div>
              <h4>Apply</h4>
              <ul>
                <li>
                  <Link href="/site#admissions">Admissions</Link>
                </li>
                <li>
                  <a href={applyHref}>Start an application</a>
                </li>
                <li>
                  <a href={loginHref}>Student login</a>
                </li>
                <li>
                  <Link href="/site#faq">FAQ</Link>
                </li>
              </ul>
            </div>
            <div>
              <h4>Institution</h4>
              <ul>
                <li>
                  <a href={`mailto:${ADMISSIONS_EMAIL}`}>Admissions</a>
                </li>
                <li>
                  <a href={`mailto:${LEGAL_EMAIL}`}>Registrar</a>
                </li>
                {site.showVerify && (
                  <li>
                    <Link href="/verify">Verify a credential</Link>
                  </li>
                )}
                <li>
                  <Link href="/site/privacy">Privacy policy</Link>
                </li>
              </ul>
            </div>
          </div>

          <p className="disclosure">
            {brand.siteName} is a program of Innotel Labs. Accreditation and state-authorization disclosures are
            provided in the catalog and with an offer of admission. Program graduates must meet the licensure
            requirements of the state or country in which they intend to practise. Tuition and calendar are for the
            Spring 2027 cohort and may change for later cohorts.
          </p>

          <div className="foot-bottom">
            <span>
              © {new Date().getFullYear()} Innotel Labs · {brand.siteName}
            </span>
            {brand.poweredBy && <span className="site-powered">Powered by AthenIQ</span>}
          </div>
        </div>
      </footer>
    </div>
  );
}
