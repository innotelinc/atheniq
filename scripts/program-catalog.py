#!/usr/bin/env python3
"""AthenIQ — program catalog.

A whole credential is more than a pile of courses: it is an ordered set of
semesters, each course carrying credit hours, prerequisites, and a final
assessment, ending in a degree or certificate that is only conferred once every
requirement is met. This module is the source of truth for that shape.

Three complete programs ship here, because they are the ones the platform is
being asked to run:

    criminal-justice         Bachelor of Science in Criminal Justice (120 cr, 8 semesters)
    business-administration  Bachelor of Business Administration      (120 cr, 8 semesters)
    nursing                  Associate of Science in Nursing          ( 75 cr, 5 semesters)

Every course is a `Course`; every term is a `Semester`; the credential is a
`ProgramTemplate`. `program-manager.py` turns a template into a stored program,
checks the prerequisite graph, plans generation, and tracks a learner to
conferral. Nothing here touches the network or the filesystem: it is data and
two helpers, so the catalog can be imported by the console, a batch script, or
a test with equal ease.

Stdlib only, like every other script in this tree.
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Course:
    """One course in a program's sequence."""

    code: str
    title: str
    credits: int
    description: str
    prerequisites: tuple[str, ...] = ()
    #: How the course is finally assessed. `comprehensive` is a proctored final
    #: exam; `practical` is a lab or clinical check-off; `project` and
    #: `portfolio` are submitted work; `none` is a participation-only seminar.
    final_exam: str = "comprehensive"
    #: core | general-education | elective | clinical | capstone
    kind: str = "core"
    #: How many OpenMAIC classrooms to generate for the course (one per
    #: chapter-sized unit of teaching).
    classrooms: int = 4

    def as_dict(self) -> dict:
        return {
            "code": self.code,
            "title": self.title,
            "credits": self.credits,
            "description": self.description,
            "prerequisites": list(self.prerequisites),
            "finalExam": self.final_exam,
            "kind": self.kind,
            "classrooms": self.classrooms,
        }


@dataclass(frozen=True)
class Semester:
    """One term of a program: a numbered, named set of courses."""

    number: int
    name: str
    courses: tuple[Course, ...]

    @property
    def credits(self) -> int:
        return sum(course.credits for course in self.courses)

    def as_dict(self) -> dict:
        return {
            "number": self.number,
            "name": self.name,
            "credits": self.credits,
            "courses": [course.as_dict() for course in self.courses],
        }


@dataclass(frozen=True)
class Certificate:
    """A stackable credential earned part-way through a program."""

    slug: str
    name: str
    after_semester: int
    required_courses: tuple[str, ...]
    description: str

    def as_dict(self) -> dict:
        return {
            "slug": self.slug,
            "name": self.name,
            "afterSemester": self.after_semester,
            "requiredCourses": list(self.required_courses),
            "description": self.description,
        }


@dataclass(frozen=True)
class ProgramTemplate:
    """A complete credential: semesters, courses, and conferral rules."""

    slug: str
    name: str
    credential: str
    credential_kind: str          # degree | certificate
    level: str                    # associate | bachelor | certificate
    total_credits: int
    description: str
    semesters: tuple[Semester, ...]
    certificates: tuple[Certificate, ...] = ()
    #: Minimum credit-weighted GPA on a 4.0 scale to confer the credential.
    min_gpa: float = 2.0
    #: Every program ends in a comprehensive final; this names the capstone.
    capstone: str = ""

    def course_index(self) -> dict[str, Course]:
        """Every course by code, across every semester."""
        return {course.code: course for semester in self.semesters
                for course in semester.courses}

    def semester_of(self, code: str) -> int:
        for semester in self.semesters:
            if any(course.code == code for course in semester.courses):
                return semester.number
        return 0

    def as_dict(self) -> dict:
        return {
            "slug": self.slug,
            "name": self.name,
            "credential": self.credential,
            "credentialKind": self.credential_kind,
            "level": self.level,
            "totalCredits": self.total_credits,
            "description": self.description,
            "minGpa": self.min_gpa,
            "capstone": self.capstone,
            "semesters": [semester.as_dict() for semester in self.semesters],
            "certificates": [cert.as_dict() for cert in self.certificates],
        }


def _c(code, title, credits, description, prereq=(), final="comprehensive",
       kind="core", classrooms=4) -> Course:
    return Course(code=code, title=title, credits=credits, description=description,
                  prerequisites=tuple(prereq), final_exam=final, kind=kind,
                  classrooms=classrooms)


# ---------------------------------------------------------------------------
# Criminal Justice — Bachelor of Science, 120 credits, 8 semesters
# ---------------------------------------------------------------------------

#: The degree this program awards. A title, not a secret — named once so the
#: template, the registrar export and the certificate all read the same string.
CRIMINAL_JUSTICE_AWARD = "Bachelor of Science in Criminal Justice"

_CRIMINAL_JUSTICE = ProgramTemplate(
    slug="criminal-justice",
    name="Criminal Justice",
    credential=CRIMINAL_JUSTICE_AWARD,
    credential_kind="degree",
    level="bachelor",
    total_credits=120,
    min_gpa=2.0,
    capstone="CJ450 Capstone Seminar II",
    description=(
        "A four-year degree for people who will work inside the justice system or "
        "alongside it: policing, courts, corrections, investigations, and policy. "
        "The sequence moves from how the system is built, to how evidence and law "
        "constrain it, to how it is led and reformed. Every core course ends in an "
        "assessment; the degree ends in a capstone and a comprehensive final."
    ),
    semesters=(
        Semester(1, "Fall — Foundations", (
            _c("CJ101", "Introduction to Criminal Justice", 3,
               "The three components of the justice system — police, courts, and "
               "corrections — and how a case moves through them. Learners map one "
               "real case from report to disposition and name each decision point.",
               kind="core"),
            _c("ENGL101", "College Writing", 3,
               "Argument, evidence, and citation for academic and professional "
               "writing. Learners revise one analytical essay against feedback.",
               final="portfolio", kind="general-education"),
            _c("MATH110", "College Algebra", 3,
               "Functions, linear systems, and applied modeling. Learners solve "
               "problems drawn from crime-rate and budget data.",
               final="comprehensive", kind="general-education"),
            _c("PSYC101", "Introduction to Psychology", 3,
               "Perception, memory, motivation, and behavior, with emphasis on "
               "eyewitness memory and stress response.",
               final="comprehensive", kind="general-education"),
            _c("CJ110", "Law Enforcement Ethics", 3,
               "Discretion, force, and integrity. Learners work through dilemma "
               "scenarios and defend a decision against a stated policy.",
               final="project", kind="core"),
        )),
        Semester(2, "Spring — The System in Motion", (
            _c("CJ102", "Criminology", 3,
               "Theories of why crime happens — strain, control, learning, and "
               "rational choice — tested against reported crime data.",
               prereq=("CJ101",)),
            _c("CJ120", "Criminal Law", 3,
               "Elements of offenses, mens rea, defenses, and the limits of "
               "statute. Learners brief cases and apply the elements to facts.",
               prereq=("CJ101",)),
            _c("CJ130", "Policing in America", 3,
               "Patrol, investigation, and community policing, including the "
               "history of reform and the evidence on what works.",
               prereq=("CJ101",)),
            _c("ENGL102", "Research and Writing", 3,
               "Finding, evaluating, and citing sources; writing a literature "
               "review in the social sciences.",
               prereq=("ENGL101",), final="portfolio", kind="general-education"),
            _c("SOC101", "Introduction to Sociology", 3,
               "Structure, inequality, and institutions, with attention to race, "
               "class, and the criminal legal system.",
               final="comprehensive", kind="general-education"),
        )),
        Semester(3, "Fall — Law, Evidence, and the State", (
            _c("CJ201", "Criminal Procedure", 3,
               "Search and seizure, interrogation, identification, and the "
               "exclusionary rule. Learners argue a suppression motion.",
               prereq=("CJ120",)),
            _c("CJ210", "Corrections and Penology", 3,
               "Incarceration, probation, parole, and reentry, with the evidence "
               "on recidivism and the economics of custody.",
               prereq=("CJ101",)),
            _c("CJ220", "Forensic Science I", 4,
               "Crime-scene processing, chain of custody, fingerprints, and "
               "trace evidence. Laboratory check-offs count toward the final.",
               prereq=("CJ120", "MATH110"), final="practical", classrooms=5),
            _c("STAT200", "Statistics for Social Science", 3,
               "Describing and testing data: rates, distributions, confidence, "
               "and the difference between correlation and cause.",
               prereq=("MATH110",), kind="general-education"),
            _c("CJ230", "Juvenile Justice", 3,
               "The juvenile court, diversion, and developmental evidence, "
               "including the consequences of trying youth as adults.",
               prereq=("CJ102",)),
        )),
        Semester(4, "Spring — Investigation and Threat", (
            _c("CJ240", "Criminal Investigations", 4,
               "Case theory, interviews, warrants, and evidence management. "
               "Learners build an investigative plan for a simulated case.",
               prereq=("CJ220", "CJ130"), final="project", classrooms=5),
            _c("CJ250", "Homeland Security and Terrorism", 3,
               "Threat models, intelligence sharing, and civil-liberties "
               "trade-offs in domestic security policy.",
               prereq=("CJ101",)),
            _c("CJ260", "Ethics and Professional Responsibility", 3,
               "Professional standards, discipline, and the cost of a compromised "
               "investigation. Learners write a departmental policy memo.",
               prereq=("CJ110",), final="project"),
            _c("POL201", "American Government", 3,
               "Federalism, separation of powers, and the courts as policy actors.",
               final="comprehensive", kind="general-education"),
            _c("CJ270", "Cybercrime Fundamentals", 3,
               "Fraud, intrusion, and digital evidence, from report to referral. "
               "Learners trace one incident across jurisdictions.",
               prereq=("CJ210",)),
        )),
        Semester(5, "Fall — Constitutional Limits", (
            _c("CJ301", "Constitutional Law", 3,
               "Due process, equal protection, and the Fourth, Fifth, and Sixth "
               "Amendments as applied to policing and prosecution.",
               prereq=("CJ201",)),
            _c("CJ310", "Forensic Science II", 4,
               "DNA, toxicology, firearms, and expert testimony. Learners "
               "cross-examine a mock expert report.",
               prereq=("CJ220",), final="practical", classrooms=5),
            _c("CJ320", "Victimology", 3,
               "Victimization patterns, trauma-informed practice, and the "
               "victim's role in a case. Learners design a support referral.",
               prereq=("CJ102",)),
            _c("CJ330", "Criminal Justice Research Methods", 3,
               "Design, sampling, and measurement for justice research. Learners "
               "write a defensible evaluation plan.",
               prereq=("STAT200",), final="project"),
            _c("CJ340", "Emergency Management", 2,
               "Incident command, mutual aid, and continuity of operations for "
               "justice agencies.",
               prereq=("CJ250",)),
        )),
        Semester(6, "Spring — Practice", (
            _c("CJ350", "Advanced Policing Strategies", 3,
               "Hot-spot policing, problem-oriented policing, and the evidence "
               "base. Learners compare two strategies on outcome and legitimacy.",
               prereq=("CJ240",)),
            _c("CJ360", "Courtroom Procedure and Testimony", 3,
               "Direct and cross examination, foundation, and the officer as "
               "witness. Learners testify in a recorded mock hearing.",
               prereq=("CJ301",), final="practical"),
            _c("CJ370", "Restorative Justice", 3,
               "Conferencing, repair, and the limits of restoration, with "
               "comparison to retributive responses.",
               prereq=("CJ320",)),
            _c("CJ380", "Intelligence Analysis", 3,
               "Collection, analysis, and dissemination, including bias and "
               "confidence language in analytic products.",
               prereq=("CJ270",), final="project"),
            _c("CJ390", "Field Practicum I", 3,
               "Supervised placement in a justice agency with a weekly reflective "
               "log and a supervisor evaluation.",
               prereq=("CJ240",), final="practical", kind="clinical", classrooms=3),
        )),
        Semester(7, "Fall — Leadership and Policy", (
            _c("CJ401", "Criminal Justice Policy", 3,
               "Agenda setting, implementation, and evaluation. Learners cost one "
               "policy alternative against its stated goal.",
               prereq=("CJ330",), final="project"),
            _c("CJ410", "Leadership in Criminal Justice", 3,
               "Command climate, accountability, and change management in "
               "hierarchical agencies.",
               prereq=("CJ260",)),
            _c("CJ420", "Capstone Seminar I", 3,
               "Framing a question, reviewing the evidence, and defending a "
               "method. Produces the capstone proposal.",
               prereq=("CJ360",), final="project", kind="capstone"),
            _c("CJ430", "Digital Forensics", 3,
               "Acquisition, preservation, and analysis of digital devices, with "
               "attention to admissibility.",
               prereq=("CJ310", "CJ270"), final="practical"),
            _c("CJ440", "Field Practicum II", 3,
               "Second supervised placement with an expanded caseload and a "
               "written analysis of one agency process.",
               prereq=("CJ390",), final="practical", kind="clinical", classrooms=3),
        )),
        Semester(8, "Spring — Conferral", (
            _c("CJ450", "Capstone Seminar II", 3,
               "Completing, presenting, and defending the capstone against a "
               "review panel.",
               prereq=("CJ420",), final="portfolio", kind="capstone"),
            _c("CJ460", "Criminal Justice Internship", 6,
               "Full-term internship with a capstone reflection on practice and "
               "a supervisor's competency assessment.",
               prereq=("CJ440",), final="practical", kind="clinical", classrooms=4),
            _c("CJ470", "Comprehensive Final Examination", 1,
               "A proctored, cumulative examination across the core: law, "
               "procedure, evidence, policing, corrections, and policy.",
               prereq=("CJ401", "CJ410", "CJ430"), final="comprehensive"),
            _c("CJ480", "Professional Portfolio", 3,
               "Assembling written work, practicum evaluations, and a "
               "professional statement for the credential file.",
               prereq=("CJ410",), final="portfolio"),
        )),
    ),
    certificates=(
        Certificate(
            slug="cj-foundations",
            name="Criminal Justice Foundations Certificate",
            after_semester=2,
            required_courses=("CJ101", "CJ102", "CJ120", "CJ130", "CJ110"),
            description=(
                "A stackable certificate for learners who complete the first year "
                "of the justice core: the system, its law, and its ethics."
            ),
        ),
    ),
)


# ---------------------------------------------------------------------------
# Business Administration — Bachelor of Business Administration, 120 credits
# ---------------------------------------------------------------------------

#: The degree this program awards. A title, not a secret — named once so the
#: template, the registrar export and the certificate all read the same string.
BUSINESS_AWARD = "Bachelor of Business Administration"

_BUSINESS = ProgramTemplate(
    slug="business-administration",
    name="Business Administration",
    credential=BUSINESS_AWARD,
    credential_kind="degree",
    level="bachelor",
    total_credits=120,
    min_gpa=2.0,
    capstone="BUS496 Capstone: Strategy Simulation",
    description=(
        "A four-year degree across the functions every organization runs on — "
        "accounting, finance, marketing, operations, people, and strategy. The "
        "sequence builds the numbers first, then the functions, then the "
        "integration: a consulting practicum, a business plan, and a strategy "
        "simulation defended in front of a panel."
    ),
    semesters=(
        Semester(1, "Fall — The Language of Business", (
            _c("BUS101", "Introduction to Business", 3,
               "How firms create and capture value: markets, models, and the "
               "functions inside a company. Learners map one real firm end to end."),
            _c("ACCT201", "Financial Accounting", 3,
               "The income statement, balance sheet, and cash flow, built from "
               "transactions. Learners prepare a full set of statements."),
            _c("ECON101", "Microeconomics", 3,
               "Supply, demand, elasticity, and market structure. Learners predict "
               "the effect of a price change on revenue.",
               final="comprehensive", kind="general-education"),
            _c("ENGL101", "College Writing", 3,
               "Argument and evidence for business writing. Learners revise a "
               "persuasive memo against feedback.",
               final="portfolio", kind="general-education"),
            _c("BUS110", "Business Communication", 3,
               "Audience, structure, and tone in memos, decks, and difficult "
               "conversations. Learners deliver a recorded briefing.",
               final="practical"),
        )),
        Semester(2, "Spring — Decision Foundations", (
            _c("ACCT202", "Managerial Accounting", 3,
               "Cost behavior, contribution margin, and budgeting for decisions. "
               "Learners build a flexible budget and explain the variance.",
               prereq=("ACCT201",)),
            _c("ECON102", "Macroeconomics", 3,
               "Growth, inflation, and policy. Learners read a central-bank "
               "statement and forecast one consequence.",
               prereq=("ECON101",)),
            _c("BUS210", "Business Law I", 3,
               "Contracts, agency, and tort in commercial life. Learners analyze "
               "a contract dispute and pick the winning argument.",
               prereq=("BUS101",)),
            _c("MATH120", "Business Mathematics", 3,
               "Percentages, interest, present value, and break-even. Learners "
               "price a loan and a lease.",
               final="comprehensive", kind="general-education"),
            _c("BUS220", "Principles of Management", 3,
               "Planning, organizing, leading, and controlling, with the evidence "
               "on what managers actually do.",
               prereq=("BUS101",)),
        )),
        Semester(3, "Fall — The Functions", (
            _c("FIN301", "Principles of Finance", 3,
               "Time value of money, risk and return, and capital budgeting. "
               "Learners rank three projects by net present value.",
               prereq=("ACCT202", "ECON102")),
            _c("MKT301", "Principles of Marketing", 3,
               "Segmentation, positioning, and the marketing mix. Learners write a "
               "go-to-market plan for one product.",
               prereq=("BUS101",), final="project"),
            _c("BUS310", "Business Statistics", 3,
               "Sampling, hypothesis tests, and regression for managers, with a "
               "spreadsheet-based project.",
               prereq=("MATH120",), final="project"),
            _c("BUS320", "Organizational Behavior", 3,
               "Motivation, teams, power, and culture, applied to one real "
               "workplace case.",
               prereq=("BUS220",)),
            _c("BUS330", "Business Ethics", 3,
               "Stakeholder analysis and the ethics of profit. Learners defend a "
               "decision against three stakeholder positions.",
               prereq=("BUS210",), final="project"),
        )),
        Semester(4, "Spring — Running the Firm", (
            _c("FIN310", "Corporate Finance", 3,
               "Capital structure, cost of capital, and working capital. Learners "
               "recommend a financing plan.",
               prereq=("FIN301",)),
            _c("MKT320", "Consumer Behavior", 3,
               "How buyers decide: attention, framing, and habit. Learners design "
               "and critique an experiment.",
               prereq=("MKT301",), final="project"),
            _c("BUS340", "Operations Management", 3,
               "Process design, capacity, quality, and inventory. Learners map a "
               "process and remove one bottleneck.",
               prereq=("BUS310",)),
            _c("BUS350", "Management Information Systems", 3,
               "Data models, systems integration, and the build-versus-buy "
               "decision.",
               prereq=("BUS220",)),
            _c("BUS360", "Business Law II", 3,
               "Employment, intellectual property, and compliance. Learners audit "
               "a policy against the statute.",
               prereq=("BUS210",)),
        )),
        Semester(5, "Fall — Beyond the Domestic Market", (
            _c("BUS401", "International Business", 3,
               "Trade, entry modes, and cultural distance. Learners choose a "
               "market and defend the entry strategy.",
               prereq=("BUS330",), final="project"),
            _c("FIN410", "Investment Analysis", 3,
               "Valuation, portfolios, and risk. Learners value a company and "
               "state the assumptions that would break the thesis.",
               prereq=("FIN310",)),
            _c("MKT410", "Digital Marketing", 3,
               "Channels, attribution, and experimentation. Learners run a budget "
               "allocation against measured outcomes.",
               prereq=("MKT320",), final="project"),
            _c("BUS420", "Human Resource Management", 3,
               "Hiring, performance, and retention, with the evidence on each "
               "practice.",
               prereq=("BUS320",)),
            _c("BUS430", "Entrepreneurship", 3,
               "Opportunity, validation, and early finance. Learners test a "
               "venture hypothesis with real customer conversations.",
               prereq=("BUS330",), final="project"),
        )),
        Semester(6, "Spring — Integration", (
            _c("BUS440", "Supply Chain Management", 3,
               "Sourcing, logistics, and resilience. Learners redesign a supply "
               "chain against a disruption scenario.",
               prereq=("BUS340",), final="project"),
            _c("BUS450", "Business Analytics", 3,
               "Descriptive, predictive, and prescriptive analytics with a "
               "decision-ready dashboard.",
               prereq=("BUS310",), final="project"),
            _c("BUS460", "Strategic Management", 3,
               "Industry analysis, competitive advantage, and strategy choice. "
               "Learners write a strategy memo for a real firm.",
               prereq=("BUS401",), final="project"),
            _c("BUS470", "International Finance", 3,
               "Exchange rates, hedging, and cross-border capital budgeting.",
               prereq=("FIN410",)),
            _c("BUS480", "Project Management", 3,
               "Scope, schedule, risk, and stakeholders. Learners plan a project "
               "and defend the critical path.",
               prereq=("BUS350",), final="project"),
        )),
        Semester(7, "Fall — Practice", (
            _c("BUS490", "Business Consulting Practicum", 3,
               "A live client engagement: scope, diagnose, recommend, and present "
               "under a partner's review.",
               prereq=("BUS460",), final="project", classrooms=3),
            _c("BUS491", "Business Plan Development", 3,
               "Writing and defending a full plan: market, model, financials, and "
               "risk.",
               prereq=("BUS430",), final="portfolio"),
            _c("BUS492", "Corporate Governance", 3,
               "Boards, disclosure, and control, including the failures that "
               "produced current rules.",
               prereq=("BUS460",)),
            _c("BUS493", "Advanced Business Analytics", 3,
               "Forecasting, optimization, and causal inference for managers.",
               prereq=("BUS450",), final="project"),
            _c("BUS494", "Internship I", 3,
               "Supervised industry placement with a weekly log and supervisor "
               "evaluation.",
               prereq=("BUS440",), final="practical", kind="clinical", classrooms=3),
        )),
        Semester(8, "Spring — Conferral", (
            _c("BUS495", "Internship II", 3,
               "Second placement with an expanded deliverable and a written "
               "analysis of one business process.",
               prereq=("BUS494",), final="practical", kind="clinical", classrooms=3),
            _c("BUS496", "Capstone: Strategy Simulation", 3,
               "A multi-round competitive simulation: pricing, capacity, and "
               "capital decisions, defended round by round.",
               prereq=("BUS490",), final="project", kind="capstone", classrooms=5),
            _c("BUS497", "Comprehensive Final Examination", 1,
               "A proctored, cumulative examination across accounting, finance, "
               "marketing, operations, and strategy.",
               prereq=("BUS470", "BUS480", "BUS493"), final="comprehensive"),
            _c("BUS498", "Professional Portfolio", 3,
               "Assembling consulting work, internship evaluations, and a "
               "professional statement for the credential file.",
               prereq=("BUS493",), final="portfolio"),
            _c("BUS499", "Business Policy Seminar", 5,
               "Strategy under uncertainty: a live case, a board presentation, "
               "and a written policy recommendation.",
               prereq=("BUS492",), final="project", kind="capstone"),
        )),
    ),
    certificates=(
        Certificate(
            slug="business-foundations",
            name="Business Foundations Certificate",
            after_semester=2,
            required_courses=("BUS101", "ACCT201", "ECON101", "BUS210", "BUS220"),
            description=(
                "A stackable certificate for learners who complete the first year: "
                "the numbers, the market, and the management basics."
            ),
        ),
    ),
)


# ---------------------------------------------------------------------------
# Nursing — Associate of Science in Nursing, 75 credits, 5 semesters
# ---------------------------------------------------------------------------

#: The degree this program awards. A title, not a secret — named once so the
#: template, the registrar export and the certificate all read the same string.
NURSING_AWARD = "Associate of Science in Nursing"

_NURSING = ProgramTemplate(
    slug="nursing",
    name="Nursing",
    credential=NURSING_AWARD,
    credential_kind="degree",
    level="associate",
    total_credits=75,
    min_gpa=2.5,
    capstone="NUR430 Comprehensive Final Examination",
    description=(
        "A five-semester clinical program that prepares a graduate to sit the "
        "registered-nurse licensure examination. The sequence is deliberately "
        "front-loaded with anatomy, chemistry, and assessment, then moves through "
        "medical-surgical, maternal, paediatric, and mental-health nursing, and "
        "ends in critical care, leadership, and a comprehensive final with a "
        "supervised practicum."
    ),
    semesters=(
        Semester(1, "Semester 1 — Science Foundations", (
            _c("NUR101", "Foundations of Nursing", 4,
               "The nursing process, safety, infection control, and professional "
               "identity. Learners demonstrate hand hygiene and vital signs in "
               "lab check-offs.",
               final="practical", classrooms=5),
            _c("BIO201", "Anatomy and Physiology I", 4,
               "Cells, tissues, and the musculoskeletal, nervous, and endocrine "
               "systems, with lab practicals.",
               final="practical", kind="general-education", classrooms=5),
            _c("CHEM101", "General Chemistry", 4,
               "Matter, solutions, acids and bases, and the chemistry of "
               "intravenous fluids.",
               final="comprehensive", kind="general-education", classrooms=4),
            _c("PSYC101", "Introduction to Psychology", 3,
               "Development, memory, and stress response, with application to "
               "patient communication.",
               final="comprehensive", kind="general-education"),
        )),
        Semester(2, "Semester 2 — Assessment and Pharmacology", (
            _c("NUR110", "Health Assessment", 3,
               "History taking, physical examination, and documentation. Learners "
               "complete a full head-to-toe assessment under observation.",
               prereq=("NUR101",), final="practical", classrooms=4),
            _c("NUR120", "Fundamentals of Nursing Practice", 4,
               "Medication administration, wound care, and mobility, practiced in "
               "lab and simulated scenarios.",
               prereq=("NUR101",), final="practical", classrooms=5),
            _c("BIO202", "Anatomy and Physiology II", 4,
               "Cardiovascular, respiratory, renal, and digestive systems, with "
               "lab practicals.",
               prereq=("BIO201",), final="practical", kind="general-education", classrooms=5),
            _c("MICR201", "Microbiology", 4,
               "Pathogens, immunity, and sterilization, with a lab project on "
               "chain of infection.",
               prereq=("CHEM101",), final="practical", kind="general-education", classrooms=4),
            _c("NUR130", "Pharmacology I", 2,
               "Drug classes, mechanisms, and the rights of administration, with "
               "a dosage-calculation check-off.",
               prereq=("NUR101",), final="practical"),
        )),
        Semester(3, "Semester 3 — Medical-Surgical Core", (
            _c("NUR201", "Medical-Surgical Nursing I", 5,
               "Care of adults with acute and chronic illness: assessment, "
               "prioritization, and intervention. Clinical rotation alongside "
               "the classroom.",
               prereq=("NUR120", "BIO202"), final="practical", classrooms=6),
            _c("NUR210", "Pharmacology II", 2,
               "High-alert medications, interactions, and adverse effects, with "
               "case-based dosing decisions.",
               prereq=("NUR130",), final="practical"),
            _c("NUR220", "Maternal-Newborn Nursing", 3,
               "Pregnancy, birth, postpartum, and newborn care, with a simulated "
               "delivery and newborn assessment.",
               prereq=("NUR120",), final="practical", classrooms=4),
            _c("NUR230", "Nursing Ethics and Law", 2,
               "Consent, capacity, confidentiality, and scope of practice, argued "
               "through case scenarios.",
               prereq=("NUR110",), final="project"),
            _c("NUR240", "Nutrition and Health Promotion", 3,
               "Dietary assessment, therapeutic diets, and patient education "
               "across the lifespan.",
               prereq=("BIO202",), final="project"),
        )),
        Semester(4, "Semester 4 — Specialties", (
            _c("NUR301", "Medical-Surgical Nursing II", 5,
               "Complex and deteriorating patients: sepsis, cardiac events, and "
               "multi-system failure. Clinical rotation with a written case study.",
               prereq=("NUR201",), final="practical", classrooms=6),
            _c("NUR310", "Paediatric Nursing", 3,
               "Growth and development, paediatric assessment, and family-centred "
               "care, with a simulated paediatric emergency.",
               prereq=("NUR220",), final="practical", classrooms=4),
            _c("NUR320", "Mental Health Nursing", 3,
               "Therapeutic communication, crisis intervention, and psychotropic "
               "medication management.",
               prereq=("NUR201",), final="practical", classrooms=4),
            _c("NUR330", "Community Health Nursing", 3,
               "Population assessment, epidemiology, and public-health "
               "intervention, with a community project.",
               prereq=("NUR240",), final="project"),
            _c("NUR340", "Nursing Research and Evidence", 2,
               "Reading, appraising, and applying evidence, ending in a "
               "critically appraised topic.",
               prereq=("NUR230",), final="portfolio"),
        )),
        Semester(5, "Semester 5 — Conferral", (
            _c("NUR401", "Critical Care Nursing", 4,
               "Haemodynamics, ventilation, and titration of care in an intensive "
               "setting. Clinical rotation with a competency check-off.",
               prereq=("NUR301",), final="practical", classrooms=5),
            _c("NUR410", "Leadership and Management in Nursing", 3,
               "Delegation, staffing, quality, and conflict, applied to a unit "
               "improvement plan.",
               prereq=("NUR340",), final="project"),
            _c("NUR420", "Clinical Practicum", 4,
               "A supervised preceptorship with an expanded patient assignment "
               "and a preceptor competency evaluation.",
               prereq=("NUR301",), final="practical", kind="clinical", classrooms=3),
            _c("NUR430", "Comprehensive Final Examination", 1,
               "A proctored, cumulative examination across the nursing process, "
               "pharmacology, and all clinical specialties, aligned to licensure "
               "blueprints.",
               prereq=("NUR301", "NUR340"), final="comprehensive"),
        )),
    ),
    certificates=(
        Certificate(
            slug="nursing-foundations",
            name="Nursing Foundations Certificate",
            after_semester=2,
            required_courses=("NUR101", "NUR110", "NUR120", "NUR130", "BIO201"),
            description=(
                "A stackable certificate for learners who complete the first year: "
                "foundations, assessment, and safe medication practice."
            ),
        ),
    ),
)


#: Every program the platform ships. Order is the order the catalog shows.
PROGRAM_TEMPLATES: dict[str, ProgramTemplate] = {
    template.slug: template
    for template in (_CRIMINAL_JUSTICE, _BUSINESS, _NURSING)
}


def list_templates() -> list[dict]:
    """Every template as a summary, for the catalog page."""
    out = []
    for template in PROGRAM_TEMPLATES.values():
        out.append({
            "slug": template.slug,
            "name": template.name,
            "credential": template.credential,
            "credentialKind": template.credential_kind,
            "level": template.level,
            "totalCredits": template.total_credits,
            "semesters": len(template.semesters),
            "courses": len(template.course_index()),
            "description": template.description,
            "certificates": [cert.name for cert in template.certificates],
        })
    return out


def get_template(slug: str) -> ProgramTemplate:
    """One template by slug, or KeyError with a useful list."""
    try:
        return PROGRAM_TEMPLATES[slug]
    except KeyError:
        raise KeyError(f"no program template {slug!r}; "
                       f"known: {', '.join(PROGRAM_TEMPLATES)}") from None


def prerequisite_errors(template: ProgramTemplate) -> list[str]:
    """Every prerequisite that is missing or scheduled at the same time or later.

    A prerequisite that is taught in the same term as the course that needs it is
    not a prerequisite — it is a scheduling error that would make the plan
    impossible to walk. This returns human-readable problems, so both the
    catalog test and the API can refuse a broken program with a real reason.
    """
    index = template.course_index()
    problems: list[str] = []
    for semester in template.semesters:
        for course in semester.courses:
            for prereq in course.prerequisites:
                if prereq not in index:
                    problems.append(f"{course.code} needs {prereq}, which is not in the program")
                    continue
                if template.semester_of(prereq) >= semester.number:
                    problems.append(
                        f"{course.code} (semester {semester.number}) needs {prereq}, "
                        f"taught in semester {template.semester_of(prereq)}")
    return problems


def catalog_credits(template: ProgramTemplate) -> int:
    """Credits actually listed in the semesters (must equal total_credits)."""
    return sum(semester.credits for semester in template.semesters)
