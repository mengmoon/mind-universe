import streamlit as st
from utils import save_chat_message, generate_ai_text_reply

def app():
    if not st.session_state.logged_in:
        st.warning("Please log in via the Home page to access the AI Mentor.")
        return

    st.header("💬 AI Mentor")
    st.caption("Chat with your supportive AI mentor for insights, coping strategies, and reflections.")
    st.divider()

    # Display chat history
    for message in st.session_state.chat_history:
        role = "user" if message["role"] == "user" else "assistant"
        avatar = "👤" if role == "user" else "🧠"
        with st.chat_message(role, avatar=avatar):
            st.markdown(message["content"])

    # Chat input
    if prompt := st.chat_input("Type your message to Mind Mentor..."):
        # Save and display user message
        with st.chat_message("user", avatar="👤"):
            st.markdown(prompt)
        save_chat_message("user", prompt)
        
        # Get and display AI response
        with st.chat_message("assistant", avatar="🧠"):
            with st.spinner("Mind Mentor is reflecting..."):
                # Pass the latest history including the user's new message
                ai_response_text = generate_ai_text_reply(prompt, st.session_state.chat_history)
                
            if ai_response_text:
                st.markdown(ai_response_text)
                save_chat_message("model", ai_response_text)
                st.rerun()
            else:
                st.error("Failed to receive a reply from the AI Mentor. Please try again.")

app()
