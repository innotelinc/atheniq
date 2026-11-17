#!/usr/bin/env node
/**
 * The mobile API's contract, exercised against a running console.
 *
 * Covers the whole app surface: sign-up and sign-in, the free and paid enrollment
 * paths (including the reference and the registrar's confirmation), lesson
 * content, progress to completion, the certificate queue, offline bundles and
 * push registration.
 *
 *   node scripts/mobile-api-test.mjs
 *
 * Environment
 *   MOBILE_API      base URL of the console (default http://localhost:3100)
 *   STAFF_EMAIL     a registrar account, used to price a course and to confirm
 *   STAFF_PASSWORD  its password (the account must not need a second factor)
 *   PRICED_CODE     use this course instead of pricing one (e.g. FAI101)
 *   PRICE_CENTS     one-off price to set when the script has to create one
 *   KEEP_PRICE=1    leave the price in place (for a deployed console)
 *   STAFF_TOKEN     a staff bearer token, instead of signing in with a password
 *
 * Without staff credentials the script still runs everything it can and skips
 * the paid path with a clear message rather than pretending it passed.
 */
const BASE = (process.env.MOBILE_API || "http://localhost:3100").replace(/\/+$/, "");
const API = `${BASE}/api/mobile/v1`;
const STAFF_EMAIL = process.env.STAFF_EMAIL || "";
const STAFF_PASSWORD = process.env.STAFF_PASSWORD || "";
const PRICED_CODE = process.env.PRICED_CODE || "";
const PRICE_CENTS = Number(process.env.PRICE_CENTS || 14900);
const KEEP_PRICE = process.env.KEEP_PRICE === "1";

let failures = 0;
let skipped = 0;

function check(condition, message) {
  if (condition) {
    console.log(`ok    ${message}`);
  } else {
    failures += 1;
    console.log(`FAIL  ${message}`);
  }
}

function skip(message) {
  skipped += 1;
  console.log(`skip  ${message}`);
}

async function call(path, { method = "GET", body, token, raw = false } = {}) {
  const response = await fetch(`${API}${path}`, {
    method,
    headers: {
      ...(body ? { "content-type": "application/json" } : {}),
      ...(token ? { authorization: `Bearer ${token}` } : {}),
    },
    body: body ? JSON.stringify(body) : undefined,
  });
  if (raw) return response;
  const json = await response.json().catch(() => ({}));
  return { status: response.status, ...json };
}

async function consoleCall(path, { method = "GET", body, cookie } = {}) {
  const response = await fetch(`${BASE}${path}`, {
    method,
    headers: {
      ...(body ? { "content-type": "application/json" } : {}),
      ...(cookie ? { cookie } : {}),
    },
    body: body ? JSON.stringify(body) : undefined,
    redirect: "manual",
  });
  const text = await response.text();
  let json = {};
  try {
    json = JSON.parse(text);
  } catch {
    /* a redirect or HTML: the status and cookies are what matter */
  }
  const cookieHeader = response.headers
    .getSetCookie?.()
    .map((entry) => entry.split(";")[0])
    .join("; ");
  return { status: response.status, json, cookie: cookieHeader };
}

async function registrarCookie() {
  if (!STAFF_EMAIL || !STAFF_PASSWORD) return null;
  const login = await consoleCall("/api/auth/login", {
    method: "POST",
    body: { email: STAFF_EMAIL, password: STAFF_PASSWORD, next: "/" },
  });
  return login.cookie && login.cookie.includes("atheniq_session") ? login.cookie : null;
}

/** Price one published course, returning what it was so it can be put back. */
async function priceOneCourse() {
  const cookie = await registrarCookie();
  if (!cookie) return { priced: null, note: "no registrar session (set STAFF_EMAIL/STAFF_PASSWORD)" };
  const list = await consoleCall("/api/courses", { cookie });
  const courses = Array.isArray(list.json?.data) ? list.json.data : [];
  const target = courses.find((course) => course.status === "published");
  if (!target) return { priced: null, note: "no published course to price" };
  const before = target.price ?? { plan: null, amountCents: null };
  const patched = await consoleCall(`/api/courses/${target.id}`, {
    method: "PATCH",
    cookie,
    body: { plan: null, amountCents: PRICE_CENTS },
  });
  if (patched.status !== 200) return { priced: null, note: `could not price ${target.code} (${patched.status})` };
  return { priced: target.code, before, cookie, id: target.id };
}

async function restorePrice(change) {
  if (!change?.priced || KEEP_PRICE) return;
  await consoleCall(`/api/courses/${change.id}`, {
    method: "PATCH",
    cookie: change.cookie,
    body: { plan: change.before.plan, amountCents: change.before.amountCents },
  });
  console.log(`note  price on ${change.priced} restored`);
}

const stamp = Date.now().toString(36);
const email = `app-test-${stamp}@example.com`;

// --- catalog ------------------------------------------------------------
const catalog = await call("/catalog");
check(catalog.status === 200 && Array.isArray(catalog.data?.courses), "catalog is public");
check((catalog.data?.courses?.length ?? 0) > 0, `catalog has ${catalog.data?.courses?.length ?? 0} courses`);

let priced = catalog.data.courses.find((course) => course.price?.amountCents > 0);
let change = null;
if (!priced && PRICED_CODE) {
  priced = catalog.data.courses.find((course) => course.code === PRICED_CODE);
  check(Boolean(priced), `priced course ${PRICED_CODE} is in the catalog`);
}
if (!priced) {
  change = await priceOneCourse();
  if (change.priced) {
    const refreshed = await call("/catalog");
    priced = refreshed.data.courses.find((course) => course.code === change.priced);
    check(priced?.price?.amountCents === PRICE_CENTS, `${change.priced} priced at ${PRICE_CENTS} cents for the test`);
  } else {
    skip(`paid path: ${change.note}`);
  }
}

const free = catalog.data.courses.find(
  (course) => !course.price?.amountCents && course.code !== priced?.code,
);
check(Boolean(free), `a course without a one-off price exists (${free?.code})`);

// --- account --------------------------------------------------------------
const registered = await call("/auth/register", {
  method: "POST",
  body: { name: "API Test Learner", email, password: "correct-horse-9" },
});
check(registered.status === 201 && registered.data?.token, "learner creates an account");
const token = registered.data.token;

const login = await call("/auth/login", { method: "POST", body: { email, password: "correct-horse-9" } });
check(login.status === 200 && login.data?.token, "learner signs in");

const badLogin = await call("/auth/login", { method: "POST", body: { email, password: "wrong" } });
check(badLogin.status === 401, "wrong password is refused");

const duplicate = await call("/auth/register", {
  method: "POST",
  body: { name: "API Test Learner", email, password: "correct-horse-9" },
});
check(duplicate.status === 409, "the same address cannot register twice");

// --- free enrollment -------------------------------------------------------
const freeEnrol = await call("/enrollments", { method: "POST", body: { courseId: free.id }, token });
check(freeEnrol.data?.enrollment?.access === "open", "a course without a price opens immediately");
const freeDetail = await call(`/courses/${free.id}`, { token });
const freeLesson = freeDetail.data.modules[0].lessons[0];
const freeRead = await call(
  `/lesson?courseId=${encodeURIComponent(free.id)}&lessonId=${encodeURIComponent(freeLesson.id)}`,
  { token },
);
check(freeRead.status === 200 && freeRead.data.blocks.length >= 4, "free lesson has real content");

// --- paid enrollment -------------------------------------------------------
let paidCourse = null;
if (priced) {
  const enroll = await call("/enrollments", { method: "POST", body: { courseId: priced.id }, token });
  check(enroll.data?.enrollment?.access === "pending_payment", "a priced course starts locked");
  const reference = enroll.data?.checkout?.reference;
  check(Boolean(reference?.startsWith("ATH-")), `a payment reference is issued (${reference})`);
  check(enroll.data?.checkout?.amountCents === priced.price.amountCents, "the amount comes from the course");

  const detail = await call(`/courses/${priced.id}`, { token });
  const lesson = detail.data.modules[0].lessons[0];

  const locked = await call(
    `/lesson?courseId=${encodeURIComponent(priced.id)}&lessonId=${encodeURIComponent(lesson.id)}`,
    { token },
  );
  check(locked.status === 402, "lessons stay shut before confirmation");

  const checkout = await call("/checkout", { method: "POST", body: { courseId: priced.id }, token });
  check(checkout.data?.reference === reference, "checkout answers for the same enrollment");
  if (checkout.data?.url) {
    check(/^https?:\/\//.test(checkout.data.url), "checkout hands off to the configured URL");
  } else {
    check(checkout.data?.url === null, "without CHECKOUT_URL the app falls back to the reference");
  }

  const wrong = await call("/purchases/claim", {
    method: "POST",
    body: { courseId: priced.id, reference: "ATH-WRONG-00000" },
    token,
  });
  check(wrong.status === 422, "a claim with the wrong reference is refused");

  const claim = await call("/purchases/claim", {
    method: "POST",
    body: { courseId: priced.id, reference, note: "automated test" },
    token,
  });
  check(claim.status === 200 && claim.data?.status === "claimed", "claim accepted with the right reference");

  // A deployed console can be proved with a staff token issued on the host
  // (no password in the environment); CI signs in normally instead.
  let staffToken = process.env.STAFF_TOKEN || "";
  if (!staffToken && STAFF_EMAIL && STAFF_PASSWORD) {
    const staffLogin = await call("/staff/login", {
      method: "POST",
      body: { email: STAFF_EMAIL, password: STAFF_PASSWORD },
    });
    if (staffLogin.status === 200) staffToken = staffLogin.data.token;
    else skip(`registrar confirmation: staff sign-in answered ${staffLogin.status}`);
  }

  if (staffToken) {
    const overview = await call("/registrar", { token: staffToken });
    const queued = overview.data?.purchases?.find((item) => item.reference === reference);
    check(Boolean(queued), "the claim reaches the registrar's payment queue");
    check(queued?.status === "claimed", "the queue shows it as claimed");

    if (queued) {
      const denied = await call("/registrar/purchase", {
        method: "POST",
        body: { purchaseId: queued.id, action: "decline" },
        token: staffToken,
      });
      check(denied.data?.status === "declined", "a registrar can decline a claim");
      const stillLocked = await call(
        `/lesson?courseId=${encodeURIComponent(priced.id)}&lessonId=${encodeURIComponent(lesson.id)}`,
        { token },
      );
      check(stillLocked.status === 402, "declining keeps the course shut");

      await call("/purchases/claim", { method: "POST", body: { courseId: priced.id, reference }, token });
      const again = await call("/registrar", { token: staffToken });
      const requeued = again.data.purchases.find((item) => item.reference === reference);

      const confirm = await call("/registrar/purchase", {
        method: "POST",
        body: { purchaseId: requeued.id, action: "confirm" },
        token: staffToken,
      });
      check(confirm.data?.status === "confirmed", "a registrar confirms the payment");

      const opened = await call(`/courses/${priced.id}`, { token });
      check(opened.data?.enrollment?.access === "paid", "the enrollment is paid");
      const unlocked = await call(
        `/lesson?courseId=${encodeURIComponent(priced.id)}&lessonId=${encodeURIComponent(lesson.id)}`,
        { token },
      );
      check(unlocked.status === 200, "the lesson opens after confirmation");
      paidCourse = priced;
    } else {
      skip("confirm path: the claim never reached the queue");
    }
  } else {
    skip("registrar confirmation: no staff credentials or token");
  }
}

// --- progress to completion ----------------------------------------------
const course = paidCourse ?? free;
const detail = await call(`/courses/${course.id}`, { token });
const lessons = detail.data.modules.flatMap((module) => module.lessons);
let completed = null;
for (const lesson of lessons) {
  const content = await call(
    `/lesson?courseId=${encodeURIComponent(course.id)}&lessonId=${encodeURIComponent(lesson.id)}`,
    { token },
  );
  const result = await call("/progress", {
    method: "POST",
    body: {
      courseId: course.id,
      lessonId: lesson.id,
      done: true,
      response: content.data?.needsResponse
        ? "Applying the module standard to the intake process I run, and documenting the decision."
        : undefined,
    },
    token,
  });
  completed = result;
}
check(completed?.data?.completedAt, "the last lesson completes the course");
check(completed?.data?.progress?.percent === 100, "progress reads 100%");

const me = await call("/me", { token });
check(me.data?.stats?.completed >= 1, "the learner's page counts the completion");
check((me.data?.credentials?.length ?? 0) >= 1, "a certificate is queued for the registrar");
check(me.data.credentials[0].status === "queued_local", "the certificate waits for the registrar");

// --- offline and push -----------------------------------------------------
const offline = await call(`/offline?courseId=${encodeURIComponent(course.id)}`, { token });
check(offline.status === 200, "offline bundle downloads");
check(offline.data?.lessons?.length === lessons.length, "the bundle holds every lesson");
check(offline.data.lessons.every((lesson) => lesson.blocks.length >= 4), "bundled lessons have content");
check(Boolean(offline.data?.course?.modules?.length), "the bundle includes the curriculum");

const anonymousOffline = await call(`/offline?courseId=${encodeURIComponent(course.id)}`, { raw: true });
check(anonymousOffline.status === 401, "the bundle is not public");

const push = await call("/push/register", {
  method: "POST",
  body: { token: "ExponentPushToken[test-device]" },
  token,
});
check(push.status === 200 && push.data?.registered, "a device token registers");

await restorePrice(change);

console.log("");
console.log(`${failures === 0 ? "PASS" : "FAIL"} — ${failures} failure(s), ${skipped} skipped`);
if (change?.priced && KEEP_PRICE) console.log(`note  ${change.priced} left priced at ${PRICE_CENTS} cents`);
console.log(`note  test learner: ${email}`);
process.exit(failures === 0 ? 0 : 1);
