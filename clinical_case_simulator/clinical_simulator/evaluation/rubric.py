"""Weights and heuristics shared by the scorer.

Kept in one place so a faculty reviewer can retune the marking scheme without
reading the scoring code.
"""

# Contribution of each skill to the overall score (research doc, section 7).
SKILL_WEIGHTS = {
    "history_taking": 0.20,
    "communication": 0.10,
    "clinical_reasoning": 0.25,
    "differential_diagnosis": 0.20,
    "investigation_selection": 0.15,
    "case_synthesis": 0.10,
}

# Words a patient should not be asked to understand.  Used as a communication
# signal, not as a hard penalty on medical vocabulary in the reasoning phase.
JARGON = [
    "dyspnea", "dyspnoea", "orthopnea", "orthopnoea", "syncope", "diaphoresis",
    "hemoptysis", "haemoptysis", "haematemesis", "hematemesis", "melena",
    "melaena", "paroxysmal nocturnal dyspnoea", "pnd", "claudication",
    "paresthesia", "paraesthesia", "myalgia", "arthralgia", "anorexia",
    "polyuria", "polydipsia", "pruritus", "dysuria", "odynophagia",
    "dysphagia", "epistaxis", "tenesmus", "oedema", "edema", "icterus",
    "pallor", "cyanosis", "palpitations", "radiation", "aggravating",
    "alleviating", "prodrome", "comorbidity", "etiology", "aetiology",
]

OPEN_STARTERS = [
    "what", "how", "why", "tell me", "describe", "walk me through",
    "can you tell", "could you tell", "can you describe", "what else",
]

EMPATHY_MARKERS = [
    "sorry to hear", "that sounds", "i understand", "thank you for",
    "must be", "take your time", "is that ok", "how are you feeling",
    "i'm going to", "i am going to", "does that make sense",
]

# Cap the credit a student can claim after leaning on hints.
HINT_PENALTY = {0: 1.00, 1: 0.94, 2: 0.86, 3: 0.75}
REVEAL_PENALTY = 0.60

BANDS = [
    (85, "Excellent", "Performing at or above the expected level for this case."),
    (70, "Good", "Solid performance with clear, addressable gaps."),
    (55, "Borderline", "The core approach is there but key steps were missed."),
    (0, "Needs work", "Rework the structured approach to this presentation."),
]


def band(score: float) -> tuple[str, str]:
    for cut, label, note in BANDS:
        if score >= cut:
            return label, note
    return BANDS[-1][1], BANDS[-1][2]
