import { redirect } from "next/navigation";
import { cookies } from "next/headers";
import { CHALLENGE_COOKIE, LOGIN_NEXT_COOKIE, readLoginChallenge, safeNext } from "@/lib/session";
import { getDb } from "@/lib/store";
import { TotpChallenge } from "@/components/TotpChallenge";

export const dynamic = "force-dynamic";

export default async function TotpPage() {
  const jar = await cookies();
  const challenge = await readLoginChallenge(jar.get(CHALLENGE_COOKIE)?.value);
  if (!challenge) redirect("/login?error=expired");

  const db = getDb();
  const staff = db.staff.find((member) => member.id === challenge.staffId && !member.disabled);
  if (!staff) redirect("/login?error=expired");

  const next = safeNext(jar.get(LOGIN_NEXT_COOKIE)?.value);
  const setup = !staff.totp?.enabled;

  return (
    <div style={{ display: "grid", placeItems: "center", minHeight: "64vh" }}>
      <div className="card" style={{ width: "100%", maxWidth: 520 }}>
        <div className="card-body stack">
          <span className="eyebrow">{db.settings.brand.siteName}</span>
          <h1 style={{ fontSize: 22, margin: 0 }}>{setup ? "Set up two-factor" : "Two-factor code"}</h1>
          <TotpChallenge setup={setup} name={staff.name} email={staff.email} next={next} />
        </div>
      </div>
    </div>
  );
}
