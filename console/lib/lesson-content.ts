import type { Course, CourseModule, Lesson, LessonType } from "./types";

/**
 * What a learner actually reads.
 *
 * The catalog carries lesson titles, types and minutes — the OLX package is the
 * full text — so the app composes each lesson from the course the registrar
 * wrote: its outcomes, the module summary, the lesson's own place in the
 * sequence. Nothing here invents facts about the subject; it frames the
 * material and gives the learner something to do with it.
 */
export type BlockKind = "lede" | "heading" | "paragraph" | "list" | "quote" | "callout" | "steps";

export interface ContentBlock {
  kind: BlockKind;
  text?: string;
  items?: string[];
  label?: string;
}

export interface LessonContent {
  id: string;
  title: string;
  type: LessonType;
  minutes: number;
  moduleTitle: string;
  objectives: string[];
  blocks: ContentBlock[];
  /** The written task, when the lesson cannot be auto-graded. */
  prompt?: string;
  /** Quiz, exam, project and discussion lessons are marked done by writing. */
  needsResponse: boolean;
}

const WRITTEN: LessonType[] = ["quiz", "exam", "project", "discussion"];

export function needsResponse(type: LessonType): boolean {
  return WRITTEN.includes(type);
}

function pick<T>(items: T[], index: number): T | undefined {
  if (!items.length) return undefined;
  return items[index % items.length];
}

/** Rotates the framing so consecutive lessons do not open the same way. */
const OPENERS = [
  "This lesson sits inside {module}, and it exists for one reason: {goal}",
  "Before the next part of {module} makes sense, {goal}",
  "The work in {module} assumes you can already do this: {goal}",
  "Treat this lesson as the practical half of {module}. Its job: {goal}",
];

const HEADINGS = [
  "Where this fits",
  "The idea, plainly",
  "What good looks like",
  "Worked through",
  "Common mistakes",
  "Put it to use",
];

function goalFor(course: Course, lesson: Lesson): string {
  const outcome = pick(course.outcomes, lesson.title.length);
  if (outcome) return `${outcome.replace(/^[A-Z]/, (c) => c.toLowerCase()).replace(/\.$/, "")}.`;
  return `${lesson.title.toLowerCase()} well enough to rely on it under pressure.`;
}

/**
 * The lesson body. Deterministic: the same lesson always reads the same, so a
 * learner can leave and come back to the paragraph they were on.
 */
export function buildLesson(
  course: Course,
  module: CourseModule,
  lesson: Lesson,
  position: { index: number; total: number },
): LessonContent {
  const goal = goalFor(course, lesson);
  const moduleName = module.title.toLowerCase();
  const opener = pick(OPENERS, position.index)!.replace("{module}", moduleName).replace("{goal}", goal);
  const outcomes = module.lessons
    .map((item, index) => pick(course.outcomes, index + position.index))
    .filter((value): value is string => Boolean(value))
    .slice(0, 3);

  const blocks: ContentBlock[] = [
    { kind: "lede", text: opener },
    {
      kind: "callout",
      label: `Lesson ${position.index + 1} of ${position.total}`,
      text: `${lesson.type === "reading" ? "Reading" : lesson.type === "video" ? "Watch and read" : lesson.type === "lab" ? "Hands-on lab" : lesson.type === "project" ? "Project" : lesson.type === "discussion" ? "Discussion" : lesson.type === "exam" ? "Final exam" : "Knowledge check"} · about ${lesson.minutes} minutes`,
    },
    { kind: "heading", text: pick(HEADINGS, position.index)! },
    {
      kind: "paragraph",
      text: `${module.summary} This lesson narrows that down to ${lesson.title.toLowerCase()}, which is where ${course.audience.toLowerCase()} usually spend the most time.`,
    },
    {
      kind: "paragraph",
      text: `In ${course.code} the standard is practical: you should be able to ${goal.replace(/\.$/, "")} without looking it up, and to explain the choice to someone who has to live with the consequence. ${module.assessment} is where that gets tested at the end of the module.`,
    },
    {
      kind: "heading",
      text: "What you should be able to do",
    },
    {
      kind: "list",
      items: outcomes.length
        ? outcomes
        : [
            `Explain ${lesson.title.toLowerCase()} in plain language.`,
            `Apply it to a case from your own work.`,
            `Notice when it is being done badly, and say why.`,
          ],
    },
    { kind: "heading", text: "Working through it" },
    {
      kind: "steps",
      items: [
        `Start from what you already do: describe one real situation involving ${lesson.title.toLowerCase()}.`,
        `Name the decision that mattered — not the paperwork, the decision.`,
        `Apply the module's standard, and write down where your instinct and the standard disagree.`,
        `Decide which one you would defend, and on what evidence.`,
      ],
    },
    {
      kind: "quote",
      text: `“${pick(course.outcomes, position.index + 2) ?? course.summary}”`,
    },
    {
      kind: "paragraph",
      text: `The mistake this lesson is trying to prevent is treating ${lesson.title.toLowerCase()} as a step to get past. ${course.department} work is mostly judgement applied consistently; the technique is the easy part. ${
        course.prerequisites.length ? `It builds on ${course.prerequisites[0].toLowerCase()}, so if that feels shaky, revisit it before the assessment.` : ""
      }`,
    },
    {
      kind: "callout",
      label: "Before you mark this complete",
      text: `Write two or three sentences: what you will do differently in the next week because of this lesson. That is the question the assessment asks in a harder form.`,
    },
  ];

  const prompt = needsResponse(lesson.type)
    ? lesson.type === "project"
      ? `Deliver the project for “${lesson.title}”. Describe what you built or produced, the decisions you made, and what you would change next time (at least 120 words).`
      : lesson.type === "discussion"
        ? `Post your answer to “${lesson.title}” and one reply you would give a colleague who disagreed (at least 100 words).`
        : lesson.type === "exam"
          ? `Final assessment: answer “${lesson.title}” in full, using the module's standard and one example from your own work (at least 150 words).`
          : `Knowledge check for “${lesson.title}”: explain the idea, apply it to one example, and state the limit of when it does not apply (at least 80 words).`
    : undefined;

  return {
    id: lesson.id,
    title: lesson.title,
    type: lesson.type,
    minutes: lesson.minutes,
    moduleTitle: module.title,
    objectives: outcomes,
    blocks,
    prompt,
    needsResponse: needsResponse(lesson.type),
  };
}

export function courseLessonCount(course: Course): number {
  return course.modules.reduce((sum, module) => sum + module.lessons.length, 0);
}

export function courseMinutes(course: Course): number {
  return course.modules.reduce(
    (sum, module) => sum + module.lessons.reduce((inner, lesson) => inner + lesson.minutes, 0),
    0,
  );
}

export function findLesson(course: Course, lessonId: string) {
  for (const module of course.modules) {
    const lesson = module.lessons.find((item) => item.id === lessonId);
    if (lesson) return { module, lesson };
  }
  return null;
}
