import requests
import streamlit as st

st.title("ProofPatch")
st.caption("Regression scenarios · targeted tests")
try:
    catalog_response = requests.get("http://127.0.0.1:8000/scenarios", timeout=10)
    catalog_response.raise_for_status()
    catalog = catalog_response.json()
except requests.RequestException:
    st.error("Could not load scenarios. Start or restart the backend.")
    st.stop()
selected = st.selectbox("Scenario", catalog, format_func=lambda item: item["title"])
st.write(selected["requirement"])
mode = st.radio("Test source", ["gemini", "fixture"], format_func=lambda value: {
    "gemini": "Generate with Gemini", "fixture": "Handwritten demo fallback"}[value])

if st.button("Analyze demo"):
    try:
        with st.spinner("Generating tests and testing both revisions" if mode == "gemini" else "Testing both revisions"):
            response = requests.post("http://127.0.0.1:8000/analyze",
                                     params={"mode": mode, "scenario": selected["id"]}, timeout=180)
            if not response.ok:
                st.error(response.json().get("detail", "Analysis failed."))
                st.stop()
            response.raise_for_status()
            report = response.json()
    except requests.RequestException as error:
        st.error(f"Analysis could not finish. Check the API and Docker. {error}")
        st.stop()

    st.metric("Verdict", report["verdict"])
    expected = report["scenario"]["expected"]
    st.caption(f"Expected: base {expected['base']} → head {expected['head']} · {expected['verdict']}")
    if report["matches_expected"]:
        st.success("Results match this scenario's expected outcome.")
    else:
        st.warning("Results differ from the expected outcome. Review the generated assertions and execution output.")
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
