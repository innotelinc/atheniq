import type { Course, Enrollment } from "./types";
import { courseLessonCount, courseMinutes } from "./lesson-content";

/** The shapes the app renders, kept in one place so every screen agrees. */
export interface Progress {
  total: number;
  done: number;
  percent: number;
  nextLessonId: string | null;
  nextLessonTitle: string | null;
}

export function progressOf(course: Course, enrollment?: Enrollment | null): Progress {
  const total = courseLessonCount(course);
  const done = enrollment
    ? course.modules.reduce(
        (sum, module) =>
          sum + module.lessons.filter((lesson) => enrollment.completedLessonIds.includes(lesson.id)).length,
        0,
      )
    : 0;
  const next = course.modules
    .flatMap((module) => module.lessons.map((lesson) => ({ module, lesson })))
    .find(({ lesson }) => !enrollment?.completedLessonIds.includes(lesson.id));
  return {
    total,
    done,
    percent: total ? Math.round((done / total) * 100) : 0,
    nextLessonId: next?.lesson.id ?? null,
    nextLessonTitle: next?.lesson.title ?? null,
  };
}

/** Seed titles often read "ACCT201 — Financial Accounting"; the card prints the code itself. */
function displayTitle(course: Course): string {
  const prefix = `${course.code} — `;
  if (course.title.startsWith(prefix)) return course.title.slice(prefix.length).trim();
  return course.title;
}

export function catalogCard(course: Course, programNames: Map<string, string>) {
  return {
    id: course.id,
    code: course.code,
    key: course.key,
    title: displayTitle(course),
    summary: course.summary,
    credits: course.credits,
    level: course.level,
    department: course.department,
    minutes: courseMinutes(course),
    lessons: courseLessonCount(course),
    modules: course.modules.length,
    price: course.price,
    programs: course.programIds.map((id) => programNames.get(id)).filter(Boolean),
    outcome: course.outcomes[0] ?? course.summary,
  };
}

export function courseDetail(course: Course, enrollment: Enrollment | null, programNames: Map<string, string>) {
  return {
    ...catalogCard(course, programNames),
    description: course.description,
    outcomes: course.outcomes,
    audience: course.audience,
    prerequisites: course.prerequisites,
    grading: course.grading,
    modules: course.modules.map((module) => ({
      id: module.id,
      title: module.title,
      summary: module.summary,
      assessment: module.assessment,
      lessons: module.lessons.map((lesson) => ({
        id: lesson.id,
        title: lesson.title,
        type: lesson.type,
        minutes: lesson.minutes,
        done: Boolean(enrollment?.completedLessonIds.includes(lesson.id)),
      })),
    })),
    enrollment: enrollment
      ? {
          id: enrollment.id,
          enrolledAt: enrollment.enrolledAt,
          completedAt: enrollment.completedAt,
          access: enrollment.access ?? "open",
          progress: progressOf(course, enrollment),
        }
      : null,
    progress: progressOf(course, enrollment),
  };
}
