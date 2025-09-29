import streamlit as st
import pandas as pd
from datetime import datetime
from utils import generate_journal_analysis

def app():
    if not st.session_state.logged_in:
        st.warning("Please log in via the Home page to view Insights.")
        return

    st.header("📊 Insights")
    st.caption("AI-Powered Insights & Visualization of your long-term emotional trends.")
    
    if not st.session_state.journal_entries:
        st.info("You need to write a few journal entries before generating insights.")
        return

    # --- Data Preparation ---
    chart_data = [
        {'date': datetime.strptime(e['date'], '%Y-%m-%d'), 'sentiment': e.get('sentiment'), 'emotion': e.get('emotion')}
        for e in st.session_state.journal_entries
        if e.get('sentiment') is not None
    ]
    
    if chart_data:
        chart_data.sort(key=lambda x: x['date'])
        df = pd.DataFrame(chart_data)
        df.set_index('date', inplace=True)

    # New Sub-Tabs for Visualization and Summary
    tab_trends, tab_frequency, tab_summary = st.tabs(["📉 Sentiment Trend", "📊 Emotion Frequency", "🧠 Deep Summary"])

    # --- Sentiment Trend Chart (Line Chart) ---
    with tab_trends:
        st.subheader("Overall Emotional Score Over Time")
        
        if chart_data:
            st.markdown("**(Range: -1.0 Negative to 1.0 Positive)**")
            st.line_chart(df[['sentiment']], height=300)
        else:
            st.warning("No entries with sentiment data found.")

    # --- Emotion Frequency (Bar Chart) ---
    with tab_frequency:
        st.subheader("Frequency of Detected Emotions")
        
        if chart_data:
            emotion_counts = df['emotion'].value_counts().reset_index()
            emotion_counts.columns = ['Emotion', 'Count']
            
            st.bar_chart(emotion_counts, x='Emotion', y='Count', color="#88C0D0", height=300)
            st.info("This chart shows the primary emotion keyword detected by the AI for each entry.")
        else:
            st.warning("No entries with sentiment data found.")

    # --- Deep Summary (AI Analysis) ---
    with tab_summary:
        st.subheader("Comprehensive Journal Summary")
        
        if st.button("Generate Deep AI Analysis", key="run_analysis"):
            st.session_state.journal_analysis = None # Clear existing analysis to force recalculation

        if st.session_state.journal_analysis is None:
            if st.session_state.journal_entries:
                # Prepare the text block for the LLM
                journal_text_block = ""
                for entry in st.session_state.journal_entries:
                    journal_text_block += (
                        f"Date: {entry.get('date', 'N/A')}, "
                        f"Sentiment: {entry.get('emotion', 'Neutral')} ({entry.get('sentiment', 0.0):.2f})\n"
                        f"Title: {entry.get('title', 'Untitled')}\n"
                        f"Content: {entry.get('content', '')[:500]}...\n\n"
                    )
                
                if journal_text_block:
                    with st.spinner("The Mind Analyst is synthesizing your entries... this may take a moment."):
                        analysis_result = generate_journal_analysis(journal_text_block)
                    st.session_state.journal_analysis = analysis_result
                else:
                    st.warning("No entries available to analyze.")
                    st.session_state.journal_analysis = "No data available."
            else:
                st.info("Write a few journal entries and click 'Generate Deep AI Analysis' to see a summary of your trends.")

        if st.session_state.journal_analysis and st.session_state.journal_analysis != "No data available.":
            st.markdown("---")
            st.markdown(st.session_state.journal_analysis)
            st.caption("This analysis summarizes themes and trends across all your entries.")
        elif st.session_state.journal_analysis == "No data available.":
            st.warning("No entries available to analyze.")


