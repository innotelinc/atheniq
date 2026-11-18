import Link from "next/link";
import { ApplicationForm } from "@/components/ApplicationForm";
import { getDb } from "@/lib/store";
import { termLabel, termOptions } from "@/lib/term";

export const dynamic = "force-dynamic";

export const metadata = { title: "Apply — AthenIQ Institute" };

/**
 * The application itself, on the public web.
 *
 * The site used to end its admissions pitch on a button that went nowhere. This
 * is the page that button points at: it collects the program, the term, a goals
 * statement and a transcript, and writes one record admissions can act on
 * instead of another email in an inbox.
 */
export default function ApplyPage() {
  const db = getDb();
  const programs = db.programs
    .filter((program) => program.status === "active")
    .map((program) => ({ id: program.id, name: program.name, credential: program.credential }));
  const terms = termOptions().map((term) => ({ value: term, label: termLabel(term) }));

  return (
    <div style={{ display: "grid", placeItems: "start center", minHeight: "64vh" }}>
      <div className="card" style={{ width: "100%", maxWidth: 680 }}>
        <div className="card-body stack">
          <span className="eyebrow">{db.settings.brand.siteName} · Admissions</span>
          <h1 style={{ fontSize: 24, margin: 0 }}>Apply to a program</h1>
          <p className="small muted" style={{ margin: 0 }}>
            One form: the program, the term you want to start, a short goals statement, and your
            transcript. A registrar reads every application and answers it — there is no test and no
            application fee.
          </p>
          <ApplicationForm programs={programs} terms={terms} />
          <p className="tiny muted" style={{ margin: 0 }}>
            Not ready to apply? <Link href="/verify">Check a credential</Link> or read the{" "}
            <Link href="/privacy">privacy policy</Link>. Questions go to{" "}
            <a href="mailto:admissions@atheniq.institute">admissions@atheniq.institute</a>.
          </p>
        </div>
      </div>
    </div>
  );
}
