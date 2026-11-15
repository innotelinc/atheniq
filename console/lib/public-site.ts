import { money } from "./format";
import type { Course, Database, Program, Track } from "./types";

/**
 * The public site is a projection of the platform, never a second source of
 * truth: a published course appears, an archived one disappears, and every
 * price is the same USD figure the console bills.
 */

export function publicCourses(db: Database): Course[] {
  return db.courses
    .filter((course) => course.status === "published")
    .sort((a, b) => a.code.localeCompare(b.code));
}

export function publicPrograms(db: Database): Program[] {
  return db.programs.filter((program) => program.status === "active");
}

export function publicTracks(db: Database): Track[] {
  return db.tracks.filter((track) => track.status === "active");
}

/** USD, or the access plan when a course is not sold singly. */
export function priceLabel(course: Course): string {
  if (course.price.amountCents) return `${money(course.price.amountCents)} USD`;
  if (course.price.plan) return `Included with ${course.price.plan}`;
  return "Free";
}

export function programTuition(program: Program): string {
  return `${money(program.totalCredits * program.tuitionPerCreditCents)} USD`;
}

export function issuedCredentials(db: Database) {
  return db.credentials
    .filter((credential) => ["issued", "signed"].includes(credential.status))
    .sort((a, b) => (b.issuedAt ?? b.createdAt).localeCompare(a.issuedAt ?? a.createdAt));
}
