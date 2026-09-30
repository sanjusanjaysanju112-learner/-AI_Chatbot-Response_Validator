# AI Chatbot-Response Validator — Prototype

## What it does
Given a question and several candidate responses (from repeated calls to a
chatbot, different model versions, or A/B variants), flags whether they are
**consistent** or **contradict each other**, with a severity rating and a
plain-English explanation.

## Run it
```bash
cd chatbot-validator
pip install -r requirements.txt
streamlit run app.py
```
Click **"Load sample Q&A sets"** to demo instantly — 5 realistic
payments-support questions are built in, 3 with genuine contradictions
(refund status, OTP lockout, failed-transaction fee) and 2 that are
consistent despite different wording (UPI limit, support hours) — this
matters for your demo: it shows the tool isn't just flagging "different
wording" as an error, it's catching actual factual drift.

- **Mock mode** (default): rule-based — known opposite-phrase pairs (e.g.
  "processed" vs "pending") plus a text-similarity check as a secondary
  signal. Zero setup, works offline.
- **LLM mode**: paste an Anthropic API key to have the model act as judge
  instead of the rules — catches subtler contradictions the rules would miss.

You can also add your own question + responses manually via the "Add a
question" expander in the app.

## Architecture (Slide 2 material)
```
Question + candidate responses (pasted / from chat logs)
        │
        ▼
 fetch_chat_logs_from_cloud()   ← stub: swap for S3 / chat-log store call
        │
        ▼
 validate_with_rules() / validate_with_llm()
        │  Mock: known contradiction pairs + text-similarity divergence
        │  LLM: model acts as judge, returns structured JSON verdict
        ▼
 Streamlit dashboard: consistent/inconsistent counts, per-question
 drill-down, contradiction detail, CSV export, one-click PPTX slides
```

## Why this design (for your presentation)
- **Why not just check exact string match?** Two responses can be worded
  completely differently and still be consistent (see the UPI-limit and
  support-hours examples) — validating meaning, not wording, is exactly
  why this needs AI rather than a simple diff.
- **Why keep the rule-based fallback?** It's not just a backup — it's
  explainable and fast, good as a first-pass filter before spending an API
  call on ambiguous cases. Worth framing as a deliberate two-tier design,
  not a compromise.
- **Business impact (Slide 3):** an inconsistent chatbot answer that
  reaches a customer (e.g. wrong refund status) is a trust and compliance
  risk in a payments context — this gives QA a repeatable way to
  regression-test response consistency before release, not just spot-check
  manually.

## If you have extra time on the day
- Add a "regenerate response" button that calls the LLM 3x on the same
  question live, instead of relying only on pre-written sample responses —
  shows the validator working on genuinely fresh model output.
- Add a confidence threshold slider so only high-confidence contradictions
  auto-flag, routing borderline cases to manual review.
