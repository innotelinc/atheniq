import { createHmac, timingSafeEqual } from "node:crypto";
import type { Database, EnrollmentAccess, Learner } from "./types";
import { catalogCard, progressOf, type Progress } from "./mobile-shape";
import { coursewareUrl, liveCourses } from "./lms";

/**
 * The student portal: a learner's own page on the web.
 *
 * The console's session belongs to staff, and the app's bearer token lives in a
 * phone. A browser needs a third thing, so the portal has its own signed cookie
 * with its own label — neither a console session nor an app token can ever be
 * replayed as it. The password is the learner's existing scrypt hash: the portal
 * adds a surface, not a second set of credentials to keep in step.
 */

export const PORTAL_COOKIE = "atheniq_learner";

/** A term is ~16 weeks; a student should not re-authenticate mid-term. */
const TTL_SECONDS = 30 * 24 * 60 * 60;

function secret(): string {
  return process.env.AUTH_SECRET || process.env.AUTH_PASSWORD || "atheniq-dev";
}

function signature(body: string): string {
  return createHmac("sha256", secret()).update(`portal:${body}`).digest("base64url");
}

export function issuePortalSession(learnerId: string): { value: string; maxAge: number } {
  const issued = Date.now().toString(36);
  const body = `${learnerId}.${issued}`;
  return { value: `pl.${body}.${signature(body)}`, maxAge: TTL_SECONDS };
}

/** Returns the learner id, or null for anything expired, tampered with or absent. */
export function readPortalSession(token: string | undefined | null): string | null {
  if (!token) return null;
  const parts = token.split(".");
  if (parts.length !== 4 || parts[0] !== "pl") return null;
  const [, learnerId, issued, mac] = parts;
  if (!learnerId || !issued) return null;
  const expected = signature(`${learnerId}.${issued}`);
  if (mac.length !== expected.length) return null;
  if (!timingSafeEqual(Buffer.from(mac), Buffer.from(expected))) return null;
  const at = Number.parseInt(issued, 36);
  if (!Number.isFinite(at) || Date.now() - at > TTL_SECONDS * 1000) return null;
  return learnerId;
}

export interface PortalCourse {
  id: string;
  code: string;
  title: string;
  key: string;
  credits: number;
  access: EnrollmentAccess;
  enrolledAt: string;
  completedAt: string | null;
  progress: Progress;
  /** False also means "the LMS did not answer in time", not necessarily missing. */
  liveInLms: boolean;
  coursewareUrl: string | null;
}

export interface PortalBilling {
  reference: string;
  amountCents: number;
  courseKey: string;
  status: string;
  createdAt: string;
}

export interface PortalCertificate {
  id: string;
  verifyId: string;
  title: string;
  type: string;
  status: string;
  /** A credential exists before it is issued, so this is genuinely nullable. */
  issuedAt: string | null;
}

export interface PortalNews {
  id: string;
  title: string;
  body: string;
  publishedAt: string;
  pinned: boolean;
}

export interface PortalView {
  learner: {
    id: string;
    name: string;
    email: string;
    programName: string | null;
    enrolledAt: string;
    /** Reserved institute address, shown so the student knows what to give out. */
    mailbox: { address: string; status: string } | null;
  };
  news: PortalNews[];
  stats: {
    enrolled: number;
    completed: number;
    credits: number;
    certificates: number;
    outstandingCents: number;
  };
  courses: PortalCourse[];
  billing: PortalBilling[];
  certificates: PortalCertificate[];
}

export async function portalView(db: Database, learner: Learner): Promise<PortalView> {
  const programNames = new Map(db.programs.map((program) => [program.id, program.name]));
  const live = await liveCourses(db.settings.lms.baseUrl);

  const courses: PortalCourse[] = db.enrollments
    .filter((enrollment) => enrollment.learnerId === learner.id)
    .map((enrollment) => {
      const course = db.courses.find((item) => item.id === enrollment.courseId);
      if (!course) return null;
      const card = catalogCard(course, programNames);
      return {
        id: enrollment.id,
        code: card.code,
        title: card.title,
        key: card.key,
        credits: card.credits,
        access: enrollment.access ?? "open",
        enrolledAt: enrollment.enrolledAt,
        completedAt: enrollment.completedAt,
        progress: progressOf(course, enrollment),
        liveInLms: live.has(card.key),
        coursewareUrl: coursewareUrl(db.settings.lms.baseUrl, card.key),
      };
    })
    .filter((item): item is NonNullable<typeof item> => Boolean(item))
    // Unfinished work first, then most recently touched.
    .sort((a, b) => {
      if (Boolean(a.completedAt) !== Boolean(b.completedAt)) return a.completedAt ? 1 : -1;
      return (b.enrolledAt || "").localeCompare(a.enrolledAt || "");
    });

  const billing: PortalBilling[] = db.purchases
    .filter((purchase) => purchase.learnerId === learner.id)
    .map((purchase) => ({
      reference: purchase.reference,
      amountCents: purchase.amountCents,
      courseKey: purchase.courseKey,
      status: purchase.status,
      createdAt: purchase.createdAt,
    }))
    .sort((a, b) => b.createdAt.localeCompare(a.createdAt));

  const certificates: PortalCertificate[] = db.credentials
    .filter((credential) => credential.learner.username === learner.username)
    .map((credential) => ({
      id: credential.id,
      verifyId: credential.verifyId,
      title: credential.title,
      type: credential.type,
      status: credential.status,
      issuedAt: credential.issuedAt,
    }))
    .sort((a, b) => (b.issuedAt ?? "").localeCompare(a.issuedAt ?? ""));

  // Only what this student can act on: the whole school, or their own cohort.
  const news: PortalNews[] = (db.news ?? [])
    .filter((post) => post.audience === "all" || post.audience === learner.programId)
    .sort(
      (a, b) =>
        Number(b.pinned) - Number(a.pinned) || b.publishedAt.localeCompare(a.publishedAt),
    )
    .slice(0, 6)
    .map((post) => ({
      id: post.id,
      title: post.title,
      body: post.body,
      publishedAt: post.publishedAt,
      pinned: post.pinned,
    }));

  const completed = courses.filter((course) => course.completedAt);

  return {
    learner: {
      id: learner.id,
      name: learner.name,
      email: learner.email,
      programName: learner.programId ? programNames.get(learner.programId) ?? null : null,
      enrolledAt: learner.enrolledAt,
      mailbox: learner.mailbox
        ? { address: learner.mailbox.address, status: learner.mailbox.status }
        : null,
    },
    news,
    stats: {
      enrolled: courses.length,
      completed: completed.length,
      credits: completed.reduce((sum, course) => sum + course.credits, 0),
      certificates: certificates.filter((certificate) => certificate.status === "issued").length,
      // What the student still owes: a claimed payment is not yet a settled one.
      outstandingCents: billing
        .filter((entry) => entry.status === "pending" || entry.status === "claimed")
        .reduce((sum, entry) => sum + entry.amountCents, 0),
    },
    courses,
    billing,
    certificates,
  };
}
