import streamlit as st
import firebase_admin
from firebase_admin import credentials, firestore
import requests
import openai
from datetime import datetime

# ----------------------
# Page Config
# ----------------------
st.set_page_config(page_title="Mind Universe", page_icon="🧠", layout="wide")
st.title("🌌 Mind Universe")
st.write("Explore your inner world with AI mentors.")

# ----------------------
# Session State Initialization
# ----------------------
if "user" not in st.session_state:
    st.session_state.user = None

# ----------------------
# Firebase Initialization
# ----------------------
try:
    if not firebase_admin._apps:
        # Convert secrets.toml FIREBASE_CONFIG to dict
        firebase_config = dict(st.secrets["FIREBASE_CONFIG"])
        cred = credentials.Certificate(firebase_config)
        firebase_admin.initialize_app(cred)
    db = firestore.client()
except Exception as e:
    st.error(f"❌ Firebase initialization failed: {e}")
    st.stop()

# ----------------------
# API Keys
# ----------------------
FIREBASE_API_KEY = st.secrets["FIREBASE_API_KEY"]
OPENAI_API_KEY = st.secrets["OPENAI_API_KEY"]
openai.api_key = OPENAI_API_KEY

# ----------------------
# Firebase Auth Functions
# ----------------------
def signup_user(email, password):
    url = f"https://identitytoolkit.googleapis.com/v1/accounts:signUp?key={FIREBASE_API_KEY}"
    payload = {"email": email, "password": password, "returnSecureToken": True}
    try:
        res = requests.post(url, json=payload)
        if res.status_code == 200:
            return res.json()
        else:
            st.error(res.json().get("error", {}).get("message", "Sign up failed"))
            return None
    except Exception as e:
        st.error(f"Network error: {e}")
        return None

def login_user(email, password):
    url = f"https://identitytoolkit.googleapis.com/v1/accounts:signInWithPassword?key={FIREBASE_API_KEY}"
    payload = {"email": email, "password": password, "returnSecureToken": True}
    try:
        res = requests.post(url, json=payload)
        if res.status_code == 200:
            return res.json()
        else:
            st.error(res.json().get("error", {}).get("message", "Login failed"))
            return None
    except Exception as e:
        st.error(f"Network error: {e}")
        return None

# ----------------------
# Firestore Journal / Chat Functions
# ----------------------
def save_journal(user_id, text):
    try:
        db.collection("journals").add({
            "uid": user_id,
            "text": text,
            "timestamp": firestore.SERVER_TIMESTAMP,
        })
        st.success("✅ Journal saved")
    except Exception as e:
        st.error(f"Failed to save journal: {e}")

def get_journals(user_id):
    try:
        docs = db.collection("journals").where("uid", "==", user_id).stream()
        journals = []
        for d in docs:
            data = d.to_dict()
            ts = data.get("timestamp")
            journals.append({
                "text": data.get("text", "[No Text]"),
                "timestamp": ts.to_datetime().strftime("%Y-%m-%d %H:%M:%S") if ts else "Unknown"
            })
        journals.sort(key=lambda x: x["timestamp"], reverse=True)
        return journals[:10]
    except Exception as e:
        st.warning(f"Could not fetch journals: {e}")
        return []

def save_chat(user_id, role, text):
    try:
        db.collection("chats").add({
            "uid": user_id,
            "role": role,
            "text": text,
            "timestamp": firestore.SERVER_TIMESTAMP,
        })
    except Exception as e:
        st.error(f"Failed to save chat: {e}")

def get_chats(user_id):
    try:
        docs = db.collection("chats").where("uid", "==", user_id).stream()
        chats = []
        for d in docs:
            data = d.to_dict()
            ts = data.get("timestamp")
            chats.append({
                "role": data.get("role", "unknown"),
                "text": data.get("text", "[No Text]"),
                "timestamp": ts.to_datetime().strftime("%Y-%m-%d %H:%M:%S") if ts else "Unknown"
            })
        chats.sort(key=lambda x: x["timestamp"])
        return chats[-20:]
    except Exception as e:
        st.warning(f"Could not fetch chats: {e}")
        return []

# ----------------------
# Dynamic GPT AI Mentor
# ----------------------
SYSTEM_PROMPT = """
You are a wise AI Mentor that can respond using the perspectives of:
- Sigmund Freud
- Alfred Adler
- Carl Jung
- Abraham Maslow
- Positive Psychology
- Cognitive Behavioral Therapy (CBT)

Provide empathetic, insightful, and psychologically informed responses based on the user's input. Adapt your style to include elements of these perspectives as appropriate.
"""

def generate_ai_reply(user_message):
    try:
        response = openai.ChatCompletion.create(
            model="gpt-4",
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_message}
            ],
            max_tokens=500
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        return f"AI error: {e}"

# ----------------------
# Authentication UI
# ----------------------
st.subheader("🔐 Login / Sign Up")
auth_mode = st.radio("Action:", ["Login", "Sign Up"])

if st.session_state.user:
    st.write(f"Logged in as: {st.session_state.user['email']}")
    if st.button("Logout"):
        st.session_state.user = None
        st.success("✅ Logged out")
        st.experimental_rerun()
else:
    email = st.text_input("Email")
    password = st.text_input("Password", type="password")
    if st.button("Submit"):
        if auth_mode == "Sign Up":
            user = signup_user(email, password)
            if user:
                st.session_state.user = user
                st.success(f"✅ Signed up as {email}")
        else:
            user = login_user(email, password)
            if user:
                st.session_state.user = user
                st.success(f"✅ Logged in as {email}")

# ----------------------
# Main App
# ----------------------
if st.session_state.user:
    uid = st.session_state.user["localId"]

    # Journal
    st.subheader("📝 Journal")
    journal_text = st.text_area("Write your thoughts here...")
    if st.button("Save Journal"):
        if journal_text.strip():
            save_journal(uid, journal_text)
        else:
            st.warning("⚠️ Please write something before saving.")

    st.subheader("📜 Journal History")
    for entry in get_journals(uid):
        st.markdown(f"- **{entry['timestamp']}**: {entry['text']}")

    # Chat
    st.subheader("🤖 AI Mentor Chat")
    user_msg = st.text_input("Say something to your AI mentor:")
    if st.button("Send"):
        if user_msg.strip():
            save_chat(uid, "user", user_msg)
            ai_reply = generate_ai_reply(user_msg)
            save_chat(uid, "ai", ai_reply)
            st.success(f"AI: {ai_reply}")

    st.subheader("💬 Chat History")
    for msg in get_chats(uid):
        st.write(f"**{msg['role']}**: {msg['text']}")
