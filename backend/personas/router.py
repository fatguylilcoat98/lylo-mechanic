"""
The Good Neighbor Guard — LYLO
Christopher Hughes · Sacramento, CA
Truth · Safety · We Got Your Back

Persona Router — 5 personas, each stays in their lane.

Personas:
    MECHANIC  — Vehicle diagnostics, OBD codes, car repair
    GUARDIAN  — Scam protection, fraud detection, safety alerts
    GUIDE     — Life guidance, planning, decisions, career, education
    BUILDER   — Projects, DIY builds, home improvement, maker projects
    BESTIE    — Emotional support, venting, encouragement, companionship

Lane enforcement:
    Each persona has a domain keyword set and an off-topic detector.
    If a question is outside the persona's lane, it returns a redirect
    to the correct persona — it does NOT answer.
"""

import re

PERSONAS = {
    "mechanic": {
        "name": "Mechanic",
        "tagline": "Your honest vehicle diagnostic partner",
        "domain": "vehicles, cars, trucks, OBD codes, car repair, engine, transmission, brakes, tires, oil, diagnostics",
        "lane_keywords": [
            r"\b(car|truck|vehicle|engine|transmission|brake|tire|oil|gas|fuel|battery|alternator)\b",
            r"\b(obd|dtc|p0\d{3}|check engine|mil|misfire|catalytic|exhaust|coolant|radiator)\b",
            r"\b(mechanic|repair|fix|diagnose|diagnostic|wrench|spark plug|ignition|coil)\b",
            r"\b(mileage|odometer|mpg|rpm|idle|stall|overheat|leak|noise|vibration|squeal)\b",
            r"\b(honda|toyota|ford|chevy|chevrolet|bmw|mercedes|nissan|hyundai|kia|subaru|jeep|dodge)\b",
        ],
        "off_topic_redirect": "That sounds like it's outside my wheelhouse — I only know cars and trucks. Let me send you to {suggested_persona} who can help with that.",
        "system_prompt": (
            "You are LYLO Mechanic — the vehicle diagnostic persona of the LYLO system. "
            "You ONLY answer questions about vehicles, car repair, OBD-II codes, and automotive diagnostics. "
            "If someone asks about anything else — scams, emotions, life advice, projects — you do NOT answer. "
            "You say: 'That's not my area — let me redirect you to the right LYLO persona.' "
            "You are warm, honest, and protective. You never guess on safety-critical vehicle questions."
        ),
    },
    "guardian": {
        "name": "Guardian",
        "tagline": "Your scam protection shield",
        "domain": "scams, fraud, phishing, identity theft, online safety, suspicious messages, financial scams",
        "lane_keywords": [
            r"\b(scam|fraud|phish|phishing|spam|suspicious|fake|con|swindle|hoax|catfish)\b",
            r"\b(identity theft|stolen|hack|breach|password|account.{0,10}compromised)\b",
            r"\b(irs|social security|medicare|gift card|wire transfer|bitcoin.{0,10}pay)\b",
            r"\b(too good to be true|guaranteed return|risk.?free|urgent.{0,15}payment)\b",
            r"\b(caller|email|text|message|link).{0,20}(suspicious|weird|legit|real|fake)\b",
            r"\b(is this (?:a |)(?:scam|legit|real|safe)|should i (?:trust|click|respond|call back))\b",
            r"\b(romance scam|lottery|sweepstakes|prize|inheritance|prince|nigerian)\b",
        ],
        "off_topic_redirect": "I'm your scam shield — but that question isn't about scams or online safety. Let me hand you off to {suggested_persona} for that.",
        "system_prompt": (
            "You are LYLO Guardian — the scam protection persona of the LYLO system. "
            "You ONLY answer questions about scams, fraud, phishing, identity theft, and online safety. "
            "If someone asks about anything else — cars, emotions, life advice, projects — you do NOT answer. "
            "You say: 'That's not my area — let me redirect you to the right LYLO persona.' "
            "You are protective, direct, and never minimize danger. When you see a scam, you say so clearly."
        ),
    },
    "guide": {
        "name": "Guide",
        "tagline": "Your life navigation partner",
        "domain": "life decisions, career, education, planning, goals, relationships, finances, housing",
        "lane_keywords": [
            r"\b(career|job|resume|interview|hire|salary|raise|promotion|quit|retire)\b",
            r"\b(college|university|degree|school|study|education|major|grad school)\b",
            r"\b(budget|savings?|invest|mortgage|rent|loan|debt|credit score|financial plan)\b",
            r"\b(move|relocate|city|apartment|house|neighborhood|cost of living)\b",
            r"\b(goal|plan|decision|choice|path|next step|what should i do|life)\b",
            r"\b(relationship|marriage|divorce|family|parenting|work.?life balance)\b",
        ],
        "off_topic_redirect": "I help with life decisions and planning — but that question needs a different LYLO. Let me send you to {suggested_persona}.",
        "system_prompt": (
            "You are LYLO Guide — the life navigation persona of the LYLO system. "
            "You ONLY answer questions about life decisions, career, education, planning, goals, finances, and relationships. "
            "If someone asks about cars, scams, emotional venting, or building projects — you do NOT answer. "
            "You say: 'That's not my area — let me redirect you to the right LYLO persona.' "
            "You are thoughtful, honest, and you help people think through decisions without pushing them."
        ),
    },
    "builder": {
        "name": "Builder",
        "tagline": "Your project co-pilot",
        "domain": "DIY projects, home improvement, woodworking, electronics, maker projects, construction",
        "lane_keywords": [
            r"\b(build|project|diy|woodwork|construct|weld|solder|drill|saw|measure)\b",
            r"\b(home improvement|remodel|renovation|deck|fence|shed|drywall|plumbing|electrical)\b",
            r"\b(arduino|raspberry pi|3d print|cnc|laser cut|maker|circuit|prototype)\b",
            r"\b(paint|tile|flooring|cabinet|shelf|workbench|tool|lumber|hardware store)\b",
            r"\b(how (?:to|do i) (?:build|make|construct|install|wire|mount|attach|frame))\b",
        ],
        "off_topic_redirect": "I'm your project partner — but that's not a building question. Let me connect you with {suggested_persona} instead.",
        "system_prompt": (
            "You are LYLO Builder — the project co-pilot persona of the LYLO system. "
            "You ONLY answer questions about DIY projects, home improvement, maker builds, woodworking, and construction. "
            "If someone asks about cars, scams, emotions, or life planning — you do NOT answer. "
            "You say: 'That's not my area — let me redirect you to the right LYLO persona.' "
            "You are practical, safety-conscious, and you help people plan before they cut."
        ),
    },
    "bestie": {
        "name": "Bestie",
        "tagline": "Your ride-or-die support system",
        "domain": "emotional support, venting, encouragement, loneliness, stress, anxiety, companionship",
        "lane_keywords": [
            r"\b(feel|feeling|sad|happy|angry|anxious|stress|depress|lonely|overwhelm)\b",
            r"\b(vent|talk|listen|support|encourage|hug|cry|worried|scared|afraid)\b",
            r"\b(friend|bestie|buddy|someone to talk to|need to talk|bad day|rough day)\b",
            r"\b(self.?care|mental health|burnout|exhaust|tired of|done with|give up)\b",
            r"\b(miss|grief|loss|breakup|heartbreak|hurt|betray|abandon|reject)\b",
            r"\b(proud|celebrate|win|accomplish|grateful|thankful|happy for me)\b",
        ],
        "off_topic_redirect": "I'm here for you emotionally — but for that question you need {suggested_persona}. They've got you.",
        "system_prompt": (
            "You are LYLO Bestie — the emotional support persona of the LYLO system. "
            "You ONLY provide emotional support, encouragement, and companionship. "
            "If someone asks about cars, scams, life planning, or projects — you do NOT answer. "
            "You say: 'That's not my area — let me redirect you to the right LYLO persona.' "
            "You are warm, real, and you never dismiss feelings. You listen first, always."
        ),
    },
}

# Map of persona -> compiled regex patterns for fast matching
_COMPILED = {}
for pid, pdata in PERSONAS.items():
    _COMPILED[pid] = [re.compile(p, re.IGNORECASE) for p in pdata["lane_keywords"]]


def classify_persona(question: str) -> str:
    """
    Determine which persona should handle this question.
    Returns the persona ID with the highest keyword match count.
    Falls back to 'guide' if no strong signal (it's the broadest).
    """
    q = question.strip()
    scores = {}
    for pid, patterns in _COMPILED.items():
        score = sum(1 for p in patterns if p.search(q))
        scores[pid] = score

    best = max(scores, key=scores.get)
    if scores[best] == 0:
        return "guide"  # Default — broadest persona
    return best


def check_lane(persona_id: str, question: str) -> dict:
    """
    Check if a question is in the given persona's lane.

    Returns:
        {
            "in_lane": True/False,
            "persona": persona_id,
            "suggested_persona": str or None,  (only if out of lane)
            "redirect_message": str or None,    (only if out of lane)
        }
    """
    persona = PERSONAS.get(persona_id)
    if not persona:
        return {"in_lane": False, "persona": persona_id, "suggested_persona": "guide",
                "redirect_message": "Unknown persona — defaulting to Guide."}

    # Check if question matches THIS persona's lane
    patterns = _COMPILED.get(persona_id, [])
    own_score = sum(1 for p in patterns if p.search(question))

    if own_score > 0:
        return {"in_lane": True, "persona": persona_id,
                "suggested_persona": None, "redirect_message": None}

    # Not in lane — find where it SHOULD go
    suggested = classify_persona(question)
    if suggested == persona_id:
        # Classifier says this persona, but no keyword match — allow it (borderline)
        return {"in_lane": True, "persona": persona_id,
                "suggested_persona": None, "redirect_message": None}

    suggested_name = PERSONAS[suggested]["name"]
    redirect_msg = persona["off_topic_redirect"].replace("{suggested_persona}", f"LYLO {suggested_name}")

    return {
        "in_lane": False,
        "persona": persona_id,
        "suggested_persona": suggested,
        "redirect_message": redirect_msg,
    }


def get_persona_info(persona_id: str) -> dict:
    """Get display info for a persona."""
    p = PERSONAS.get(persona_id)
    if not p:
        return None
    return {
        "id": persona_id,
        "name": p["name"],
        "tagline": p["tagline"],
        "domain": p["domain"],
    }


def list_personas() -> list:
    """Return all persona summaries."""
    return [get_persona_info(pid) for pid in PERSONAS]
