// AthenIQ console — domain types.
// Mirrors the shapes the AthenIQ platform already publishes:
//   config/course-prices.json      -> Course.price
//   config/workforce-tracks.json   -> Track
//   config/workforce-programs.json -> Program (workforce)
//   course-v1:ORG+CODE+TERM        -> Course.key
//   Signara signing ledger         -> Credential.signara

export type CourseStatus = "draft" | "in_review" | "published" | "archived";

export type LessonType =
  | "reading"
  | "video"
  | "lab"
  | "discussion"
  | "quiz"
  | "project"
  | "exam";

export interface Lesson {
  id: string;
  title: string;
  type: LessonType;
  minutes: number;
}

export interface CourseModule {
  id: string;
  title: string;
  summary: string;
  lessons: Lesson[];
  assessment: string;
}

export interface GradingComponent {
  component: string;
  weight: number;
}

export interface CoursePrice {
  /** Magnate plan that gates access, e.g. "premium"; null means free. */
  plan: string | null;
  /** One-off hosted checkout price in cents, when the course is sold singly. */
  amountCents: number | null;
}

export interface Course {
  id: string;
  code: string;
  term: string;
  title: string;
  slug: string;
  key: string;
  org: string;
  credits: number;
  level: 100 | 200 | 300 | 400 | 500;
  department: string;
  programIds: string[];
  trackIds: string[];
  summary: string;
  description: string;
  outcomes: string[];
  audience: string;
  prerequisites: string[];
  modules: CourseModule[];
  grading: GradingComponent[];
  price: CoursePrice;
  status: CourseStatus;
  image: string;
  generationId: string | null;
  publishedAt: string | null;
  createdAt: string;
  updatedAt: string;
}

export interface SemesterCourse {
  code: string;
  title: string;
}

export interface Semester {
  number: number;
  focus: string;
  credits: number;
  courses: SemesterCourse[];
}

export type ProgramStatus = "active" | "draft" | "retired";

export interface Program {
  id: string;
  slug: string;
  name: string;
  credential: string;
  credentialType: "Bachelor" | "Associate" | "Master" | "Certificate";
  department: string;
  summary: string;
  totalCredits: number;
  tuitionPerCreditCents: number;
  semesters: Semester[];
  status: ProgramStatus;
  accreditation: string;
  signaraTemplate: string;
  createdAt: string;
  updatedAt: string;
}

export type TrackKind = "certificate" | "badge" | "degree";

export interface TrackCredential {
  type: TrackKind;
  title: string;
  signara_template: string;
}

export interface Track {
  id: string;
  title: string;
  summary: string;
  audience: string;
  targetRole: string;
  status: "active" | "draft" | "retired";
  /** Course keys, in ladder order. */
  courses: string[];
  credential: TrackCredential;
  entitlement: { plan: string | null };
  skills: string[];
  createdAt: string;
  updatedAt: string;
}

export interface Learner {
  id: string;
  username: string;
  name: string;
  email: string;
  programId: string | null;
  enrolledAt: string;
  /** scrypt hash for app sign-in; absent on learners the registrar created. */
  passwordHash?: string | null;
  lastSeenAt?: string | null;
  /** Expo push token for the device this learner last signed in on. */
  pushToken?: string | null;
}

export type EnrollmentAccess = "open" | "pending_payment" | "paid" | "granted";

/** One learner's run through one course, taken in the app. */
export interface Enrollment {
  id: string;
  learnerId: string;
  courseId: string;
  courseKey: string;
  enrolledAt: string;
  lastSeenAt: string;
  completedLessonIds: string[];
  /** Written answers for quiz, exam, project and discussion lessons. */
  responses: Record<string, string>;
  completedAt: string | null;
  /** Whether lessons are open yet: paid courses start pending. */
  access: EnrollmentAccess;
  purchaseId?: string | null;
}

/** A priced course the learner says they paid for, awaiting the registrar. */
export interface Purchase {
  id: string;
  learnerId: string;
  courseId: string;
  courseKey: string;
  amountCents: number;
  /** Printed to the learner and quoted in the claim. */
  reference: string;
  status: "pending" | "claimed" | "confirmed" | "declined";
  note: string;
  createdAt: string;
  decidedAt: string | null;
  decidedBy: string | null;
  /** True when a registrar opened the course without a payment. */
  granted: boolean;
}

export interface Completion {
  id: string;
  learnerId: string;
  courseKey: string;
  grade: string;
  completedOn: string;
  status: "pass" | "fail";
}

export type CredentialType =
  | "course_certificate"
  | "track_credential"
  | "degree_conferral";

export type CredentialStatus =
  | "draft"
  | "queued_local"
  | "submitted"
  | "partial"
  | "signed"
  | "issued"
  | "revoked"
  | "failed";

export interface CredentialEvidence {
  grade?: string;
  completedOn?: string;
  courses?: string[];
  credits?: number;
  gpa?: string;
  program?: string;
}

export interface SignaraRecord {
  documentId: string | null;
  requestId: string | null;
  signerToken: string | null;
  apiBase: string | null;
  lastHttp: number | null;
  lastError: string | null;
}

export interface Credential {
  id: string;
  /** Public verification id, printed on the certificate. */
  verifyId: string;
  type: CredentialType;
  title: string;
  subjectRef: string;
  subjectLabel: string;
  learner: { username: string; name: string; email: string };
  evidence: CredentialEvidence;
  status: CredentialStatus;
  signara: SignaraRecord;
  template: string;
  signer: { name: string; title: string; email: string };
  /** sha256 over the canonical credential payload (evidence hash). */
  hash: string;
  previewPath: string | null;
  createdAt: string;
  updatedAt: string;
  signedAt: string | null;
  issuedAt: string | null;
  revokedAt: string | null;
  revokeReason: string | null;
  timeline: { at: string; label: string; detail?: string }[];
}

export type LogoPlacement = "left" | "center" | "right";

/** What this school is called and how it is marked, wherever the console speaks for it. */
export interface BrandSettings {
  siteName: string;
  tagline: string;
  /** Absolute or root-relative image URL; empty falls back to the monogram. */
  logoUrl: string;
  /** Up to three characters used as the monogram when no image is set. */
  logoText: string;
  logoPlacement: LogoPlacement;
  /** Six-digit hex accent for the public site. */
  accent: string;
  supportEmail: string;
  /** Show “Powered by AthenIQ” in the public footer. */
  poweredBy: boolean;
  domain: string;
}

/**
 * Retired with /site. The console no longer renders or publishes a website —
 * that is a static tree, `web/landing/`, published by a deploy script — but the
 * shape stays so stored records and old exports keep parsing. No page edits
 * these, and the integrations API ignores a caller that sends them.
 */
export interface SiteSettings {
  published: boolean;
  headline: string;
  intro: string;
  showPrices: boolean;
  showPrograms: boolean;
  showVerify: boolean;
  ctaLabel: string;
  ctaHref: string;
  lastPublishedAt: string | null;
}

export interface PasskeyRecord {
  id: string;
  /** Credential id, base64url, as the authenticator reports it. */
  credentialId: string;
  /** COSE public key, base64url. */
  publicKey: string;
  /** COSE algorithm: -7 ES256, -257 RS256. */
  algorithm: number;
  signCount: number;
  label: string;
  transports: string[];
  createdAt: string;
  lastUsedAt: string | null;
}

export type AuthOutcome =
  | "success"
  | "invalid_password"
  /** Well-formed address with no active account — not a bad password. */
  | "unknown_account"
  | "blocked_domain"
  | "totp_failed"
  | "recovery_used"
  | "passkey_failed";

export interface AuthEvent {
  id: string;
  at: string;
  email: string;
  outcome: AuthOutcome;
  detail: string;
  /** Address the attempt came from, or "this computer" for loopback. */
  source?: string;
}

export type AccessRequestStatus = "pending" | "approved" | "declined";

export interface AccessRequest {
  id: string;
  name: string;
  email: string;
  title: string;
  reason: string;
  /** scrypt hash of the password they chose; activation is the registrar's call. */
  passwordHash: string;
  status: AccessRequestStatus;
  createdAt: string;
  decidedAt: string | null;
  decidedBy: string | null;
}

/** Where an application stands. Only a registrar moves it past "received". */
export type ApplicationStatus = "received" | "reviewing" | "accepted" | "waitlisted" | "declined";

/** The transcript a learner uploaded with the application, as stored on disk. */
export interface TranscriptRef {
  /** What the applicant called the file, kept for the download. */
  fileName: string;
  mimeType: string;
  bytes: number;
  /** Basename under data/transcripts; never a path the client supplied. */
  storedAs: string;
  uploadedAt: string;
}

/**
 * One application to a program for a term. The goals statement and the
 * transcript are what admissions reads; everything else is the person and the
 * plan they picked, snapshotted so a later program rename does not rewrite
 * history.
 */
export interface Application {
  id: string;
  name: string;
  email: string;
  phone: string;
  programId: string;
  programName: string;
  term: string;
  goals: string;
  transcript: TranscriptRef | null;
  status: ApplicationStatus;
  /** The registrar's note: why it was decided, or what is still missing. */
  note: string;
  source: string;
  createdAt: string;
  updatedAt: string;
  decidedAt: string | null;
  decidedBy: string | null;
}

export type SessionEndReason =
  | "signed_out"
  | "ended_by_registrar"
  | "signed_out_everywhere"
  | "access_change"
  | "evicted";

/** A session that stopped being usable, kept after the registry row is pruned. */
export interface SessionEnd {
  id: string;
  sessionId: string;
  staffId: string;
  source: string;
  startedAt: string;
  endedAt: string;
  reason: SessionEndReason;
  /** Who ended it, when a person did; null for eviction and sign-out. */
  endedBy: ActorRef | null;
}

/** One live sign-in, so a single address can only hold a few at once. */
export interface LoginSession {
  id: string;
  staffId: string;
  /** "this computer" or the client IP the sign-in came from. */
  source: string;
  createdAt: string;
  expiresAt: string;
  revokedAt: string | null;
  /** First sign-in this person has ever made from this source. */
  newSource?: boolean;
}

/** The Vaultwarden account created for a staff member. */
export interface VaultLink {
  id: string;
  email: string;
  url: string;
  createdAt: string;
  /**
   * Personal API key minted while the password was known, so the console can
   * tell whether the account still exists. Server-only — never sent to a browser.
   */
  apiKey?: string | null;
  /** True when the vault account uses the same password as the console login. */
  sharedPassword?: boolean | null;
}

export interface StaffTotp {
  /** base32 secret; null until enrollment starts. */
  secret: string | null;
  enabled: boolean;
  enrolledAt: string | null;
  /** sha256 of each unused recovery code — the codes themselves are shown once. */
  recoveryCodes: string[];
}

/** Who may hold an account, and what it takes to sign in. */
export interface AuthSettings {
  /** Registered domains; staff emails must end with one of these. */
  allowedDomains: string[];
  /** Require an authenticator code for every sign-in. */
  require2fa: boolean;
}

export interface MailSettings {
  /** Comma-separated recipients for the operations digest. */
  digestTo: string;
  /**
   * Where security alerts go. Empty means every registrar; set one address to
   * keep alerts out of personal inboxes.
   */
  alertsTo: string;
  /** Days between digests; drives the reminder, not the scheduler. */
  cadenceDays: number;
  lastDigestAt: string | null;
}

export interface Settings {
  org: string;
  orgShort: string;
  defaultTerm: string;
  creditsPerCourse: number;
  tuitionPerCreditCents: number;
  applicationFeeCents: number;
  graduationFeeCents: number;
  lms: {
    baseUrl: string;
    studioUrl: string;
    catalogUrl: string;
    importUrl: string;
    apiToken: string;
  };
  signara: {
    baseUrl: string;
    apiKey: string;
    autoSign: boolean;
    defaultTemplate: string;
    /** ISO date the current key stops working; drives the rotation warning. */
    keyExpiresAt: string | null;
    /** Public prefix Signara shows for the key, e.g. sgn_pxIWWf. */
    keyPrefix: string;
  };
  ai: {
    baseUrl: string;
    apiKey: string;
    model: string;
  };
  signer: { name: string; title: string; email: string };
  sites: { instituteUrl: string; coursesUrl: string; workforceUrl: string };
  brand: BrandSettings;
  site: SiteSettings;
  mail: MailSettings;
  auth: AuthSettings;
}

export type StaffRole = "registrar" | "publisher";

export interface Staff {
  id: string;
  email: string;
  name: string;
  title: string;
  role: StaffRole;
  /** scrypt$<salt>$<hash> — never leaves the server. */
  passwordHash: string;
  createdAt: string;
  lastLoginAt: string | null;
  disabled: boolean;
  totp: StaffTotp;
  passkeys: PasskeyRecord[];
  /** Vaultwarden account created when this person was added, when reachable. */
  vault?: VaultLink | null;
  /** Sources this person has signed in from before, so a new one can be flagged. */
  seenSources?: string[];
}

/** Who did it, denormalised onto the activity trail so it survives edits. */
export interface ActorRef {
  id: string;
  name: string;
  email: string;
  role: StaffRole;
}

export interface CourseDraft {
  code: string;
  title: string;
  summary: string;
  description: string;
  outcomes: string[];
  audience: string;
  prerequisites: string[];
  level: 100 | 200 | 300 | 400 | 500;
  credits: number;
  department: string;
  modules: CourseModule[];
  grading: GradingComponent[];
}

export type GenerationEngine = "model" | "rules" | "pending";

export interface GenMessage {
  id: string;
  role: "user" | "assistant";
  content: string;
  at: string;
  engine?: GenerationEngine;
  changes?: string[];
}

export interface GenVersion {
  id: string;
  at: string;
  label: string;
  draft: CourseDraft;
}

export interface GenSession {
  id: string;
  idea: string;
  audience: string;
  level: 100 | 200 | 300 | 400 | 500;
  credits: number;
  term: string;
  department: string;
  engine: GenerationEngine;
  draft: CourseDraft | null;
  versions: GenVersion[];
  messages: GenMessage[];
  courseId: string | null;
  createdAt: string;
  updatedAt: string;
}

export interface Activity {
  id: string;
  at: string;
  kind:
    | "course.created"
    | "course.published"
    | "course.updated"
    | "program.updated"
    | "session.created"
    | "session.revised"
    | "credential.issued"
    | "credential.signed"
    | "credential.revoked"
    | "settings.updated"
    | "site.updated"
    | "key.rotated"
    | "digest.sent"
    | "learner.enrolled"
    | "learner.completed"
    | "course.purchased"
    | "application.received"
    | "application.decided";
  message: string;
  ref: string;
  actor?: ActorRef | null;
}

export interface Database {
  version: number;
  staff: Staff[];
  courses: Course[];
  programs: Program[];
  tracks: Track[];
  learners: Learner[];
  enrollments: Enrollment[];
  purchases: Purchase[];
  completions: Completion[];
  credentials: Credential[];
  sessions: GenSession[];
  activity: Activity[];
  accessRequests: AccessRequest[];
  applications: Application[];
  authLog: AuthEvent[];
  loginSessions: LoginSession[];
  /** Recently ended sessions; capped, so the list survives pruning. */
  sessionEnds?: SessionEnd[];
  settings: Settings;
}

/** The exact body AthenIQ publishes to atheniq.courses for one course. */
export interface CatalogListing {
  id: string;
  name: string;
  number: string;
  org: string;
  short_description: string;
  start: string;
  enrollment_start: string;
  enrollment_end: string;
  pacing: "instructor" | "self";
  media: { course_image: { uri: string }; banner_image: { uri: string } };
  price: CoursePrice;
  access: string;
}

export interface PublishManifest {
  courseKey: string;
  generatedAt: string;
  listing: CatalogListing;
  priceEntry: { name: string; plan: string | null; amount_cents: number | null };
  trackPatches: {
    trackId: string;
    trackTitle: string;
    courses: string[];
    credential: TrackCredential;
  }[];
  programPatches: {
    programId: string;
    programName: string;
    semester: number;
    focus: string;
    courses: SemesterCourse[];
  }[];
  olxFiles: { path: string; content: string; bytes: number }[];
  checks: { id: string; label: string; ok: boolean; detail: string }[];
  blocking: string[];
  warnings: string[];
}
