import streamlit as st
from utils import (
    firebase_sign_in,
    firebase_sign_up,
    save_journal_entry,
    get_journal_history,
    save_chat_message,
    get_chat_history,
    generate_ai_reply,
)

st.set_page_config(page_title="Mind Universe", page_icon="🧠", layout="wide")

st.title("🌌 Mind Universe")
st.write("Welcome to Mind Universe — explore your inner world with AI mentors.")


# ----------------------
# Login / Signup Section
# ----------------------
if "user" not in st.session_state:
    st.session_state.user = None

if st.session_state.user is None:
    st.subheader("🔐 Login / Sign Up")

    tab1, tab2 = st.tabs(["Login", "Sign Up"])

    with tab1:
        email = st.text_input("Email", key="login_email")
        password = st.text_input("Password", type="password", key="login_password")
        if st.button("Login"):
            user = firebase_sign_in(email, password)
            if user:
                st.session_state.user = user
                st.success("✅ Logged in successfully")
                st.rerun()
            else:
                st.error("❌ Invalid email or password")

    with tab2:
        new_email = st.text_input("New Email", key="signup_email")
        new_password = st.text_input("New Password", type="password", key="signup_password")
        if st.button("Sign Up"):
            user = firebase_sign_up(new_email, new_password)
            if user:
                st.session_state.user = user
                st.success("✅ Account created and logged in")
                st.rerun()
            else:
                st.error("❌ Failed to create account")

else:
    st.success(f"✅ Logged in as {st.session_state.user['email']}")

    # ----------------------
    # Journal Section
    # ----------------------
    st.subheader("📝 Journal")
    journal_text = st.text_area("Write your thoughts here...")

    if st.button("Save Journal Entry"):
        if journal_text.strip():
            save_journal_entry(st.session_state.user["uid"], journal_text)
            st.success("✅ Journal entry saved.")
        else:
            st.warning("⚠️ Please write something before saving.")

    history = get_journal_history(st.session_state.user["uid"])
    if history:
        st.write("### 📜 Journal History")
        for entry in history:
            st.write(f"- {entry['timestamp']}: {entry['text']}")

    # ----------------------
    # Chat Section
    # ----------------------
    st.subheader("🤖 AI Mentor Chat")
    user_message = st.text_input("Ask something or share your thoughts...", key="chat_input")

    if st.button("Send"):
        if user_message.strip():
            save_chat_message(st.session_state.user["uid"], "user", user_message)
            ai_reply = generate_ai_reply(user_message)
            save_chat_message(st.session_state.user["uid"], "mentor", ai_reply)
            st.success("✅ Reply generated")
        else:
            st.warning("⚠️ Please type a message before sending.")

    chat_history = get_chat_history(st.session_state.user["uid"])
    if chat_history:
        st.write("### 💬 Chat History")
        for msg in chat_history:
            role = "🧑 You" if msg["role"] == "user" else "✨ Mentor"
            st.write(f"**{role}:** {msg['text']}")

    if st.button("Logout"):
        st.session_state.user = None
        st.rerun()
