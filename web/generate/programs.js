// AthenIQ programs.
//
// One page, two audiences. A learner sees the catalog, enrols, and watches
// credits, GPA, finals, and the next course they can take. An instructor or
// administrator sees the same page with the controls that build and run a
// program: create it from a template, generate its classrooms semester by
// semester, record grades, and confer the credential.
//
// No framework, no build step. Every value is written with textContent through
// the `el` helper, so a course title with angle brackets stays a title.

const state = {
  me: null,
  templates: [],
  programs: [],
  current: null,      // the program document, with `plan`
  progress: null,     // the selected learner's progress
  student: "",
  open: new Set(),    // semester numbers expanded in the plan
  editing: null,      // the template slug open in the editor, null when new
  originals: new Map(), // course code -> description/classrooms, kept out of the row
};

const el = (tag, props = {}, ...children) => {
  const node = document.createElement(tag);
  for (const [key, value] of Object.entries(props)) {
    if (key === "class") node.className = value;
    else if (key === "dataset") Object.assign(node.dataset, value);
    else if (key.startsWith("on")) node.addEventListener(key.slice(2), value);
    else if (value !== null && value !== undefined && value !== false) node.setAttribute(key, value);
  }
  for (const child of children.flat()) {
    if (child === null || child === undefined || child === false) continue;
    node.append(child.nodeType ? child : document.createTextNode(String(child)));
  }
  return node;
};

const api = async (path, options = {}) => {
  const response = await fetch(path, {
    credentials: "same-origin",
    ...options,
    headers: {
      "X-Atheniq-Console": "1",
      ...(options.body ? { "Content-Type": "application/json" } : {}),
      ...(options.headers || {}),
    },
  });
  const text = await response.text();
  let payload = null;
  try { payload = text ? JSON.parse(text) : null; } catch (_) { payload = { error: text }; }
  if (!response.ok) {
    const error = new Error((payload && payload.error) || `request failed (${response.status})`);
    error.status = response.status;
    throw error;
  }
  return payload;
};

let toastTimer = null;
const toast = (message, kind = "ok") => {
  const box = document.getElementById("toast");
  box.textContent = message;
  box.dataset.kind = kind;
  box.hidden = false;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => { box.hidden = true; }, kind === "bad" ? 9000 : 5000);
};

const isStaff = () => Boolean(state.me && state.me.mayGenerate);
const badge = (text, kind = "") => el("span", { class: `badge ${kind}`.trim() }, text);

// A workforce certificate is awarded without credit hours, so its scope is its
// courses, not a credit count it never had. Degrees are unchanged.
const scopeLine = (doc) => {
  const terms = `${doc.semesters} ${doc.semesters === 1 ? "term" : "semesters"}`;
  const courses = `${doc.courses} courses`;
  return doc.totalCredits ? `${terms} · ${courses} · ${doc.totalCredits} credits` : `${terms} · ${courses}`;
};
const num = (value) => (value === null || value === undefined ? "—" : String(value));

// -- catalog ---------------------------------------------------------------

const templateCard = (template) => el("button", {
  class: "program-card", type: "button",
  onclick: () => startFromTemplate(template.slug),
},
  el("span", { class: "program-kind" }, template.credentialKind === "degree" ? "Degree" : "Certificate"),
  el("span", { class: "program-name" }, template.name),
  el("span", { class: "program-credential" }, template.credential),
  el("span", { class: "program-meta" }, scopeLine(template)),
  el("span", { class: "program-desc" }, template.description),
  template.certificates && template.certificates.length
    ? el("span", { class: "program-certs" }, `Includes ${template.certificates.join(", ")}`)
    : null,
  el("span", { class: "program-cta" }, isStaff() ? "Create this program →" : "View curriculum →"),
);

const programCard = (program) => el("button", {
  class: "program-card live", type: "button",
  onclick: () => openProgram(program.id),
},
  el("span", { class: "program-kind" }, program.credentialKind === "degree" ? "Degree" : "Certificate"),
  el("span", { class: "program-name" }, program.name),
  el("span", { class: "program-credential" }, program.credential),
  el("span", { class: "program-meta" }, scopeLine(program)),
  el("span", { class: "program-meta" },
    `${program.generated}/${program.courses} classrooms generated · `
    + `${program.built || 0} with lessons · ${program.enrolled} enrolled`),
  el("span", { class: "program-cta" }, "Open program →"),
);

const renderCatalog = () => {
  const host = document.getElementById("catalog");
  host.replaceChildren();
  document.getElementById("counts").textContent =
    `${state.programs.length} running · ${state.templates.length} templates`;

  if (state.programs.length) {
    host.append(el("h2", { class: "group-h" }, "Running programs"));
    const grid = el("div", { class: "program-grid" });
    for (const program of state.programs) grid.append(programCard(program));
    host.append(grid);
  }
  host.append(el("h2", { class: "group-h" }, "Catalog"));
  const grid = el("div", { class: "program-grid" });
  for (const template of state.templates) grid.append(templateCard(template));
  host.append(grid);

  const programSelect = document.getElementById("enroll-program");
  const chosen = programSelect.value;
  programSelect.replaceChildren();
  for (const program of state.programs) {
    programSelect.append(el("option", { value: program.id }, `${program.name} — ${program.credential}`));
  }
  if (chosen) programSelect.value = chosen;
  if (!state.programs.length) {
    programSelect.append(el("option", { value: "" }, "No program is running yet"));
  }
  const templateSelect = document.getElementById("create-template");
  const templatesChosen = templateSelect.value;
  templateSelect.replaceChildren();
  for (const template of state.templates) {
    templateSelect.append(el("option", { value: template.slug }, `${template.name} — ${template.credential}`));
  }
  if (templatesChosen) templateSelect.value = templatesChosen;
};

// -- catalog templates -------------------------------------------------------

const FINALS = ["comprehensive", "practical", "project", "portfolio", "none"];
const KINDS = ["core", "general-education", "elective", "clinical", "capstone"];

const templateRow = (template) => el("div", { class: "template-item" },
  el("div", { class: "template-item-main" },
    el("div", { class: "template-item-name" }, template.name),
    el("div", { class: "template-item-sub" }, template.credential),
    el("div", { class: "template-item-sub" }, scopeLine(template)),
  ),
  el("div", { class: "template-item-actions" },
    template.edited ? badge("edited here", "ready") : badge("shipped"),
    el("button", {
      class: "btn btn-secondary btn-small", type: "button",
      onclick: () => openTemplateEditor(template.slug),
    }, "Edit"),
    el("button", {
      class: "btn btn-secondary btn-small", type: "button",
      onclick: () => deleteTemplate(template.slug),
    }, "Remove"),
  ),
);

const renderTemplates = () => {
  const host = document.getElementById("template-list");
  if (!host) return;
  host.replaceChildren();
  if (!state.templates.length) {
    host.append(el("p", { class: "empty" }, "The catalog has no templates yet."));
    return;
  }
  for (const template of state.templates) host.append(templateRow(template));
};

const selectField = (field, values, current) => el("select", { "data-field": field },
  ...values.map((value) => {
    const option = el("option", { value }, value);
    if (value === current) option.selected = true;
    return option;
  }));

const inputField = (field, props, value) => el("input", {
  "data-field": field, type: "text", ...props, value: value || "",
});

const courseEditorRow = (course) => el("div", { class: "template-course" },
  inputField("code", { placeholder: "CJ101", "aria-label": "Course code", maxlength: "12" }, course.code),
  inputField("title", { placeholder: "Introduction to Criminal Justice",
                        "aria-label": "Course title", maxlength: "160" }, course.title),
  el("input", { "data-field": "credits", type: "number", min: "1", max: "12", step: "1",
                "aria-label": "Credits", value: course.credits === undefined ? 3 : course.credits }),
  inputField("prerequisites", { placeholder: "prerequisites, comma separated",
                               "aria-label": "Prerequisites", maxlength: "200" },
             (course.prerequisites || []).join(", ")),
  selectField("finalExam", FINALS, course.finalExam || course.final_exam || "comprehensive"),
  selectField("kind", KINDS, course.kind || "core"),
  el("button", {
    class: "link", type: "button",
    onclick: (event) => {
      event.currentTarget.closest(".template-course").remove();
      tallyTemplate();
    },
  }, "Remove"),
);

const semesterEditor = (semester, number) => {
  const courses = el("div", { class: "template-courses" },
    ...((semester && semester.courses) || []).map(courseEditorRow));
  const block = el("div", { class: "template-semester" },
    el("div", { class: "template-semester-head" },
      el("span", { class: "template-semester-name" }, `Semester ${number}`),
      el("button", {
        class: "link", type: "button",
        onclick: (event) => {
          event.currentTarget.closest(".template-semester").remove();
          renumberSemesters();
        },
      }, "Remove semester"),
    ),
    el("label", {}, "Term name"),
    inputField("name", { placeholder: `Semester ${number}`, maxlength: "80" },
               (semester && semester.name) || ""),
    courses,
    el("button", {
      class: "btn btn-secondary btn-small", type: "button",
      onclick: (event) => {
        event.currentTarget.previousElementSibling
          .append(courseEditorRow({ credits: 3 }));
        tallyTemplate();
      },
    }, "Add course"),
  );
  return block;
};

const renumberSemesters = () => {
  const blocks = document.querySelectorAll("#tpl-semesters .template-semester");
  blocks.forEach((block, index) => {
    block.querySelector(".template-semester-name").textContent = `Semester ${index + 1}`;
  });
  tallyTemplate();
};

// The running total is the point of the form: credits are what the credential
// says it awards, and a typo here is a program that cannot confer.
const tallyTemplate = () => {
  let credits = 0;
  let courses = 0;
  for (const row of document.querySelectorAll("#tpl-semesters .template-course")) {
    const code = row.querySelector('[data-field="code"]').value.trim();
    if (!code) continue;
    courses += 1;
    credits += Number(row.querySelector('[data-field="credits"]').value || 0);
  }
  const tally = document.getElementById("tpl-tally");
  if (tally) tally.textContent = `${courses} courses · ${credits} credits`;
};

const openTemplateEditor = async (slug) => {
  const form = document.getElementById("template-form");
  const hint = document.getElementById("tpl-hint");
  state.editing = slug || null;
  state.originals = new Map();
  let template = { name: "", credential: "", level: "custom", credentialKind: "degree",
                   minGpa: 2.0, capstone: "", description: "", semesters: [{ name: "", courses: [] }] };
  if (slug) {
    try {
      template = await api(`/api/templates/${encodeURIComponent(slug)}`);
    } catch (error) {
      toast(error.message, "bad");
      return;
    }
    for (const semester of template.semesters || []) {
      for (const course of semester.courses || []) {
        state.originals.set(course.code, {
          description: course.description || "", classrooms: course.classrooms || 4,
        });
      }
    }
  }
  document.getElementById("tpl-name").value = template.name || "";
  document.getElementById("tpl-credential").value = template.credential || "";
  document.getElementById("tpl-level").value = template.level || "custom";
  document.getElementById("tpl-kind").value = template.credentialKind || "degree";
  document.getElementById("tpl-min-gpa").value = template.minGpa === undefined ? 2.0 : template.minGpa;
  document.getElementById("tpl-capstone").value = template.capstone || "";
  document.getElementById("tpl-description").value = template.description || "";
  const semesters = document.getElementById("tpl-semesters");
  semesters.replaceChildren();
  const list = (template.semesters || []).length ? template.semesters : [{ name: "", courses: [] }];
  list.forEach((semester, index) => semesters.append(semesterEditor(semester, index + 1)));
  hint.textContent = slug ? `editing ${slug}` : "a new template";
  form.hidden = false;
  form.scrollIntoView({ behavior: "smooth", block: "start" });
  tallyTemplate();
};

const closeTemplateEditor = () => {
  state.editing = null;
  document.getElementById("template-form").hidden = true;
};

const collectTemplate = () => {
  const semesters = [...document.querySelectorAll("#tpl-semesters .template-semester")]
    .map((block, index) => ({
      name: block.querySelector('[data-field="name"]').value.trim() || `Semester ${index + 1}`,
      courses: [...block.querySelectorAll(".template-course")].map((row) => {
        const field = (name) => row.querySelector(`[data-field="${name}"]`).value.trim();
        const code = field("code").toUpperCase();
        const original = state.originals.get(code) || {};
        return {
          code,
          title: field("title") || code,
          credits: Number(field("credits") || 3),
          prerequisites: field("prerequisites").split(",")
            .map((value) => value.trim().toUpperCase()).filter(Boolean),
          finalExam: field("finalExam"),
          kind: field("kind"),
          description: original.description || "",
          classrooms: original.classrooms || 4,
        };
      }).filter((course) => course.code),
    }))
    .filter((semester) => semester.courses.length);
  return {
    name: document.getElementById("tpl-name").value.trim(),
    credential: document.getElementById("tpl-credential").value.trim(),
    level: document.getElementById("tpl-level").value,
    credentialKind: document.getElementById("tpl-kind").value,
    minGpa: Number(document.getElementById("tpl-min-gpa").value || 2.0),
    capstone: document.getElementById("tpl-capstone").value.trim(),
    description: document.getElementById("tpl-description").value.trim(),
    semesters,
  };
};

const saveTemplate = async (event) => {
  event.preventDefault();
  const body = collectTemplate();
  if (!body.name) { toast("A template needs a name", "bad"); return; }
  if (!body.semesters.length) { toast("A template needs at least one course", "bad"); return; }
  const button = document.getElementById("tpl-save");
  button.disabled = true;
  try {
    const answer = state.editing
      ? await api(`/api/templates/${encodeURIComponent(state.editing)}`,
                  { method: "PUT", body: JSON.stringify(body) })
      : await api("/api/templates", { method: "POST", body: JSON.stringify(body) });
    toast(`${answer.name} saved — ${answer.semesters.length} semesters, ${answer.totalCredits} credits`);
    closeTemplateEditor();
    await loadPrograms();
    renderTemplates();
  } catch (error) {
    toast(error.message, "bad");
  } finally {
    button.disabled = false;
  }
};

const deleteTemplate = async (slug) => {
  if (!window.confirm(`Remove the ${slug} template from the catalog?\n\nPrograms already created from it are unaffected.`)) return;
  try {
    await api(`/api/templates/${encodeURIComponent(slug)}`, { method: "DELETE" });
    toast(`${slug} removed from the catalog`);
    await loadPrograms();
    renderTemplates();
  } catch (error) {
    toast(error.message, "bad");
  }
};

// -- detail ------------------------------------------------------------------

const semesterStatus = (semester) => {
  const row = (state.progress && state.progress.semesters || []).find((s) => s.number === semester.number);
  return row || { number: semester.number, state: "not-started", completed: 0, total: semester.courses.length };
};

const courseState = (course) => {
  if (!state.progress) return { label: "planned", kind: "" };
  const done = (state.progress.completed || []).some((c) => c.code === course.code);
  if (done) return { label: "complete", kind: "ok" };
  const available = (state.progress.available || []).some((c) => c.code === course.code);
  if (available) return { label: "available", kind: "ready" };
  return { label: "locked", kind: "locked" };
};

const courseRow = (course, semester) => {
  const detail = courseState(course);
  const prereq = (course.prerequisites || []).length
    ? el("span", { class: "prereq" }, `prerequisite: ${course.prerequisites.join(", ")}`)
    : el("span", { class: "prereq" }, "no prerequisite");
  const finalType = course.final && course.final.type ? course.final.type : course.finalExam;
  const lessons = course.lessons && typeof course.lessons === "object" ? course.lessons : null;
  const standing = progressRow(course.code);
  return el("div", { class: "course-row" },
    el("div", { class: "course-main" },
      el("div", { class: "course-title" },
        el("code", {}, course.code), ` ${course.title}`),
      el("div", { class: "course-sub" },
        `${course.credits} credits · ${course.kind || "core"} · final: ${finalType}`),
      el("div", { class: "course-sub" }, prereq),
      isStaff() ? gradeControl(course) : null,
    ),
    el("div", { class: "course-side" },
      badge(detail.label, detail.kind),
      course.classroomIds && course.classroomIds.length
        ? el("span", { class: "course-sub" }, `${course.classroomIds.length} classroom${course.classroomIds.length === 1 ? "" : "s"}`)
        : el("span", { class: "course-sub" }, "not generated"),
      lessons
        ? el("span", { class: "course-sub" },
            `${lessons.count} lesson${lessons.count === 1 ? "" : "s"} · `
            + `${lessons.questions} graded question${lessons.questions === 1 ? "" : "s"}`)
        : el("span", { class: "course-sub" }, "no lessons in the LMS yet"),
      standing
        ? el("span", { class: "course-sub" },
            `${standing.score === null || standing.score === undefined ? "—" : standing.score + "%"}`
            +      ` · ${standing.source === "lms" ? "LMS grade" : "office grade"}`)
        : null,
      isStaff() ? el("button", {
        class: "link", type: "button",
        title: "Remove this course, its classrooms and its course in the LMS",
        onclick: (event) => removeCourse(course, event.currentTarget),
      }, "Remove course") : null,
    ),
  );
};

// Removing a course is a curriculum change, so the classes and the LMS course
// that existed for it go too — a course nobody teaches should not stay
// enrollable. A course another course requires asks first, and says which one.
const removeCourse = async (course, button) => {
  if (!state.current) return;
  const confirmText = `Remove ${course.code} ${course.title} from ${state.current.name}?\n\n`
    + "Its generated classrooms and its course in the LMS are deleted with it.";
  if (!window.confirm(confirmText)) return;
  const path = `/api/programs/${state.current.id}/courses/${encodeURIComponent(course.code)}`;
  button.disabled = true;
  try {
    let answer;
    try {
      answer = await api(path, { method: "DELETE" });
    } catch (error) {
      if (error.status !== 409) throw error;
      if (!window.confirm(`${error.message}\n\nRemove ${course.code} anyway and drop that requirement?`)) {
        button.disabled = false;
        return;
      }
      answer = await api(`${path}?force=1`, { method: "DELETE" });
    }
    const classes = (answer.classrooms && answer.classrooms.deleted || []).length;
    const lms = (answer.lms && answer.lms.deleted || []).length;
    toast(`${course.code} removed · ${classes} classroom(s), ${lms} LMS course(s) deleted`);
    await loadPrograms();
    await refreshDetail();
  } catch (error) {
    toast(error.message, "bad");
    button.disabled = false;
  }
};

// The learner's standing in one course, with where the mark came from.
const progressRow = (code) => {
  const progress = state.progress;
  if (!progress) return null;
  return (progress.completed || []).find((row) => row.code === code)
    || (progress.failed || []).find((row) => row.code === code)
    || (progress.remaining || []).find((row) => row.code === code && row.score !== null)
    || null;
};

const gradeControl = (course) => {
  if (!state.current || !state.student) return null;
  const input = el("input", {
    type: "number", min: "0", max: "100", step: "1", class: "score-input",
    placeholder: "grade", "aria-label": `Grade for ${course.code}`,
  });
  const passed = el("input", { type: "checkbox", class: "final-input", "aria-label": `Final passed for ${course.code}` });
  passed.checked = true;
  const button = el("button", {
    class: "btn btn-secondary btn-small", type: "button",
    onclick: async (event) => {
      const node = event.currentTarget;
      node.disabled = true;
      try {
        await api(`/api/programs/${state.current.id}/complete`, {
          method: "POST",
          body: JSON.stringify({
            student: state.student, course: course.code,
            score: input.value === "" ? 0 : Number(input.value),
            finalPassed: passed.checked,
          }),
        });
        toast(`${course.code} recorded`);
        await refreshDetail();
      } catch (error) {
        toast(error.message, "bad");
        node.disabled = false;
      }
    },
  }, "Record");
  return el("div", { class: "grade-row" },
    input, el("label", { class: "grade-label" }, passed, " final passed"), button);
};

const semesterBlock = (semester) => {
  const status = semesterStatus(semester);
  const open = state.open.has(semester.number);
  const body = el("div", { class: "semester-body" });
  if (open) for (const course of semester.courses) body.append(courseRow(course, semester));

  const generate = isStaff() ? el("button", {
    class: "btn btn-secondary btn-small", type: "button",
    onclick: async (event) => {
      const node = event.currentTarget;
      node.disabled = true;
      node.textContent = "starting…";
      try {
        const answer = await api(`/api/programs/${state.current.id}/generate`, {
          method: "POST", body: JSON.stringify({ semester: semester.number }),
        });
        const started = (answer.started || []).length;
        toast(started
          ? `Started ${started} classroom run${started === 1 ? "" : "s"} for ${semester.name}`
          : `Nothing started${answer.blocked ? " — " + answer.blocked : ""}`,
          started ? "ok" : "bad");
        await loadPrograms();
        await refreshDetail();
      } catch (error) {
        toast(error.message, "bad");
      } finally {
        node.disabled = false;
        node.textContent = "Generate semester";
      }
    },
  }, "Generate semester") : null;

  return el("div", { class: "semester", dataset: { open: open ? "1" : "0" } },
    el("div", { class: "semester-head" },
      el("button", {
        class: "semester-toggle", type: "button", "aria-expanded": open ? "true" : "false",
        onclick: () => {
          if (state.open.has(semester.number)) state.open.delete(semester.number);
          else state.open.add(semester.number);
          renderDetail();
        },
      },
        el("span", { class: "chev" }, "▸"),
        el("span", { class: "semester-name" }, `Semester ${semester.number} — ${semester.name}`),
        el("span", { class: "semester-tally" },
          `${status.completed}/${status.total} complete · ${semester.credits} credits`),
      ),
      status.state === "complete" ? badge("complete", "ok")
        : status.state === "in-progress" ? badge("in progress", "ready")
        : badge("not started", "locked"),
      generate),
    body);
};

// The LMS holds the courses a learner can actually enroll in, so "is this
// program real there" is a fact the page states rather than implies.
const lmsBadge = (doc) => {
  const lms = doc.lms || {};
  if (!lms.available) return badge("LMS: publishing off", "locked");
  const total = lms.courses || 0;
  const done = lms.published || 0;
  return badge(`LMS: ${done}/${total} courses`, done === total ? "ok" : "ready");
};

// How much of the curriculum is real courseware — lessons written into the LMS,
// not just a classroom id in a JSON file.
const lessonsBadge = (doc) => {
  const courses = (doc.plan && doc.plan.semesters || [])
    .flatMap((semester) => semester.courses || []);
  const built = courses.filter((course) => (course.lessons || {}).count).length;
  const questions = courses.reduce((total, course) =>
    total + ((course.lessons || {}).questions || 0), 0);
  if (!built) return badge("lessons: none in the LMS", "locked");
  return badge(`${built} course${built === 1 ? "" : "s"} with lessons · ${questions} graded questions`,
               built === courses.length ? "ok" : "ready");
};

const publishProgram = async (doc, button) => {
  button.disabled = true;
  button.textContent = "publishing…";
  try {
    const answer = await api(`/api/programs/${doc.id}/publish`, { method: "POST", body: "{}" });
    toast(answer.alreadyRunning
      ? "A publish run is already working through this program"
      : "Creating the missing courses in the LMS…");
    // Each course is a CMS import, so this finishes in minutes, not milliseconds.
    for (let attempt = 0; attempt < 150; attempt += 1) {
      await new Promise((resolve) => setTimeout(resolve, 2000));
      const fresh = await api(`/api/programs/${encodeURIComponent(doc.id)}`);
      state.current = fresh;
      renderDetail();
      const run = fresh.lms && fresh.lms.run;
      if (run && !run.running) {
        const failed = run.failed || [];
        toast(failed.length
          ? `${run.published} published · ${failed.length} failed — ${failed[0].code}: ${failed[0].error}`
          : `${run.published} course${run.published === 1 ? "" : "s"} now in the LMS`,
          failed.length ? "bad" : "ok");
        return;
      }
    }
    toast("Still publishing — reopen the program to see where it got to", "bad");
  } catch (error) {
    toast(error.message, "bad");
  } finally {
    button.disabled = false;
    button.textContent = "Publish to LMS";
  }
};

// Lessons are written into the LMS course by course, so the page starts the job
// and watches the program until every course with a classroom has been built.
const buildLessons = async (doc, button) => {
  button.disabled = true;
  button.textContent = "building…";
  try {
    await api(`/api/programs/${doc.id}/lessons`, { method: "POST", body: "{}" });
    toast("Writing each generated classroom's lessons into its course…");
    for (let attempt = 0; attempt < 150; attempt += 1) {
      await new Promise((resolve) => setTimeout(resolve, 2000));
      const fresh = await api(`/api/programs/${encodeURIComponent(doc.id)}`);
      state.current = fresh;
      renderDetail();
      const run = fresh.lessonsRun;
      if (run && !run.running) {
        const failed = run.failed || [];
        toast(failed.length
          ? `${run.lessons} lesson(s) built · ${failed.length} course(s) failed — ${failed[0].code}: ${failed[0].error}`
          : `${run.lessons} lesson(s) and ${run.questions} graded question(s) are in the LMS`,
          failed.length ? "bad" : "ok");
        return;
      }
    }
    toast("Still building lessons — reopen the program to see where it got to", "bad");
  } catch (error) {
    toast(error.message, "bad");
  } finally {
    button.disabled = false;
    button.textContent = "Build lessons";
  }
};

// Completion is a fact about graded work, so it is pulled from the LMS's own
// gradebook rather than typed in. An office can still record a grade by hand.
const pullGrades = async (doc, button) => {
  button.disabled = true;
  button.textContent = "pulling…";
  try {
    const answer = await api(`/api/programs/${doc.id}/grades`, { method: "POST", body: "{}" });
    const skipped = (answer.skipped || []).length;
    toast(answer.recorded.length
      ? `${answer.recorded.length} course grade(s) read from the LMS`
        + (skipped ? ` · ${skipped} without a grade yet` : "")
      : `No grades in the LMS yet${skipped ? ` (${skipped} course(s) awaiting work)` : ""}`,
      answer.recorded.length ? "ok" : "bad");
    await refreshDetail();
  } catch (error) {
    toast(error.message, "bad");
  } finally {
    button.disabled = false;
    button.textContent = "Pull LMS grades";
  }
};

const stat = (label, value, note) => el("div", { class: "stat" },
  el("div", { class: "stat-value" }, value),
  el("div", { class: "stat-label" }, label),
  note ? el("div", { class: "stat-note" }, note) : null);

const progressPanel = () => {
  const progress = state.progress;
  if (!progress) {
    return el("p", { class: "empty" }, "Enroll below to see credits, GPA, finals, and what you can take next.");
  }
  const confer = isStaff() ? el("button", {
    class: "btn btn-primary", type: "button", disabled: progress.conferred ? true : !progress.eligible,
    onclick: async (event) => {
      const node = event.currentTarget;
      node.disabled = true;
      try {
        const answer = await api(`/api/programs/${state.current.id}/confer`, {
          method: "POST", body: JSON.stringify({ student: state.student }),
        });
        toast(`${answer.conferred.credential} conferred — ${answer.conferred.student}`);
        await refreshDetail();
      } catch (error) {
        toast(error.message, "bad");
        node.disabled = false;
      }
    },
  }, progress.conferred ? "Credential conferred" : "Confer credential") : null;

  return el("div", { class: "progress" },
    el("div", { class: "stat-grid" },
      progress.creditsRequired
        ? stat("credits earned", `${progress.creditsEarned} / ${progress.creditsRequired}`,
               `${progress.creditsRemaining} to go`)
        : null,
      stat("GPA", progress.gpa.toFixed(2),
           `minimum ${progress.minGpa}`),
      stat("courses complete", `${(progress.completed || []).length}`,
           `${(progress.remaining || []).length} remaining`),
      stat("finals passed", `${(progress.finals || []).filter((f) => f.passed).length}`,
           `${(progress.finals || []).length} scheduled`),
    ),
    (progress.certificates || []).length
      ? el("div", { class: "certs" },
          el("span", { class: "certs-label" }, "Certificates earned:"),
          ...progress.certificates.map((cert) => badge(cert.name, "ok")))
      : null,
    progress.conferred
      ? el("div", { class: "conferred" },
          el("b", {}, `${progress.conferred.credential} conferred`),
          ` on ${progress.conferred.conferredAt} · GPA ${progress.conferred.gpa}`,
          progress.conferred.credits ? ` · ${progress.conferred.credits} credits` : "")
      : el("div", { class: "confer-row" },
          el("div", {},
            progress.eligible
              ? el("span", { class: "eligible" }, "Every requirement is met.")
              : el("ul", { class: "blockers" },
                  ...progress.blockers.map((line) => el("li", {}, line)))),
          confer),
    (progress.available || []).length
      ? el("div", { class: "available" },
          el("div", { class: "group-h" }, "Available next"),
          el("div", { class: "chip-row" },
            ...progress.available.slice(0, 12).map((course) =>
              el("span", { class: "chip", title: course.title }, course.code))))
      : null,
    (progress.finals || []).length
      ? el("details", { class: "finals" },
          el("summary", {}, `Final examinations (${progress.finals.length})`),
          el("div", { class: "final-grid" },
            ...progress.finals.map((final) => el("div", { class: "final-row" },
              el("code", {}, final.code),
              el("span", { class: "final-label" }, final.label),
              el("span", { class: "final-meta" },
                `semester ${final.semester} · weight ${final.weight}% · `,
                final.passed ? "passed" : final.score !== null ? "not passed" : "scheduled")))))
      : null,
  );
};

const studentBar = () => {
  const input = el("input", { type: "email", value: state.student, placeholder: "learner@example.org",
                              "aria-label": "Learner identity" });
  return el("div", { class: "student-bar" },
    el("label", {}, "Learner"),
    input,
    el("button", {
      class: "btn btn-secondary", type: "button",
      onclick: async () => {
        state.student = input.value.trim();
        if (!state.student) { toast("Enter a learner identity", "bad"); return; }
        await loadProgress();
      },
    }, "Load progress"),
  );
};

const renderDetail = () => {
  const host = document.getElementById("detail");
  const doc = state.current;
  host.replaceChildren();
  if (!doc) return;
  const plan = doc.plan || { semesters: [], finals: [] };

  host.append(el("div", { class: "detail-head" },
    el("div", {},
      el("h2", {}, doc.name),
      el("div", { class: "program-credential" }, doc.credential),
      el("div", { class: "badge-row" },
        badge(doc.totalCredits ? `${doc.totalCredits} credits` : "no credit hours"),
        badge(`${plan.semesters.length} semesters`),
        badge(`${plan.finals.length} final examinations`),
        badge(`minimum GPA ${doc.minGpa}`),
        doc.startTerm ? badge(doc.startTerm) : null,
        doc.credentialKind === "certificate" ? badge("certificate", "ok") : badge("degree", "ok"),
        lmsBadge(doc),
        lessonsBadge(doc),
      ),
      el("p", { class: "sub" }, doc.description),
      (doc.certificates || []).length
        ? el("p", { class: "sub" },
            el("b", {}, "Stackable certificates: "),
            doc.certificates.map((cert) =>
              `${cert.name} (after semester ${cert.afterSemester})`).join(" · "))
        : null,
    ),
    isStaff() ? el("div", { class: "detail-actions" },
      el("button", {
        class: "btn btn-primary", type: "button",
        disabled: !(doc.lms || {}).available,
        title: (doc.lms || {}).available
          ? "Create every missing course in the LMS so learners can enroll and it lists in Explore courses"
          : "Publishing to the LMS is off on this console",
        onclick: (event) => publishProgram(doc, event.currentTarget),
      }, "Publish to LMS"),
      el("button", {
        class: "btn btn-primary", type: "button",
        onclick: async (event) => {
          const node = event.currentTarget;
          node.disabled = true;
          node.textContent = "starting…";
          try {
            const answer = await api(`/api/programs/${doc.id}/generate`, {
              method: "POST", body: JSON.stringify({}),
            });
            const started = (answer.started || []).length;
            toast(started
              ? `Started ${started} classroom run${started === 1 ? "" : "s"} across ${answer.queued} courses`
              : `Nothing started${answer.blocked ? " — " + answer.blocked : ""}`,
              started ? "ok" : "bad");
            await loadPrograms();
            await refreshDetail();
          } catch (error) {
            toast(error.message, "bad");
          } finally {
            node.disabled = false;
            node.textContent = "Generate whole program";
          }
        },
      }, "Generate whole program"),
      el("button", {
        class: "btn btn-secondary", type: "button",
        onclick: async (event) => {
          const node = event.currentTarget;
          node.disabled = true;
          try {
            const answer = await api(`/api/programs/${doc.id}/sync`, { method: "POST", body: "{}" });
            toast(`${(answer.recorded || []).length} classroom(s) recorded into the plan`);
            await loadPrograms();
            await refreshDetail();
          } catch (error) {
            toast(error.message, "bad");
          } finally {
            node.disabled = false;
          }
        },
      }, "Sync runs"),
      el("button", {
        class: "btn btn-secondary", type: "button",
        disabled: !(doc.lms || {}).available,
        title: "Write each generated classroom's lessons and graded final examination into its LMS course",
        onclick: (event) => buildLessons(doc, event.currentTarget),
      }, "Build lessons"),
      el("button", {
        class: "btn btn-secondary", type: "button",
        disabled: !(doc.lms || {}).available,
        title: "Read every learner's course grade from the LMS and record it as the completion",
        onclick: (event) => pullGrades(doc, event.currentTarget),
      }, "Pull LMS grades"),
      el("button", {
        class: "btn btn-secondary", type: "button",
        onclick: async (event) => {
          if (!window.confirm(`Regenerate every generated classroom in ${doc.name}?\n\nGrades, enrollments and conferrals are kept; the classroom ids are cleared and queued again.`)) return;
          const node = event.currentTarget;
          node.disabled = true;
          node.textContent = "queueing…";
          try {
            const answer = await api(`/api/programs/${doc.id}/regenerate`, {
              method: "POST", body: JSON.stringify({}),
            });
            const started = (answer.started || []).length;
            toast(started
              ? `Cleared ${(answer.cleared || []).length} and started ${started} run${started === 1 ? "" : "s"}`
              : `Nothing started${answer.blocked ? " — " + answer.blocked : ""}`,
              started ? "ok" : "bad");
            await loadPrograms();
            await refreshDetail();
          } catch (error) {
            toast(error.message, "bad");
          } finally {
            node.disabled = false;
            node.textContent = "Regenerate";
          }
        },
      }, "Regenerate"),
      el("button", {
        class: "btn btn-secondary", type: "button",
        onclick: async (event) => {
          const name = window.prompt("Program name", doc.name);
          if (name === null) return;
          const credential = window.prompt("Credential awarded", doc.credential);
          if (credential === null) return;
          const node = event.currentTarget;
          node.disabled = true;
          try {
            await api(`/api/programs/${doc.id}`, {
              method: "PATCH",
              body: JSON.stringify({ name: name.trim(), credential: credential.trim() }),
            });
            toast("Program updated");
            await loadPrograms();
            await refreshDetail();
          } catch (error) {
            toast(error.message, "bad");
          } finally {
            node.disabled = false;
          }
        },
      }, "Edit"),
      el("button", {
        class: "btn btn-secondary", type: "button",
        onclick: async (event) => {
          const courses = (doc.plan && doc.plan.semesters || [])
            .reduce((total, semester) => total + semester.courses.length, 0);
          if (!window.confirm(`Delete ${doc.name}?\n\nIts ${courses} courses, the classrooms generated for them and their courses in the LMS are deleted too. This cannot be undone.`)) return;
          const node = event.currentTarget;
          node.disabled = true;
          try {
            const answer = await api(`/api/programs/${doc.id}`, { method: "DELETE" });
            const classes = (answer.classrooms && answer.classrooms.deleted || []).length;
            const lms = (answer.lms && answer.lms.deleted || []).length;
            const kept = (answer.kept || []).length;
            toast(`${doc.name} deleted · ${(answer.courses || []).length} courses, ${classes} classroom(s), ${lms} LMS course(s)`
              + (kept ? ` · ${kept} kept, another program teaches them` : ""));
            state.current = null;
            state.progress = null;
            document.getElementById("detail-wrap").hidden = true;
            await loadPrograms();
          } catch (error) {
            toast(error.message, "bad");
            node.disabled = false;
          }
        },
      }, "Delete"),
    ) : null,
  ));

  host.append(studentBar());
  host.append(el("div", { class: "panel-sub" }, el("h3", {}, "Progress"), progressPanel()));

  host.append(el("div", { class: "panel-sub" },
    el("h3", {}, "Curriculum"),
    el("p", { class: "sub" }, isStaff()
      ? "Generate a semester to create its classrooms, then Sync runs and Build lessons to put each lesson and a graded final examination into its LMS course. Pull LMS grades records completion from work the learner actually did; the credential is conferred here only when every requirement is met."
      : "Every course in sequence, with its prerequisites and final assessment."),
    ...plan.semesters.map(semesterBlock),
  ));
};

// -- actions -----------------------------------------------------------------

const refreshDetail = async () => {
  if (!state.current) return;
  const doc = await api(`/api/programs/${state.current.id}`);
  state.current = doc;
  if (state.student) await loadProgress();
  renderDetail();
};

const loadProgress = async () => {
  if (!state.current || !state.student) { state.progress = null; return; }
  try {
    state.progress = await api(
      `/api/programs/${state.current.id}/progress?student=${encodeURIComponent(state.student)}`);
  } catch (error) {
    state.progress = null;
    toast(error.message, "bad");
  }
};

const openProgram = async (programId) => {
  try {
    state.current = await api(`/api/programs/${encodeURIComponent(programId)}`);
    state.progress = null;
    if (state.student) await loadProgress();
    const wrap = document.getElementById("detail-wrap");
    wrap.hidden = false;
    state.open = new Set([1]);
    renderDetail();
    wrap.scrollIntoView({ behavior: "smooth", block: "start" });
  } catch (error) {
    toast(error.message, "bad");
  }
};

const startFromTemplate = async (slug) => {
  if (!isStaff()) {
    toast("Sign in as an instructor or administrator to run a program.", "bad");
    return;
  }
  const template = state.templates.find((item) => item.slug === slug);
  if (!template) return;
  try {
    const doc = await api("/api/programs", {
      method: "POST",
      body: JSON.stringify({
        template: slug,
        name: document.getElementById("create-name").value.trim() || undefined,
        startTerm: document.getElementById("create-term").value.trim() || undefined,
      }),
    });
    toast(`${doc.credential} created — ${doc.plan.semesters.length} semesters, ${doc.plan.finals.length} finals`);
    await loadPrograms();
    await openProgram(doc.id);
  } catch (error) {
    toast(error.message, "bad");
  }
};

const loadPrograms = async () => {
  try {
    const answer = await api("/api/programs");
    state.templates = answer.templates || [];
    state.programs = answer.programs || [];
    renderCatalog();
    renderTemplates();
  } catch (error) {
    toast(error.message, "bad");
  }
};

const loadMe = async () => {
  try {
    state.me = await api("/api/me");
    const who = document.getElementById("who");
    who.replaceChildren(el("b", {}, state.me.user), state.me.mayGenerate ? " · staff" : " · student");
    const mode = document.getElementById("mode");
    if (isStaff()) {
      mode.textContent = "instructor / admin";
      mode.dataset.state = "ok";
      document.getElementById("create-panel").hidden = false;
      document.getElementById("templates-wrap").hidden = false;
    } else {
      mode.textContent = "student view";
      mode.dataset.state = "ok";
    }
    state.student = state.me.email || state.me.user || "";
    document.getElementById("enroll-student").value = state.student;
    document.getElementById("enroll-hint").textContent = state.student ? `signed in as ${state.student}` : "";
  } catch (error) {
    document.getElementById("who").replaceChildren(el("b", {}, error.status === 401 ? "signed out" : "unknown"));
  }
};

// -- boot --------------------------------------------------------------------

const boot = async () => {
  document.getElementById("create-form").addEventListener("submit", (event) => {
    event.preventDefault();
    const slug = document.getElementById("create-template").value;
    if (slug) startFromTemplate(slug);
  });
  document.getElementById("template-form").addEventListener("submit", saveTemplate);
  document.getElementById("template-new").addEventListener("click", () => openTemplateEditor(null));
  document.getElementById("tpl-cancel").addEventListener("click", closeTemplateEditor);
  document.getElementById("tpl-add-semester").addEventListener("click", () => {
    const host = document.getElementById("tpl-semesters");
    host.append(semesterEditor({ name: "", courses: [] }, host.children.length + 1));
    tallyTemplate();
  });
  document.getElementById("tpl-semesters").addEventListener("input", tallyTemplate);
  document.getElementById("enroll-form").addEventListener("submit", async (event) => {
    event.preventDefault();
    const programId = document.getElementById("enroll-program").value;
    const student = document.getElementById("enroll-student").value.trim();
    if (!programId) { toast("No program is running yet.", "bad"); return; }
    if (!student) { toast("Enter a learner identity.", "bad"); return; }
    state.student = student;
    try {
      const answer = await api(`/api/programs/${programId}/enroll`, {
        method: "POST", body: JSON.stringify({ student }),
      });
      await openProgram(programId);
      // The LMS is where "My courses" comes from, so say what it did — including
      // the case where the learner has no LMS account yet.
      const lms = answer.lms;
      const row = lms && lms.students && lms.students[0];
      if (row && row.missing) toast(`Enrolled ${student} on the program — no LMS account yet`);
      else if (row) toast(`Enrolled ${student} — ${row.enrolled.length} courses in the LMS`);
      else toast(`Enrolled ${student}`);
    } catch (error) {
      toast(error.message, "bad");
    }
  });

  await loadMe();
  await loadPrograms();
  const params = new URLSearchParams(window.location.search);
  if (params.get("program")) await openProgram(params.get("program"));
};

boot();
