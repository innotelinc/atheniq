/**
 * What the running Open edX site says about its courses.
 *
 * The console is the academic record and the LMS delivers the courseware, so the
 * portal needs one fact from the LMS that the console cannot know: whether a
 * course is actually live there right now. `GET /api/courses/v1/courses/` is the
 * one endpoint that answers without a token, which is deliberate — the portal
 * must not hold a learner's LMS credentials just to draw a status badge.
 *
 * Every failure here is swallowed on purpose. The LMS is a separate service on a
 * separate host; if it is restarting, the portal still has to render the
 * student's records rather than a 500.
 */

export interface LiveCourse {
  id: string;
  name: string;
  start: string | null;
  end: string | null;
}

/** Long enough for a cold LMS, short enough that a dead one does not stall a page. */
const TIMEOUT_MS = 4000;

/** The API caps one page at 100; more courses than that are reported as unknown. */
const PAGE_SIZE = 100;

function root(baseUrl: string): string {
  return (baseUrl || "").trim().replace(/\/+$/, "");
}

export async function liveCourses(baseUrl: string): Promise<Map<string, LiveCourse>> {
  const live = new Map<string, LiveCourse>();
  const base = root(baseUrl);
  if (!base) return live;
  try {
    const response = await fetch(`${base}/api/courses/v1/courses/?page_size=${PAGE_SIZE}`, {
      headers: { accept: "application/json" },
      signal: AbortSignal.timeout(TIMEOUT_MS),
      cache: "no-store",
    });
    if (!response.ok) return live;
    const payload = (await response.json()) as {
      results?: { id?: string; name?: string; start?: string | null; end?: string | null }[];
    };
    for (const course of payload.results ?? []) {
      if (!course?.id) continue;
      live.set(course.id, {
        id: course.id,
        name: course.name ?? course.id,
        start: course.start ?? null,
        end: course.end ?? null,
      });
    }
  } catch {
    return live;
  }
  return live;
}

/** The learner's own page inside the courseware, not the public catalog entry. */
export function coursewareUrl(baseUrl: string, courseKey: string): string | null {
  const base = root(baseUrl);
  if (!base || !courseKey) return null;
  return `${base}/courses/${courseKey}/course/`;
}
