import requests
import streamlit as st

st.title("ProofPatch")
st.caption("Shipping threshold demo · targeted regression tests")
mode = st.radio("Test source", ["gemini", "fixture"], format_func=lambda value: {
    "gemini": "Generate with Gemini", "fixture": "Handwritten demo fallback"}[value])

if st.button("Analyze demo"):
    try:
        with st.spinner("Generating tests and testing both revisions" if mode == "gemini" else "Testing both revisions"):
            response = requests.post("http://127.0.0.1:8000/analyze", params={"mode": mode}, timeout=180)
            if not response.ok:
                st.error(response.json().get("detail", "Analysis failed."))
                st.stop()
            response.raise_for_status()
            report = response.json()
    except requests.RequestException as error:
        st.error(f"Analysis could not finish. Check the API and Docker. {error}")
        st.stop()

    st.metric("Verdict", report["verdict"])
    st.caption("A passing result covers only the tests shown below.")
    st.write("Requirement:", report["requirement"])
    generation = report["generation"]
    st.write("Test source:", generation["source"])
    if generation["model"]:
        st.caption(generation["model"])
    st.write(generation["rationale"])
    for side, column in zip(("base", "head"), st.columns(2)):
        result = report[side]
        with column:
            st.subheader(f"{side.title()} · {result['status']}")
            st.caption(result["commit"][:8])
            st.code(result["output"])
    st.subheader("Git diff")
    st.code(report["diff"], language="diff")
    st.subheader("Test")
    st.code(report["test_source"], language="python")
