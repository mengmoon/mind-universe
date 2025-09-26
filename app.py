import streamlit as st
from utils import (
    save_journal,
    get_journals,
    signup_user,
    login_user,
    save_chat,
    get_chats,
    generate_ai_reply,
)

# ----------------------
# Session State
# ----------------------
if "user" not in st.session_state:
    st.session_state.user = None


# ----------------------
# Login / Signup Screen
# ----------------------
def login_screen():
    st.title("🔐 Mind Universe Login")

    choice = st.radio("Choose an option:", ["Login", "Sign Up"])

    email = st.text_input("Email")
    password = st.text_input("Password", type="password")

    if choice == "Sign Up":
        if st.button("Create Account"):
            result = signup_user(email, password)
            if result:
                st.session_state.user = result
                st.success("✅ Account created! You are now logged in.")
                st.rerun()
            else:
                st.error("❌ Sign up failed. Try again.")
    else:  # Login
        if st.button("Login"):
            result = login_user(email, password)
            if result:
                st.session_state.user = result
                st.success("✅ Logged in successfully!")
                st.rerun()
            else:
                st.error("❌ Invalid email or password.")


# ----------------------
# Journal Screen
# ----------------------
def journal_screen(user):
    st.subheader("📓 Your Journal")
    entry = st.text_area("Write your thoughts here...")

    if st.button("Save Entry"):
        save_journal(user["localId"], entry)
        st.success("✅ Journal entry saved!")

    st.write("### Recent Entries")
    history = get_journals(user["localId"])
    for h in history:
        st.markdown(f"- {h['text']} ({h.get('timestamp')})")


# ----------------------
# Chat Screen
# ----------------------
def chat_screen(user):
    st.subheader("💬 AI Mentor Chat")

    chats = get_chats(user["localId"])
    for c in chats:
        st.markdown(f"**{c['role'].capitalize()}:** {c['text']}")

    user_msg = st.text_input("Your message:")
    if st.button("Send"):
        if user_msg.strip():
            save_chat(user["localId"], "user", user_msg)
            ai_reply = generate_ai_reply(user_msg)
            save_chat(user["localId"], "mentor", ai_reply)
            st.rerun()


# ----------------------
# Main App
# ----------------------
def main():
    if not st.session_state.user:
        login_screen()
    else:
        st.sidebar.success(f"Logged in as {st.session_state.user.get('email', 'Unknown')}")
        page = st.sidebar.radio("Navigate", ["Journal", "Chat"])

        if page == "Journal":
            journal_screen(st.session_state.user)
        elif page == "Chat":
            chat_screen(st.session_state.user)


if __name__ == "__main__":
    main()
