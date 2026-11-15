import { fail, num, ok, str } from "@/lib/api";
import { currentActor, allowed } from "@/lib/current-staff";
import { mintSignaraKey, updateEnvFile, verifyKey } from "@/lib/rotation";
import { getDb, logActivity, mutate } from "@/lib/store";

export const dynamic = "force-dynamic";

/**
 * Mint a replacement Signara key, prove it works, then swap it in.
 *
 * The new key is verified against Signara *before* anything is written, so a
 * bad rotation never leaves the console unable to sign. The old key stays
 * active in Signara until a registrar revokes it there — deliberately, so a
 * failed deploy can still fall back.
 */
export async function POST(request: Request) {
  if (!(await allowed("settings"))) return fail("Only a registrar can rotate the Signara key.", 403);

  const body = (await request.json().catch(() => ({}))) as {
    confirm?: boolean;
    name?: string;
    expiresInDays?: number;
  };
  if (body.confirm !== true) {
    return fail("Rotation mints a new key and replaces the one in use. Send { confirm: true }.", 428);
  }

  const db = getDb();
  const days = Math.min(730, Math.max(7, num(body.expiresInDays, 365)));
  const name = str(body.name) || `AthenIQ console — rotated ${new Date().toISOString().slice(0, 10)}`;

  const minted = await mintSignaraKey(db.settings.signara, name, days);
  if (!minted.ok) return fail(minted.error, 502);

  const verified = await verifyKey(db.settings.signara, minted.key.apiKey);
  if (!verified.ok) {
    return fail(`${verified.detail} Nothing was changed — the current key is still in place.`, 502);
  }

  const actor = await currentActor();
  const saved = await mutate((store) => {
    store.settings.signara.apiKey = minted.key.apiKey;
    store.settings.signara.keyPrefix = minted.key.prefix;
    store.settings.signara.keyExpiresAt = minted.key.expiresAt;
    logActivity(store, "key.rotated", `Rotated the Signara key to ${minted.key.prefix}`, "settings", actor);
    return { prefix: minted.key.prefix, expiresAt: minted.key.expiresAt };
  });

  const env = updateEnvFile({
    SIGNARA_API_KEY: minted.key.apiKey,
    SIGNARA_KEY_EXPIRES_AT: minted.key.expiresAt ?? "",
  });

  return ok({
    ...saved,
    verification: verified.detail,
    envKeys: env.changed,
    note: "The previous key is still active in Signara. Revoke it there once an award has been signed with the new one.",
  });
}
