import { PrivacyPolicy } from "@/components/PrivacyPolicy";
import { publicSiteOrigin } from "@/lib/branding";

export const dynamic = "force-dynamic";

export const metadata = { title: "Privacy policy — AthenIQ" };

/**
 * The App Store's privacy policy URL: https://registrar.atheniq.institute/privacy
 *
 * A plain public page, because a reviewer opens it with no account. Both this
 * path and `/_next/` are exempt from the console host's oauth2-proxy
 * (`deploy/compose/atheniq-sso.yml`), so the page and the bundle it hydrates
 * from arrive signed out. The words come from the shared component, so the
 * website can publish the same text without a second copy of it.
 */
export default function PrivacyPage() {
  return (
    <div className="content" style={{ maxWidth: 900 }}>
      <div className="stack-sm">
        <span className="eyebrow">Legal</span>
        <h1 style={{ fontSize: 30 }}>Privacy policy</h1>
      </div>
      <div style={{ marginTop: 16 }}>
        <PrivacyPolicy />
      </div>
      <p className="tiny muted" style={{ marginTop: 32 }}>
        <a href={`${publicSiteOrigin()}/`}>AthenIQ Institute</a>
      </p>
    </div>
  );
}
