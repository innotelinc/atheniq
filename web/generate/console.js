// AthenIQ generation console.
//
// No framework and no build step: the page is served by the same small server
// that answers the API, and every value it shows came from that API. Text is
// written with textContent (never innerHTML) so a course title is a course
// title even if it contains angle brackets.

const state = {
  courses: [],
  runs: [],
  maxRequirement: 6000,
  filter: "",
  open: new Set(),
  me: null,
  health: null,
};

const el = (tag, props = {}, ...children) => {
  const node = document.createElement(tag);
  for (const [key, value] of Object.entries(props)) {
    if (key === "class") node.className = value;
    else if (key === "dataset") Object.assign(node.dataset, value);
    else if (key.startsWith("on")) node.addEventListener(key.slice(2), value);
    else if (value !== null && value !== undefined) node.setAttribute(key, value);
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

const shortTime = (iso) => {
  if (!iso) return "";
  const then = new Date(iso);
  if (Number.isNaN(then.valueOf())) return "";
  const mins = Math.round((Date.now() - then.valueOf()) / 60000);
  if (mins < 1) return "just now";
  if (mins < 60) return `${mins}m ago`;
  if (mins < 1440) return `${Math.round(mins / 60)}h ago`;
  return then.toLocaleDateString();
};

// -- health ----------------------------------------------------------------

const renderHealth = () => {
  const pill = document.getElementById("health");
  const health = state.health;
  if (!health) {
    pill.dataset.state = "bad";
    pill.textContent = "OpenMAIC unreachable";
    const hint = state.healthError ? ` — ${state.healthError}` : "";
    pill.title = `The generator did not answer${hint}`;
    return;
  }
  pill.dataset.state = health.ok ? "ok" : "bad";
  const model = (health.slots || []).find((s) => s.slot === "classroom") ||
                (health.slots || []).find((s) => s.slot === "llm");
  pill.textContent = health.ok
    ? `OpenMAIC ${health.version || ""}${model && model.model ? " · " + model.model : ""}`.trim()
    : "OpenMAIC unhealthy";
  pill.title = (health.slots || []).map((s) => `${s.slot}: ${s.model || "?"}`).join("\n");
};

// -- courses ---------------------------------------------------------------

const matches = (course) => {
  if (!state.filter) return true;
  const needle = state.filter.toLowerCase();
  return [course.slug, course.course, ...course.classrooms.map((c) => `${c.title} ${c.id}`)]
    .some((value) => String(value || "").toLowerCase().includes(needle));
};

const classroomRow = (course, classroom) => {
  const actions = [];
  if (classroom.url) {
    actions.push(el("a", { class: "btn btn-secondary", href: classroom.url, target: "_blank", rel: "noopener" }, "Open"));
  }
  const button = classroom.url ? null : el("button", {
    class: "btn btn-primary", type: "button",
    onclick: async (event) => {
      const node = event.currentTarget;
      node.disabled = true;
      node.textContent = "submitting…";
      try {
        const answer = await api("/api/generate", {
          method: "POST",
          body: JSON.stringify({ course: course.slug, classroom: classroom.id }),
        });
        toast(`Generating “${classroom.title}” — run ${answer.runId}`);
        await Promise.all([loadRuns(), loadCourses()]);
      } catch (error) {
        toast(error.message, "bad");
        node.disabled = false;
        node.textContent = "Generate";
      }
    },
  }, "Generate");
  if (button) actions.push(button);

  return el("div", { class: "row" },
    el("div", {},
      el("div", { class: "t" }, classroom.title || classroom.id),
      el("div", { class: "m" },
        `${classroom.chapter || "—"} · `,
        el("code", {}, classroom.id),
        classroom.units && classroom.units.length ? ` · ${classroom.units.join(", ")}` : "",
        classroom.classroomId ? ` · ` : "",
        classroom.classroomId ? el("code", {}, classroom.classroomId) : ""),
    ),
    el("div", { class: "actions" },
      el("span", { class: "state" },
        el("i", { class: `dot ${classroom.generated ? "ok" : ""}`.trim() }),
        classroom.generated ? "live" : "missing"),
      ...actions),
  );
};

const courseCard = (course) => {
  const open = state.open.has(course.slug);
  const card = el("div", { class: "course", dataset: { open: open ? "1" : "0" } });
  const head = el("button", {
    class: "course-head", type: "button", "aria-expanded": open ? "true" : "false",
    onclick: () => {
      if (state.open.has(course.slug)) state.open.delete(course.slug);
      else state.open.add(course.slug);
      renderCourses();
    },
  },
    el("span", { class: "chev" }, "▸"),
    el("span", { class: "name" }, course.slug),
    el("span", { class: "code" }, course.course.replace("course-v1:", "")),
    el("span", { class: "tally" }, `${course.generated}/${course.total} live`),
  );
  const body = el("div", { class: "course-body" });
  for (const classroom of course.classrooms) body.append(classroomRow(course, classroom));
  card.append(head, body);
  return card;
};

const renderCourses = () => {
  const host = document.getElementById("courses");
  const courses = state.courses.filter(matches);
  const live = state.courses.reduce((n, c) => n + c.generated, 0);
  const total = state.courses.reduce((n, c) => n + c.total, 0);
  document.getElementById("counts").textContent = `${live}/${total} classrooms live`;
  host.replaceChildren();
  if (!courses.length) {
    host.append(el("p", { class: "empty" }, state.courses.length ? "No course matches that filter." : "No course specs found."));
    return;
  }
  for (const course of courses) host.append(courseCard(course));
};

// -- runs ------------------------------------------------------------------

const runAction = (run, label, path, method) => el("button", {
  class: "btn btn-secondary", type: "button",
  onclick: async (event) => {
    const node = event.currentTarget;
    node.disabled = true;
    try {
      const answer = await api(path, { method, body: method === "POST" ? "{}" : undefined });
      toast(answer.classroomId ? `Recorded ${answer.classroomId} in ${answer.course}/${answer.classroom}`
                               : `${label} accepted`);
      await Promise.all([loadRuns(), loadCourses()]);
    } catch (error) {
      toast(error.message, "bad");
      node.disabled = false;
    }
  },
}, label);

const runCard = (run) => {
  const done = (run.progress && run.progress.done) || 0;
  const total = (run.progress && run.progress.total) || 0;
  const card = el("div", { class: "run" });
  const stateLabel = el("span", { class: `state ${run.state || ""}` }, run.state || "unknown");
  card.append(el("div", { class: "run-top" },
    stateLabel,
    el("span", { class: "id" }, run.id || ""),
  ));
  if (run.source && run.source.title) {
    card.append(el("div", { class: "step" }, run.source.title));
  }
  if (run.step) card.append(el("div", { class: "step" }, `step ${run.step}`));
  if (run.progress && total) {
    card.append(el("div", { class: "bar" },
      el("i", { style: `width:${Math.max(2, Math.round((done / total) * 100))}%` })));
  }
  if (run.error && run.error.message) {
    const code = [run.error.code, run.error.status].filter(Boolean).join(" ");
    card.append(el("div", { class: "err" }, `${code ? code + ": " : ""}${run.error.message}`));
  }
  const actions = [];
  if (run.state === "paused") {
    actions.push(runAction(run, "Retry", `/api/runs/${run.id}/retry`, "POST"));
    actions.push(runAction(run, "Discard", `/api/runs/${run.id}`, "DELETE"));
  }
  if (run.recordable) actions.push(runAction(run, "Record in spec", `/api/runs/${run.id}/record`, "POST"));
  if (run.classroomId) {
    const host = (state.me && state.me.classroomHost) || "https://classroom.innotel.us";
    actions.push(el("a", {
      class: "btn btn-secondary", target: "_blank", rel: "noopener",
      href: `${host}/classroom/${run.classroomId}`,
    }, "Open classroom"));
  }
  if (actions.length) card.append(el("div", { class: "actions" }, ...actions));
  return card;
};

const renderRuns = () => {
  const host = document.getElementById("runs");
  host.replaceChildren();
  if (!state.runs.length) {
    host.append(el("p", { class: "empty" }, "Nothing in flight. A finished classroom shows up in its course once it is recorded."));
    return;
  }
  for (const run of state.runs) host.append(runCard(run));
};

// -- loading ---------------------------------------------------------------

const loadCourses = async () => {
  try {
    const answer = await api("/api/courses");
    state.courses = answer.courses || [];
    state.maxRequirement = answer.maxRequirement || state.maxRequirement;
    if (!state.open.size) {
      for (const course of state.courses) {
        if (course.generated < course.total) state.open.add(course.slug);
      }
    }
    renderCourses();
    updateCharHint();
  } catch (error) {
    toast(error.message, "bad");
  }
};

const loadRuns = async () => {
  try {
    const answer = await api("/api/runs");
    state.runs = answer.runs || [];
    renderRuns();
  } catch (error) {
    document.getElementById("runs").replaceChildren(el("p", { class: "empty" }, error.message));
  }
};

const loadHealth = async () => {
  try {
    state.health = await api("/api/health");
    state.healthError = null;
  } catch (error) {
    state.health = null;
    state.healthError = error.message;
  }
  renderHealth();
};

const loadMe = async () => {
  try {
    state.me = await api("/api/me");
    document.getElementById("who").replaceChildren(
      el("b", {}, state.me.user),
      state.me.mayGenerate ? "" : " · read-only");
  } catch (error) {
    document.getElementById("who").replaceChildren(el("b", {}, error.status === 401 ? "signed out" : "unknown"));
  }
};

// -- brief form ------------------------------------------------------------

const updateCharHint = () => {
  const field = document.getElementById("brief-requirement");
  const hint = document.getElementById("charhint");
  const length = field.value.trim().length;
  hint.textContent = `${length}/${state.maxRequirement}`;
  field.classList.toggle("over", length > state.maxRequirement);
};

const submitBrief = async (event) => {
  event.preventDefault();
  const title = document.getElementById("brief-title");
  const field = document.getElementById("brief-requirement");
  const button = document.getElementById("brief-submit");
  const requirement = field.value.trim();
  if (requirement.length < 80) {
    toast("A brief needs at least 80 characters.", "bad");
    field.focus();
    return;
  }
  if (requirement.length > state.maxRequirement) {
    toast(`Trim the brief to ${state.maxRequirement} characters.`, "bad");
    field.focus();
    return;
  }
  button.disabled = true;
  button.textContent = "submitting…";
  try {
    const answer = await api("/api/generate", {
      method: "POST",
      body: JSON.stringify({ title: title.value.trim() || undefined, requirement }),
    });
    toast(`Generating — run ${answer.runId}`);
    field.value = "";
    title.value = "";
    updateCharHint();
    await loadRuns();
  } catch (error) {
    toast(error.message, "bad");
  } finally {
    button.disabled = false;
    button.textContent = "Generate";
  }
};

// -- boot ------------------------------------------------------------------

const boot = async () => {
  document.getElementById("filter").addEventListener("input", (event) => {
    state.filter = event.target.value.trim();
    renderCourses();
  });
  document.getElementById("runs-refresh").addEventListener("click", () => {
    loadRuns();
    loadHealth();
  });
  document.getElementById("brief").addEventListener("submit", submitBrief);
  document.getElementById("brief-requirement").addEventListener("input", updateCharHint);

  await Promise.all([loadMe(), loadHealth()]);
  await Promise.all([loadCourses(), loadRuns()]);

  // Runs change every few seconds while something generates; the specs only
  // change when a classroom is recorded, so they are polled far less often.
  setInterval(() => { if (!document.hidden) loadRuns(); }, 7000);
  setInterval(() => { if (!document.hidden) loadCourses(); }, 45000);
};

boot();
