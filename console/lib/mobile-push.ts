import type { Database } from "./types";

/**
 * Expo push, sent without a dependency: one HTTPS POST to Expo's push service.
 *
 * A push is a courtesy, never a transaction — a failure is recorded and the
 * award still stands. Tokens come from the device at sign-in; a token Expo
 * rejects is dropped so the record does not keep trying it.
 */
const ENDPOINT = process.env.EXPO_PUSH_URL || "https://exp.host/--/api/v2/push/send";

export interface PushMessage {
  to: string;
  title: string;
  body: string;
  data?: Record<string, unknown>;
}

export async function sendPush(messages: PushMessage[]): Promise<{ sent: number; rejected: string[] }> {
  const usable = messages.filter((message) => message.to.startsWith("ExponentPushToken[") || message.to.startsWith("ExpoPushToken["));
  if (!usable.length) return { sent: 0, rejected: [] };
  try {
    const response = await fetch(ENDPOINT, {
      method: "POST",
      headers: { "content-type": "application/json", accept: "application/json" },
      body: JSON.stringify(usable.map((message) => ({ ...message, sound: "default" }))),
    });
    if (!response.ok) return { sent: 0, rejected: [] };
    const payload = (await response.json().catch(() => ({}))) as {
      data?: { status?: string; details?: { error?: string } }[];
    };
    const tickets = Array.isArray(payload.data) ? payload.data : [];
    const rejected: string[] = [];
    tickets.forEach((ticket, index) => {
      if (ticket?.status === "error" && ticket.details?.error === "DeviceNotRegistered") {
        const token = usable[index]?.to;
        if (token) rejected.push(token);
      }
    });
    return { sent: tickets.filter((ticket) => ticket?.status === "ok").length, rejected };
  } catch {
    // Offline or Expo is down; the award is unaffected.
    return { sent: 0, rejected: [] };
  }
}

/** Everyone holding a device token for this person, newest token first. */
export function pushTargets(db: Database, learnerId: string): string[] {
  const learner = db.learners.find((item) => item.id === learnerId);
  return learner?.pushToken ? [learner.pushToken] : [];
}
