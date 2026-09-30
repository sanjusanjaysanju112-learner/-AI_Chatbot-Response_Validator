"""
AI Chatbot-Response Validator - Streamlit app.

Run:
    pip install -r requirements.txt
    streamlit run app.py
"""
import json
import os
import pandas as pd
import streamlit as st

from validator import validate_with_rules, validate_with_llm

# ---------------------------------------------------------------------------
# "Cloud" integration point (stubbed).
# In production, question/response pairs would come from a live chat log
# store or a queue rather than being pasted in - swap this for a real call.
# ---------------------------------------------------------------------------
def fetch_chat_logs_from_cloud(source: str):
    """
    Placeholder for a cloud chat-log source. Real version, e.g. from S3:

        import boto3
        s3 = boto3.client("s3")
        obj = s3.get_object(Bucket="npci-chatbot-logs", Key=source)
        return json.loads(obj["Body"].read())
    """
    raise NotImplementedError("Wire this up to S3 / a chat-log store in the real environment.")


st.set_page_config(page_title="AI Chatbot Response Validator", layout="wide")
st.title("🔍 AI Chatbot-Response Validator")
st.caption("Given the same question answered multiple times, flags inconsistent or contradictory responses.")

with st.sidebar:
    st.header("Settings")
    mode = st.radio("Validation mode", ["Mock (rule-based, offline)", "LLM (Anthropic API, as judge)"])
    api_key = None
    if mode.startswith("LLM"):
        api_key = st.text_input("Anthropic API key", type="password",
                                 value=os.environ.get("ANTHROPIC_API_KEY", ""))
    st.markdown("---")
    st.caption("Cloud angle: in production, question/response pairs are pulled from a chat-log "
               "store (S3, a queue, etc.) instead of pasted here. See "
               "`fetch_chat_logs_from_cloud()` in app.py for the integration point.")

st.subheader("1. Provide question + candidate responses")

if "qa_sets" not in st.session_state:
    st.session_state["qa_sets"] = []

col1, col2 = st.columns([1, 1])

# Column 1: Load sample file button & Clear button
with col1:
    if st.button("Load sample Q&A sets"):
        try:
            with open("sample_qa.json") as f:
                st.session_state["qa_sets"] = json.load(f)
            st.success("Sample Q&A sets loaded successfully!")
            st.rerun()
        except FileNotFoundError:
            st.error("sample_qa.json file not found in the directory.")
    
    if st.button("Clear all Q&A sets"):
        st.session_state["qa_sets"] = []
        st.rerun()

# Column 2: Manual file uploader for custom JSON files
with col2:
    uploaded_file = st.file_uploader("Upload custom Q&A JSON file", type=["json"])
    if uploaded_file is not None:
        try:
            st.session_state["qa_sets"] = json.load(uploaded_file)
            st.success("Custom Q&A sets uploaded successfully!")
            st.rerun()
        except Exception as e:
            st.error(f"Error reading JSON file: {e}")

with st.expander("➕ Add a question manually"):
    q = st.text_input("Question")
    r_text = st.text_area("Candidate responses (one per line, at least 2)")
    if st.button("Add"):
        responses = [r.strip() for r in r_text.split("\n") if r.strip()]
        if q and len(responses) >= 2:
            st.session_state["qa_sets"].append({"question": q, "responses": responses})
            st.rerun()
        else:
            st.warning("Need a question and at least 2 responses.")

qa_sets = st.session_state["qa_sets"]
st.write(f"**{len(qa_sets)} question(s) loaded.**")

if qa_sets and st.button("🔍 Validate consistency", type="primary"):
    client = None
    if mode.startswith("LLM"):
        if not api_key:
            st.error("Enter an Anthropic API key, or switch to Mock mode.")
            st.stop()
        import anthropic
        client = anthropic.Anthropic(api_key=api_key)

    rows = []
    progress = st.progress(0.0, text="Validating...")
    for i, qa in enumerate(qa_sets):
        try:
            if client:
                result = validate_with_llm(qa["question"], qa["responses"], client)
            else:
                result = validate_with_rules(qa["question"], qa["responses"])
        except Exception as e:
            result = {"consistent": False, "severity": "Medium", "confidence": 0.0,
                      "contradictions": [], "explanation": f"Validation failed: {e}",
                      "recommended_action": "Retry or review manually."}
        rows.append({
            "": "✅" if result["consistent"] else "🚩",
            "question": qa["question"],
            "verdict": "Consistent" if result["consistent"] else "Inconsistent",
            "severity": result["severity"],
            "confidence": result["confidence"],
            "contradictions": "; ".join(result["contradictions"]) if result["contradictions"] else "-",
            "explanation": result["explanation"],
            "recommended_action": result["recommended_action"],
        })
        progress.progress((i + 1) / len(qa_sets), text=f"Validating... {i+1}/{len(qa_sets)}")
    progress.empty()

    df = pd.DataFrame(rows)

    st.subheader("2. Results")
    m1, m2 = st.columns(2)
    m1.metric("✅ Consistent", int((df["verdict"] == "Consistent").sum()))
    m2.metric("🚩 Inconsistent", int((df["verdict"] == "Inconsistent").sum()))

    st.dataframe(df, use_container_width=True, hide_index=True)

    st.subheader("3. Detail view")
    for i, qa in enumerate(qa_sets):
        row = rows[i]
        with st.expander(f"{row['']} {qa['question']}  —  {row['verdict']} ({row['severity']})"):
            for j, r in enumerate(qa["responses"]):
                st.markdown(f"**Response {j+1}:** {r}")
            if row["contradictions"] != "-":
                st.error(f"Contradictions: {row['contradictions']}")
            st.caption(row["explanation"])

    st.download_button("Download results as CSV", df.to_csv(index=False), "validation_results.csv")

    st.subheader("4. Presentation")
    if st.button("📊 Generate 3-slide PPTX"):
        from slide_generator import build_deck
        sev_counts = df["severity"].value_counts().to_dict()
        deck_bytes = build_deck(
            problem_statement=(
                "Chatbot responses to the same question sometimes drift or contradict each other "
                "across retries or app versions, risking incorrect information reaching users."
            ),
            architecture_steps=[
                "Question/response pairs pulled from chat logs (S3 / log store)",
                "An LLM acts as a judge: compares responses, flags contradictions with severity",
                "Rule-based fallback catches explicit contradictions and divergent wording offline",
                "Results shown in a dashboard with per-question drill-down and CSV export",
            ],
            severity_counts=sev_counts,
            impact_points=[
                "Catches factual drift before it reaches end users",
                "Gives QA a repeatable way to regression-test AI response consistency",
                "Works even without live API access via the rule-based fallback",
            ],
        )
        st.download_button("Download presentation.pptx", deck_bytes, "presentation.pptx")
