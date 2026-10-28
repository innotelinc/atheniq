/* AthenIQ portal — one page, two views.
 *
 * The view is not a client-side choice: the server answers `/api/me` with the
 * SSO identity it was given, and only an allowed group sees the admin view. The
 * page renders the catalog the same way for both, and adds the generation panel
 * when (and only when) the server says this person may act on it.
 */
"use strict";

const el = (tag, attrs = {}, ...children) => {
  const node = document.createElement(tag);
  for (const [key, value] of Object.entries(attrs)) {
    if (value === null || value === undefined || value === false) continue;
    if (key === "class") node.className = value;
    else if (key === "text") node.textContent = value;
    else if (key.startsWith("on")) node.addEventListener(key.slice(2), value);
    else node.setAttribute(key, value === true ? "" : String(value));
  }
  for (const child of children.flat()) {
    if (child === null || child === undefined || child === false) continue;
    node.append(child.nodeType ? child : document.createTextNode(String(child)));
  }
  return node;
};

const $ = (id) => document.getElementById(id);
let catalog = { programs: [], courses: [] };
let admin = false;

function toast(message) {
  const box = $("toast");
  box.textContent = message;
  box.hidden = false;
  clearTimeout(toast.timer);
  toast.timer = setTimeout(() => { box.hidden = true; }, 5200);
}

async function api(path, options = {}) {
  const response = await fetch(path, {
    headers: { Accept: "application/json", ...(options.headers || {}) },
    ...options,
  });
  const body = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(body.error || `${response.status} ${response.statusText}`);
  return body;
}

/* -- the views ------------------------------------------------------------- */

function renderPrograms(programs) {
  const grid = $("program-grid");
  grid.replaceChildren();
  $("program-count").textContent = `${programs.length} program${programs.length === 1 ? "" : "s"}`;
  if (!programs.length) {
    grid.append(el("p", { class: "empty", text: "No programs yet." }));
    return;
  }
  for (const program of programs) {
    const ready = program.courses ? Math.round((program.generated / program.courses) * 100) : 0;
    const detail = el("div", { class: "bar", role: "img",
      "aria-label": `${program.generated} of ${program.courses} courses ready` },
      el("i", { style: `width:${ready}%` }));
    grid.append(el("article", { class: "program" },
      el("span", { class: "kind", text: program.credentialKind === "certificate" ? "Certificate" : "Degree" }),
      el("h3", { text: program.name }),
      el("span", { class: "credential", text: program.credential || "" }),
      el("span", { class: "meta", text:
        `${program.semesters} semester${program.semesters === 1 ? "" : "s"} · ` +
        `${program.courses} course${program.courses === 1 ? "" : "s"}` +
        (program.totalCredits ? ` · ${program.totalCredits} credits` : "") +
        (program.startTerm ? ` · starts ${program.startTerm}` : "") }),
      detail,
      el("div", { class: "foot" },
        el("a", { href: `#courses`, text: "See its courses",
          onclick: (event) => { event.preventDefault(); filterCourses(program.name); } }),
        admin ? el("span", { class: "chip", text: `${program.generated}/${program.courses} ready` }) : null)));
  }
}

function courseRow(course) {
  const ready = course.total > 0 && course.generated >= course.total;
  const tone = course.planned ? "planned" : (ready ? "ready" : "");
  const status = course.planned ? "Planned" : (ready ? "Ready" : "Being built");
  return el("tr", {},
    el("td", {}, el("div", { class: "code", text: course.code }),
      el("div", { class: "title", text: course.title })),
    el("td", { text: course.program || "—" }),
    el("td", { text: course.total ? `${course.generated}/${course.total}` : "—" }),
    el("td", {}, el("span", { class: "chip", "data-tone": tone, text: status })),
    el("td", {}, course.url
      ? el("a", { href: course.url, rel: "noopener", text: "Open in the LMS" })
      : el("span", { class: "muted", text: "Not in the LMS yet" })));
}

function renderCourses(courses) {
  const rows = $("course-rows");
  rows.replaceChildren();
  const ready = courses.filter((course) => !course.planned).length;
  $("course-count").textContent =
    `${courses.length} course${courses.length === 1 ? "" : "s"} · ${ready} ready`;
  if (!courses.length) {
    rows.append(el("tr", {}, el("td", { colspan: "5", class: "empty", text: "No courses yet." })));
    return;
  }
  for (const course of courses) rows.append(courseRow(course));
}

function filterCourses(text) {
  const needle = String(text || $("filter").value || "").trim().toLowerCase();
  $("filter").value = needle;
  const matches = catalog.courses.filter((course) => !needle ||
    [course.code, course.title, course.program].join(" ").toLowerCase().includes(needle));
  renderCourses(matches);
  $("courses").scrollIntoView({ behavior: "smooth", block: "start" });
}

function renderStats() {
  const courses = catalog.courses || [];
  const ready = courses.filter((course) => !course.planned).length;
  const classrooms = courses.reduce((total, course) => total + course.generated, 0);
  $("stats").replaceChildren(
    el("div", { class: "stat" }, el("b", { text: String((catalog.programs || []).length) }),
      el("span", { text: "programs" })),
    el("div", { class: "stat" }, el("b", { text: String(courses.length) }),
      el("span", { text: "courses" })),
    el("div", { class: "stat" }, el("b", { text: String(ready) }), el("span", { text: "ready now" })),
    el("div", { class: "stat" }, el("b", { text: String(classrooms) }),
      el("span", { text: "classrooms" })));
}

function renderRuns(queue) {
  const rows = $("run-rows");
  rows.replaceChildren();
  const runs = queue.runs || [];
  if (!runs.length) {
    rows.append(el("tr", {}, el("td", { colspan: "5", class: "empty",
      text: queue.queued && queue.queued.length
        ? `${queue.queued.length} classroom(s) queued for a slot.`
        : "Nothing generating and nothing paused." })));
    return;
  }
  for (const run of runs) {
    const paused = String(run.state || "").includes("paus") || Boolean(run.error);
    const retry = el("button", { class: "btn", type: "button", text: "Retry",
      onclick: async (event) => {
        const button = event.currentTarget;
        button.disabled = true;
        try {
          await api(`/api/admin/runs/${encodeURIComponent(run.id)}/retry`, {
            method: "POST",
            headers: { "Content-Type": "application/json", "X-Atheniq-Portal": "1" },
            body: "{}",
          });
          toast(`Retried ${run.id}.`);
          await loadRuns();
        } catch (error) {
          toast(`Retry failed: ${error.message}`);
        } finally {
          button.disabled = false;
        }
      } });
    rows.append(el("tr", {},
      el("td", {}, el("div", { class: "code", text: run.title || run.classroom || run.id }),
        el("div", { class: "title", text: run.id })),
      el("td", {}, el("span", { class: "chip", "data-tone": paused ? "bad" : "",
        text: run.state || "—" })),
      el("td", { class: "title", text: run.step || "—" }),
      el("td", { class: "title", text: run.error || "" }),
      el("td", {}, paused ? retry : el("span", { class: "muted", text: "running" }))));
  }
}

async function loadRuns() {
  if (!admin) return;
  try {
    renderRuns(await api("/api/admin/runs"));
  } catch (error) {
    toast(`The generation queue could not be read: ${error.message}`);
  }
}

async function load() {
  try {
    const me = await api("/api/me");
    admin = Boolean(me.admin);
    $("mode").textContent = admin ? `${me.user} · staff view` : "learner view";
    $("mode").dataset.state = admin ? "admin" : "learner";
    $("who").replaceChildren(admin
      ? el("span", {}, "signed in as ", el("b", { text: me.email || me.user || "staff" }))
      : el("a", { href: "https://atheniq.courses/login", text: "Sign in" }));
    $("view-label").textContent = admin ? "Platform Services" : "Catalog";
    $("generation").hidden = !admin;
    $("generation-link").hidden = !admin;
    $("tools-link").hidden = !admin;
  } catch (error) {
    $("who").textContent = "";
  }

  try {
    catalog = await api("/api/catalog");
  } catch (error) {
    $("program-grid").replaceChildren(el("p", { class: "empty", text: `The catalog could not be read: ${error.message}` }));
    $("course-rows").replaceChildren(el("tr", {}, el("td", { colspan: "5", class: "empty",
      text: "The catalog could not be read." })));
    return;
  }
  renderStats();
  renderPrograms(catalog.programs || []);
  renderCourses(catalog.courses || []);

  $("filter").addEventListener("input", (event) => filterCourses(event.target.value));
  if (admin) {
    await loadRuns();
    $("generate-missing").addEventListener("click", async (event) => {
      const button = event.currentTarget;
      button.disabled = true;
      try {
        const answer = await api("/api/admin/generate-missing", {
          method: "POST",
          headers: { "Content-Type": "application/json", "X-Atheniq-Portal": "1" },
          body: "{}",
        });
        const started = (answer.started || []).length;
        toast(started ? `Queued ${started} classroom(s).` : "Nothing is missing a classroom.");
        await loadRuns();
      } catch (error) {
        toast(`Could not queue: ${error.message}`);
      } finally {
        button.disabled = false;
      }
    });
    setInterval(loadRuns, 20000);
  }
}

load();
