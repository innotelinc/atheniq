import type { Metadata } from "next";
import Link from "next/link";
import { headers } from "next/headers";
import "./globals.css";
import { Nav } from "@/components/Nav";
import { SignOutButton } from "@/components/SignOutButton";
import { currentStaff } from "@/lib/current-staff";
import { LEGAL_EMAIL } from "@/lib/legal";
import { authEnabled } from "@/lib/session";
import { ROLE_LABELS } from "@/lib/staff-policy";

export const metadata: Metadata = {
  title: "AthenIQ — Course & School Management",
  description:
    "Create, generate and publish AthenIQ courses; manage degree plans and award certificates and degrees through Signara.",
};

export default async function RootLayout({ children }: { children: React.ReactNode }) {
  const headerList = await headers();

  // The public website wears its own white-labeled chrome (app/site/layout.tsx).
  if (headerList.get("x-atheniq-public") === "1") {
    return (
      <html lang="en">
        <body>{children}</body>
      </html>
    );
  }

  const staff = await currentStaff();

  // Public pages a visitor reaches without a session wear a header of public
  // links. The console sidebar is a set of doors that each answer with the
  // sign-in page, which turns a stranger's first page into a dead end.
  if (!staff && headerList.get("x-atheniq-public-shell") === "1") {
    return (
      <html lang="en">
        <body>
          <div className="public-shell">
            <header className="public-bar">
              <Link className="brand" href="/site">
                <BrandMark />
                <span className="brand-text">
                  <span className="brand-name">AthenIQ</span>
                  <span className="brand-sub">Institute</span>
                </span>
              </Link>
              <nav className="public-links" aria-label="Public">
                <Link href="/verify">Verify a credential</Link>
                <Link href="/privacy">Privacy</Link>
                <Link className="btn small" href="/login">
                  Sign in
                </Link>
              </nav>
            </header>
            <main className="main">{children}</main>
            <footer className="public-foot">
              <span>Innotel Labs · AthenIQ</span>
              <a href={`mailto:${LEGAL_EMAIL}`}>{LEGAL_EMAIL}</a>
            </footer>
          </div>
        </body>
      </html>
    );
  }

  return (
    <html lang="en">
      <body>
        <div className="shell">
          <aside className="sidebar">
            <div className="brand">
              <BrandMark />
              <span className="brand-text">
                <span className="brand-name">AthenIQ</span>
                <span className="brand-sub">Registrar console</span>
              </span>
            </div>
            <Nav role={staff?.role} />
            <div className="sidebar-foot">
              {authEnabled() && staff ? (
                <>
                  <span className="small strong">{staff.name}</span>
                  <span className="tiny muted">
                    {ROLE_LABELS[staff.role]} · {staff.email}
                  </span>
                  <SignOutButton />
                </>
              ) : (
                <>
                  <span className="small">Innotel Labs · AthenIQ</span>
                  <span className="small">Course engine · Signara</span>
                </>
              )}
            </div>
          </aside>
          <main className="main">{children}</main>
        </div>
      </body>
    </html>
  );
}

function BrandMark() {
  return (
    <span className="brand-mark" aria-hidden="true">
      <svg width="20" height="20" viewBox="0 0 64 64" fill="none" stroke="currentColor" strokeWidth="4.6" strokeLinecap="round" strokeLinejoin="round">
        <path d="M32 14 L56 25 L32 36 L8 25 L32 14" />
        <path d="M22 38 L22 45 L32 50 L42 45 L42 38" />
        <path d="M56 25 L56 38" />
      </svg>
    </span>
  );
}
