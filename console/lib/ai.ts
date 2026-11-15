import { normaliseGrading } from "./curriculum";
import type { CourseDraft, CourseModule, LessonType, Settings } from "./types";

/**
 * Course generation against an OpenAI-compatible gateway (OmniRoute in the
 * AthenIQ stack, or any provider that speaks /v1/chat/completions).
 *
 * The model is never trusted with the shape: every response is coerced back
 * into CourseDraft and checked. Anything the gateway cannot supply — no key,
 * a timeout, malformed JSON — returns null so the caller can fall back to the
 * deterministic curriculum engine.
 */

export interface GatewayResult {
  draft: CourseDraft | null;
  error: string | null;
  raw?: unknown;
}

const SYSTEM_PROMPT = `You are the curriculum office of AthenIQ Institute, an online university.
Write one complete, teachable course. Return ONLY a JSON object, no prose, with this shape:
{
  "title": string,                      // no course code, max 80 chars
  "summary": string,                    // 2-3 sentences, 200-400 chars
  "description": string,                // 2 short paragraphs
  "outcomes": string[],                 // 4-6 measurable outcomes
  "audience": string,
  "prerequisites": string[],            // empty array when there are none
  "level": 100|200|300|400,
  "credits": number,                    // 1-6
  "department": string,
  "modules": [                          // 4-6 modules, in teaching order
    {
      "title": string,
      "summary": string,
      "assessment": string,
      "lessons": [{"title": string, "type": "reading"|"video"|"lab"|"discussion"|"quiz"|"project"|"exam", "minutes": number}]
    }
  ],
  "grading": [{"component": string, "weight": number}]   // weights sum to 100
}
Rules: each module has 3-5 lessons; the last module ends in a graded project and a proctored exam;
write for adults with jobs; be concrete, never generic filler; do not include markdown.`;

function chatEndpoint(baseUrl: string): string {
  const base = baseUrl.replace(/\/+$/, "");
  if (/\/chat\/completions$/.test(base)) return base;
  if (/\/v\d+$/.test(base)) return `${base}/chat/completions`;
  return `${base}/v1/chat/completions`;
}

export function modelsEndpoint(baseUrl: string): string {
  const base = baseUrl.replace(/\/+$/, "");
  if (/\/v\d+$/.test(base)) return `${base}/models`;
  return `${base}/v1/models`;
}

async function chat(
  settings: Settings["ai"],
  messages: { role: "system" | "user" | "assistant"; content: string }[],
  timeoutMs = 60_000,
): Promise<{ ok: boolean; content: string | null; error: string | null }> {
  if (!settings.baseUrl) return { ok: false, content: null, error: "No model gateway URL configured." };
  if (!settings.apiKey) return { ok: false, content: null, error: "No model gateway API key configured." };

  try {
    const response = await fetch(chatEndpoint(settings.baseUrl), {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Authorization: `Bearer ${settings.apiKey}`,
      },
      body: JSON.stringify({
        model: settings.model || "gpt-4o-mini",
        messages,
        temperature: 0.5,
        response_format: { type: "json_object" },
      }),
      signal: AbortSignal.timeout(timeoutMs),
    });

    const text = await response.text();
    if (!response.ok) {
      return { ok: false, content: null, error: `Gateway returned HTTP ${response.status}: ${text.slice(0, 240)}` };
    }
    let payload: unknown;
    try {
      payload = JSON.parse(text);
    } catch {
      return { ok: false, content: null, error: "The gateway did not return JSON." };
    }
    const content = (payload as { choices?: { message?: { content?: string } }[] }).choices?.[0]
      ?.message?.content;
    if (!content) return { ok: false, content: null, error: "The gateway returned no message content." };
    return { ok: true, content, error: null };
  } catch (error) {
    const message = error instanceof Error ? error.message : String(error);
    return { ok: false, content: null, error: `Model gateway unreachable: ${message}` };
  }
}

function asString(value: unknown, fallback = ""): string {
  return typeof value === "string" ? value.trim() : fallback;
}

function asStringArray(value: unknown): string[] {
  if (!Array.isArray(value)) return [];
  return value.map((v) => asString(v)).filter(Boolean);
}

const LESSON_TYPES: LessonType[] = [
  "reading",
  "video",
  "lab",
  "discussion",
  "quiz",
  "project",
  "exam",
];

function coerceLessonType(value: unknown): LessonType {
  const raw = asString(value).toLowerCase() as LessonType;
  return LESSON_TYPES.includes(raw) ? raw : "reading";
}

/** Force whatever the model returned into a valid CourseDraft, or null. */
export function coerceDraft(raw: unknown, fallback: CourseDraft): CourseDraft | null {
  if (!raw || typeof raw !== "object") return null;
  const data = raw as Record<string, unknown>;
  const rawModules = Array.isArray(data.modules) ? data.modules : [];
  if (!rawModules.length) return null;

  const modules: CourseModule[] = rawModules.slice(0, 8).map((entry, i) => {
    const module = (entry ?? {}) as Record<string, unknown>;
    const lessons = Array.isArray(module.lessons) ? module.lessons : [];
    return {
      id: `m${i + 1}`,
      title: asString(module.title, `Module ${i + 1}`),
      summary: asString(module.summary, ""),
      assessment: asString(module.assessment, `Module ${i + 1} assessment`),
      lessons: lessons.slice(0, 8).map((lesson, j) => {
        const l = (lesson ?? {}) as Record<string, unknown>;
        const minutes = Number(l.minutes);
        return {
          id: `m${i + 1}-l${j + 1}`,
          title: asString(l.title, `Lesson ${j + 1}`),
          type: coerceLessonType(l.type),
          minutes: Number.isFinite(minutes) && minutes > 0 ? Math.min(360, Math.round(minutes)) : 45,
        };
      }),
    };
  });

  if (modules.some((m) => m.lessons.length === 0)) return null;

  const levelRaw = Number(data.level);
  const level = ([100, 200, 300, 400] as const).includes(levelRaw as 100)
    ? (levelRaw as 100 | 200 | 300 | 400)
    : fallback.level;
  const creditsRaw = Number(data.credits);
  const credits = Number.isFinite(creditsRaw) ? Math.min(6, Math.max(1, Math.round(creditsRaw))) : fallback.credits;

  const gradingRaw = Array.isArray(data.grading) ? data.grading : [];
  const grading = gradingRaw
    .map((g) => {
      const entry = (g ?? {}) as Record<string, unknown>;
      return { component: asString(entry.component), weight: Number(entry.weight) || 0 };
    })
    .filter((g) => g.component && g.weight > 0);

  return {
    code: fallback.code,
    title: asString(data.title, fallback.title).slice(0, 90),
    summary: asString(data.summary, fallback.summary),
    description: asString(data.description, fallback.description),
    outcomes: asStringArray(data.outcomes).length ? asStringArray(data.outcomes) : fallback.outcomes,
    audience: asString(data.audience, fallback.audience),
    prerequisites: Array.isArray(data.prerequisites) ? asStringArray(data.prerequisites) : fallback.prerequisites,
    level,
    credits,
    department: asString(data.department, fallback.department),
    modules,
    grading: normaliseGrading(grading.length ? grading : fallback.grading),
  };
}

function parseJsonObject(content: string): unknown {
  const trimmed = content.trim().replace(/^```(?:json)?/i, "").replace(/```$/, "").trim();
  try {
    return JSON.parse(trimmed);
  } catch {
    const start = trimmed.indexOf("{");
    const end = trimmed.lastIndexOf("}");
    if (start >= 0 && end > start) {
      try {
        return JSON.parse(trimmed.slice(start, end + 1));
      } catch {
        return null;
      }
    }
    return null;
  }
}

export async function generateWithModel(
  settings: Settings["ai"],
  input: { idea: string; audience: string; level: number; credits: number; department: string },
  fallback: CourseDraft,
): Promise<GatewayResult> {
  const user = [
    `Idea: ${input.idea}`,
    `Audience: ${input.audience}`,
    `Level: ${input.level}`,
    `Credits: ${input.credits}`,
    `Department: ${input.department}`,
    `Course code (use as-is, do not put it in the title): ${fallback.code}`,
  ].join("\n");

  const result = await chat(settings, [
    { role: "system", content: SYSTEM_PROMPT },
    { role: "user", content: user },
  ]);
  if (!result.ok || !result.content) return { draft: null, error: result.error };
  const parsed = parseJsonObject(result.content);
  const draft = coerceDraft(parsed, fallback);
  if (!draft) return { draft: null, error: "The model returned a draft that did not match the course schema.", raw: parsed };
  return { draft, error: null, raw: parsed };
}

export async function reviseWithModel(
  settings: Settings["ai"],
  draft: CourseDraft,
  instruction: string,
): Promise<GatewayResult> {
  const user = [
    "Here is the current course as JSON:",
    JSON.stringify(draft),
    "",
    `Revision instruction: ${instruction}`,
    "",
    "Return the complete revised course in the same JSON shape. Keep everything the instruction does not ask you to change.",
  ].join("\n");

  const result = await chat(settings, [
    { role: "system", content: SYSTEM_PROMPT },
    { role: "user", content: user },
  ]);
  if (!result.ok || !result.content) return { draft: null, error: result.error };
  const parsed = parseJsonObject(result.content);
  const next = coerceDraft(parsed, draft);
  if (!next) return { draft: null, error: "The model returned a revision that did not match the course schema.", raw: parsed };
  return { draft: next, error: null, raw: parsed };
}

export interface ProbeResult {
  ok: boolean;
  detail: string;
  models: string[];
}

export async function probeModel(settings: Settings["ai"]): Promise<ProbeResult> {
  if (!settings.baseUrl) return { ok: false, detail: "No base URL configured.", models: [] };
  try {
    const headers: Record<string, string> = {};
    if (settings.apiKey) headers.Authorization = `Bearer ${settings.apiKey}`;
    const response = await fetch(modelsEndpoint(settings.baseUrl), {
      headers,
      signal: AbortSignal.timeout(8000),
    });
    const text = await response.text();
    if (response.status === 401 || response.status === 403) {
      return { ok: false, detail: `Gateway reachable but rejected the key (HTTP ${response.status}).`, models: [] };
    }
    if (!response.ok) {
      return { ok: false, detail: `Gateway answered HTTP ${response.status}.`, models: [] };
    }
    let models: string[] = [];
    try {
      const parsed = JSON.parse(text) as { data?: { id?: string }[] };
      models = (parsed.data ?? []).map((m) => m.id ?? "").filter(Boolean).slice(0, 12);
    } catch {
      /* some gateways answer /models with plain text */
    }
    return {
      ok: Boolean(settings.apiKey),
      detail: settings.apiKey
        ? `Gateway reachable${models.length ? ` — ${models.length} models advertised` : ""}.`
        : "Gateway reachable, but no API key is set — generation will use the rules engine.",
      models,
    };
  } catch (error) {
    const message = error instanceof Error ? error.message : String(error);
    return { ok: false, detail: `Could not reach the gateway: ${message}`, models: [] };
  }
}
