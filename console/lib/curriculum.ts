import type { CourseDraft, CourseModule, GradingComponent, LessonType } from "./types";

/**
 * The rules engine is the deterministic half of course generation: it turns an
 * idea into a real, structurally valid course without a model provider, and it
 * applies revision instructions to an existing draft. When the configured model
 * gateway answers, its draft replaces the rules draft and lands in the same
 * shape, so publishing and validation never depend on which engine ran.
 */

const STOP_WORDS = new Set([
  "a",
  "an",
  "the",
  "course",
  "class",
  "about",
  "for",
  "that",
  "which",
  "with",
  "and",
  "of",
  "to",
  "on",
  "in",
  "teaching",
  "teaches",
  "learners",
  "students",
  "how",
  "using",
]);

const ACRONYMS = new Set([
  "AI", "ML", "LLM", "GPT", "SQL", "API", "BI", "HR", "IT", "OS", "DNS", "MFA",
  "EMR", "EHR", "HIPAA", "GDPR", "NIST", "SOC", "ROI", "KPI", "CRM", "SEO", "UX",
  "UI", "QA", "MBA", "BBA", "ASN", "RN", "LPN", "CPA", "PMP", "AWS", "ETL", "RPA",
  "P&L", "B2B", "B2C", "FAA", "OSHA",
]);

function titleCase(value: string): string {
  const small = new Set(["a", "an", "the", "and", "or", "for", "of", "to", "in", "on", "with", "by", "at"]);
  return value
    .split(/\s+/)
    .filter(Boolean)
    .map((raw, index) => {
      const bare = raw.replace(/^[^A-Za-z0-9&]+|[^A-Za-z0-9&]+$/g, "");
      if (bare && bare.length <= 5 && ACRONYMS.has(bare.toUpperCase())) {
        return raw.replace(bare, bare.toUpperCase());
      }
      const lower = raw.toLowerCase();
      if (index > 0 && small.has(lower)) return lower;
      return lower.replace(/(^|[-/])([a-z])/g, (_match, sep: string, chr: string) => sep + chr.toUpperCase());
    })
    .join(" ");
}

const LEAD_IN =
  /^\s*(?:i\s+want|i'd\s+like|we\s+need|please)?\s*(?:a|an|the)?\s*(?:short|new|online|introductory|intensive|compact|practical|hands-on|capstone|graduate|undergraduate)?\s*(?:course|class|module|program|workshop|training)?\s*(?:on|about|in|covering|that\s+teaches|which\s+teaches|teaching|where)\s+/i;

/** Strip the request wrapper: "A short course teaching X" -> "X". */
function cleanPhrase(idea: string): string {
  let text = idea.replace(/\s+/g, " ").trim().replace(/[.!?]+$/, "");
  for (let i = 0; i < 2; i += 1) text = text.replace(LEAD_IN, "");
  return text.replace(/^(?:a|an|the)\s+/i, "").trim();
}

export function deriveTopic(idea: string): string {
  const cleaned = cleanPhrase(idea);
  const words = cleaned.split(/\s+/).filter((w) => !STOP_WORDS.has(w.toLowerCase()));
  const topic = words.slice(0, 9).join(" ") || cleaned;
  return titleCase(topic.split(" ").slice(0, 7).join(" "));
}

/**
 * A teachable title from a request. "A short course teaching clinic front-desk
 * staff to use AI for patient intake without breaking HIPAA" -> "AI for Patient
 * Intake". The title stays editable, so this only has to be a good starting point.
 */
export function deriveTitle(idea: string): string {
  let text = cleanPhrase(idea);

  // "<audience> to use <subject>" -> the subject is the course.
  const useClause = text.match(/\b(?:to\s+)?(?:use|apply|build|adopt|run|work\s+with)\s+(.+)$/i);
  if (useClause && useClause[1].split(/\s+/).length >= 2) {
    text = useClause[1].replace(/^(?:a|an|the)\s+/i, "");
  }

  // Drop the constraints and the audience tail.
  text = text.split(/\s+(?:without|so\s+that|while|and\s+then|and\s+defend)\s+/i)[0];
  text = text.split(/\s+for\s+(?:first[- ]time|new|working|front[- ]line|front[- ]desk|busy|entry[- ]level|senior|aspiring|adult)\b.*$/i)[0];
  text = text.split(/\s+with\s+(?:no|little|limited)\s+.*$/i)[0];
  text = text.split(/[.;]/)[0].replace(/^(?:how\s+to\s+)/i, "");

  const words = text.split(/\s+/).filter(Boolean).slice(0, 8).join(" ");
  return titleCase(words) || deriveTopic(idea);
}

const PHASE_LABELS = [
  "Foundations",
  "Core practice",
  "Applied workflows",
  "Evidence and judgement",
  "Integration",
  "Capstone",
];

const LESSON_PATTERNS: LessonType[][] = [
  ["reading", "video", "quiz"],
  ["reading", "lab", "discussion"],
  ["video", "lab", "quiz"],
  ["reading", "project", "discussion"],
  ["lab", "project", "discussion"],
  ["project", "exam", "discussion"],
];

function moduleCountFor(credits: number): number {
  if (credits <= 1) return 3;
  if (credits === 2) return 4;
  if (credits === 3) return 5;
  return 6;
}

function buildModule(topic: string, index: number, total: number, level: number): CourseModule {
  const label = PHASE_LABELS[Math.min(index, PHASE_LABELS.length - 1)];
  const isLast = index === total - 1;
  const types = LESSON_PATTERNS[Math.min(index, LESSON_PATTERNS.length - 1)];
  const minutes = level <= 100 ? 35 : level === 200 ? 45 : 55;

  const lessons = types.map((type, i) => ({
    id: `m${index + 1}-l${i + 1}`,
    title:
      type === "quiz"
        ? `${label} check`
        : type === "exam"
          ? "Final examination (proctored)"
          : type === "project"
            ? `${label} project: ${topic}`
            : type === "lab"
              ? `${label} lab: ${topic}`
              : type === "discussion"
                ? `${label} seminar: ${topic}`
                : `${label}: ${topic}`,
    type,
    minutes: type === "exam" ? 120 : type === "project" ? 90 : minutes,
  }));

  return {
    id: `m${index + 1}`,
    title: isLast && total > 3 ? "Capstone and assessment" : `${label}: ${topic}`,
    summary: isLast
      ? `Pull the course together: a scoped project on ${topic.toLowerCase()}, a defence of the choices made, and the graded final.`
      : `${label} — what ${topic.toLowerCase()} requires at this stage, worked through on cases the learner brings from their own role.`,
    lessons,
    assessment: isLast
      ? "Capstone project (40%) + proctored final (60%)"
      : `${label} problem set (graded, rubric published)`,
  };
}

export interface SynthesisInput {
  idea: string;
  audience?: string;
  level?: 100 | 200 | 300 | 400 | 500;
  credits?: number;
  department?: string;
  code?: string;
}

export function synthesizeDraft(input: SynthesisInput): CourseDraft {
  const topic = deriveTopic(input.idea);
  const level = input.level ?? 100;
  const credits = input.credits ?? 3;
  const department = input.department || "General Studies";
  const code = input.code || "GEN100";
  const count = moduleCountFor(credits);

  const modules = Array.from({ length: count }, (_, i) => buildModule(topic, i, count, level));

  const outcomes = [
    `Explain what ${topic.toLowerCase()} is, where it applies and where it does not.`,
    `Apply ${topic.toLowerCase()} to a real task from the learner's own role.`,
    "Judge the quality of an output against a stated standard, and say what would change the judgement.",
    "Produce a documented artefact another practitioner could follow.",
    `Work within the rules, constraints and review steps that govern ${topic.toLowerCase()}.`,
    "Reflect on what worked, what failed, and what to change next time.",
  ];

  const grading: GradingComponent[] = [
    { component: "Participation and seminars", weight: 10 },
    { component: "Labs and short exercises", weight: 30 },
    { component: "Project work", weight: 30 },
    { component: "Proctored final examination", weight: 30 },
  ];

  return {
    code,
    title: deriveTitle(input.idea) || topic,
    summary: `A ${credits}-credit ${level}-level course on ${topic.toLowerCase()} for ${input.audience || "working adults"}. Learners leave with a documented method, a graded artefact and the judgement to know when the method fails.`,
    description: `This course teaches ${topic.toLowerCase()} by doing it. Each module pairs a short reading with a worked example, then asks the learner to apply the method to a case from their own work. Graded work is assessed against a published rubric, and the course ends in a scoped project and a proctored final examination. Pass at 60% for credit.`,
    outcomes,
    audience: input.audience || "Working adults and career changers",
    prerequisites:
      level <= 100 ? ["No prior coursework required."] : ["One 100-level course in the same subject, or instructor permission."],
    level,
    credits,
    department,
    modules,
    grading,
  };
}

/* ------------------------------------------------------------------ */
/* Revision rules                                                      */
/* ------------------------------------------------------------------ */

interface Intent {
  match: RegExp;
  changes: string[];
  apply: (draft: CourseDraft, m: RegExpMatchArray, topic: string) => CourseDraft;
}

const clone = (draft: CourseDraft): CourseDraft => JSON.parse(JSON.stringify(draft));

function renumber(draft: CourseDraft): CourseDraft {
  draft.modules = draft.modules.map((module, i) => ({
    ...module,
    id: `m${i + 1}`,
    lessons: module.lessons.map((lesson, j) => ({ ...lesson, id: `m${i + 1}-l${j + 1}` })),
  }));
  return draft;
}

const INTENTS: Intent[] = [
  {
    match: /\b(shorter|fewer|condense|trim|tighten|cut)\b/i,
    changes: ["Removed a module and folded its assessment into the preceding one."],
    apply: (draft) => {
      const next = clone(draft);
      if (next.modules.length > 3) next.modules.splice(next.modules.length - 2, 1);
      return renumber(next);
    },
  },
  {
    match: /\b(longer|more modules|expand|deeper|more depth|comprehensive)\b/i,
    changes: ["Added a module with a new lab and its own graded check."],
    apply: (draft) => {
      const next = clone(draft);
      const topic = deriveTopic(draft.title);
      const added = buildModule(topic, next.modules.length, next.modules.length + 1, draft.level);
      next.modules.splice(next.modules.length, 0, added);
      return renumber(next);
    },
  },
  {
    match: /\b(practical|hands-on|applied|workshop|do the work)\b/i,
    changes: ["Converted readings into labs and added a project artefact per module."],
    apply: (draft) => {
      const next = clone(draft);
      next.modules = next.modules.map((module, i) => ({
        ...module,
        lessons: module.lessons.map((lesson, j) =>
          lesson.type === "reading" && j === 1
            ? { ...lesson, type: "lab" as LessonType, title: `Applied lab: ${module.title}` }
            : lesson,
        ),
      }));
      next.grading = [
        { component: "Labs and applied exercises", weight: 40 },
        { component: "Project work", weight: 30 },
        { component: "Proctored final examination", weight: 30 },
      ];
      return next;
    },
  },
  {
    match: /\b(rigor|rigorous|academic|theory|theoretical|scholarly)\b/i,
    changes: ["Added a reading-led seminar per module and reweighted toward written assessment."],
    apply: (draft) => {
      const next = clone(draft);
      next.modules = next.modules.map((module) => ({
        ...module,
        lessons: [
          ...module.lessons,
          {
            id: `${module.id}-seminar`,
            title: `Seminar: literature and critique — ${module.title}`,
            type: "discussion" as LessonType,
            minutes: 60,
          },
        ],
      }));
      next.grading = [
        { component: "Seminar participation", weight: 20 },
        { component: "Written analysis", weight: 40 },
        { component: "Proctored final examination", weight: 40 },
      ];
      return next;
    },
  },
  {
    match: /\b(beginner|introductory|entry level|entry-level|no experience|novice)\b/i,
    changes: ["Set the course to 100 level and added a no-prerequisite note."],
    apply: (draft) => {
      const next = clone(draft);
      next.level = 100;
      next.prerequisites = ["No prior coursework required."];
      return next;
    },
  },
  {
    match: /\b(advanced|expert|senior|500 level|graduate)\b/i,
    changes: ["Raised the course to 400 level and added an advanced prerequisite."],
    apply: (draft) => {
      const next = clone(draft);
      next.level = 400;
      next.prerequisites = ["Two 300-level courses in the subject, or instructor permission."];
      return next;
    },
  },
  {
    match: /\b(capstone|final project|portfolio|defence|defense)\b/i,
    changes: ["Added a capstone module with a scoped project and a defence."],
    apply: (draft) => {
      const next = clone(draft);
      if (!next.modules.some((m) => /capstone/i.test(m.title))) {
        next.modules.push({
          id: "capstone",
          title: "Capstone: scoped project and defence",
          summary:
            "A single project, scoped with the instructor, that shows the method end to end, plus a short defence of the choices made.",
          lessons: [
            { id: "capstone-l1", title: "Scope the capstone", type: "discussion", minutes: 45 },
            { id: "capstone-l2", title: "Build and iterate", type: "project", minutes: 240 },
            { id: "capstone-l3", title: "Defence", type: "exam", minutes: 45 },
          ],
          assessment: "Capstone project and defence (graded against the published rubric)",
        });
      }
      return renumber(next);
    },
  },
  {
    match: /\b(more quizzes|quiz|checks|formative|practice questions)\b/i,
    changes: ["Added a formative check to every module."],
    apply: (draft) => {
      const next = clone(draft);
      next.modules = next.modules.map((module) => {
        if (module.lessons.some((l) => l.type === "quiz")) return module;
        return {
          ...module,
          lessons: [
            ...module.lessons,
            {
              id: `${module.id}-check`,
              title: `Check your understanding: ${module.title}`,
              type: "quiz" as LessonType,
              minutes: 20,
            },
          ],
        };
      });
      return next;
    },
  },
  {
    match: /\b(compliance|hipaa|gdpr|regulation|legal|policy|governance)\b/i,
    changes: ["Added a compliance module covering rules, review steps and evidence."],
    apply: (draft) => {
      const next = clone(draft);
      next.modules.push({
        id: "compliance",
        title: "Rules, compliance and evidence",
        summary:
          "What the applicable rules require, what may and may not go into a tool, and the evidence an auditor would ask for.",
        lessons: [
          { id: "compliance-l1", title: "The rules that apply", type: "reading", minutes: 45 },
          { id: "compliance-l2", title: "Handling a refusal", type: "lab", minutes: 60 },
          { id: "compliance-l3", title: "Evidence and audit trail", type: "project", minutes: 60 },
        ],
        assessment: "Compliance review worksheet (graded)",
      });
      return renumber(next);
    },
  },
  {
    match: /\b(ai|artificial intelligence|model|gpt|automation)\b/i,
    changes: ["Threaded AI use through every module, with a verification step."],
    apply: (draft) => {
      const next = clone(draft);
      if (!next.outcomes.some((o) => /ai|model/i.test(o))) {
        next.outcomes.push(
          "Use AI tools where they help, and verify what they produce before it is relied on.",
        );
      }
      return next;
    },
  },
];

export interface RevisionResult {
  draft: CourseDraft;
  changes: string[];
}

export function reviseDraft(draft: CourseDraft, instruction: string): RevisionResult {
  const changes: string[] = [];
  let next = clone(draft);

  for (const intent of INTENTS) {
    const match = instruction.match(intent.match);
    if (!match) continue;
    next = intent.apply(next, match, deriveTopic(next.title));
    changes.push(...intent.changes);
  }

  // "focus on X" / "make it about X" — retarget the subject matter.
  const focus = instruction.match(/(?:focus(?:ed)? on|make it about|centre on|center on|instead of .*? about)\s+([^.,;]+)/i);
  if (focus) {
    const subject = focus[1].trim();
    next.modules = next.modules.map((module) => ({
      ...module,
      title: module.title.replace(/:\s*.*$/, `: ${titleCase(subject)}`),
      summary: `${module.summary} Refocused on ${subject}.`.replace(/\s+/g, " "),
    }));
    next.outcomes = next.outcomes.map((o) => o.replace(/this course/i, titleCase(subject)));
    next.summary = `${next.summary.split(" Learners")[0]} Focused on ${subject}.`;
    changes.push(`Refocused the curriculum on ${subject}.`);
  }

  // "for <audience>"
  const audience = instruction.match(/\bfor\s+(first[- ]year|second[- ]year|new|experienced|senior|front[- ]line|front[- ]desk|manager[s]?|supervisor[s]?|nurse[s]?|teacher[s]?|worker[s]?|clinical|admin(?:istrative)?)\s*(?:staff|learners|workers|students)?\b/i);
  if (audience) {
    next.audience = `${titleCase(audience[1])} staff`;
    next.summary = next.summary.replace(/for [^.]+\./, `for ${next.audience.toLowerCase()}.`);
    changes.push(`Set the audience to ${next.audience.toLowerCase()}.`);
  }

  // "rename it to X" / "call it X"
  const rename = instruction.match(/(?:rename (?:it|the course) to|call it|title it)\s+["“']?([^"”'.,;]+)/i);
  if (rename) {
    next.title = titleCase(rename[1].trim());
    changes.push(`Retitled the course "${next.title}".`);
  }

  // "3 credits" / "2 credit"
  const credits = instruction.match(/\b([1-6])\s*credits?\b/i);
  if (credits) {
    const value = Number(credits[1]);
    if (value !== next.credits) {
      next.credits = value;
      const target = moduleCountFor(value);
      if (next.modules.length > target) {
        next.modules = next.modules.slice(0, target);
      } else {
        while (next.modules.length < target) {
          next.modules.push(
            buildModule(deriveTopic(next.title), next.modules.length, target, next.level),
          );
        }
      }
      next = renumber(next);
      changes.push(`Set the course to ${value} credits and rebuilt the module count.`);
    }
  }

  // A new outcome when the instruction talks about a capability.
  const wantsOutcome = instruction.match(/\b(add|include)\b.*\b(outcome|objective|skill)\b/i);
  if (wantsOutcome) {
    next.outcomes = [
      ...next.outcomes,
      `Demonstrate ${deriveTopic(instruction).toLowerCase()} in a graded artefact.`,
    ];
    changes.push("Added a learning outcome tied to the new capability.");
  }

  // Nothing recognised: treat the instruction as new subject matter.
  if (changes.length === 0) {
    const subject = deriveTopic(instruction) || instruction.trim();
    next.modules.push({
      id: "added",
      title: `Additional module: ${subject}`,
      summary: `Added on request: ${instruction.trim()}`,
      lessons: [
        { id: "added-l1", title: `${subject} — concepts`, type: "reading", minutes: 45 },
        { id: "added-l2", title: `${subject} — applied`, type: "lab", minutes: 60 },
        { id: "added-l3", title: `${subject} — check`, type: "quiz", minutes: 20 },
      ],
      assessment: `${subject} problem set (graded)`,
    });
    next = renumber(next);
    changes.push(`Added a module on ${subject}.`);
  }

  next.grading = normaliseGrading(next.grading);
  return { draft: next, changes };
}

export function normaliseGrading(grading: GradingComponent[]): GradingComponent[] {
  const total = grading.reduce((sum, g) => sum + g.weight, 0);
  if (!grading.length || total <= 0) return grading;
  if (total === 100) return grading;
  const scaled = grading.map((g) => ({ ...g, weight: Math.round((g.weight / total) * 100) }));
  const drift = 100 - scaled.reduce((sum, g) => sum + g.weight, 0);
  if (scaled.length) scaled[0].weight += drift;
  return scaled;
}

/** Structural check used before a draft can be accepted into the catalog. */
export function draftIssues(draft: CourseDraft): string[] {
  const issues: string[] = [];
  if (!draft.title.trim()) issues.push("The course needs a title.");
  if (!draft.summary.trim() || draft.summary.trim().length < 40)
    issues.push("The summary needs at least 40 characters.");
  if (!draft.modules.length) issues.push("The course needs at least one module.");
  for (const module of draft.modules) {
    if (!module.lessons.length) issues.push(`Module "${module.title}" has no lessons.`);
  }
  if (!draft.outcomes.length) issues.push("Add at least one learning outcome.");
  const total = draft.grading.reduce((sum, g) => sum + g.weight, 0);
  if (total !== 100) issues.push(`Grading weights add up to ${total}%, not 100%.`);
  return issues;
}
