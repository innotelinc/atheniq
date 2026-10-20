// Library — the shared shelves a course draws media from.
//
// The page lists what exists and creates a shelf. Files are put into a shelf
// through the storage host (ONYX for the object-storage option), which is why a
// row says how many assets it holds rather than offering an upload it cannot
// finish on its own.

const el = (tag, attrs = {}, ...children) => {
  const node = document.createElement(tag);
  for (const [key, value] of Object.entries(attrs)) {
    if (value === null || value === undefined || value === false) continue;
    if (key === "class") node.className = value;
    else if (key === "dataset") Object.assign(node.dataset, value);
    else if (key.startsWith("on")) node.addEventListener(key.slice(2), value);
    else node.setAttribute(key, value === true ? "" : value);
  }
  for (const child of children.flat()) {
    if (child === null || child === undefined || child === false) continue;
    node.append(child instanceof Node ? child : document.createTextNode(String(child)));
  }
  return node;
};

const state = { me: null, libraries: [] };
let timer = null;

const toast = (message, kind = "ok") => {
  const box = document.getElementById("toast");
  box.textContent = message;
  box.dataset.kind = kind;
  box.hidden = false;
  clearTimeout(timer);
  timer = setTimeout(() => { box.hidden = true; }, kind === "bad" ? 9000 : 5000);
};

const api = async (path, options = {}) => {
  const response = await fetch(path, {
    credentials: "same-origin",
    headers: { "X-Atheniq-Console": "1", "Content-Type": "application/json" },
    ...options,
  });
  const text = await response.text();
  if (!response.ok) throw new Error(text || `request failed (${response.status})`);
  return text ? JSON.parse(text) : null;
};

const isStaff = () => Boolean(state.me && state.me.mayGenerate);

const row = (library) => el("div", { class: "course", dataset: { open: "1" } },
  el("div", { class: "row" },
    el("div", {},
      el("div", { class: "t" }, library.name),
      el("div", { class: "m" },
        el("code", {}, library.slug),
        ` · ${library.assets} asset${library.assets === 1 ? "" : "s"}`,
        ` · ${library.source}`,
        library.created ? ` · ${library.created.slice(0, 10)}` : ""),
      library.description ? el("div", { class: "m" }, library.description) : null,
    ),
    el("div", { class: "actions" },
      el("span", { class: "state" },
        el("i", { class: `dot ${library.assets ? "ok" : ""}`.trim() }),
        library.assets ? "stocked" : "empty"),
    ),
  ),
);

const render = () => {
  const host = document.getElementById("libraries");
  host.replaceChildren();
  document.getElementById("counts").textContent =
    `${state.libraries.length} librar${state.libraries.length === 1 ? "y" : "ies"}`;
  if (!state.libraries.length) {
    host.append(el("p", { class: "empty" },
      "No libraries yet. A course that shares media with another is the reason to make the first one."));
    return;
  }
  for (const library of state.libraries) host.append(row(library));
};

const load = async () => {
  try {
    const answer = await api("/api/library");
    state.libraries = answer.libraries || [];
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
  document.getElementById("library-hint").textContent = isStaff()
    ? "staff only"
    : "read-only: your account is not in a staff group";

  document.getElementById("library-form").addEventListener("submit", async (event) => {
    event.preventDefault();
    const button = document.getElementById("library-submit");
    button.disabled = true;
    try {
      const answer = await api("/api/library", {
        method: "POST",
        body: JSON.stringify({
          name: document.getElementById("library-name").value.trim(),
          description: document.getElementById("library-description").value.trim(),
          source: document.getElementById("library-source").value,
        }),
      });
      state.libraries = answer.libraries || [];
      render();
      toast(`Library ${answer.created.slug} created`);
      document.getElementById("library-form").reset();
    } catch (error) {
      toast(error.message, "bad");
    } finally {
      button.disabled = false;
    }
  });

  await load();
};

boot();
