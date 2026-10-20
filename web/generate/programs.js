// AthenIQ programs.
//
// One page, two audiences. A learner sees the catalogue, enrols, and watches
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
const num = (value) => (value === null || value === undefined ? "—" : String(value));

// -- catalogue ---------------------------------------------------------------

const templateCard = (template) => el("button", {
  class: "program-card", type: "button",
  onclick: () => startFromTemplate(template.slug),
},
  el("span", { class: "program-kind" }, template.credentialKind === "degree" ? "Degree" : "Certificate"),
  el("span", { class: "program-name" }, template.name),
  el("span", { class: "program-credential" }, template.credential),
  el("span", { class: "program-meta" },
    `${template.semesters} semesters · ${template.courses} courses · ${template.totalCredits} credits`),
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
  el("span", { class: "program-meta" },
    `${program.semesters} semesters · ${program.courses} courses · ${program.totalCredits} credits`),
  el("span", { class: "program-meta" },
    `${program.generated}/${program.courses} classrooms generated · ${program.enrolled} enrolled`),
  el("span", { class: "program-cta" }, "Open program →"),
);

const renderCatalogue = () => {
  const host = document.getElementById("catalogue");
  host.replaceChildren();
  document.getElementById("counts").textContent =
    `${state.programs.length} running · ${state.templates.length} templates`;

  if (state.programs.length) {
    host.append(el("h2", { class: "group-h" }, "Running programs"));
    const grid = el("div", { class: "program-grid" });
    for (const program of state.programs) grid.append(programCard(program));
    host.append(grid);
  }
  host.append(el("h2", { class: "group-h" }, "Catalogue"));
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
    ),
  );
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

const stat = (label, value, note) => el("div", { class: "stat" },
  el("div", { class: "stat-value" }, value),
  el("div", { class: "stat-label" }, label),
  note ? el("div", { class: "stat-note" }, note) : null);

const progressPanel = () => {
  const progress = state.progress;
  if (!progress) {
    return el("p", { class: "empty" }, "Enrol below to see credits, GPA, finals, and what you can take next.");
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
      stat("credits earned", `${progress.creditsEarned} / ${progress.creditsRequired}`,
           `${progress.creditsRemaining} to go`),
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
          ` on ${progress.conferred.conferredAt} · GPA ${progress.conferred.gpa} · `,
          `${progress.conferred.credits} credits`)
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
        badge(`${doc.totalCredits} credits`),
        badge(`${plan.semesters.length} semesters`),
        badge(`${plan.finals.length} final examinations`),
        badge(`minimum GPA ${doc.minGpa}`),
        doc.startTerm ? badge(doc.startTerm) : null,
        doc.credentialKind === "certificate" ? badge("certificate", "ok") : badge("degree", "ok"),
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
        onclick: async (event) => {
          if (!window.confirm(`Regenerate every generated classroom in ${doc.name}?\n\nGrades, enrolments and conferrals are kept; the classroom ids are cleared and queued again.`)) return;
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
          if (!window.confirm(`Archive ${doc.name}? It moves to programs/.archive/ and leaves the catalogue; conferrals it already issued are kept.`)) return;
          const node = event.currentTarget;
          node.disabled = true;
          try {
            await api(`/api/programs/${doc.id}`, { method: "DELETE" });
            toast(`${doc.name} archived`);
            state.current = null;
            state.progress = null;
            document.getElementById("detail-wrap").hidden = true;
            await loadPrograms();
          } catch (error) {
            toast(error.message, "bad");
            node.disabled = false;
          }
        },
      }, "Archive"),
    ) : null,
  ));

  host.append(studentBar());
  host.append(el("div", { class: "panel-sub" }, el("h3", {}, "Progress"), progressPanel()));

  host.append(el("div", { class: "panel-sub" },
    el("h3", {}, "Curriculum"),
    el("p", { class: "sub" }, isStaff()
      ? "Generate a semester to create its classrooms, then record each learner's grade and final. The credential is conferred here only when every requirement is met."
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
    renderCatalogue();
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
  document.getElementById("enroll-form").addEventListener("submit", async (event) => {
    event.preventDefault();
    const programId = document.getElementById("enroll-program").value;
    const student = document.getElementById("enroll-student").value.trim();
    if (!programId) { toast("No program is running yet.", "bad"); return; }
    if (!student) { toast("Enter a learner identity.", "bad"); return; }
    state.student = student;
    try {
      await api(`/api/programs/${programId}/enroll`, {
        method: "POST", body: JSON.stringify({ student }),
      });
      await openProgram(programId);
      toast(`Enrolled ${student}`);
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
