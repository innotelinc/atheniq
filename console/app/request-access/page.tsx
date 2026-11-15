import Link from "next/link";
import { getDb } from "@/lib/store";
import { AccessRequestForm } from "@/components/AccessRequestForm";

export const dynamic = "force-dynamic";

/** Public: anyone on a registered domain can ask for an account. */
export default function RequestAccessPage() {
  const db = getDb();
  const brand = db.settings.brand;

  return (
    <div style={{ display: "grid", placeItems: "center", minHeight: "64vh" }}>
      <div className="card" style={{ width: "100%", maxWidth: 520 }}>
        <div className="card-body stack">
          <span className="eyebrow">{brand.siteName}</span>
          <h1 style={{ fontSize: 22, margin: 0 }}>Request staff access</h1>
          <p className="small muted" style={{ margin: 0 }}>
            Staff accounts are limited to the school&apos;s registered domains. A registrar reviews every request
            before the account is opened.
          </p>
          <AccessRequestForm domains={db.settings.auth.allowedDomains} />
          <p className="tiny muted" style={{ margin: 0 }}>
            Already have an account? <Link href="/login">Sign in</Link>.
          </p>
        </div>
      </div>
    </div>
  );
}
