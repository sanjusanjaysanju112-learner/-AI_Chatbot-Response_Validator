"""
AI Chatbot-Response Validator
------------------------------
Given a question and multiple candidate responses (e.g. from repeated calls
to a chatbot, or from different model versions), flags whether the answers
are semantically consistent or contradict each other, and assigns a
severity to the inconsistency.
"""

import difflib
import itertools
import json
import re

# ---------------------------------------------------------------------------
# Mock mode: explainable, rule-based baseline. No API/network needed.
# Two signals combined:
#   1. Known opposite-meaning phrase pairs (explicit contradictions)
#   2. Pairwise text similarity (catches divergence even without a known pair)
# ---------------------------------------------------------------------------
CONTRADICTION_PAIRS = [
    ("processed", "pending"),
    ("processed", "no refund"),
    ("processed", "not found"),
    ("pending", "no refund"),
    ("pending", "not found"),
    ("temporarily locked", "fully accessible"),
    ("locked", "accessible"),
    ("will be temporarily locked", "remains fully accessible"),
    ("no fee", "fee of"),
    ("not charged", "fee of"),
    ("no refund", "refund for"),
]


def _similarity(a: str, b: str) -> float:
    return difflib.SequenceMatcher(None, a.lower(), b.lower()).ratio()


def find_contradictions(responses):
    texts = [r.lower() for r in responses]
    found = []
    for (i, ti), (j, tj) in itertools.combinations(enumerate(texts), 2):
        for a, b in CONTRADICTION_PAIRS:
            if (a in ti and b in tj) or (b in ti and a in tj):
                found.append({"pair": (i + 1, j + 1), "detail": f'"{a}" vs "{b}"'})
    return found


def validate_with_rules(question: str, responses: list) -> dict:
    contradictions = find_contradictions(responses)
    sims = [
        _similarity(a, b)
        for a, b in itertools.combinations(responses, 2)
    ]
    avg_sim = sum(sims) / len(sims) if sims else 1.0

    if contradictions:
        unique_details = list(dict.fromkeys(c["detail"] for c in contradictions))
        return {
            "consistent": False,
            "severity": "Critical",
            "confidence": 0.9,
            "contradictions": unique_details,
            "explanation": "Responses contain directly opposing claims.",
            "recommended_action": "Escalate for review; do not surface any of these responses to users until resolved.",
        }
    if avg_sim < 0.35:
        return {
            "consistent": False,
            "severity": "Medium",
            "confidence": round(1 - avg_sim, 2),
            "contradictions": [],
            "explanation": f"Responses diverge significantly in wording/content (avg similarity {avg_sim:.2f}); "
                            f"no explicit contradiction detected, but worth a manual check.",
            "recommended_action": "Spot-check manually; may just be paraphrasing, but verify no factual drift.",
        }
    return {
        "consistent": True,
        "severity": "Low",
        "confidence": round(avg_sim, 2),
        "contradictions": [],
        "explanation": "Responses are semantically aligned (consistent wording/content).",
        "recommended_action": "No action needed.",
    }


# ---------------------------------------------------------------------------
# LLM mode: ask the model to act as judge.
# ---------------------------------------------------------------------------
JUDGE_PROMPT = """You are validating consistency across multiple chatbot responses to the
SAME question. Respond with ONLY a JSON object (no prose, no markdown fences)
with these exact keys:

- "consistent": true or false
- "severity": one of "Critical", "High", "Medium", "Low" ("Low" if consistent)
- "confidence": a number 0-1
- "contradictions": a list of short strings describing any factual contradictions found (empty list if none)
- "explanation": one sentence explaining your verdict
- "recommended_action": one short sentence on what to do next

Question: {question}

Responses:
{responses_block}
"""


def validate_with_llm(question: str, responses: list, client) -> dict:
    responses_block = "\n".join(f"{i+1}. {r}" for i, r in enumerate(responses))
    message = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=400,
        messages=[{"role": "user", "content": JUDGE_PROMPT.format(
            question=question, responses_block=responses_block)}],
    )
    text = message.content[0].text.strip()
    text = re.sub(r"^```(json)?|```$", "", text, flags=re.MULTILINE).strip()
    return json.loads(text)


if __name__ == "__main__":
    with open("sample_qa.json") as f:
        qa_sets = json.load(f)
    for qa in qa_sets:
        result = validate_with_rules(qa["question"], qa["responses"])
        status = "CONSISTENT" if result["consistent"] else f"INCONSISTENT ({result['severity']})"
        print(f"[{status}] {qa['question']}")
        if result["contradictions"]:
            for c in result["contradictions"]:
                print(f"    contradiction: {c}")
        print(f"    -> {result['explanation']}\n")
