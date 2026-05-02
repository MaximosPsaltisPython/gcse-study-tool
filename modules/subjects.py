SUBJECT_PROFILES = {
    "First Language English": {
        "focus": [
            "Directed writing",
            "Reading comprehension",
            "Summary writing",
            "Language analysis",
            "Speaking preparation",
        ],
        "question_styles": [
            "comprehension question",
            "directed writing task",
            "writer's effect analysis",
            "summary practice",
        ],
    },
    "Literature in English": {
        "focus": [
            "Poetry analysis",
            "Prose extract response",
            "Drama response",
            "Unseen-style paragraph planning",
        ],
        "question_styles": [
            "essay plan",
            "extract analysis",
            "theme comparison",
            "quotation recall",
        ],
    },
    "Economics": {
        "focus": [
            "Definitions and diagrams",
            "Calculation questions",
            "Short explanations",
            "Evaluation paragraphs",
        ],
        "question_styles": [
            "multiple choice",
            "calculation",
            "explain question",
            "evaluate question",
        ],
    },
    "Biology": {
        "focus": [
            "Core definitions",
            "Required practical ideas",
            "Data interpretation",
            "Extended responses",
        ],
        "question_styles": [
            "short answer",
            "data question",
            "six-mark explanation",
            "process recall",
        ],
    },
    "Geography": {
        "focus": [
            "Case studies",
            "Map and graph skills",
            "Process explanation",
            "Decision-making questions",
        ],
        "question_styles": [
            "case-study paragraph",
            "data interpretation",
            "explain question",
            "evaluate question",
        ],
    },
    "Physics": {
        "focus": [
            "Formula recall",
            "Calculation method",
            "Practical skills",
            "Explanation questions",
        ],
        "question_styles": [
            "calculation",
            "graph interpretation",
            "practical analysis",
            "concept explanation",
        ],
    },
    "Music": {
        "focus": [
            "Listening terminology",
            "Set work/style recognition",
            "Performing evidence",
            "Composition development",
        ],
        "question_styles": [
            "listening analysis",
            "terminology recall",
            "comparison question",
            "composition reflection",
        ],
    },
    "Further Mathematics": {
        "focus": [
            "Algebraic fluency",
            "Coordinate geometry",
            "Trigonometry",
            "Calculus and functions",
        ],
        "question_styles": [
            "multi-step calculation",
            "proof-style question",
            "graph sketching",
            "grade 9 challenge",
        ],
    },
}


def profile_for(subject: str) -> dict[str, list[str]]:
    return SUBJECT_PROFILES.get(subject, {"focus": [], "question_styles": []})
