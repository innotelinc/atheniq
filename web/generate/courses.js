// AthenIQ Platform Services — courses.
//
// One list, three actions: open the classrooms, queue the missing ones, or
// delete the course. A delete is a delete: the spec, the classrooms generated
// for it and its course in the LMS all go, because the platform is in rollout
// and a course left behind is still enrollable.

const state = { courses: [], me: null };

const el = (tag, props = {}, ...children) => {
  const node = document.createElement(tag);
  for (const [key, value] of Object.entries(props)) {
    if (key === "class") node.className = value;
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
  if (!response.ok) throw new Error((payload && payload.error) || `request failed (${response.status})`);
  return payload;
};

let timer = null;
const toast = (message, kind = "ok") => {
  const box = document.getElementById("toast");
  box.textContent = message;
  box.dataset.kind = kind;
  box.hidden = false;
  clearTimeout(timer);
  timer = setTimeout(() => { box.hidden = true; }, kind === "bad" ? 9000 : 5000);
};

const isStaff = () => Boolean(state.me && state.me.mayGenerate);

const action = (label, run, kind = "btn-secondary") => el("button", {
  class: `btn ${kind} btn-small`, type: "button",
  onclick: async (event) => {
    const node = event.currentTarget;
    node.disabled = true;
    const original = node.textContent;
    node.textContent = "working…";
    try { await run(); } catch (error) { toast(error.message, "bad"); }
    finally { node.disabled = false; node.textContent = original; }
  },
}, label);

const courseRow = (course) => {
  const missing = course.total - course.generated;
  return el("div", { class: "course", dataset: { open: "1" } },
    el("div", { class: "row" },
      el("div", {},
        el("div", { class: "t" }, course.slug),
        el("div", { class: "m" },
          el("code", {}, String(course.course || "").replace("course-v1:", "")),
          ` · ${course.generated}/${course.total} classrooms live`,
          missing ? ` · ${missing} missing` : ""),
      ),
      el("div", { class: "actions" },
        el("a", { class: "btn btn-secondary btn-small", href: `index.html#${course.slug}` }, "Classrooms"),
        isStaff() && missing
          ? action("Regenerate missing", async () => {
              const answer = await api(`/api/courses/${course.slug}/regenerate`, { method: "POST", body: "{}" });
              toast(`${(answer.started || []).length} run(s) started`);
              await loadCourses();
            }, "btn-primary")
          : null,
        isStaff()
          ? action("Delete", async () => {
              if (!window.confirm(`Delete ${course.slug}?\n\nIts ${course.generated} generated classroom(s) and its course in the LMS are deleted too. This cannot be undone.`)) return;
              const answer = await api(`/api/courses/${course.slug}`, { method: "DELETE" });
              const classes = (answer.classrooms && answer.classrooms.deleted || []).length;
              const lms = (answer.lms && answer.lms.deleted || []).length;
              toast(`${course.slug} deleted · ${classes} classroom(s), ${lms} LMS course(s)`);
              await loadCourses();
            })
          : null,
      ),
    ),
  );
};

const render = () => {
  const host = document.getElementById("courses");
  host.replaceChildren();
  const live = state.courses.reduce((n, c) => n + c.generated, 0);
  const total = state.courses.reduce((n, c) => n + c.total, 0);
  document.getElementById("counts").textContent = `${state.courses.length} courses · ${live}/${total} classrooms live`;
  document.getElementById("hint").textContent = isStaff()
    ? "Staff actions are enabled for your account."
    : "Read-only: your account is not in a staff group.";
  if (!state.courses.length) {
    host.append(el("p", { class: "empty" }, "No course specs found."));
    return;
  }
  for (const course of state.courses) host.append(courseRow(course));
};

const loadCourses = async () => {
  try {
    const answer = await api("/api/courses");
    state.courses = answer.courses || [];
    render();
  } catch (error) {
    toast(error.message, "bad");
  }
};

const boot = async () => {
  try {
    state.me = await api("/api/me");
    document.getElementById("who").replaceChildren(
      el("b", {}, state.me.user), state.me.mayGenerate ? " · staff" : " · read-only");
  } catch (error) {
    document.getElementById("who").replaceChildren(el("b", {}, error.status === 401 ? "signed out" : "unknown"));
  }
  await loadCourses();
};

boot();
