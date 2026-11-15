import Link from "next/link";
import type { Metadata } from "next";
import "./site.css";
import { BrandMark } from "@/components/BrandMark";
import { brandOf, brandVars } from "@/lib/branding";
import { getDb } from "@/lib/store";

export const dynamic = "force-dynamic";

export async function generateMetadata(): Promise<Metadata> {
  const db = getDb();
  const brand = brandOf(db.settings);
  return {
    title: `${brand.siteName} — ${db.settings.site.headline}`,
    description: db.settings.site.intro.slice(0, 180),
  };
}

export default function SiteLayout({ children }: { children: React.ReactNode }) {
  const db = getDb();
  const brand = brandOf(db.settings);
  const site = db.settings.site;

  return (
    <div className="site" style={brandVars(brand) as React.CSSProperties} data-placement={brand.logoPlacement}>
      <header className={`site-head ${brand.logoPlacement}`}>
        <Link href="/site" className="site-brand">
          <BrandMark brand={brand} size={34} />
          <span className="site-brand-text">
            <strong>{brand.siteName}</strong>
            <em>{brand.tagline}</em>
          </span>
        </Link>
        <nav className="site-nav">
          <Link href="/site/courses">Courses</Link>
          {site.showPrograms && <Link href="/site/programs">Degree programs</Link>}
          {site.showVerify && <Link href="/verify">Verify a credential</Link>}
          <a className="site-cta" href={`mailto:${brand.supportEmail}?subject=Admissions`}>
            Admissions
          </a>
        </nav>
      </header>

      <main className="site-main">{children}</main>

      <footer className="site-foot">
        <div>
          © {new Date().getFullYear()} {brand.siteName} · {brand.domain}
        </div>
        <div className="site-foot-links">
          <Link href="/site/courses">Catalog</Link>
          {site.showPrograms && <Link href="/site/programs">Programs</Link>}
          {site.showVerify && <Link href="/verify">Verification</Link>}
          <a href={`mailto:${brand.supportEmail}`}>{brand.supportEmail}</a>
        </div>
        {brand.poweredBy && <div className="site-powered">Powered by AthenIQ</div>}
      </footer>
    </div>
  );
}
