import { synthesizeDraft } from "./curriculum";
import type {
  Completion,
  Course,
  CourseModule,
  Credential,
  Database,
  GenSession,
  Learner,
  Program,
  Settings,
  Track,
} from "./types";

const SEEDED_AT = "2026-11-10T09:00:00.000Z";

const ORG = "InnotelLabs";
export const ORG_SHORT = "InnotelLabs";

export function courseKey(code: string, term: string): string {
  return `course-v1:${ORG}+${code.toUpperCase()}+${term}`;
}

export function slugify(value: string): string {
  return value
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "")
    .slice(0, 64);
}

/** Runtime course keys look like `course-v1:ORG+CODE+RUN`. */
export function parseCourseKey(key: string): { org: string; code: string; run: string } | null {
  if (!key.startsWith("course-v1:")) return null;
  const parts = key.slice("course-v1:".length).split("+");
  if (parts.length !== 3) return null;
  return { org: parts[0], code: parts[1], run: parts[2] };
}

export function codeFromKey(key: string): string {
  return parseCourseKey(key)?.code ?? key;
}

/* ------------------------------------------------------------------ */
/* Degree programs — the published Spring 2027 plans                   */
/* ------------------------------------------------------------------ */

interface PlanSeed {
  id: string;
  slug: string;
  name: string;
  credential: string;
  credentialType: Program["credentialType"];
  department: string;
  summary: string;
  totalCredits: number;
  tuitionPerCreditCents: number;
  accreditation: string;
  semesters: { focus: string; credits: number; courses: string }[];
}

const PLAN_SEEDS: PlanSeed[] = [
  {
    id: "prog-bba",
    slug: "business-administration",
    name: "Business Administration",
    credential: "Bachelor of Business Administration",
    credentialType: "Bachelor",
    department: "Business",
    summary:
      "How firms create and capture value: markets, models, finance, operations and strategy. Learners map one real company end to end, then take it through a capstone simulation.",
    totalCredits: 120,
    tuitionPerCreditCents: 32500,
    accreditation:
      "AthenIQ is a program of Innotel Labs. Accreditation and state-authorization disclosures are provided in the catalog and with every offer of admission.",
    semesters: [
      {
        focus: "The Language of Business",
        credits: 15,
        courses:
          "BUS101 Introduction to Business|ACCT201 Financial Accounting|ECON101 Microeconomics",
      },
      {
        focus: "Decision Foundations",
        credits: 15,
        courses:
          "ACCT202 Managerial Accounting|ECON102 Macroeconomics|BUS210 Business Law I",
      },
      {
        focus: "The Functions",
        credits: 15,
        courses:
          "FIN301 Principles of Finance|MKT301 Principles of Marketing|BUS310 Business Statistics",
      },
      {
        focus: "Running the Firm",
        credits: 15,
        courses:
          "FIN310 Corporate Finance|MKT320 Consumer Behavior|BUS340 Operations Management",
      },
      {
        focus: "Beyond the Domestic Market",
        credits: 15,
        courses:
          "BUS401 International Business|FIN410 Investment Analysis|MKT410 Digital Marketing",
      },
      {
        focus: "Integration",
        credits: 15,
        courses:
          "BUS440 Supply Chain Management|BUS450 Business Analytics|BUS460 Strategic Management",
      },
      {
        focus: "Practice",
        credits: 15,
        courses:
          "BUS490 Business Consulting Practicum|BUS491 Business Plan Development|BUS492 Corporate Governance",
      },
      {
        focus: "Conferral",
        credits: 15,
        courses:
          "BUS496 Capstone: Strategy Simulation|BUS497 Comprehensive Final Examination|BUS498 Business Elective",
      },
    ],
  },
  {
    id: "prog-cj",
    slug: "criminal-justice",
    name: "Criminal Justice",
    credential: "Bachelor of Science in Criminal Justice",
    credentialType: "Bachelor",
    department: "Criminal Justice",
    summary:
      "The justice system from the inside: policing, law and procedure, corrections, forensic science, policy and leadership. Includes investigative practice, a capstone, and a supervised internship.",
    totalCredits: 120,
    tuitionPerCreditCents: 32500,
    accreditation:
      "AthenIQ is a program of Innotel Labs. Accreditation and state-authorization disclosures are provided in the catalog and with every offer of admission.",
    semesters: [
      {
        focus: "Foundations",
        credits: 15,
        courses:
          "CJ101 Introduction to Criminal Justice|ENGL101 College Writing|MATH110 College Algebra",
      },
      {
        focus: "The System in Motion",
        credits: 15,
        courses: "CJ102 Criminology|CJ120 Criminal Law|CJ130 Policing in America",
      },
      {
        focus: "Law, Evidence, and the State",
        credits: 16,
        courses:
          "CJ201 Criminal Procedure|CJ210 Corrections and Penology|CJ220 Forensic Science I",
      },
      {
        focus: "Investigation and Threat",
        credits: 16,
        courses:
          "CJ240 Criminal Investigations|CJ250 Homeland Security and Terrorism|CJ260 Ethics in Criminal Justice",
      },
      {
        focus: "Constitutional Limits",
        credits: 15,
        courses:
          "CJ301 Constitutional Law|CJ310 Forensic Science II|CJ320 Victimology",
      },
      {
        focus: "Practice",
        credits: 15,
        courses:
          "CJ350 Advanced Policing Strategies|CJ360 Courtroom Procedure and Testimony|CJ370 Restorative Justice",
      },
      {
        focus: "Leadership and Policy",
        credits: 15,
        courses:
          "CJ401 Criminal Justice Policy|CJ410 Leadership in Criminal Justice|CJ420 Capstone Seminar I",
      },
      {
        focus: "Conferral",
        credits: 13,
        courses:
          "CJ450 Capstone Seminar II|CJ460 Criminal Justice Internship|CJ470 Comprehensive Final Examination",
      },
    ],
  },
  {
    id: "prog-asn",
    slug: "nursing",
    name: "Nursing",
    credential: "Associate of Science in Nursing",
    credentialType: "Associate",
    department: "Nursing",
    summary:
      "Science foundations, health assessment, pharmacology and medical-surgical nursing through to critical care and clinical practicum. Built for licensure preparation, with supervised clinical hours arranged locally.",
    totalCredits: 75,
    tuitionPerCreditCents: 32500,
    accreditation:
      "Nursing graduates must meet the licensure requirements of the state or country in which they intend to practice. Clinical placement, immunisations and a background check are required before practicum.",
    semesters: [
      {
        focus: "Science Foundations",
        credits: 15,
        courses:
          "NUR101 Foundations of Nursing|BIO201 Anatomy and Physiology I|CHEM101 General Chemistry",
      },
      {
        focus: "Assessment and Pharmacology",
        credits: 17,
        courses:
          "NUR110 Health Assessment|NUR120 Fundamentals of Nursing Practice|BIO202 Anatomy and Physiology II",
      },
      {
        focus: "Medical-Surgical Core",
        credits: 15,
        courses:
          "NUR201 Medical-Surgical Nursing I|NUR210 Pharmacology II|NUR220 Maternal-Newborn Nursing",
      },
      {
        focus: "Specialties",
        credits: 16,
        courses:
          "NUR301 Medical-Surgical Nursing II|NUR310 Paediatric Nursing|NUR320 Mental Health Nursing",
      },
      {
        focus: "Conferral",
        credits: 12,
        courses:
          "NUR401 Critical Care Nursing|NUR410 Leadership and Management|NUR420 Clinical Practicum",
      },
    ],
  },
];

/* ------------------------------------------------------------------ */
/* Workforce courses — the published catalog and its real chapter map  */
/* ------------------------------------------------------------------ */

interface WorkforceCourse {
  code: string;
  term: string;
  title: string;
  department: string;
  credits: number;
  level: 100 | 200 | 300 | 400;
  plan: string | null;
  amountCents: number | null;
  summary: string;
  chapters: string[];
  tracks: string[];
}

const WORKFORCE_COURSES: WorkforceCourse[] = [
  {
    code: "TEST101",
    term: "2027_T1",
    title: "AthenIQ Demo Course",
    department: "Platform",
    credits: 1,
    level: 100,
    plan: null,
    amountCents: null,
    summary:
      "The reference course for the platform: every component type, a graded final, and a certificate that proves the whole pipeline works.",
    chapters: [
      "Welcome & how the demo works",
      "Text, video and images",
      "Question types",
      "Grading and certificates",
    ],
    tracks: [],
  },
  {
    code: "ITSP101",
    term: "2026_T1",
    title: "IT Support Foundations",
    department: "Information Technology",
    credits: 3,
    level: 100,
    plan: "premium",
    amountCents: null,
    summary:
      "Support users, devices and operating systems — then run a help desk. The entry certification of the workforce ladder.",
    chapters: [
      "How IT support works",
      "Hardware basics",
      "Operating systems and accounts",
      "Networking fundamentals",
      "Security essentials",
      "Help desk operations",
      "Troubleshooting practice",
    ],
    tracks: ["it-support"],
  },
  {
    code: "ITSP102",
    term: "2026_T1",
    title: "Networking & Systems Support",
    department: "Information Technology",
    credits: 3,
    level: 200,
    plan: "premium",
    amountCents: null,
    summary:
      "Network architecture, routing and switching, Windows and Linux administration for the support desk.",
    chapters: ["Network architecture", "Routing and switching", "Windows administration", "Linux administration"],
    tracks: ["it-support"],
  },
  {
    code: "ITSP103",
    term: "2026_T1",
    title: "Security Operations Foundations",
    department: "Information Technology",
    credits: 3,
    level: 200,
    plan: "premium",
    amountCents: null,
    summary:
      "Run a SOC shift: monitoring, identity and access, defensive controls, and incident response.",
    chapters: ["The security operations center", "Identity and access", "Defensive controls", "Incident response"],
    tracks: ["it-support"],
  },
  {
    code: "ITSP104",
    term: "2026_T1",
    title: "IT Support Capstone",
    department: "Information Technology",
    credits: 3,
    level: 300,
    plan: "premium",
    amountCents: null,
    summary:
      "A brief, a simulated estate, and a review: the capstone that turns the ladder into a credential.",
    chapters: ["The client brief", "Simulated estate", "Review and handover"],
    tracks: ["it-support"],
  },
  {
    code: "DATA101",
    term: "2026_T1",
    title: "Data Foundations",
    department: "Data",
    credits: 3,
    level: 100,
    plan: "premium",
    amountCents: null,
    summary:
      "Spreadsheets to clean, reported data: the data literacy every operations role now expects.",
    chapters: ["Data literacy", "Cleaning and shaping", "Reporting", "Governance and judgement"],
    tracks: ["data-foundations"],
  },
  {
    code: "SQL101",
    term: "2026_T1",
    title: "SQL Essentials",
    department: "Data",
    credits: 3,
    level: 100,
    plan: "premium",
    amountCents: null,
    summary:
      "The relational model, SELECT, aggregation and schema design — querying a real database from the first lesson.",
    chapters: ["The relational model", "SELECT and filtering", "Aggregation", "Design and joins"],
    tracks: ["data-foundations"],
  },
  {
    code: "MAIC101",
    term: "2027_T1",
    title: "AI Classroom Facilitation",
    department: "Teaching & Learning",
    credits: 3,
    level: 200,
    plan: "premium",
    amountCents: null,
    summary:
      "Run generative AI classrooms: author with OpenMAIC, facilitate live sessions, and assess learners fairly.",
    chapters: ["Generative classrooms", "Authoring with OpenMAIC", "Live facilitation", "Assessment design"],
    tracks: ["ai-classroom-facilitator"],
  },
  {
    code: "FAI101",
    term: "2026_T4",
    title: "Applied AI Foundations for Work",
    department: "Applied AI",
    credits: 3,
    level: 100,
    plan: "premium",
    amountCents: null,
    summary:
      "What a language model actually does, which tasks to hand it, what data may go in, and the verification habit every AI draft needs.",
    chapters: ["How models work", "Task fit", "Data rules", "Verification"],
    tracks: ["fast-ai"],
  },
  {
    code: "FAI102",
    term: "2026_T4",
    title: "Prompt Engineering & AI Productivity",
    department: "Applied AI",
    credits: 3,
    level: 100,
    plan: "premium",
    amountCents: null,
    summary:
      "Briefs instead of wishes: prompts that state the task, the source and the standard, iteration that converges, and a prompt library a team can share.",
    chapters: ["Context and the brief", "Iteration that converges", "A working prompt suite", "A shared library"],
    tracks: ["fast-ai"],
  },
  {
    code: "FAI103",
    term: "2026_T4",
    title: "AI-Assisted Data Analysis & BI",
    department: "Applied AI",
    credits: 3,
    level: 200,
    plan: "premium",
    amountCents: null,
    summary:
      "From a business question to a checked answer: what AI analysis can and cannot tell you, assisted analysis with checks, and reporting for a decision.",
    chapters: ["Question to data", "Where models fail", "Assisted analysis", "Reporting for a decision"],
    tracks: ["fast-ai"],
  },
  {
    code: "FAI104",
    term: "2026_T4",
    title: "Occupation-Specific AI Workflows",
    department: "Applied AI",
    credits: 3,
    level: 200,
    plan: "premium",
    amountCents: null,
    summary:
      "Map the work before automating it, build the workflow on the tools the role already uses, handle client-facing work, then pilot, measure and hand over.",
    chapters: ["Map the work", "Build the workflow", "Client-facing work", "Pilot and handover"],
    tracks: ["fast-ai"],
  },
  {
    code: "FAI105",
    term: "2026_T4",
    title: "AI for Managers & Leaders",
    department: "Applied AI",
    credits: 3,
    level: 300,
    plan: "premium",
    amountCents: null,
    summary:
      "A manager's map of AI, process improvement rather than tool envy, what changes for roles and people, and the business case with its rules attached.",
    chapters: ["The manager's map", "Process before tools", "People and roles", "The business case"],
    tracks: ["fast-ai"],
  },
  {
    code: "FAI106",
    term: "2026_T4",
    title: "AI Governance, Risk & Responsible Use",
    department: "Applied AI",
    credits: 3,
    level: 300,
    plan: "premium",
    amountCents: null,
    summary:
      "The frameworks that apply, a risk assessment you can defend, transparency and worker rights, and vendor review with an incident response path.",
    chapters: ["Frameworks", "Risk assessment", "Transparency and rights", "Vendor review"],
    tracks: ["fast-ai"],
  },
];

const TRACK_SEEDS: Omit<Track, "createdAt" | "updatedAt">[] = [
  {
    id: "it-support",
    title: "IT Support Specialist",
    summary:
      "Support users, devices, operating systems, and networks — then run a help desk. The entry certification of the workforce ladder.",
    audience: "workforce",
    targetRole: "IT Support Specialist",
    status: "active",
    courses: ["ITSP101", "ITSP102", "ITSP103", "ITSP104"].map((c) =>
      courseKey(c, "2026_T1"),
    ),
    credential: {
      type: "certificate",
      title: "IT Support Specialist — Certification",
      signara_template: "course-completion",
    },
    entitlement: { plan: "premium" },
    skills: [
      "help desk operations",
      "operating systems",
      "hardware support",
      "networking basics",
      "security fundamentals",
      "troubleshooting",
    ],
  },
  {
    id: "data-foundations",
    title: "Data Foundations",
    summary: "Spreadsheets to SQL: the data literacy every operations role now expects.",
    audience: "workforce",
    targetRole: "Data / Operations Analyst",
    status: "active",
    courses: [courseKey("DATA101", "2026_T1"), courseKey("SQL101", "2026_T1")],
    credential: {
      type: "certificate",
      title: "Data Foundations — Track Completion",
      signara_template: "course-completion",
    },
    entitlement: { plan: "premium" },
    skills: ["spreadsheets", "SQL", "data cleaning", "reporting"],
  },
  {
    id: "fast-ai",
    title: "FAST AI — Applied AI Skills",
    summary:
      "The Focused AI Skills Training ladder: applied AI foundations, prompting and productivity, AI-assisted analysis, occupation-specific workflows, AI for managers, and governance. Built for incumbent workers, aligned to the CommCorp FAST AI training priorities.",
    audience: "workforce",
    targetRole: "AI-Ready Professional",
    status: "active",
    courses: [1, 2, 3, 4, 5, 6].map((n) => courseKey(`FAI10${n}`, "2026_T4")),
    credential: {
      type: "certificate",
      title: "FAST AI — Applied AI Skills",
      signara_template: "course-completion",
    },
    entitlement: { plan: "premium" },
    skills: [
      "AI literacy",
      "prompt engineering",
      "AI productivity",
      "AI-assisted analysis",
      "workflow automation",
      "AI for managers",
      "AI governance and risk",
    ],
  },
  {
    id: "ai-classroom-facilitator",
    title: "AI Classroom Facilitator",
    summary:
      "Run generative AI classrooms: author with OpenMAIC, facilitate sessions, assess learners.",
    audience: "instructors",
    targetRole: "AI Classroom Facilitator",
    status: "active",
    courses: [courseKey("MAIC101", "2027_T1")],
    credential: {
      type: "certificate",
      title: "AI Classroom Facilitator — Track Completion",
      signara_template: "course-completion",
    },
    entitlement: { plan: "premium" },
    skills: ["course authoring", "multi-agent lessons", "live facilitation", "assessment design"],
  },
];

export const DEFAULT_SETTINGS: Settings = {
  org: "AthenIQ Institute",
  orgShort: ORG,
  defaultTerm: "2027_T1",
  creditsPerCourse: 3,
  tuitionPerCreditCents: 32500,
  applicationFeeCents: 5000,
  graduationFeeCents: 15000,
  lms: {
    baseUrl: "https://atheniq.courses",
    studioUrl: "https://atheniq.courses",
    catalogUrl: "https://atheniq.courses/catalog/",
    importUrl: "",
    apiToken: "",
  },
  signara: {
    baseUrl: process.env.SIGNARA_API_URL || "https://api.signara.innotel.us",
    apiKey: process.env.SIGNARA_API_KEY || "",
    autoSign: true,
    defaultTemplate: "course-completion",
    keyExpiresAt: process.env.SIGNARA_KEY_EXPIRES_AT || null,
    keyPrefix: "",
  },
  ai: {
    baseUrl: process.env.OMNIROUTE_BASE_URL || "https://api.openai.com/v1",
    apiKey: process.env.OMNIROUTE_API_KEY || process.env.OPENAI_API_KEY || "",
    model: process.env.OMNIROUTE_MODEL || "gpt-4o-mini",
  },
  signer: {
    name: process.env.CERT_SIGNER_NAME || "D. Hunter",
    title: process.env.CERT_SIGNER_TITLE || "Founder — Innotel",
    email: process.env.CERT_SIGNER_EMAIL || "dhunter@innotel.us",
  },
  sites: {
    instituteUrl: "https://atheniq.institute",
    coursesUrl: "https://atheniq.courses",
    workforceUrl: "https://workforce.atheniq.online",
  },
  brand: {
    siteName: "AthenIQ Institute",
    tagline: "An online university from Innotel Labs",
    logoUrl: "",
    logoText: "",
    logoPlacement: "left",
    accent: "#178f68",
    // The published admissions desk, not whoever signs certificates: the
    // console sends an applicant here, and the website prints the same address.
    supportEmail: process.env.ADMISSIONS_EMAIL || "admissions@atheniq.institute",
    poweredBy: true,
    domain: process.env.PUBLIC_SITE_DOMAIN || "atheniq.institute",
  },
  // Retired with /site: the console renders no website now, but the shape stays
  // so stored records and old exports keep parsing.
  site: {
    published: true,
    headline: "A university for the work that’s coming.",
    intro:
      "Earn an online bachelor’s or associate degree in business, criminal justice or nursing — taught in small, AI-native classrooms, assessed by faculty, and finished with a credential you can verify.",
    showPrices: true,
    showPrograms: true,
    showVerify: true,
    ctaLabel: "Explore the catalog",
    ctaHref: "/catalog/",
    lastPublishedAt: null,
  },
  mail: {
    digestTo: process.env.DIGEST_TO || process.env.CERT_SIGNER_EMAIL || "dhunter@innotel.us",
    alertsTo: process.env.ALERT_TO || "",
    cadenceDays: 7,
    lastDigestAt: null,
  },
  auth: {
    allowedDomains: (process.env.STAFF_EMAIL_DOMAINS || "innotel.us,atheniq.institute")
      .split(",")
      .map((domain) => domain.trim().toLowerCase())
      .filter(Boolean),
    // Required by default: an unenrolled account enrolls at its first sign-in.
    // AUTH_REQUIRE_2FA=off makes the password sufficient until it enrolls.
    require2fa: (process.env.AUTH_REQUIRE_2FA || "on").toLowerCase() !== "off",
  },
};

/* ------------------------------------------------------------------ */

function titleCase(value: string): string {
  return value
    .split(/\s+/)
    .map((w) =>
      w.length <= 2 && w === w.toLowerCase() ? w : w.charAt(0).toUpperCase() + w.slice(1),
    )
    .join(" ");
}

const PHASES = [
  { label: "Foundations", kind: "orientation" },
  { label: "Core concepts", kind: "core" },
  { label: "Applied practice", kind: "practice" },
  { label: "Analysis and judgement", kind: "analysis" },
  { label: "Integration", kind: "integration" },
  { label: "Capstone", kind: "capstone" },
] as const;

/** A four-module scaffold used for catalog courses seeded from a degree plan. */
export function scaffoldModules(
  code: string,
  title: string,
  department: string,
  moduleTitles?: string[],
): CourseModule[] {
  if (moduleTitles && moduleTitles.length) {
    return moduleTitles.map((t, i) => ({
      id: `${code}-m${i + 1}`,
      title: titleCase(t),
      summary: `${titleCase(t)}: the ${t.toLowerCase()} that ${title.toLowerCase()} is built on.`,
      lessons: [
        { id: `${code}-m${i + 1}-l1`, title: `${titleCase(t)} — concepts`, type: "reading", minutes: 45 },
        { id: `${code}-m${i + 1}-l2`, title: `${titleCase(t)} in practice`, type: "lab", minutes: 60 },
        { id: `${code}-m${i + 1}-l3`, title: `${titleCase(t)} check`, type: "quiz", minutes: 20 },
      ],
      assessment: `${titleCase(t)} problem set (graded)`,
    }));
  }

  return PHASES.slice(0, 4).map((phase, i) => ({
    id: `${code}-m${i + 1}`,
    title: `${phase.label}: ${title}`,
    summary: `${phase.label} of ${title} in the ${department} program.`,
    lessons: [
      { id: `${code}-m${i + 1}-l1`, title: `${phase.label} — reading`, type: "reading", minutes: 45 },
      { id: `${code}-m${i + 1}-l2`, title: `${phase.label} — worked example`, type: "video", minutes: 30 },
      { id: `${code}-m${i + 1}-l3`, title: `${phase.label} practice`, type: "quiz", minutes: 25 },
    ],
    assessment: `${phase.label} problem set`,
  }));
}

const LEVEL_BY_NUMBER: Record<number, 100 | 200 | 300 | 400> = {
  1: 100,
  2: 100,
  3: 200,
  4: 200,
  5: 300,
  6: 300,
  7: 400,
  8: 400,
  9: 400,
};

function levelFor(code: string, fallback: 100 | 200 | 300 | 400 = 100): 100 | 200 | 300 | 400 {
  const digits = code.match(/(\d{3})$/);
  if (!digits) return fallback;
  const hundred = Number(digits[1][0]);
  return LEVEL_BY_NUMBER[hundred] ?? fallback;
}

export function buildSeed(): Database {
  const programs: Program[] = PLAN_SEEDS.map((plan) => ({
    id: plan.id,
    slug: plan.slug,
    name: plan.name,
    credential: plan.credential,
    credentialType: plan.credentialType,
    department: plan.department,
    summary: plan.summary,
    totalCredits: plan.totalCredits,
    tuitionPerCreditCents: plan.tuitionPerCreditCents,
    semesters: plan.semesters.map((s, i) => ({
      number: i + 1,
      focus: s.focus,
      credits: s.credits,
      courses: s.courses.split("|").map((entry) => {
        const [code, ...rest] = entry.split(" ");
        return { code, title: rest.join(" ") };
      }),
    })),
    status: "active",
    accreditation: plan.accreditation,
    signaraTemplate: "degree-conferral",
    createdAt: SEEDED_AT,
    updatedAt: SEEDED_AT,
  }));

  const courses = new Map<string, Course>();

  // 1. Workforce / priced catalog — the real published chapters.
  for (const wc of WORKFORCE_COURSES) {
    const key = courseKey(wc.code, wc.term);
    courses.set(key, {
      id: wc.code,
      code: wc.code,
      term: wc.term,
      title: `${wc.code} — ${wc.title}`,
      slug: slugify(wc.title),
      key,
      org: ORG,
      credits: wc.credits,
      level: wc.level,
      department: wc.department,
      programIds: [],
      trackIds: wc.tracks,
      summary: wc.summary,
      description: `${wc.code} — ${wc.title}. ${wc.summary} Delivered as a facilitated AI classroom with graded work and a proctored final; pass at 60% for credit.`,
      outcomes: wc.chapters.slice(0, 5).map((c) => `Explain and apply ${c.toLowerCase()}.`),
      audience:
        wc.tracks.includes("fast-ai")
          ? "Massachusetts employers and their incumbent or newly hired workers"
          : "Workforce learners and career changers",
      prerequisites: wc.level >= 200 ? ["No formal prerequisite; 100-level readiness expected."] : [],
      modules: scaffoldModules(wc.code, wc.title, wc.department, wc.chapters),
      grading: [
        { component: "Chapter checks", weight: 20 },
        { component: "Labs and exercises", weight: 35 },
        { component: "Applied project", weight: 25 },
        { component: "Proctored final", weight: 20 },
      ],
      price: { plan: wc.plan, amountCents: wc.amountCents },
      status: "published",
      image: `/static/atheniq/images/courses/${wc.code}.jpg`,
      generationId: null,
      publishedAt: SEEDED_AT,
      createdAt: SEEDED_AT,
      updatedAt: SEEDED_AT,
    });
  }

  // 2. Degree catalog — derived from the published semester plans.
  for (const plan of programs) {
    for (const semester of plan.semesters) {
      for (const entry of semester.courses) {
        const term = "2027_T1";
        const key = courseKey(entry.code, term);
        if (courses.has(key)) continue;
        const department = plan.department;
        courses.set(key, {
          id: entry.code,
          code: entry.code,
          term,
          title: `${entry.code} — ${entry.title}`,
          slug: slugify(entry.title),
          key,
          org: ORG,
          credits: entry.code.startsWith("CHEM") || entry.code.startsWith("BIO") ? 4 : 3,
          level: levelFor(entry.code),
          department,
          programIds: [plan.id],
          trackIds: [],
          summary: `${entry.title} — a required course in the ${plan.credential} plan, semester ${semester.number} (${semester.focus}).`,
          description: `${entry.code} — ${entry.title}. Part of ${plan.name}. Taught in small AI-native classrooms with faculty assessment, graded work every week and a proctored final; pass at 60% for credit.`,
          outcomes: [
            `Explain the core ideas of ${entry.title.toLowerCase()}.`,
            `Apply ${entry.title.toLowerCase()} to a real case.`,
            "Write and defend an evidence-based conclusion.",
          ],
          audience: `${plan.credential} candidates`,
          prerequisites: levelFor(entry.code) >= 300 ? ["Junior standing or instructor permission."] : [],
          modules: scaffoldModules(entry.code, entry.title, department),
          grading: [
            { component: "Discussions", weight: 15 },
            { component: "Problem sets", weight: 30 },
            { component: "Projects", weight: 25 },
            { component: "Proctored final", weight: 30 },
          ],
          price: { plan: "premium", amountCents: null },
          status: "published",
          image: `/static/atheniq/images/courses/${entry.code}.jpg`,
          generationId: null,
          publishedAt: SEEDED_AT,
          createdAt: SEEDED_AT,
          updatedAt: SEEDED_AT,
        });
      }
    }
  }

  const tracks: Track[] = TRACK_SEEDS.map((t) => ({
    ...t,
    createdAt: SEEDED_AT,
    updatedAt: SEEDED_AT,
  }));

  const learners: Learner[] = [
    {
      id: "lrn-ada",
      username: "ada.mensah",
      name: "Ada Mensah",
      email: "ada.mensah@example.edu",
      programId: "prog-bba",
      enrolledAt: "2026-08-30T00:00:00.000Z",
    },
    {
      id: "lrn-marcus",
      username: "marcus.bell",
      name: "Marcus Bell",
      email: "marcus.bell@acme.test",
      programId: null,
      enrolledAt: "2026-09-14T00:00:00.000Z",
    },
    {
      id: "lrn-priya",
      username: "priya.raman",
      name: "Priya Raman",
      email: "priya.raman@example.org",
      programId: "prog-cj",
      enrolledAt: "2026-08-30T00:00:00.000Z",
    },
    {
      id: "lrn-jonas",
      username: "jonas.weber",
      name: "Jonas Weber",
      email: "jonas.weber@example.edu",
      programId: "prog-asn",
      enrolledAt: "2026-08-30T00:00:00.000Z",
    },
  ];

  const completions: Completion[] = [
    { id: "cmp-1", learnerId: "lrn-marcus", courseKey: courseKey("FAI101", "2026_T4"), grade: "92", completedOn: "2026-10-18", status: "pass" },
    { id: "cmp-2", learnerId: "lrn-marcus", courseKey: courseKey("FAI102", "2026_T4"), grade: "88", completedOn: "2026-10-24", status: "pass" },
    { id: "cmp-3", learnerId: "lrn-marcus", courseKey: courseKey("FAI103", "2026_T4"), grade: "90", completedOn: "2026-10-30", status: "pass" },
    { id: "cmp-4", learnerId: "lrn-marcus", courseKey: courseKey("FAI104", "2026_T4"), grade: "85", completedOn: "2026-11-02", status: "pass" },
    { id: "cmp-5", learnerId: "lrn-marcus", courseKey: courseKey("FAI105", "2026_T4"), grade: "87", completedOn: "2026-11-05", status: "pass" },
    { id: "cmp-6", learnerId: "lrn-marcus", courseKey: courseKey("FAI106", "2026_T4"), grade: "91", completedOn: "2026-11-07", status: "pass" },
    { id: "cmp-7", learnerId: "lrn-ada", courseKey: courseKey("BUS101", "2027_T1"), grade: "94", completedOn: "2026-05-08", status: "pass" },
    { id: "cmp-8", learnerId: "lrn-ada", courseKey: courseKey("ACCT201", "2027_T1"), grade: "89", completedOn: "2026-05-08", status: "pass" },
    { id: "cmp-9", learnerId: "lrn-ada", courseKey: courseKey("ECON101", "2027_T1"), grade: "91", completedOn: "2026-05-08", status: "pass" },
    { id: "cmp-10", learnerId: "lrn-priya", courseKey: courseKey("CJ101", "2027_T1"), grade: "88", completedOn: "2026-05-08", status: "pass" },
    { id: "cmp-11", learnerId: "lrn-priya", courseKey: courseKey("ENGL101", "2027_T1"), grade: "90", completedOn: "2026-05-08", status: "pass" },
    { id: "cmp-12", learnerId: "lrn-jonas", courseKey: courseKey("NUR101", "2027_T1"), grade: "93", completedOn: "2026-05-08", status: "pass" },
  ];

  const signer = DEFAULT_SETTINGS.signer;

  const credentials: Credential[] = [
    {
      id: "cred-seed-1",
      verifyId: "7f3c1a92e5b44d0a9c6e2b81",
      type: "track_credential",
      title: "FAST AI — Applied AI Skills (Marcus Bell)",
      subjectRef: "fast-ai",
      subjectLabel: "FAST AI — Applied AI Skills",
      learner: { username: "marcus.bell", name: "Marcus Bell", email: "marcus.bell@acme.test" },
      evidence: {
        grade: "Pass",
        completedOn: "2026-11-07",
        courses: TRACK_SEEDS[2].courses,
      },
      status: "signed",
      signara: {
        documentId: "doc_8f21c0ae",
        requestId: "req_4ab902d1",
        signerToken: null,
        apiBase: DEFAULT_SETTINGS.signara.baseUrl,
        lastHttp: 200,
        lastError: null,
      },
      template: "course-completion",
      signer,
      hash: "3c9f0d6a1e7b24c5f80d91ab66d2ee4705b1c8f2a93d4e6071bc9d55aa8e3f10",
      previewPath: null,
      createdAt: "2026-11-07T16:10:00.000Z",
      updatedAt: "2026-11-07T16:11:20.000Z",
      signedAt: "2026-11-07T16:11:20.000Z",
      issuedAt: "2026-11-07T16:12:00.000Z",
      revokedAt: null,
      revokeReason: null,
      timeline: [
        { at: "2026-11-07T16:10:00.000Z", label: "Eligibility confirmed", detail: "6 of 6 courses passed" },
        { at: "2026-11-07T16:10:20.000Z", label: "Document uploaded", detail: "doc_8f21c0ae" },
        { at: "2026-11-07T16:10:40.000Z", label: "Signing request created", detail: "req_4ab902d1" },
        { at: "2026-11-07T16:11:20.000Z", label: "Signed by D. Hunter", detail: "TYPED signature" },
        { at: "2026-11-07T16:12:00.000Z", label: "Issued to learner record" },
      ],
    },
    {
      id: "cred-seed-2",
      verifyId: "b1d84e07c2f94a3e8d15f0aa",
      type: "course_certificate",
      title: "ITSP101 — IT Support Foundations — Certificate of Completion (Ada Mensah)",
      subjectRef: courseKey("ITSP101", "2026_T1"),
      subjectLabel: "ITSP101 — IT Support Foundations",
      learner: { username: "ada.mensah", name: "Ada Mensah", email: "ada.mensah@example.edu" },
      evidence: { grade: "94", completedOn: "2026-10-02" },
      status: "issued",
      signara: {
        documentId: "doc_2b7de114",
        requestId: "req_91c0be37",
        signerToken: null,
        apiBase: DEFAULT_SETTINGS.signara.baseUrl,
        lastHttp: 200,
        lastError: null,
      },
      template: "course-completion",
      signer,
      hash: "9a4e21c8f70b35d612e8c0a94f7b3d5216ce80fa94b7d3e1026af5c8b90d4e71",
      previewPath: null,
      createdAt: "2026-10-02T12:00:00.000Z",
      updatedAt: "2026-10-02T12:03:00.000Z",
      signedAt: "2026-10-02T12:02:10.000Z",
      issuedAt: "2026-10-02T12:03:00.000Z",
      revokedAt: null,
      revokeReason: null,
      timeline: [
        { at: "2026-10-02T12:00:00.000Z", label: "Eligibility confirmed", detail: "Grade 94" },
        { at: "2026-10-02T12:02:10.000Z", label: "Signed via Signara", detail: "req_91c0be37" },
        { at: "2026-10-02T12:03:00.000Z", label: "Issued to learner record" },
      ],
    },
    {
      id: "cred-seed-3",
      verifyId: "c40a7b19d3e24f6a90b8e1d7",
      type: "degree_conferral",
      title: "Bachelor of Business Administration — Ada Mensah",
      subjectRef: "prog-bba",
      subjectLabel: "Bachelor of Business Administration",
      learner: { username: "ada.mensah", name: "Ada Mensah", email: "ada.mensah@example.edu" },
      evidence: { credits: 120, gpa: "3.72", program: "Business Administration", completedOn: "2027-05-14" },
      status: "queued_local",
      signara: {
        documentId: null,
        requestId: null,
        signerToken: null,
        apiBase: null,
        lastHttp: null,
        lastError: null,
      },
      template: "degree-conferral",
      signer,
      hash: "6d12b904af38c7e5b20d1194a6c7f3801e5b4d9c2a7f60831bd4e5a0917c2fd8",
      previewPath: null,
      createdAt: "2026-11-09T09:30:00.000Z",
      updatedAt: "2026-11-09T09:30:00.000Z",
      signedAt: null,
      issuedAt: null,
      revokedAt: null,
      revokeReason: null,
      timeline: [
        {
          at: "2026-11-09T09:30:00.000Z",
          label: "Staged for conferral",
          detail: "Signara is not configured — the award is held locally",
        },
      ],
    },
  ];

  const seedIdea =
    "A short certificate course that teaches clinic front-desk staff to use AI for patient intake without breaking HIPAA";
  const seedDraft = synthesizeDraft({
    idea: seedIdea,
    audience: "Front-desk staff at independent clinics",
    level: 100,
    credits: 2,
    department: "Health Administration",
    code: "HCA101",
  });

  const sessions: GenSession[] = [
    {
      id: "gen-seed-1",
      idea: seedIdea,
      audience: "Front-desk staff at independent clinics",
      level: 100,
      credits: 2,
      term: "2027_T1",
      department: "Health Administration",
      engine: "rules",
      draft: seedDraft,
      versions: [
        { id: "v-seed-1", at: "2026-11-08T14:05:00.000Z", label: "Initial draft", draft: seedDraft },
      ],
      messages: [
        {
          id: "msg-seed-1",
          role: "assistant",
          at: "2026-11-08T14:05:00.000Z",
          engine: "rules",
          content: `Drafted **${seedDraft.title}** — ${seedDraft.modules.length} modules, ${seedDraft.modules.reduce(
            (n, m) => n + m.lessons.length,
            0,
          )} lessons, ${seedDraft.credits} credits. Tell me what to change: length, rigour, audience, a module to add, the title, the assessment mix.`,
        },
      ],
      courseId: null,
      createdAt: "2026-11-08T14:05:00.000Z",
      updatedAt: "2026-11-08T14:05:00.000Z",
    },
  ];

  return {
    version: 1,
    staff: [],
    accessRequests: [],
    applications: [],
    authLog: [],
    loginSessions: [],
    enrollments: [],
    purchases: [],
    courses: Array.from(courses.values()),
    programs,
    tracks,
    learners,
    completions,
    credentials,
    sessions,
    activity: [
      {
        id: "act-1",
        at: "2026-11-09T09:30:00.000Z",
        kind: "credential.issued",
        message: "Degree conferral staged for Ada Mensah — BBA",
        ref: "prog-bba",
      },
      {
        id: "act-2",
        at: "2026-11-07T16:12:00.000Z",
        kind: "credential.signed",
        message: "FAST AI credential signed through Signara for Marcus Bell",
        ref: "fast-ai",
      },
      {
        id: "act-3",
        at: "2026-11-06T11:00:00.000Z",
        kind: "course.published",
        message: "FAI106 — AI Governance, Risk & Responsible Use published to atheniq.courses",
        ref: courseKey("FAI106", "2026_T4"),
      },
    ],
    settings: DEFAULT_SETTINGS,
  };
}
