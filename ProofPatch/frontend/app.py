import requests
import streamlit as st

st.title("ProofPatch")
api = "http://127.0.0.1:8000"
local = st.radio("Compare", ["Built-in scenario", "Local checkout repository"]) == "Local checkout repository"

if local:
    st.caption("Supports checkout.py, pricing.py, and shipping.py at the repository root.")
    repo_path = st.text_input("Absolute repository path")
    base = st.text_input("Base commit or tag", value="baseline")
    head = st.text_input("New commit or tag", value="regression")
    requirement = st.text_area("Expected behavior")
    mode = st.radio("Test source", ["Generate with Gemini", "Provide a test"])
    generate = mode == "Generate with Gemini"
    test_source = None if generate else st.text_area(
        "Pytest source",
        value="from checkout import checkout_total\n\ndef test_free_shipping_after_discount():\n    assert checkout_total(60) == 50",
    )
    if generate:
        st.caption("Gemini receives the three source files from both commits, their diff, and the expected behavior.")
    trusted = st.checkbox("I trust this repository's Python code.")
    path = "/analyze/local"
    request = {"json": {"repo_path": repo_path, "base": base, "head": head,
                        "requirement": requirement, "test_source": test_source, "trusted": trusted}}
    disabled = not all((repo_path.strip(), base.strip(), head.strip(), requirement.strip(), trusted))
    disabled = disabled or (not generate and not test_source.strip())
else:
    try:
        catalog_response = requests.get(api + "/scenarios", timeout=10)
        catalog_response.raise_for_status()
        catalog = catalog_response.json()
    except requests.RequestException:
        st.error("Could not load scenarios. Start or restart the backend.")
        st.stop()
    selected = st.selectbox("Scenario", catalog, format_func=lambda item: item["title"])
    st.write(selected["requirement"])
    mode = st.radio("Test source", ["gemini", "fixture"], format_func=lambda value: {
        "gemini": "Generate with Gemini", "fixture": "Handwritten demo fallback"}[value])
    generate = mode == "gemini"
    path = "/analyze"
    request = {"params": {"mode": mode, "scenario": selected["id"]}}
    disabled = False

if st.button("Compare commits" if local else "Analyze demo", disabled=disabled):
    try:
        with st.spinner("Generating tests and testing both revisions" if generate else "Testing both revisions"):
            response = requests.post(api + path, **request, timeout=180)
            if not response.ok:
                detail = response.json().get("detail")
                st.error(detail if isinstance(detail, str) else "Check the comparison inputs and try again.")
                st.stop()
            response.raise_for_status()
            report = response.json()
    except requests.RequestException as error:
        st.error(f"Analysis could not finish. Check the API and Docker. {error}")
        st.stop()

    st.metric("Verdict", report["verdict"])
    if not local:
        expected = report["scenario"]["expected"]
        st.caption(f"Expected: base {expected['base']} → head {expected['head']} · {expected['verdict']}")
        if report["matches_expected"]:
            st.success("Results match this scenario's expected outcome.")
        else:
            st.warning("Results differ from the expected outcome. Review the assertions and execution output.")
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
    st.subheader("Git diff for checkout files" if local else "Git diff")
    if report["diff"]:
        st.code(report["diff"], language="diff")
    else:
        st.caption("No changes in the compared files.")
    st.subheader("Test")
    st.code(report["test_source"], language="python")
