// AthenIQ generation console.
//
// No framework and no build step: the page is served by the same small server
// that answers the API, and every value it shows came from that API. Text is
// written with textContent (never innerHTML) so a course title is a course
// title even if it contains angle brackets.

const state = {
  courses: [],
  runs: [],
  recorded: [],
  queued: [],
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

  // A live classroom can be replaced or retired. Both act on the spec, which is
  // what the courseware reads, so the page re-reads it after either one.
  const staff = Boolean(state.me && state.me.mayGenerate);
  const path = `/api/courses/${encodeURIComponent(course.slug)}` +
               `/classrooms/${encodeURIComponent(classroom.id)}`;
  const act = (label, method, suffix, confirmText, done) => el("button", {
    class: "btn btn-secondary btn-small", type: "button",
    onclick: async (event) => {
      if (confirmText && !window.confirm(confirmText)) return;
      const node = event.currentTarget;
      node.disabled = true;
      try {
        await api(path + suffix, { method, body: method === "POST" ? "{}" : undefined });
        toast(done);
        await loadCourses();
      } catch (error) {
        toast(error.message, "bad");
        node.disabled = false;
      }
    },
  }, label);
  // Delete is offered for every classroom, generated or not: a brief that was
  // queued and never filled is exactly the one somebody wants gone, and hiding
  // the button on it left the row with no way out. Regenerate still needs a
  // live classroom to replace.
  if (staff) {
    if (classroom.generated) {
      actions.push(act("Regenerate", "POST", "/regenerate",
        `Regenerate “${classroom.title || classroom.id}”? Its classroom id is cleared and queued again.`,
        `Regenerating “${classroom.title || classroom.id}”`));
    }
    actions.push(act("Delete", "DELETE", "",
      `Delete the classroom for “${classroom.title || classroom.id}”? The lesson stays in the spec and is marked missing; a live classroom id is retired, not erased.`,
      `${classroom.id} deleted`));
  }

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
  const card = el("div", { class: "course", dataset: { open: open ? "1" : "0", token: course.slug } });
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
  const missing = total - live;
  document.getElementById("counts").textContent = `${live}/${total} classrooms live`;
  const bulk = document.getElementById("generate-missing");
  bulk.textContent = missing ? `Generate all missing (${missing})` : "Nothing missing";
  bulk.disabled = missing === 0 || !(state.me && state.me.mayGenerate);
  document.getElementById("missing-hint").textContent = missing
    ? "One run each, recorded into its spec when it finishes."
    : "Every classroom in every spec has one.";
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
  if (run.recordError) {
    card.append(el("div", { class: "err" }, `not recorded: ${run.recordError}`));
  }
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

//: The last few classrooms written back without a click. Shown so the recording
//: is something an operator watched happen, rather than something they infer from
//: a run silently leaving the list.
const renderRecorded = () => {
  const host = document.getElementById("recorded");
  host.replaceChildren();
  const recent = state.recorded.slice(-3).reverse();
  if (!recent.length) return;
  host.append(el("p", { class: "hint" }, "Recorded into the spec automatically"));
  for (const item of recent) {
    host.append(el("div", { class: "recorded-row" },
      el("code", {}, item.classroomId || ""),
      ` ${item.course}/${item.classroom}`));
  }
};

//: Classrooms a batch could not start yet. Shown above the runs because it is
//: the queue that explains why "Generate all missing" reported more than started.
const renderQueued = (host) => {
  if (!state.queued.length) return;
  const titles = state.queued.slice(0, 3).map((item) => item.title || item.classroom);
  const more = state.queued.length - titles.length;
  host.append(el("p", { class: "hint" },
    `${state.queued.length} waiting for a slot — they start as runs finish: `,
    el("span", {}, titles.join(" · ") + (more > 0 ? ` · +${more} more` : ""))));
};

const renderRuns = () => {
  const host = document.getElementById("runs");
  host.replaceChildren();
  renderQueued(host);
  if (!state.runs.length) {
    host.append(el("p", { class: "empty" }, "Nothing in flight. A finished classroom is recorded into its spec and leaves this list."));
  } else {
    for (const run of state.runs) host.append(runCard(run));
  }
  renderRecorded();
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
    state.recorded = answer.recorded || [];
    state.queued = answer.queued || [];
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

// -- the whole catalogue ---------------------------------------------------

const generateMissing = async (event) => {
  const button = event.currentTarget;
  button.disabled = true;
  button.textContent = "starting…";
  try {
    const answer = await api("/api/generate-missing", { method: "POST", body: "{}" });
    const started = (answer.started || []).length;
    const skipped = (answer.skipped || []).length;
    const queued = answer.queued || 0;
    const why = answer.blocked ? ` — ${answer.blocked}` : "";
    const parts = [];
    if (started) parts.push(`Started ${started} classroom${started === 1 ? "" : "s"}`);
    if (queued) parts.push(`${queued} queued`);
    if (skipped) parts.push(`${skipped} not started`);
    toast(parts.length
      ? `${parts.join(", ")}${queued ? " — the rest start as runs finish" : ""}${why}`
      : `Nothing to start${skipped ? ` (${skipped} skipped)` : ""}${why}`,
      started || queued ? "ok" : "bad");
    await Promise.all([loadRuns(), loadCourses()]);
  } catch (error) {
    toast(error.message, "bad");
  } finally {
    renderCourses();
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

/** A link from Courses or Programs names the spec it means. Open that course,
 *  put it in view, and drop the parameter so a refresh lands on the plain list
 *  rather than re-flashing a card the operator has already read. */
const focusLinkedCourse = () => {
  const wanted = new URLSearchParams(window.location.search).get("course");
  if (!wanted) return;
  const course = state.courses.find((c) => c.slug === wanted || c.course === wanted);
  if (!course) {
    toast(`No course spec named ${wanted}`, "bad");
  } else {
    state.open.add(course.slug);
    renderCourses();
    const card = document.querySelector(`.course[data-token="${CSS.escape(course.slug)}"]`);
    if (card) {
      card.scrollIntoView({ block: "center", behavior: "smooth" });
      card.classList.add("linked");
    }
  }
  history.replaceState(null, "", "index.html");
};

const boot = async () => {
  document.getElementById("filter").addEventListener("input", (event) => {
    state.filter = event.target.value.trim();
    renderCourses();
  });
  document.getElementById("runs-refresh").addEventListener("click", () => {
    loadRuns();
    loadHealth();
  });
  document.getElementById("generate-missing").addEventListener("click", generateMissing);
  document.getElementById("brief").addEventListener("submit", submitBrief);
  document.getElementById("brief-requirement").addEventListener("input", updateCharHint);

  await Promise.all([loadMe(), loadHealth()]);
  await Promise.all([loadCourses(), loadRuns()]);
  focusLinkedCourse();

  // Runs change every few seconds while something generates; the specs only
  // change when a classroom is recorded, so they are polled far less often.
  setInterval(() => { if (!document.hidden) loadRuns(); }, 7000);
  setInterval(() => { if (!document.hidden) loadCourses(); }, 45000);
};

boot();
