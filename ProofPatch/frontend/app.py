import requests
import streamlit as st

st.title("ProofPatch")
st.caption("Shipping threshold demo · fixed pytest fixture")

if st.button("Analyze demo"):
    try:
        with st.spinner("Testing both revisions"):
            response = requests.post("http://127.0.0.1:8000/analyze", timeout=100)
            response.raise_for_status()
            report = response.json()
    except requests.RequestException as error:
        st.error(f"Analysis could not finish. Check the API and Docker. {error}")
        st.stop()

    st.metric("Verdict", report["verdict"])
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
