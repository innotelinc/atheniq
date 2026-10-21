// AthenIQ learner portal.
//
// Two reads and no writes. The page fetches the public catalog once, renders
// programs and courses from it, and fetches one program when it is opened.
// Text goes through `el()` (textContent), never innerHTML: a course title is a
// course title even if it contains angle brackets.

const state = {
  programs: [],
  templates: [],
  courses: [],
  current: null,
  open: new Set([1]),
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

const api = async (path) => {
  const response = await fetch(path, { credentials: "omit" });
  if (!response.ok) {
    let message = `request failed (${response.status})`;
    try {
      const payload = await response.json();
      if (payload && payload.error) message = payload.error;
    } catch (_) { /* the status is the message */ }
    throw new Error(message);
  }
  return response.json();
};

const number = (value) => (value === null || value === undefined ? "—" : String(value));
const badge = (text, kind = "") => el("span", { class: `badge ${kind}`.trim() }, text);

// -- catalog ---------------------------------------------------------------

const renderStats = () => {
  const host = document.getElementById("stats");
  const credits = state.programs.reduce((n, p) => n + (p.totalCredits || 0), 0);
  const courses = state.programs.reduce((n, p) => n + (p.courses || 0), 0);
  host.replaceChildren(
    el("div", {}, el("div", { class: "stat-value" }, String(state.programs.length)),
       el("div", { class: "stat-label" }, "programs")),
    el("div", {}, el("div", { class: "stat-value" }, String(courses)),
       el("div", { class: "stat-label" }, "courses in sequence")),
    el("div", {}, el("div", { class: "stat-value" }, String(credits)),
       el("div", { class: "stat-label" }, "credits across credentials")),
  );
};

const programCard = (program) => el("button", {
  class: "program-card", type: "button",
  onclick: () => openProgram(program.id),
},
  el("span", { class: "kind" }, program.credentialKind === "certificate" ? "Certificate" : "Degree"),
  el("span", { class: "program-name" }, program.name),
  el("span", { class: "program-credential" }, program.credential),
  el("span", { class: "program-meta" },
    `${number(program.semesters)} semesters · ${number(program.courses)} courses · ${number(program.totalCredits)} credits`),
  program.description ? el("span", { class: "program-desc" }, program.description) : null,
  (program.certificates || []).length
    ? el("span", { class: "program-certs" }, `Includes ${program.certificates.join(", ")}`)
    : null,
  el("span", { class: "program-meta" },
    `${number(program.finals)} final examinations · ${number(program.generated)} classrooms live`),
);

const courseCard = (course) => {
  // A course that exists only in a program plan: the program carries it from
  // the moment it is saved, but a spec (and so a classroom) only appears once
  // one is generated. Listed rather than hidden, and linked to the program that
  // teaches it, so a new course can be found before it is built.
  if (course.planned) {
    return el("div", { class: "course-card planned" },
      el("div", { class: "slug" }, course.code),
      el("div", { class: "key" }, course.title || ""),
      el("div", { class: "tally" }, "planned · not built yet"),
      course.program
        ? el("div", { class: "rooms" },
            el("span", { class: "dot" }),
            el("a", {
              href: `#program/${course.program.id}`,
              onclick: (event) => {
                event.preventDefault();
                openProgram(course.program.id);
              },
            }, `in ${course.program.name}`))
        : null,
    );
  }
  const rooms = course.classrooms.slice(0, 6).map((room) => el("div", {
    class: `room${room.generated ? " live" : ""}`.trim(),
  },
    el("span", { class: "dot" }),
    room.url
      ? el("a", { href: room.url, target: "_blank", rel: "noopener" }, room.title)
      : el("span", {}, room.title),
  ));
  return el("div", { class: "course-card" },
    el("div", { class: "slug" }, course.slug),
    el("div", { class: "key" }, String(course.course || "").replace("course-v1:", "")),
    el("div", { class: "tally" }, `${course.generated}/${course.total} classrooms live`),
    el("div", { class: "rooms" }, ...rooms),
  );
};

const renderCatalog = () => {
  const grid = document.getElementById("program-grid");
  grid.replaceChildren();
  if (!state.programs.length) {
    grid.append(el("p", { class: "empty" },
      "No program is running yet. Platform Services can create one from the catalog."));
  } else {
    for (const program of state.programs) grid.append(programCard(program));
  }
  document.getElementById("programs-count").textContent =
    `${state.programs.length} running · ${state.templates.length} catalog templates`;

  const courses = document.getElementById("course-grid");
  courses.replaceChildren();
  if (!state.courses.length) {
    courses.append(el("p", { class: "empty" }, "No course specs found."));
    return;
  }
  const live = state.courses.reduce((n, c) => n + c.generated, 0);
  const total = state.courses.reduce((n, c) => n + c.total, 0);
  document.getElementById("courses-count").textContent = `${live}/${total} classrooms live`;
  for (const course of state.courses) courses.append(courseCard(course));
};

// -- one program -----------------------------------------------------------

const courseRow = (course) => el("div", { class: "course-row" },
  el("div", { class: "course-title" },
    el("code", {}, course.code), ` ${course.title}`),
  el("div", { class: "course-sub" },
    `${number(course.credits)} credits · ${course.kind || "core"} · final: `,
    (course.final && course.final.type) || course.finalExam || "assessment",
    course.prerequisites && course.prerequisites.length
      ? ` · prerequisite: ${course.prerequisites.join(", ")}`
      : " · no prerequisite"),
  course.description ? el("div", { class: "course-desc" }, course.description) : null,
);

const semesterBlock = (semester) => {
  const open = state.open.has(semester.number);
  const body = el("div", { class: "semester-body" });
  if (open) for (const course of semester.courses) body.append(courseRow(course));
  return el("div", { class: "semester", dataset: { open: open ? "1" : "0" } },
    el("div", {
      class: "semester-head", role: "button", tabindex: "0",
      onclick: () => toggleSemester(semester.number),
      onkeydown: (event) => {
        if (event.key === "Enter" || event.key === " ") {
          event.preventDefault();
          toggleSemester(semester.number);
        }
      },
    },
      el("span", { class: "chev" }, "▸"),
      el("span", { class: "semester-name" }, `Semester ${semester.number} — ${semester.name}`),
      el("span", { class: "semester-tally" },
        `${number(semester.credits)} credits · ${semester.courses.length} courses`),
    ),
    body);
};

const toggleSemester = (number) => {
  if (state.open.has(number)) state.open.delete(number);
  else state.open.add(number);
  renderDetail();
};

const renderDetail = () => {
  const doc = state.current;
  if (!doc) return;
  const view = document.getElementById("program-view");
  view.replaceChildren(el("article", { class: "detail" },
    el("div", { class: "detail-head" },
      el("button", {
        class: "back", type: "button",
        onclick: () => {
          state.current = null;
          view.hidden = true;
          window.location.hash = "";
          document.getElementById("programs").scrollIntoView({ behavior: "smooth" });
        },
      }, "← All programs"),
    ),
    el("h2", {}, doc.name),
    el("div", { class: "program-credential" }, doc.credential),
    el("div", { class: "badges" },
      badge(`${number(doc.totalCredits)} credits`),
      badge(`${doc.semesters.length} semesters`),
      badge(`${doc.finals.length} final examinations`),
      badge(`minimum GPA ${number(doc.minGpa)}`),
      doc.startTerm ? badge(doc.startTerm) : null,
      badge(doc.credentialKind === "certificate" ? "certificate" : "degree", "ok"),
    ),
    doc.description ? el("p", { class: "lede" }, doc.description) : null,
    (doc.certificates || []).length
      ? el("p", { class: "lede small" },
          el("b", {}, "Stackable certificates: "),
          doc.certificates.map((cert) =>
            `${cert.name} (after semester ${cert.afterSemester})`).join(" · "))
      : null,
    el("div", { class: "cta-row" },
      el("a", {
        class: "btn btn-primary",
        href: "https://apps.learn.innotel.us/catalog/",
      }, "Enroll in the LMS"),
      el("a", {
        class: "btn btn-secondary",
        href: "https://ai.lms.innotel.us/programs.html",
      }, "Open program workspace"),
    ),
    ...doc.semesters.map(semesterBlock),
  ));
  view.hidden = false;
};

const openProgram = async (programId) => {
  try {
    state.current = await api(`/api/public/programs/${encodeURIComponent(programId)}`);
    state.open = new Set([state.current.semesters[0] ? state.current.semesters[0].number : 1]);
    renderDetail();
    window.location.hash = `program/${programId}`;
    document.getElementById("program-view").scrollIntoView({ behavior: "smooth" });
  } catch (error) {
    document.getElementById("program-grid").prepend(
      el("p", { class: "empty" }, error.message));
  }
};

// -- boot --------------------------------------------------------------------

const boot = async () => {
  try {
    const [catalog, courses] = await Promise.all([
      api("/api/public/programs"),
      api("/api/public/courses"),
    ]);
    state.programs = catalog.programs || [];
    state.templates = catalog.templates || [];
    state.courses = courses.courses || [];
    renderStats();
    renderCatalog();
  } catch (error) {
    document.getElementById("program-grid").replaceChildren(
      el("p", { class: "empty" }, error.message));
  }
  const match = window.location.hash.match(/^#program\/(.+)$/);
  if (match) openProgram(decodeURIComponent(match[1]));
};

boot();
