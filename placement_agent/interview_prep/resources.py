# -*- coding: utf-8 -*-
"""
interview_prep/resources.py
Curated role-specific resources, question banks, prep strategies,
and mock interview question sets for the Interview Preparation Agent.
"""

from typing import Optional

# ---------------------------------------------------------------------------
# Master resource library — keyed by role category
# ---------------------------------------------------------------------------

_RESOURCES: dict[str, dict] = {
    "software_engineer": {
        "description": "Software Engineer / SWE / Backend / Frontend / Full-Stack",
        "skill_areas": [
            "Data Structures & Algorithms",
            "System Design",
            "Object-Oriented Programming",
            "Database Design & SQL",
            "Operating Systems & Concurrency",
            "API Design & REST",
            "Version Control (Git)",
            "Testing & Debugging",
        ],
        "interview_formats": [
            "Online Assessments (LeetCode-style coding rounds)",
            "Technical Phone Screens (algorithm questions)",
            "System Design Interviews (whiteboard/virtual)",
            "Behavioral / HR rounds (STAR method)",
            "Take-home assignments",
        ],
        "resources": {
            "platforms": [
                {"name": "LeetCode", "url": "https://leetcode.com", "focus": "DSA practice, company-specific problems"},
                {"name": "NeetCode", "url": "https://neetcode.io", "focus": "Structured DSA roadmap with video explanations"},
                {"name": "HackerRank", "url": "https://hackerrank.com", "focus": "Coding challenges and certifications"},
                {"name": "GeeksforGeeks", "url": "https://geeksforgeeks.org", "focus": "CS fundamentals, interview articles"},
                {"name": "Pramp", "url": "https://pramp.com", "focus": "Free peer-to-peer mock interviews"},
                {"name": "Interviewing.io", "url": "https://interviewing.io", "focus": "Anonymous mock interviews with engineers"},
            ],
            "youtube": [
                {"name": "NeetCode YouTube", "url": "https://youtube.com/@NeetCode", "focus": "DSA solutions with clear explanations"},
                {"name": "TechLead", "url": "https://youtube.com/@TechLead", "focus": "FAANG interview experience & tips"},
                {"name": "Gaurav Sen", "url": "https://youtube.com/@gkcs", "focus": "System design deep dives"},
                {"name": "Clement Mihailescu (AlgoExpert)", "url": "https://youtube.com/@AlgoExpert", "focus": "Algorithm walkthroughs"},
                {"name": "Abdul Bari", "url": "https://youtube.com/@abdul_bari", "focus": "Algorithms from scratch"},
            ],
            "books_blogs": [
                {"name": "Cracking the Coding Interview", "url": "https://www.crackingthecodinginterview.com", "focus": "Classic SWE interview bible"},
                {"name": "System Design Primer (GitHub)", "url": "https://github.com/donnemartin/system-design-primer", "focus": "Free comprehensive system design guide"},
                {"name": "High Scalability Blog", "url": "http://highscalability.com", "focus": "Real-world system design case studies"},
                {"name": "roadmap.sh", "url": "https://roadmap.sh", "focus": "Developer skill roadmaps"},
            ],
        },
        "question_bank": {
            "technical_easy": [
                "Reverse a linked list.",
                "Check if a string is a palindrome.",
                "Find the two numbers in an array that add up to a target sum.",
                "Implement a stack using an array.",
                "Write a function to check if brackets are balanced.",
            ],
            "technical_medium": [
                "Find the longest substring without repeating characters.",
                "Implement a binary search tree with insert and search.",
                "Given a matrix, rotate it 90 degrees in place.",
                "Design an LRU (Least Recently Used) cache.",
                "Find all permutations of a string.",
            ],
            "technical_hard": [
                "Design a distributed rate limiter.",
                "Implement a trie with autocomplete functionality.",
                "Solve the N-Queens problem using backtracking.",
                "Design a URL shortener like bit.ly (system design).",
                "Find the median of a data stream in O(log n).",
            ],
            "behavioral": [
                "Tell me about a time you had to debug a critical production issue under pressure.",
                "Describe a project where you had to learn a new technology quickly.",
                "How do you handle disagreements with teammates about technical decisions?",
                "Tell me about a time you improved a process or system significantly.",
                "Describe a situation where you had to meet a tight deadline.",
            ],
            "system_design": [
                "Design Twitter's newsfeed.",
                "Design a ride-sharing app like Uber.",
                "Design a video streaming service like YouTube.",
                "Design a chat application like WhatsApp.",
                "Design a search autocomplete system.",
            ],
        },
    },

    "data_analyst": {
        "description": "Data Analyst / Business Analyst / BI Analyst",
        "skill_areas": [
            "SQL & Database Querying",
            "Excel / Google Sheets",
            "Python (pandas, numpy) or R",
            "Data Visualization (Tableau, Power BI, Matplotlib)",
            "Statistics & Probability",
            "Business Acumen & Metrics",
            "Data Cleaning & Wrangling",
            "A/B Testing & Experimentation",
        ],
        "interview_formats": [
            "SQL take-home or live coding tests",
            "Case study / business problem analysis",
            "Excel/spreadsheet challenge",
            "Metrics & analytics questions",
            "Behavioral rounds",
        ],
        "resources": {
            "platforms": [
                {"name": "Mode Analytics SQL Tutorial", "url": "https://mode.com/sql-tutorial", "focus": "SQL for data analysis"},
                {"name": "StrataScratch", "url": "https://stratascratch.com", "focus": "Real company SQL & Python interview questions"},
                {"name": "DataLemur", "url": "https://datalemur.com", "focus": "SQL interview questions from top companies"},
                {"name": "Kaggle", "url": "https://kaggle.com", "focus": "Datasets, notebooks, competitions"},
                {"name": "W3Schools SQL", "url": "https://w3schools.com/sql", "focus": "SQL fundamentals reference"},
            ],
            "youtube": [
                {"name": "Alex The Analyst", "url": "https://youtube.com/@AlexTheAnalyst", "focus": "SQL, Excel, Python for analysts"},
                {"name": "Luke Barousse", "url": "https://youtube.com/@LukeBarousse", "focus": "Data analyst career & SQL projects"},
                {"name": "Tina Huang", "url": "https://youtube.com/@TinaHuang1", "focus": "Data science interview prep & tips"},
                {"name": "StatQuest", "url": "https://youtube.com/@statquest", "focus": "Statistics explained simply"},
            ],
            "books_blogs": [
                {"name": "Towards Data Science", "url": "https://towardsdatascience.com", "focus": "Data analysis tutorials and case studies"},
                {"name": "SQL Zoo", "url": "https://sqlzoo.net", "focus": "Interactive SQL practice"},
                {"name": "Storytelling with Data", "url": "https://storytellingwithdata.com", "focus": "Data visualization best practices"},
            ],
        },
        "question_bank": {
            "technical_easy": [
                "Write a SQL query to find the second-highest salary.",
                "What is the difference between INNER JOIN and LEFT JOIN?",
                "How would you handle NULL values in a dataset?",
                "What is the difference between COUNT(*) and COUNT(column)?",
                "Explain the difference between a fact table and a dimension table.",
            ],
            "technical_medium": [
                "Write a SQL query to find customers who made purchases in consecutive months.",
                "How would you detect and handle outliers in a dataset?",
                "Explain the difference between standard deviation and variance.",
                "Write a SQL query using window functions to calculate a running total.",
                "How do you perform cohort analysis?",
            ],
            "technical_hard": [
                "Design a metrics dashboard to track product health for an e-commerce app.",
                "How would you set up an A/B test for a new checkout flow?",
                "A KPI suddenly drops 20% — walk me through your investigation process.",
                "How would you build a churn prediction model from scratch?",
                "Explain the difference between correlation and causation with a business example.",
            ],
            "behavioral": [
                "Describe a time you turned a complex dataset into a clear business recommendation.",
                "How do you prioritize when multiple stakeholders request reports simultaneously?",
                "Tell me about a time your analysis led to a significant business decision.",
                "How do you communicate findings to non-technical stakeholders?",
                "Describe a time you found an error in existing data or reports.",
            ],
        },
    },

    "product_manager": {
        "description": "Product Manager / Associate PM / Senior PM",
        "skill_areas": [
            "Product Strategy & Vision",
            "User Research & Empathy",
            "Roadmap Planning & Prioritization",
            "Metrics & KPIs",
            "Stakeholder Management",
            "Agile / Scrum Methodologies",
            "Competitive Analysis",
            "Technical Literacy",
        ],
        "interview_formats": [
            "Product design / redesign questions",
            "Estimation / market sizing questions",
            "Metrics & root cause analysis questions",
            "Strategy & go-to-market questions",
            "Behavioral / leadership rounds",
            "Case studies",
        ],
        "resources": {
            "platforms": [
                {"name": "Exponent", "url": "https://tryexponent.com", "focus": "PM interview courses and mock interviews"},
                {"name": "Product School", "url": "https://productschool.com", "focus": "PM resources, webinars, communities"},
                {"name": "Lenny's Newsletter", "url": "https://lennysnewsletter.com", "focus": "Top PM tactics and career advice"},
                {"name": "PM Exercises", "url": "https://pmexercises.com", "focus": "Free PM interview question practice"},
            ],
            "youtube": [
                {"name": "Exponent YouTube", "url": "https://youtube.com/@ExponentTV", "focus": "PM mock interviews and walkthroughs"},
                {"name": "Jeff H Shen", "url": "https://youtube.com/@JeffHShen", "focus": "PM interview frameworks"},
                {"name": "Product School YouTube", "url": "https://youtube.com/@ProductSchool", "focus": "PM talks and AMAs"},
            ],
            "books_blogs": [
                {"name": "Cracking the PM Interview", "url": "https://www.crackingthepminterview.com", "focus": "Classic PM interview book"},
                {"name": "Inspired by Marty Cagan", "url": "https://svpg.com/inspired-how-to-create-products-customers-love", "focus": "Product management bible"},
                {"name": "Mind the Product", "url": "https://mindtheproduct.com", "focus": "PM articles, conferences, community"},
            ],
        },
        "question_bank": {
            "technical_easy": [
                "What is a North Star metric? Give an example for Spotify.",
                "How would you prioritize a product backlog with limited resources?",
                "What is the difference between output and outcome metrics?",
                "How do you define success for a new feature launch?",
                "What frameworks do you use for product prioritization?",
            ],
            "technical_medium": [
                "Design a feature to improve user retention for a food delivery app.",
                "DAU for your product dropped 15% — how do you investigate?",
                "How would you decide whether to build, buy, or partner for a new capability?",
                "Walk me through how you would launch a new product in a market you haven't entered.",
                "How would you estimate the market size for electric scooters in a city?",
            ],
            "technical_hard": [
                "How would you redesign the onboarding experience for a B2B SaaS product?",
                "You have budget for one feature — how do you decide what to build?",
                "Design a recommendation system for a streaming platform.",
                "How would you approach entering a market dominated by one competitor?",
                "Walk me through a full product strategy for a wearable health device.",
            ],
            "behavioral": [
                "Tell me about a product you launched from 0 to 1.",
                "Describe a time you had to say no to a stakeholder request.",
                "How do you handle conflict between engineering and design teams?",
                "Tell me about a product failure you were responsible for and what you learned.",
                "How do you stay informed about user needs and market trends?",
            ],
        },
    },

    "data_scientist": {
        "description": "Data Scientist / ML Engineer / AI Engineer",
        "skill_areas": [
            "Machine Learning Algorithms",
            "Python (scikit-learn, pandas, numpy)",
            "Deep Learning (TensorFlow / PyTorch)",
            "Feature Engineering",
            "Model Evaluation & Validation",
            "SQL & Data Wrangling",
            "Statistics & Probability",
            "MLOps & Model Deployment",
        ],
        "interview_formats": [
            "Take-home ML project",
            "Live coding (ML implementation)",
            "ML theory & concept questions",
            "Statistics & probability questions",
            "Case study / product sense",
            "Behavioral rounds",
        ],
        "resources": {
            "platforms": [
                {"name": "Kaggle", "url": "https://kaggle.com", "focus": "Competitions, notebooks, datasets"},
                {"name": "fast.ai", "url": "https://fast.ai", "focus": "Free practical deep learning course"},
                {"name": "Coursera ML Specialization", "url": "https://coursera.org/specializations/machine-learning-introduction", "focus": "Andrew Ng's ML course"},
                {"name": "StrataScratch", "url": "https://stratascratch.com", "focus": "DS interview questions from real companies"},
            ],
            "youtube": [
                {"name": "Andrej Karpathy", "url": "https://youtube.com/@AndrejKarpathy", "focus": "Deep learning fundamentals from OpenAI founder"},
                {"name": "3Blue1Brown", "url": "https://youtube.com/@3blue1brown", "focus": "Neural networks and math visualized"},
                {"name": "StatQuest", "url": "https://youtube.com/@statquest", "focus": "ML algorithms explained clearly"},
                {"name": "Sentdex", "url": "https://youtube.com/@sentdex", "focus": "Python ML and data science tutorials"},
            ],
            "books_blogs": [
                {"name": "Hands-On ML with Scikit-Learn & TensorFlow", "url": "https://oreilly.com/library/view/hands-on-machine-learning", "focus": "Practical ML book by Aurelien Geron"},
                {"name": "Distill.pub", "url": "https://distill.pub", "focus": "Visual ML research articles"},
                {"name": "Papers With Code", "url": "https://paperswithcode.com", "focus": "Latest ML papers with implementations"},
            ],
        },
        "question_bank": {
            "technical_easy": [
                "What is the bias-variance tradeoff?",
                "Explain the difference between supervised and unsupervised learning.",
                "What is regularization and why is it used?",
                "How do you handle imbalanced datasets?",
                "What is cross-validation and why is it important?",
            ],
            "technical_medium": [
                "Explain how gradient boosting works.",
                "What is the difference between L1 and L2 regularization?",
                "How would you build a recommendation system?",
                "Explain precision, recall, and F1-score with a real example.",
                "What is the curse of dimensionality?",
            ],
            "technical_hard": [
                "How would you design an ML system to detect fraudulent transactions at scale?",
                "Explain the transformer architecture and attention mechanisms.",
                "How do you detect and handle data drift in production models?",
                "Design an A/B testing framework to evaluate model performance.",
                "How would you approach feature selection for a dataset with 500 features?",
            ],
            "behavioral": [
                "Describe an end-to-end ML project you built from data collection to deployment.",
                "Tell me about a time your model performed well in testing but failed in production.",
                "How do you communicate model limitations to non-technical stakeholders?",
                "Describe a time you had to work with messy or incomplete data.",
                "How do you stay current with the latest developments in ML/AI?",
            ],
        },
    },

    "generic": {
        "description": "General / Any Role",
        "skill_areas": [
            "Communication & Presentation",
            "Problem-Solving",
            "Teamwork & Collaboration",
            "Time Management",
            "Adaptability",
            "Leadership",
        ],
        "interview_formats": [
            "HR / Screening round",
            "Behavioral interviews (STAR method)",
            "Panel interviews",
            "Group discussions",
        ],
        "resources": {
            "platforms": [
                {"name": "Glassdoor Interview Questions", "url": "https://glassdoor.com/Interview", "focus": "Real interview questions by company"},
                {"name": "LinkedIn Interview Prep", "url": "https://linkedin.com/interview-prep", "focus": "Role-specific behavioral questions with tips"},
                {"name": "Big Interview", "url": "https://biginterview.com", "focus": "Video mock interview practice"},
            ],
            "youtube": [
                {"name": "Don Georgevich", "url": "https://youtube.com/@JobInterviewTools", "focus": "Interview answer frameworks"},
                {"name": "Self Made Millennial", "url": "https://youtube.com/@SelfMadeMillennial", "focus": "Career and interview coaching"},
                {"name": "Jeff Su", "url": "https://youtube.com/@JeffSu", "focus": "Career growth and interview strategies"},
            ],
            "books_blogs": [
                {"name": "The STAR Method Explained", "url": "https://www.themuse.com/advice/star-interview-method", "focus": "Behavioral interview framework"},
            ],
        },
        "question_bank": {
            "behavioral": [
                "Tell me about yourself.",
                "What is your greatest strength? Give an example.",
                "What is your greatest weakness and how do you manage it?",
                "Where do you see yourself in 5 years?",
                "Why do you want to work here?",
                "Tell me about a time you overcame a significant challenge.",
                "Describe a time you worked with a difficult colleague.",
                "Tell me about a time you failed and what you learned.",
                "How do you prioritize tasks when you have multiple deadlines?",
                "Why are you leaving your current role?",
            ],
        },
    },
}

# Difficulty progression order
_DIFFICULTY_LEVELS = ["easy", "medium", "hard"]

# Role keyword mapping for fuzzy matching
_ROLE_KEYWORDS: dict[str, list[str]] = {
    "software_engineer": [
        "software", "engineer", "developer", "swe", "backend", "frontend",
        "fullstack", "full-stack", "full stack", "coding", "programmer",
        "devops", "cloud", "mobile", "ios", "android", "web developer",
    ],
    "data_analyst": [
        "data analyst", "analyst", "business analyst", "bi analyst",
        "business intelligence", "reporting", "sql analyst", "data analytics",
    ],
    "product_manager": [
        "product manager", "pm", "apm", "associate pm", "senior pm",
        "product owner", "po", "product lead", "product strategy",
    ],
    "data_scientist": [
        "data scientist", "machine learning", "ml engineer", "ai engineer",
        "deep learning", "nlp", "computer vision", "research scientist",
        "data science", "ml", "artificial intelligence",
    ],
}


# ---------------------------------------------------------------------------
# Public tool functions
# ---------------------------------------------------------------------------

def detect_role_category(role_input: str) -> dict:
    """
    Map a free-text role description to a known resource category.

    Args:
        role_input: User-provided role string (e.g. 'software engineer', 'PM').

    Returns:
        dict with:
          - matched_category (str): key into _RESOURCES
          - confidence (str): 'high' | 'low'
          - description (str): human-readable category description
    """
    lowered = role_input.lower().strip()
    for category, keywords in _ROLE_KEYWORDS.items():
        for kw in keywords:
            if kw in lowered:
                return {
                    "matched_category": category,
                    "confidence": "high",
                    "description": _RESOURCES[category]["description"],
                }
    return {
        "matched_category": "generic",
        "confidence": "low",
        "description": _RESOURCES["generic"]["description"],
    }


def get_prep_strategy(role_category: str) -> dict:
    """
    Return the preparation strategy for a given role category,
    including skill areas and interview formats.

    Args:
        role_category: One of 'software_engineer', 'data_analyst',
                       'product_manager', 'data_scientist', 'generic'.

    Returns:
        dict with skill_areas (list) and interview_formats (list).
    """
    data = _RESOURCES.get(role_category, _RESOURCES["generic"])
    return {
        "role": data["description"],
        "skill_areas": data.get("skill_areas", []),
        "interview_formats": data.get("interview_formats", []),
    }


def get_resources(role_category: str, resource_type: str = "all") -> dict:
    """
    Fetch curated resources for a role category.

    Args:
        role_category: Role category key.
        resource_type: 'platforms' | 'youtube' | 'books_blogs' | 'all'.

    Returns:
        dict with requested resource lists.
    """
    data = _RESOURCES.get(role_category, _RESOURCES["generic"])
    all_resources = data.get("resources", {})

    if resource_type == "all":
        return {"resources": all_resources, "categories": list(all_resources.keys())}
    elif resource_type in all_resources:
        return {"resources": {resource_type: all_resources[resource_type]}}
    else:
        return {"resources": all_resources, "note": f"Type '{resource_type}' not found, returning all."}


def get_practice_questions(
    role_category: str,
    difficulty: str = "easy",
    question_type: str = "all",
) -> dict:
    """
    Return a set of practice questions for a role and difficulty level.

    Args:
        role_category: Role category key.
        difficulty: 'easy' | 'medium' | 'hard'.
        question_type: 'technical' | 'behavioral' | 'system_design' | 'all'.

    Returns:
        dict with questions grouped by type and the next difficulty suggestion.
    """
    data = _RESOURCES.get(role_category, _RESOURCES["generic"])
    bank = data.get("question_bank", {})

    result: dict[str, list] = {}

    if question_type in ("technical", "all"):
        key = f"technical_{difficulty}"
        if key in bank:
            result["technical"] = bank[key]
        elif "technical_easy" in bank:
            result["technical"] = bank["technical_easy"]

    if question_type in ("behavioral", "all") and "behavioral" in bank:
        result["behavioral"] = bank["behavioral"]

    if question_type in ("system_design", "all") and "system_design" in bank:
        result["system_design"] = bank["system_design"]

    # Suggest next level
    current_idx = _DIFFICULTY_LEVELS.index(difficulty) if difficulty in _DIFFICULTY_LEVELS else 0
    next_difficulty = _DIFFICULTY_LEVELS[min(current_idx + 1, len(_DIFFICULTY_LEVELS) - 1)]

    return {
        "role": data["description"],
        "current_difficulty": difficulty,
        "next_difficulty": next_difficulty,
        "questions": result,
        "total_questions": sum(len(v) for v in result.values()),
    }


def get_mock_interview_set(role_category: str, difficulty: str = "medium") -> dict:
    """
    Generate a complete mock interview question set for a role.
    Combines technical, behavioral, and role-specific questions
    into a realistic interview simulation.

    Args:
        role_category: Role category key.
        difficulty: 'easy' | 'medium' | 'hard'.

    Returns:
        dict with a structured mock interview containing rounds and questions.
    """
    data = _RESOURCES.get(role_category, _RESOURCES["generic"])
    bank = data.get("question_bank", {})

    tech_key = f"technical_{difficulty}"
    tech_questions = bank.get(tech_key, bank.get("technical_easy", []))[:3]
    behavioral_questions = bank.get("behavioral", [])[:3]
    system_design_questions = bank.get("system_design", [])[:1]

    rounds = []

    if tech_questions:
        rounds.append({
            "round": "Technical Round",
            "duration": "45-60 minutes",
            "questions": tech_questions,
            "tips": [
                "Think out loud — interviewers want to hear your reasoning.",
                "Clarify requirements before jumping into a solution.",
                "Start with a brute-force approach, then optimize.",
                "Test your solution with edge cases before saying you're done.",
            ],
        })

    if system_design_questions:
        rounds.append({
            "round": "System Design Round",
            "duration": "45-60 minutes",
            "questions": system_design_questions,
            "tips": [
                "Start by clarifying functional and non-functional requirements.",
                "Estimate scale (users, requests/sec, storage) before designing.",
                "Draw a high-level architecture first, then dive deep.",
                "Discuss trade-offs — there is no single right answer.",
            ],
        })

    if behavioral_questions:
        rounds.append({
            "round": "Behavioral Round",
            "duration": "30-45 minutes",
            "questions": behavioral_questions,
            "tips": [
                "Use the STAR method: Situation, Task, Action, Result.",
                "Quantify your results wherever possible.",
                "Prepare 5-6 core stories that can be adapted to different questions.",
                "Be honest about failures — show what you learned.",
            ],
        })

    return {
        "role": data["description"],
        "difficulty": difficulty,
        "total_rounds": len(rounds),
        "estimated_total_time": f"{len(rounds) * 50}-{len(rounds) * 65} minutes",
        "rounds": rounds,
        "general_tips": [
            "Research the company: products, culture, recent news, and mission.",
            "Prepare 3-5 thoughtful questions to ask the interviewer.",
            "Review your own resume and be ready to deep-dive any item on it.",
            "Practice answers out loud — not just in your head.",
            "Get 8 hours of sleep the night before.",
        ],
    }


def get_company_research_guide(company_name: str = "") -> dict:
    """
    Provide a structured company research framework for interview preparation.

    Args:
        company_name: Optional company name for personalized guidance.

    Returns:
        dict with research checklist, key areas, and resources.
    """
    company_label = company_name.strip() if company_name.strip() else "your target company"
    return {
        "company": company_label,
        "research_checklist": [
            f"Read {company_label}'s About page and understand their mission/vision.",
            f"Study {company_label}'s main products and services.",
            f"Look up recent news about {company_label} (last 6-12 months).",
            f"Check {company_label}'s Glassdoor reviews for culture insights.",
            f"Research {company_label}'s competitors and market position.",
            f"Understand {company_label}'s tech stack (for engineering roles).",
            f"Find the LinkedIn profiles of your interviewers (if known).",
            f"Review {company_label}'s engineering blog or product blog.",
        ],
        "key_questions_to_answer": [
            "Why do you want to work here specifically?",
            "What recent company achievement excites you?",
            "How does this role contribute to the company's goals?",
            "What challenges is this company currently facing?",
        ],
        "resources": [
            {"name": "Glassdoor", "url": "https://glassdoor.com", "focus": "Reviews, salaries, interview questions"},
            {"name": "LinkedIn", "url": "https://linkedin.com", "focus": "Company page, employee profiles, recent posts"},
            {"name": "Crunchbase", "url": "https://crunchbase.com", "focus": "Funding, investors, company history"},
            {"name": "The company's engineering blog", "url": "", "focus": "Technical culture and current problems they solve"},
            {"name": "Blind (anonymous reviews)", "url": "https://teamblind.com", "focus": "Honest insider perspectives"},
        ],
    }
