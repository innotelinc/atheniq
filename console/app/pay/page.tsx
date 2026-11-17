import Link from "next/link";
import { getDb } from "@/lib/store";
import { money } from "@/lib/mobile-commerce";
import { LEGAL_EMAIL } from "@/lib/legal";
import { publicSiteOrigin } from "@/lib/branding";

export const dynamic = "force-dynamic";

export const metadata = { title: "Pay for your course — AthenIQ" };

/**
 * The page CHECKOUT_URL points at.
 *
 * The console has no card processing of its own, so this is the hand-off: it
 * states the amount and the reference, tells the learner how the school takes
 * money, and says plainly that the course opens once the registrar confirms.
 * The reference is the only thing that ties a transfer back to an enrollment.
 */
export default async function PayPage({
  searchParams,
}: {
  searchParams: Promise<{ ref?: string; amount?: string; course?: string }>;
}) {
  const params = await searchParams;
  const reference = (params.ref ?? "").trim();
  const amountCents = Number(params.amount ?? 0);
  const courseKey = (params.course ?? "").trim();
  const db = getDb();
  const course = courseKey ? db.courses.find((item) => item.key === courseKey) : undefined;
  const brand = db.settings.brand;
  const amount = Number.isFinite(amountCents) && amountCents > 0 ? money(amountCents) : null;

  return (
    <div style={{ display: "grid", placeItems: "center", minHeight: "64vh" }}>
      <div className="card" style={{ width: "100%", maxWidth: 520 }}>
        <div className="card-body stack">
          <span className="eyebrow">{brand.siteName} · Course payment</span>
          <h1 style={{ fontSize: 24, margin: 0 }}>{course ? course.title : "Pay for your course"}</h1>

          {reference ? (
            <>
              <p className="muted" style={{ margin: 0 }}>
                Quote this reference with your payment — it is how the registrar matches the money to
                your enrollment.
              </p>
              <div
                className="card"
                style={{ background: "var(--surface-2)", padding: 16, textAlign: "center" }}
              >
                <div className="small muted" style={{ letterSpacing: 1, textTransform: "uppercase" }}>
                  Reference
                </div>
                <div style={{ fontSize: 22, fontWeight: 700, letterSpacing: 1, marginTop: 4 }}>
                  {reference}
                </div>
                {amount ? (
                  <div className="muted" style={{ marginTop: 6 }}>
                    Amount due: <strong style={{ color: "var(--ink)" }}>{amount}</strong>
                  </div>
                ) : null}
              </div>

              <div className="stack-sm">
                <strong>How to pay</strong>
                <p className="muted" style={{ margin: 0 }}>
                  Pay by the method the registrar gave you — bank transfer to the institute account,
                  or the school&apos;s card link if one was sent. Include the reference exactly as
                  shown. {amount ? `The amount is ${amount}.` : ""}
                </p>
              </div>

              <div className="stack-sm">
                <strong>What happens next</strong>
                <ol className="muted" style={{ margin: 0, paddingLeft: 18 }}>
                  <li>Pay and keep the receipt.</li>
                  <li>
                    In the app, open the course and send the claim with this reference (quote your
                    receipt note).
                  </li>
                  <li>The registrar confirms it — usually the same working day — and the lessons open.</li>
                </ol>
              </div>

              <p className="small muted" style={{ margin: 0 }}>
                Already claimed? Nothing else is needed; the app shows the course as locked until the
                registrar confirms. Questions about this payment:{" "}
                <a href={`mailto:${LEGAL_EMAIL}`}>{LEGAL_EMAIL}</a>.
              </p>
            </>
          ) : (
            <p className="muted" style={{ margin: 0 }}>
              This link is missing its payment reference. Open the course in the app and choose
              &ldquo;Pay and enroll&rdquo; to get a fresh one.
            </p>
          )}

          <div style={{ display: "flex", gap: 10, flexWrap: "wrap" }}>
            <a className="btn" href={`${publicSiteOrigin()}/`}>
              AthenIQ Institute
            </a>
            {course ? (
              <Link className="btn" href={`/verify`}>
                Verify a credential
              </Link>
            ) : null}
          </div>
        </div>
      </div>
    </div>
  );
}
