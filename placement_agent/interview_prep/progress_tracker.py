# -*- coding: utf-8 -*-
"""
interview_prep/progress_tracker.py
Progress tracking for the Interview Preparation Agent.
Tracks completed topics, current difficulty, and suggests next steps.

Storage is ADK session state (``tool_context.state``), not process memory.
Deployed on Agent Runtime that is VertexAiSessionService, so a record survives
container restarts and is isolated per (app, user, session) by construction.

The user is identified from ``tool_context.session.user_id`` -- never from a
model-supplied argument. An earlier version took ``user_id`` as a tool
parameter and the prompt told the model to pass the literal 'default_user',
which merged every student's progress into one shared record.
"""

import time

from google.adk.tools.tool_context import ToolContext

# Session-state key holding this user's progress record.
_STATE_KEY = "interview_progress"

_TOPIC_AREAS = [
    "data_structures",
    "algorithms",
    "system_design",
    "behavioral",
    "sql_databases",
    "object_oriented_design",
    "statistics",
    "machine_learning_basics",
    "product_sense",
    "company_research",
]

_DIFFICULTY_LEVELS = ["easy", "medium", "hard"]

_BADGES = {
    "first_step":    {"label": "First Step",    "desc": "Completed your first topic."},
    "momentum":      {"label": "Momentum",      "desc": "Completed 3 topics."},
    "halfway":       {"label": "Halfway There", "desc": "Completed 5 topics."},
    "level_up":      {"label": "Level Up",      "desc": "Progressed to a harder difficulty."},
    "full_prep":     {"label": "Full Prep",     "desc": "Completed all topic areas."},
    "mock_hero":     {"label": "Mock Hero",     "desc": "Completed 3 mock interview sets."},
}


# ---------------------------------------------------------------------------
# Session-state access
# ---------------------------------------------------------------------------

def _user_id(tool_context: ToolContext) -> str:
    """The signed-in user, straight from the session. Never from the model."""
    session = getattr(tool_context, "session", None)
    return getattr(session, "user_id", "") or "unknown_user"


def _load(tool_context: ToolContext) -> dict | None:
    return tool_context.state.get(_STATE_KEY)


def _save(tool_context: ToolContext, record: dict) -> None:
    """Assign the whole record back.

    ADK tracks state deltas by assignment. Mutating a dict already sitting in
    state is not recorded, so the write would be silently dropped by the real
    session service.
    """
    record["last_active"] = time.time()
    tool_context.state[_STATE_KEY] = record


def _get_or_create(tool_context: ToolContext, role: str = "") -> dict:
    record = _load(tool_context)
    if record is None:
        record = {
            "user_id": _user_id(tool_context),
            "role": role,
            "current_difficulty": "easy",
            "completed_topics": [],
            "skipped_topics": [],
            "mock_interviews_done": 0,
            "questions_attempted": 0,
            "questions_correct": 0,
            "session_start": time.time(),
            "last_active": time.time(),
            "badges_earned": [],
            "notes": [],
        }
    if role and not record["role"]:
        record["role"] = role
    return record


def _check_and_award_badges(record: dict) -> list[str]:
    """Check progress milestones and award any new badges. Returns list of new badge labels."""
    new_badges = []
    earned = set(record["badges_earned"])

    completed = len(record["completed_topics"])
    mocks = record["mock_interviews_done"]

    if completed >= 1 and "first_step" not in earned:
        new_badges.append("first_step")
    if completed >= 3 and "momentum" not in earned:
        new_badges.append("momentum")
    if completed >= 5 and "halfway" not in earned:
        new_badges.append("halfway")
    if completed >= len(_TOPIC_AREAS) and "full_prep" not in earned:
        new_badges.append("full_prep")
    if mocks >= 3 and "mock_hero" not in earned:
        new_badges.append("mock_hero")
    if record["current_difficulty"] != "easy" and "level_up" not in earned:
        new_badges.append("level_up")

    for b in new_badges:
        record["badges_earned"].append(b)

    return new_badges


# ---------------------------------------------------------------------------
# Public tool functions
# ---------------------------------------------------------------------------

def init_progress(tool_context: ToolContext, role: str, difficulty: str = "easy") -> dict:
    """
    Initialize or reset the current user's interview preparation progress.

    Args:
        role: Target job role (e.g., 'software engineer').
        difficulty: Starting difficulty level: 'easy' | 'medium' | 'hard'.

    Returns:
        dict with the initialized progress record summary.
    """
    tool_context.state[_STATE_KEY] = None
    record = _get_or_create(tool_context, role)
    if difficulty in _DIFFICULTY_LEVELS:
        record["current_difficulty"] = difficulty
    _save(tool_context, record)
    return {
        "status": "initialized",
        "user_id": record["user_id"],
        "role": role,
        "starting_difficulty": record["current_difficulty"],
        "total_topics": len(_TOPIC_AREAS),
        "message": f"Progress tracker started for '{role}' at {difficulty} level.",
    }


def mark_topic_complete(tool_context: ToolContext, topic: str, role: str = "") -> dict:
    """
    Mark a preparation topic as completed and check for difficulty progression.

    Args:
        topic: Topic name (e.g., 'data_structures', 'behavioral', 'system_design').
        role: Optional role, used if no session exists yet.

    Returns:
        dict with updated progress, any new badges, and next topic suggestion.
    """
    record = _get_or_create(tool_context, role)

    if topic not in record["completed_topics"]:
        record["completed_topics"].append(topic)

    # Auto-level-up: every 3 completions, suggest next difficulty
    completed_count = len(record["completed_topics"])
    current_idx = _DIFFICULTY_LEVELS.index(record["current_difficulty"])
    if completed_count > 0 and completed_count % 3 == 0:
        new_idx = min(current_idx + 1, len(_DIFFICULTY_LEVELS) - 1)
        record["current_difficulty"] = _DIFFICULTY_LEVELS[new_idx]

    new_badges = _check_and_award_badges(record)
    _save(tool_context, record)

    # Suggest the next incomplete topic
    remaining = [t for t in _TOPIC_AREAS if t not in record["completed_topics"]]
    next_topic = remaining[0] if remaining else None

    return {
        "topic_marked": topic,
        "completed_topics": record["completed_topics"],
        "total_completed": completed_count,
        "current_difficulty": record["current_difficulty"],
        "next_suggested_topic": next_topic,
        "new_badges": [_BADGES[b] for b in new_badges],
        "remaining_topics": len(remaining),
    }


def log_question_attempt(
    tool_context: ToolContext,
    correct: bool,
    role: str = "",
) -> dict:
    """
    Log a question attempt and update accuracy stats.

    Args:
        correct: Whether the user answered correctly.
        role: Optional role, used if no session exists yet.

    Returns:
        dict with updated attempt stats and accuracy percentage.
    """
    record = _get_or_create(tool_context, role)
    record["questions_attempted"] += 1
    if correct:
        record["questions_correct"] += 1
    _save(tool_context, record)

    accuracy = (
        int(100 * record["questions_correct"] / record["questions_attempted"])
        if record["questions_attempted"] > 0 else 0
    )

    return {
        "questions_attempted": record["questions_attempted"],
        "questions_correct": record["questions_correct"],
        "accuracy_percent": accuracy,
        "current_difficulty": record["current_difficulty"],
    }


def log_mock_interview(tool_context: ToolContext, role: str = "") -> dict:
    """
    Log the completion of a full mock interview session.

    Args:
        role: Optional role, used if no session exists yet.

    Returns:
        dict with mock count, any new badges, and encouragement message.
    """
    record = _get_or_create(tool_context, role)
    record["mock_interviews_done"] += 1
    new_badges = _check_and_award_badges(record)
    _save(tool_context, record)

    messages = [
        "Great practice! Each mock makes the real thing easier.",
        "Mock #{}! You are building real interview muscle memory.".format(record["mock_interviews_done"]),
        "Excellent commitment! {} mocks done — you're well ahead of most candidates.".format(record["mock_interviews_done"]),
    ]
    msg = messages[min(record["mock_interviews_done"] - 1, len(messages) - 1)]

    return {
        "mock_interviews_done": record["mock_interviews_done"],
        "new_badges": [_BADGES[b] for b in new_badges],
        "message": msg,
    }


def get_progress_summary(tool_context: ToolContext) -> dict:
    """
    Get a full progress summary for the current user's preparation session.

    Returns:
        dict with completion stats, difficulty, badges, and next steps.
    """
    record = _load(tool_context)
    if record is None:
        return {
            "status": "no_session",
            "message": "No active session found. Start by telling me what role you are preparing for.",
        }

    completed = record["completed_topics"]
    remaining = [t for t in _TOPIC_AREAS if t not in completed]
    pct = int(100 * len(completed) / len(_TOPIC_AREAS)) if _TOPIC_AREAS else 0

    session_minutes = int((time.time() - record["session_start"]) / 60)

    return {
        "user_id": record["user_id"],
        "role": record["role"],
        "completion_percent": pct,
        "current_difficulty": record["current_difficulty"],
        "completed_topics": completed,
        "remaining_topics": remaining,
        "mock_interviews_done": record["mock_interviews_done"],
        "questions_attempted": record["questions_attempted"],
        "accuracy_percent": (
            int(100 * record["questions_correct"] / record["questions_attempted"])
            if record["questions_attempted"] > 0 else 0
        ),
        "badges_earned": [_BADGES[b] for b in record["badges_earned"] if b in _BADGES],
        "session_minutes": session_minutes,
        "next_steps": [
            f"Practice {remaining[0].replace('_', ' ')} questions at {record['current_difficulty']} level." if remaining else "All topics covered!",
            "Run a full mock interview to simulate the real experience.",
            "Review any topics where your accuracy is below 70%.",
        ],
    }


def suggest_next_step(tool_context: ToolContext) -> dict:
    """
    Suggest the single most impactful next preparation step for the current user.

    Returns:
        dict with a focused next action recommendation.
    """
    record = _load(tool_context)
    if record is None:
        return {
            "suggestion": "Start by telling me the role you are preparing for so I can build your personalized plan.",
            "action": "provide_role",
        }

    remaining = [t for t in _TOPIC_AREAS if t not in record["completed_topics"]]

    if not remaining:
        return {
            "suggestion": "You have covered all topic areas! Run a full mock interview at 'hard' difficulty to polish your performance.",
            "action": "mock_interview",
            "difficulty": "hard",
        }

    # Prioritize behavioral if not done (often neglected)
    if "behavioral" in remaining:
        return {
            "suggestion": f"Practice behavioral questions — these are often the deciding factor. Start with {record['current_difficulty']} level.",
            "action": "practice_questions",
            "topic": "behavioral",
            "difficulty": record["current_difficulty"],
        }

    return {
        "suggestion": f"Work on '{remaining[0].replace('_', ' ')}' at {record['current_difficulty']} difficulty.",
        "action": "practice_questions",
        "topic": remaining[0],
        "difficulty": record["current_difficulty"],
    }
