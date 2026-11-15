import fs from "node:fs";
import path from "node:path";
import { gzipSync } from "node:zlib";
import { money } from "./format";
import { slugify } from "./seed";
import type {
  CatalogListing,
  Course,
  Database,
  PublishManifest,
  SemesterCourse,
  Settings,
} from "./types";

/* ------------------------------------------------------------------ */
/* helpers                                                             */
/* ------------------------------------------------------------------ */

function esc(value: string): string {
  return value
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

/** Term code → the first day of classes published on the institute site. */
export function termStart(term: string): string {
  const match = term.match(/^(\d{4})_T(\d)$/);
  if (!match) return "2027-01-11";
  const year = match[1];
  const starts: Record<string, string> = {
    T1: `${year}-01-11`,
    T2: `${year}-05-10`,
    T3: `${year}-08-22`,
    T4: `${year}-10-21`,
  };
  return starts[`T${match[2]}`] ?? `${year}-01-11`;
}

export function termLabel(term: string): string {
  const match = term.match(/^(\d{4})_T(\d)$/);
  if (!match) return term;
  return ["Spring", "Summer", "Fall", "Winter"][Number(match[2]) - 1] + ` ${match[1]}`;
}

/* ------------------------------------------------------------------ */
/* LMS listing payload (the shape atheniq.courses serves)              */
/* ------------------------------------------------------------------ */

export function buildListing(course: Course): CatalogListing {
  const start = termStart(course.term);
  return {
    id: course.key,
    name: course.title,
    number: course.code,
    org: course.org,
    short_description: `${course.title}. ${course.summary}\n`.slice(0, 700),
    start: `${start}T00:00:00Z`,
    enrollment_start: `${start}T00:00:00Z`,
    enrollment_end: `${course.term.slice(0, 4)}-12-31T00:00:00Z`,
    pacing: "instructor",
    media: {
      course_image: { uri: course.image },
      banner_image: { uri: course.image },
    },
    price: course.price,
    access: course.price.amountCents
      ? `${money(course.price.amountCents)} USD one-off`
      : course.price.plan
        ? `Magnate \`${course.price.plan}\``
        : "Free",
  };
}

/* ------------------------------------------------------------------ */
/* OLX — the authoring package import-courses.py consumes               */
/* ------------------------------------------------------------------ */

export interface OlxFile {
  path: string;
  content: string;
  bytes: number;
}

export function buildOlx(course: Course): OlxFile[] {
  const run = course.key.split("+").pop() ?? course.term;
  const files: { path: string; content: string }[] = [];

  files.push({
    path: "course.xml",
    content: `<?xml version="1.0" encoding="UTF-8"?>\n<course url_name="${esc(run)}" org="${esc(course.org)}" course="${esc(course.code)}"/>\n`,
  });

  const modules = course.modules.length ? course.modules : [];

  files.push({
    path: `course/${run}.xml`,
    content: [
      '<?xml version="1.0" encoding="UTF-8"?>',
      `<course display_name="${esc(course.title)}" org="${esc(course.org)}" course="${esc(course.code)}" start="${termStart(course.term)}T00:00:00Z">`,
      ...modules.map((_, i) => `  <chapter url_name="c${i + 1}"/>`),
      "  <wiki slug=\"atheniq.${esc(course.code)}\"/>",
      "</course>",
      "",
    ].join("\n"),
  });

  modules.forEach((module, mi) => {
    const n = mi + 1;
    files.push({
      path: `chapter/c${n}.xml`,
      content: `<?xml version="1.0" encoding="UTF-8"?>\n<chapter display_name="${esc(module.title)}">\n  <sequential url_name="s${n}"/>\n</chapter>\n`,
    });
    files.push({
      path: `sequential/s${n}.xml`,
      content: `<?xml version="1.0" encoding="UTF-8"?>\n<sequential display_name="${esc(module.title)}">\n  <vertical url_name="u${n}"/>\n</sequential>\n`,
    });

    const components: string[] = [];
    module.lessons.forEach((lesson, li) => {
      const l = li + 1;
      if (lesson.type === "quiz" || lesson.type === "exam") return;
      components.push(`  <html url_name="l${n}_${l}"/>`);
      files.push({
        path: `html/l${n}_${l}.xml`,
        content: `<?xml version="1.0" encoding="UTF-8"?>\n<html filename="l${n}_${l}" display_name="${esc(lesson.title)}"/>\n`,
      });
      files.push({
        path: `html/l${n}_${l}.html`,
        content: renderLessonHtml(course, module.title, lesson.title, lesson.type, lesson.minutes),
      });
    });

    const quiz = module.lessons.find(
      (lesson) => lesson.type === "quiz" || lesson.type === "exam",
    );
    if (quiz) {
      components.push(`  <problem url_name="q${n}"/>`);
      files.push({
        path: `problem/q${n}.xml`,
        content: renderProblemXml(course, module.title, quiz.type === "exam"),
      });
    }

    files.push({
      path: `vertical/u${n}.xml`,
      content: [
        '<?xml version="1.0" encoding="UTF-8"?>',
        `<vertical display_name="${esc(module.title)}">`,
        ...components,
        "</vertical>",
        "",
      ].join("\n"),
    });
  });

  files.push({
    path: "about/overview.html",
    content: renderOverviewHtml(course),
  });
  files.push({
    path: "about/short_description.html",
    content: `<section class="atheniq-about"><p>${esc(course.summary)}</p></section>\n`,
  });
  files.push({
    path: "assets/assets.xml",
    content: '<?xml version="1.0" encoding="UTF-8"?>\n<assets/>\n',
  });
  files.push({
    path: `policies/${run}/grading_policy.json`,
    content: JSON.stringify(
      {
        GRADER: course.grading.map((g) => ({
          type: g.component,
          min_count: 1,
          drop_count: 0,
          short_label: g.component.split(" ")[0],
          weight: Number((g.weight / 100).toFixed(4)),
        })),
        GRADE_CUTOFFS: { Pass: 0.6, "B": 0.8, "A": 0.9 },
      },
      null,
      2,
    ),
  });

  return files.map((file) => ({
    ...file,
    bytes: Buffer.byteLength(file.content, "utf8"),
  }));
}

function renderLessonHtml(
  course: Course,
  moduleTitle: string,
  lessonTitle: string,
  type: string,
  minutes: number,
): string {
  return `<div class="atheniq-lesson">
  <h2>${esc(lessonTitle)}</h2>
  <p class="atheniq-meta">${esc(course.code)} &middot; ${esc(moduleTitle)} &middot; ${esc(type)} &middot; ${minutes} minutes</p>
  <p>This lesson is part of <strong>${esc(course.title)}</strong>. Read the brief below, then do the task. Graded work is marked against the rubric published in the syllabus.</p>
  <h3>What you will be able to do</h3>
  <ul>
    <li>Explain the concept in your own words, with an example from your own role.</li>
    <li>Apply it to the case in this lesson and show your reasoning.</li>
  </ul>
  <h3>Task</h3>
  <p>Take the scenario you brought to this module, apply ${esc(lessonTitle.toLowerCase())}, and record what you produced and what you would change. Submit it to the module problem set.</p>
  <h3>Before you move on</h3>
  <p>Check your work against the standard: would another practitioner be able to follow what you did? If not, say what is missing.</p>
</div>
`;
}

function renderProblemXml(course: Course, moduleTitle: string, isExam: boolean): string {
  return `<?xml version="1.0" encoding="UTF-8"?>
<problem display_name="${esc(isExam ? "Final examination" : moduleTitle + " check")}">
  <multiplechoiceresponse>
    <label>${esc(course.code)} — ${esc(moduleTitle)}</label>
    <p>Which statement best describes what this module expects you to be able to do?</p>
    <choicegroup type="MultipleChoice">
      <choice correct="false">Recite the definitions without applying them.</choice>
      <choice correct="true">Apply the method to a real case, show the reasoning, and state what would change the conclusion.</choice>
      <choice correct="false">Wait for a colleague to review the work first.</choice>
      <choice correct="false">Use a tool output without checking it against the source.</choice>
    </choicegroup>
    <solution>
      <div class="detailed-solution">
        <p>Explanation</p>
        <p>The course assesses applied judgement: the method, the evidence, and the limits of the conclusion.</p>
      </div>
    </solution>
  </multiplechoiceresponse>
</problem>
`;
}

function renderOverviewHtml(course: Course): string {
  const outcomes = course.outcomes.map((o) => `      <li>${esc(o)}</li>`).join("\n");
  const modules = course.modules
    .map(
      (m, i) =>
        `      <li><strong>${i + 1}. ${esc(m.title)}</strong> — ${esc(m.summary)} <em>${esc(m.assessment)}</em></li>`,
    )
    .join("\n");
  return `<section class="atheniq-overview">
  <h2>${esc(course.title)}</h2>
  <p class="atheniq-meta">${esc(course.code)} &middot; ${course.credits} credits &middot; ${esc(course.department)} &middot; ${esc(termLabel(course.term))}</p>
  <p>${esc(course.description)}</p>
  <h3>What you will achieve</h3>
  <ul>
${outcomes}
  </ul>
  <h3>Course outline</h3>
  <ol>
${modules}
  </ol>
  <h3>Assessment</h3>
  <ul>
${course.grading.map((g) => `      <li>${esc(g.component)} — ${g.weight}%</li>`).join("\n")}
  </ul>
  <p class="atheniq-muted">Pass at 60% for credit. Completion is signed through Signara and issued to your learner record.</p>
</section>
`;
}

/* ------------------------------------------------------------------ */
/* Manifest + checks                                                   */
/* ------------------------------------------------------------------ */

export function buildManifest(course: Course, db: Database): PublishManifest {
  const listing = buildListing(course);
  const olxFiles = buildOlx(course);

  const trackPatches = db.tracks
    .filter((track) => course.trackIds.includes(track.id))
    .map((track) => ({
      trackId: track.id,
      trackTitle: track.title,
      courses: Array.from(new Set([...track.courses, course.key])),
      credential: track.credential,
    }));

  const programPatches = db.programs
    .filter((program) => course.programIds.includes(program.id))
    .map((program) => {
      const existing = program.semesters.find((s) =>
        s.courses.some((c) => c.code === course.code),
      );
      const semester = existing ?? program.semesters[program.semesters.length - 1];
      const courses: SemesterCourse[] = semester
        ? existing
          ? semester.courses
          : [...semester.courses, { code: course.code, title: course.title.replace(`${course.code} — `, "") }]
        : [{ code: course.code, title: course.title }];
      return {
        programId: program.id,
        programName: program.credential,
        semester: semester?.number ?? 1,
        focus: semester?.focus ?? "New coursework",
        courses,
      };
    });

  const checks: PublishManifest["checks"] = [];
  const push = (id: string, label: string, ok: boolean, detail: string) =>
    checks.push({ id, label, ok, detail });

  push(
    "key",
    "Runtime course key",
    /^course-v1:[A-Za-z0-9._-]+\+[A-Z0-9]{2,12}\+[A-Za-z0-9_-]+$/.test(course.key),
    course.key,
  );
  push("title", "Title", course.title.length >= 8 && course.title.length <= 120, `${course.title.length} characters`);
  push(
    "summary",
    "Catalog summary",
    course.summary.length >= 40,
    course.summary.length >= 40 ? `${course.summary.length} characters` : "Needs 40+ characters",
  );
  push(
    "credits",
    "Credit load",
    course.credits >= 1 && course.credits <= 6,
    `${course.credits} credits`,
  );
  push(
    "modules",
    "Curriculum",
    course.modules.length > 0 && course.modules.every((m) => m.lessons.length > 0),
    `${course.modules.length} modules / ${course.modules.reduce((n, m) => n + m.lessons.length, 0)} lessons`,
  );
  const weightTotal = course.grading.reduce((sum, g) => sum + g.weight, 0);
  push("grading", "Grading weights", weightTotal === 100, `${weightTotal}% allocated`);
  push(
    "price",
    "Price and access",
    Boolean(course.price.plan) || Boolean(course.price.amountCents),
    course.price.amountCents
      ? `${money(course.price.amountCents)} USD one-off`
      : course.price.plan
        ? `Magnate plan "${course.price.plan}"`
        : "Free course",
  );
  push(
    "placement",
    "Catalog placement",
    course.programIds.length + course.trackIds.length > 0,
    course.programIds.length + course.trackIds.length > 0
      ? `${course.programIds.length} program(s), ${course.trackIds.length} track(s)`
      : "Not on any program or track",
  );
  push(
    "outcomes",
    "Learning outcomes",
    course.outcomes.length >= 2,
    `${course.outcomes.length} outcomes`,
  );
  push(
    "olx",
    "OLX package",
    olxFiles.length > 0 && olxFiles.every((f) => f.bytes > 0),
    `${olxFiles.length} files, ${(olxFiles.reduce((n, f) => n + f.bytes, 0) / 1024).toFixed(1)} KB`,
  );

  const blocking = checks.filter((c) => !c.ok && c.id !== "placement").map((c) => c.label);
  const warnings = checks.filter((c) => !c.ok && c.id === "placement").map((c) => c.label);

  return {
    courseKey: course.key,
    generatedAt: new Date().toISOString(),
    listing,
    priceEntry: {
      name: course.title,
      plan: course.price.plan,
      amount_cents: course.price.amountCents,
    },
    trackPatches,
    programPatches,
    olxFiles,
    checks,
    blocking,
    warnings,
  };
}

/* ------------------------------------------------------------------ */
/* tar.gz + bundle on disk                                             */
/* ------------------------------------------------------------------ */

function tarHeader(name: string, size: number, mtime: number): Buffer {
  const block = Buffer.alloc(512, 0);
  block.write(name.slice(0, 100), 0, "utf8");
  block.write("0000644\0", 100, "ascii");
  block.write("0000000\0", 108, "ascii");
  block.write("0000000\0", 116, "ascii");
  block.write(`${size.toString(8).padStart(11, "0")}\0`, 124, "ascii");
  block.write(`${mtime.toString(8).padStart(11, "0")}\0`, 136, "ascii");
  block.write("        ", 148, "ascii");
  block.write("0", 156, "ascii");
  block.write("ustar\0", 257, "ascii");
  block.write("00", 263, "ascii");
  let sum = 0;
  for (const byte of block) sum += byte;
  block.write(`${sum.toString(8).padStart(6, "0")}\0 `, 148, "ascii");
  return block;
}

export function tarGz(files: { path: string; content: string }[]): Buffer {
  const mtime = Math.floor(Date.now() / 1000);
  const chunks: Buffer[] = [];
  for (const file of files) {
    const data = Buffer.from(file.content, "utf8");
    chunks.push(tarHeader(file.path, data.length, mtime));
    chunks.push(data);
    const padding = data.length % 512;
    if (padding) chunks.push(Buffer.alloc(512 - padding, 0));
  }
  chunks.push(Buffer.alloc(1024, 0));
  return gzipSync(Buffer.concat(chunks));
}

export interface BundleResult {
  dir: string;
  relativeDir: string;
  archivePath: string;
  manifest: PublishManifest;
}

export function writeBundle(course: Course, manifest: PublishManifest): BundleResult {
  const safeCode = course.code.replace(/[^A-Za-z0-9_-]/g, "");
  const relativeDir = path.posix.join("published", `${safeCode}-${course.term}`);
  const root = path.join(process.cwd(), "data");
  const dir = path.join(root, relativeDir);

  fs.mkdirSync(path.join(dir, "olx"), { recursive: true });
  fs.mkdirSync(path.join(dir, "catalog"), { recursive: true });

  for (const file of manifest.olxFiles) {
    const target = path.join(dir, "olx", file.path);
    fs.mkdirSync(path.dirname(target), { recursive: true });
    fs.writeFileSync(target, file.content, "utf8");
  }

  const archive = tarGz(manifest.olxFiles.map((f) => ({ path: f.path, content: f.content })));
  const archivePath = path.join(dir, `${course.code}-${course.term}.tar.gz`);
  fs.writeFileSync(archivePath, archive);

  fs.writeFileSync(
    path.join(dir, "manifest.json"),
    JSON.stringify(
      {
        ...manifest,
        olxFiles: manifest.olxFiles.map((f) => ({ path: f.path, bytes: f.bytes })),
      },
      null,
      2,
    ),
    "utf8",
  );

  // The exact files the AthenIQ repo commits, as merge-ready patches.
  fs.writeFileSync(
    path.join(dir, "catalog", "course-prices.patch.json"),
    JSON.stringify(
      {
        version: 1,
        subscribe_url: "https://subscribe.atheniq.innotel.us",
        courses: {
          [course.key]: { name: course.title, plan: course.price.plan, amount_cents: course.price.amountCents },
        },
      },
      null,
      2,
    ),
  );

  if (manifest.trackPatches.length) {
    fs.writeFileSync(
      path.join(dir, "catalog", "workforce-tracks.patch.json"),
      JSON.stringify({ version: 1, tracks: manifest.trackPatches }, null, 2),
    );
  }

  if (manifest.programPatches.length) {
    fs.writeFileSync(
      path.join(dir, "catalog", "program-plans.patch.json"),
      JSON.stringify({ version: 1, programs: manifest.programPatches }, null, 2),
    );
  }

  fs.writeFileSync(
    path.join(dir, "catalog", "listing.json"),
    JSON.stringify(manifest.listing, null, 2),
  );

  fs.writeFileSync(
    path.join(dir, "catalog", "olx-import.txt"),
    [
      "# Import into Studio (CMS). The archive is the same tar.gz `make course-import` builds.",
      `python3 scripts/import-courses.py --course ${course.code} --bundle --execute`,
      "",
      `# Or from Studio: Tools -> Import, upload ${path.basename(archivePath)}`,
      "",
      `# Then confirm the catalog entry at ${"https://atheniq.courses/catalog/"}`,
      "",
    ].join("\n"),
  );

  return { dir, relativeDir, archivePath, manifest };
}

/* ------------------------------------------------------------------ */
/* LMS push (only when a token + import URL are configured)            */
/* ------------------------------------------------------------------ */

export interface LmsPushResult {
  attempted: boolean;
  ok: boolean;
  status: number | null;
  detail: string;
}

export async function pushToLms(
  course: Course,
  settings: Settings,
  archive: Buffer,
): Promise<LmsPushResult> {
  if (!settings.lms.importUrl) {
    return {
      attempted: false,
      ok: false,
      status: null,
      detail:
        "No LMS import endpoint configured — the bundle is on disk and the catalog patches are ready to commit.",
    };
  }
  try {
    const boundary = `----atheniqimport${Date.now().toString(16)}`;
    const parts: Buffer[] = [
      Buffer.from(
        `--${boundary}\r\nContent-Disposition: form-data; name="course_id"\r\n\r\n${course.key}\r\n`,
      ),
      Buffer.from(
        `--${boundary}\r\nContent-Disposition: form-data; name="file"; filename="${slugify(course.code)}.tar.gz"\r\nContent-Type: application/gzip\r\n\r\n`,
      ),
      archive,
      Buffer.from(`\r\n--${boundary}--\r\n`),
    ];
    const response = await fetch(settings.lms.importUrl, {
      method: "POST",
      headers: {
        "Content-Type": `multipart/form-data; boundary=${boundary}`,
        ...(settings.lms.apiToken ? { Authorization: `Bearer ${settings.lms.apiToken}` } : {}),
      },
      body: new Uint8Array(Buffer.concat(parts)),
      signal: AbortSignal.timeout(120_000),
    });
    const text = await response.text();
    return {
      attempted: true,
      ok: response.ok,
      status: response.status,
      detail: response.ok
        ? "LMS accepted the import."
        : `LMS returned HTTP ${response.status}: ${text.slice(0, 240)}`,
    };
  } catch (error) {
    const message = error instanceof Error ? error.message : String(error);
    return { attempted: true, ok: false, status: null, detail: `Import failed: ${message}` };
  }
}
