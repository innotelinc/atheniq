import { slugify } from "./seed";
import type { Course, CourseDraft, CourseModule, CoursePrice, Database, GradingComponent, LessonType } from "./types";
import { normaliseGrading } from "./curriculum";

const PREFIX_BY_DEPARTMENT: Record<string, string> = {
  Business: "BUS",
  "Criminal Justice": "CJ",
  Nursing: "NUR",
  "Applied AI": "FAI",
  Data: "DATA",
  "Information Technology": "ITSP",
  "Teaching & Learning": "MAIC",
  "Health Administration": "HCA",
  "General Studies": "GEN",
  Platform: "PLAT",
};

export function departmentPrefix(department: string): string {
  return PREFIX_BY_DEPARTMENT[department] ?? (department.replace(/[^A-Za-z]/g, "").slice(0, 4).toUpperCase() || "GEN");
}

export function normaliseCode(input: string): string {
  return input.trim().toUpperCase().replace(/[^A-Z0-9]/g, "").slice(0, 12);
}

/** Next free catalog number for a department, continuing its existing block. */
export function nextCourseCode(db: Database, department: string): string {
  const prefix = departmentPrefix(department);
  const numbers = db.courses
    .filter((course) => course.code.startsWith(prefix))
    .map((course) => Number(course.code.slice(prefix.length)))
    .filter((n) => Number.isFinite(n));
  const max = numbers.length ? Math.max(...numbers) : 199;
  let next = Math.max(201, max + 1);
  while (db.courses.some((course) => course.code === `${prefix}${next}`)) next += 1;
  return `${prefix}${next}`;
}

const LEVELS = [100, 200, 300, 400, 500] as const;

export function coerceLevel(value: unknown, fallback: Course["level"] = 100): Course["level"] {
  const n = Number(value);
  return (LEVELS as readonly number[]).includes(n) ? (n as Course["level"]) : fallback;
}

const LESSON_TYPES: LessonType[] = ["reading", "video", "lab", "discussion", "quiz", "project", "exam"];

export function coerceModules(value: unknown): CourseModule[] {
  if (!Array.isArray(value)) return [];
  return value.slice(0, 12).map((raw, i) => {
    const module = (raw ?? {}) as Record<string, unknown>;
    const lessons = Array.isArray(module.lessons) ? module.lessons : [];
    return {
      id: `m${i + 1}`,
      title: String(module.title ?? `Module ${i + 1}`).trim() || `Module ${i + 1}`,
      summary: String(module.summary ?? ""),
      assessment: String(module.assessment ?? ""),
      lessons: lessons.slice(0, 10).map((rawLesson, j) => {
        const lesson = (rawLesson ?? {}) as Record<string, unknown>;
        const type = String(lesson.type ?? "reading").toLowerCase() as LessonType;
        return {
          id: `m${i + 1}-l${j + 1}`,
          title: String(lesson.title ?? `Lesson ${j + 1}`).trim() || `Lesson ${j + 1}`,
          type: LESSON_TYPES.includes(type) ? type : "reading",
          minutes: Math.max(5, Math.min(360, Number(lesson.minutes) || 45)),
        };
      }),
    };
  });
}

export function coerceGrading(value: unknown, fallback: GradingComponent[]): GradingComponent[] {
  if (!Array.isArray(value)) return fallback;
  const grading = value
    .map((raw) => {
      const entry = (raw ?? {}) as Record<string, unknown>;
      return { component: String(entry.component ?? "").trim(), weight: Number(entry.weight) || 0 };
    })
    .filter((g) => g.component && g.weight > 0);
  return grading.length ? normaliseGrading(grading) : fallback;
}

export interface CreateCourseInput {
  code: string;
  title: string;
  term: string;
  credits: number;
  level: Course["level"];
  department: string;
  summary: string;
  description?: string;
  outcomes?: string[];
  audience?: string;
  prerequisites?: string[];
  modules?: CourseModule[];
  grading?: GradingComponent[];
  price?: CoursePrice;
  programIds?: string[];
  trackIds?: string[];
  generationId?: string | null;
  org?: string;
}

const DEFAULT_GRADING: GradingComponent[] = [
  { component: "Participation and seminars", weight: 10 },
  { component: "Labs and short exercises", weight: 30 },
  { component: "Project work", weight: 30 },
  { component: "Proctored final examination", weight: 30 },
];

export function buildCourse(input: CreateCourseInput, db: Database): Course {
  const code = normaliseCode(input.code);
  const term = input.term || db.settings.defaultTerm;
  const org = input.org || db.settings.orgShort || "InnotelLabs";
  const now = new Date().toISOString();
  const title = input.title.trim();

  return {
    id: `${code}-${term}-${Math.random().toString(36).slice(2, 6)}`,
    code,
    term,
    title: input.title.startsWith(`${code} —`) ? title : `${code} — ${title}`,
    slug: slugify(title.replace(`${code} — `, "")),
    key: `course-v1:${org}+${code}+${term}`,
    org,
    credits: Math.min(6, Math.max(1, Math.round(input.credits || db.settings.creditsPerCourse || 3))),
    level: input.level,
    department: input.department || "General Studies",
    programIds: input.programIds ?? [],
    trackIds: input.trackIds ?? [],
    summary: input.summary.trim(),
    description: (input.description ?? input.summary).trim(),
    outcomes: input.outcomes?.length ? input.outcomes : [],
    audience: input.audience ?? "",
    prerequisites: input.prerequisites ?? [],
    modules: input.modules ?? [],
    grading: coerceGrading(input.grading, DEFAULT_GRADING),
    price: input.price ?? { plan: "premium", amountCents: null },
    status: "draft",
    image: `/static/atheniq/images/courses/${code}.jpg`,
    generationId: input.generationId ?? null,
    publishedAt: null,
    createdAt: now,
    updatedAt: now,
  };
}

export function courseFromDraft(
  draft: CourseDraft,
  db: Database,
  options: { code?: string; term?: string; price?: CoursePrice; programIds?: string[]; trackIds?: string[]; generationId?: string | null },
): Course {
  const code = normaliseCode(options.code || draft.code || nextCourseCode(db, draft.department));
  return buildCourse(
    {
      code,
      title: draft.title,
      term: options.term || db.settings.defaultTerm,
      credits: draft.credits,
      level: coerceLevel(draft.level),
      department: draft.department,
      summary: draft.summary,
      description: draft.description,
      outcomes: draft.outcomes,
      audience: draft.audience,
      prerequisites: draft.prerequisites,
      modules: coerceModules(draft.modules),
      grading: draft.grading,
      price: options.price,
      programIds: options.programIds,
      trackIds: options.trackIds,
      generationId: options.generationId ?? null,
    },
    db,
  );
}

export function titleFor(course: Course): string {
  return course.title.includes("—") ? course.title.split("—").slice(1).join("—").trim() : course.title;
}
