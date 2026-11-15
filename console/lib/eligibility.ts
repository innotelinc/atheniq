import type { Completion, Course, Database, Learner, Program, Track } from "./types";

export function courseByKey(db: Database, key: string): Course | undefined {
  return db.courses.find((course) => course.key === key);
}

export function learnerCompletions(db: Database, learnerId: string): Completion[] {
  return db.completions.filter((c) => c.learnerId === learnerId && c.status === "pass");
}

export function earnedKeys(db: Database, learnerId: string): string[] {
  return Array.from(new Set(learnerCompletions(db, learnerId).map((c) => c.courseKey)));
}

export function learnersForProgram(db: Database, programId: string): Learner[] {
  return db.learners.filter((learner) => learner.programId === programId);
}

export interface TrackEligibility {
  eligible: boolean;
  earned: string[];
  missing: string[];
  progress: number;
}

export function trackEligibility(
  db: Database,
  track: Track,
  learner: Learner,
): TrackEligibility {
  const earned = earnedKeys(db, learner.id);
  const inTrack = track.courses.filter((key) => earned.includes(key));
  const missing = track.courses.filter((key) => !earned.includes(key));
  return {
    eligible: track.courses.length > 0 && missing.length === 0,
    earned: inTrack,
    missing,
    progress: track.courses.length ? Math.round((inTrack.length / track.courses.length) * 100) : 0,
  };
}

export interface ProgramEligibility {
  creditsEarned: number;
  creditsRequired: number;
  coursesCompleted: number;
  eligible: boolean;
  progress: number;
  gpa: string;
}

export function programEligibility(
  db: Database,
  program: Program,
  learner: Learner,
): ProgramEligibility {
  const completions = learnerCompletions(db, learner.id);
  const codes = new Set(
    program.semesters.flatMap((semester) => semester.courses.map((course) => course.code)),
  );
  const relevant = completions.filter((c) => {
    const code = c.courseKey.split("+")[1];
    return codes.size === 0 || codes.has(code);
  });
  const creditsEarned = relevant.reduce((sum, completion) => {
    const course = courseByKey(db, completion.courseKey);
    return sum + (course?.credits ?? 3);
  }, 0);
  const grades = relevant
    .map((c) => Number(c.grade))
    .filter((n) => Number.isFinite(n) && n > 0);
  const gpa =
    grades.length > 0
      ? (grades.reduce((sum, g) => sum + gradePoint(g), 0) / grades.length).toFixed(2)
      : "—";

  return {
    creditsEarned,
    creditsRequired: program.totalCredits,
    coursesCompleted: relevant.length,
    eligible: creditsEarned >= program.totalCredits,
    progress: Math.min(100, Math.round((creditsEarned / Math.max(1, program.totalCredits)) * 100)),
    gpa,
  };
}

function gradePoint(score: number): number {
  if (score >= 93) return 4.0;
  if (score >= 90) return 3.7;
  if (score >= 87) return 3.3;
  if (score >= 83) return 3.0;
  if (score >= 80) return 2.7;
  if (score >= 77) return 2.3;
  if (score >= 73) return 2.0;
  if (score >= 70) return 1.7;
  if (score >= 67) return 1.3;
  if (score >= 60) return 1.0;
  return 0;
}

export interface AwardCandidate {
  learner: Learner;
  track?: Track;
  eligibility: TrackEligibility | ProgramEligibility;
  kind: "track" | "degree";
  ready: boolean;
}

/** Everyone who can be awarded the given subject right now. */
export function candidatesFor(db: Database, kind: "track" | "degree", ref: string): AwardCandidate[] {
  if (kind === "track") {
    const track = db.tracks.find((t) => t.id === ref);
    if (!track) return [];
    return db.learners
      .map((learner) => {
        const eligibility = trackEligibility(db, track, learner);
        return { learner, track, eligibility, kind: "track" as const, ready: eligibility.eligible };
      })
      .filter((candidate) => candidate.eligibility.earned.length > 0)
      .sort((a, b) => Number(b.ready) - Number(a.ready));
  }
  const program = db.programs.find((p) => p.id === ref);
  if (!program) return [];
  return learnersForProgram(db, program.id)
    .map((learner) => {
      const eligibility = programEligibility(db, program, learner);
      return { learner, eligibility, kind: "degree" as const, ready: eligibility.eligible };
    })
    .sort((a, b) => Number(b.ready) - Number(a.ready));
}

/** Award history for one learner, newest first. */
export function credentialsFor(db: Database, learnerId: string) {
  return db.credentials.filter((credential) => credential.learner.username === learnerId);
}
