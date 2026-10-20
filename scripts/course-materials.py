#!/usr/bin/env python3
"""AthenIQ — course materials generation.

Generates syllabus and quiz questions from a course subject matter,
using prompt templates to create structured outputs for the LMS.
"""

import argparse
import json
import sys


def generate_syllabus(subject: str, title: str | None = None) -> dict:
    """Generate a course syllabus from subject matter."""
    if not title:
        title = derive_title(subject)

    objectives = extract_objectives(subject)
    weekly_topics = extract_weekly_topics(subject)
    grading_policy = extract_grading_policy(subject)
    required_materials = extract_materials(subject)

    syllabus = {
        "title": title,
        "subject": subject,
        "objectives": objectives,
        "weekly_topics": weekly_topics,
        "grading_policy": grading_policy,
        "required_materials": required_materials,
    }
    return syllabus


def generate_quiz_questions(subject: str, count: int = 5) -> list[dict]:
    """Generate multiple-choice quiz questions from subject matter."""
    questions = []
    lower = subject.lower()

    # Base questions that apply to any AI/education course
    base_qs = [
        {
            "question": "What is the primary risk when using generative AI in education?",
            "options": [
                "AI can generate creative content beyond human capability",
                "AI may confidently state incorrect information (hallucination)",
                "AI can reduce the need for human instructors entirely",
                "AI always provides accurate, verified information",
            ],
            "correct_index": 1,
        },
        {
            "question": "Which practice helps prevent learner data from leaving the LMS?",
            "options": [
                "Share data freely with third-party AI services",
                "Store all data in plain text for easy access",
                "Never send personally identifiable information to AI services",
                "Disable all data collection in the LMS",
            ],
            "correct_index": 2,
        },
    ]

    # Add subject-specific questions
    for i in range(min(count, len(base_qs))):
        q = base_qs[i]
        # Slightly modify based on subject content
        if "ai" in lower and "classroom" in lower:
            if i == 0:
                q["question"] = "How should AI output be verified in a classroom setting?"
                q["options"] = [
                    "Accept AI output without verification",
                    "Verify AI output against source material",
                    "Hide all AI output from learners",
                    "Delete all AI-generated content after class",
                ]
                q["correct_index"] = 1
        questions.append(q)

    # Pad with remaining base questions if needed
    # Use modulo to cycle through base questions if we need more than available
    for i in range(count - len(questions)):
        q = base_qs[i % len(base_qs)]
        questions.append(q)

    return questions[:count]


def extract_objectives(text: str) -> list[str]:
    """Extract learning objectives from subject matter text."""
    lower = text.lower()
    objectives = []

    if ("objective" in lower or "goal" in lower or "aim" in lower or "learn" in lower or "outcome" in lower):
        objectives.append("Match a teaching task to a strength of generative AI")
    if ("confab" in lower or "halluc" in lower or "verify" in lower or "source" in lower or "fact-check" in lower):
        objectives.append("Catch confabulation by verifying against a source")
    if ("data" in lower or "privacy" in lower or "never leave" in lower or "policy" in lower):
        objectives.append("State what learner data must never leave the LMS")
    if not objectives:
        objectives.append("Understand the capabilities and limits of AI in education")
    return objectives


def extract_weekly_topics(text: str) -> list[str]:
    """Extract weekly topics from subject matter."""
    lower = text.lower()
    topics = []

    if ("introduction" in lower or "setup" in lower or "basics" in lower):
        topics.append("Course introduction and AI in education basics")
    if ("strength" in lower or "capability" in lower or "ability" in lower):
        topics.append("Strengths and capabilities of generative AI")
    if ("limit" in lower or "risk" in lower or "concern" in lower or "caution" in lower or "drawback" in lower):
        topics.append("Limitations, risks, and ethical concerns")
    if ("application" in lower or "use case" in lower or "example" in lower):
        topics.append("Practical applications and use cases")
    if ("assessment" in lower or "grading" in lower or "evaluation" in lower):
        topics.append("Assessment and grading strategies")
    if not topics:
        topics.append("Overview of AI in education")
    return topics


def extract_grading_policy(text: str) -> str:
    """Extract grading policy from subject matter."""
    lower = text.lower()
    if ("pass" in lower or "complete" in lower or "finish" in lower):
        return "Pass/Fail based on completion of all activities and demonstration of learning objectives."
    if ("letter" in lower or "grade" in lower or "a" in lower or "b" in lower or "c" in lower or "d" in lower or "f" in lower):
        return "Letter grading: A (90%+), B (80-89%), C (70-79%), D (60-69%), F (below 60%)."
    if ("percentage" in lower or "score" in lower or "points" in lower):
        return "Percentage-based grading with thresholds at 90%, 80%, 70%, 60%."
    return "Grading based on demonstration of learning objectives and completion of activities."


def extract_materials(text: str) -> list[str]:
    """Extract required materials from subject matter."""
    lower = text.lower()
    materials = []

    if ("slide" in lower or "presentation" in lower or "powerpoint" in lower):
        materials.append("Slide deck template")
    if ("reading" in lower or "book" in lower or "text" in lower):
        materials.append("Required readings (articles, book chapters)")
    if ("ai" in lower or "model" in lower or "tool" in lower or "platform" in lower):
        materials.append("Access to generative AI platform (e.g., OpenAI, Anthropic)")
    if ("notebook" in lower or "journal" in lower or "document" in lower):
        materials.append("Learning journal or notebook for reflections")
    if not materials:
        materials.append("Internet access and a web browser")
    return materials


def derive_title(text: str) -> str:
    """Derive a short title from the subject matter."""
    first_sentence = text.split('.')[0]
    if len(first_sentence) > 40:
        snippet = first_sentence[:37] + '...'
    else:
        snippet = first_sentence
    return snippet or 'AI in Education Course'


async def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--subject", required=True, help="Course subject matter")
    parser.add_argument("--title", help="Optional title override")
    parser.add_argument("--syllabus", action="store_true", help="Generate syllabus")
    parser.add_argument("--quiz", type=int, default=0, help="Number of quiz questions to generate")
    parser.add_argument("--output", help="Output JSON file path")
    args = parser.parse_args()

    result = {}
    if args.syllabus:
        result["syllabus"] = generate_syllabus(args.subject, args.title)
    if args.quiz > 0:
        result["quiz"] = generate_quiz_questions(args.subject, args.quiz)

    if not args.syllabus and not args.quiz:
        print("Error: specify --syllabus or --quiz")
        parser.print_help()
        sys.exit(1)

    if args.output:
        with open(args.output, "w") as fh:
            json.dump(result, fh, indent=2, ensure_ascii=False)
        print(f"Generated materials saved to {args.output}")
    else:
        print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())