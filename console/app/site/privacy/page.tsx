import type { Metadata } from "next";
import { PrivacyPolicy } from "@/components/PrivacyPolicy";
import { brandOf } from "@/lib/branding";
import { getDb } from "@/lib/store";

export const dynamic = "force-dynamic";

/** The policy under the storefront, named so a tab does not read as the landing page. */
export async function generateMetadata(): Promise<Metadata> {
  const brand = brandOf(getDb().settings);
  return { title: `Privacy policy — ${brand.siteName}` };
}

/** The policy at /privacy on the public site host. */
export default function SitePrivacyPage() {
  return (
    <section className="site-section narrow">
      <header className="section-head">
        <div>
          <div className="eyebrow">Legal</div>
          <h1>Privacy policy</h1>
        </div>
      </header>
      <PrivacyPolicy />
    </section>
  );
}
