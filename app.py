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
if not firebase_admin._apps:
    firebase_config = st.secrets["FIREBASE_CONFIG"]  # Already a dict from secrets
    cred = credentials.Certificate(firebase_config)
    firebase_admin.initialize_app(cred)

db = firestore.client()

# ----------------------
# API Keys
# ----------------------
FIREBASE_API_KEY = st.secrets["FIREBASE_API_KEY"]
OPENAI_API_KEY = st.secrets["OPENAI_API_KEY"]
openai.api_key = OPENAI_API_KEY

# ----------------------
# Firebase Auth (REST API)
# ----------------------
def signup_user(email, password):
    url = f"https://identitytoolkit.googleapis.com/v1/accounts:signUp?key={FIREBASE_API_KEY}"
    payload = {"email": email, "password": password, "returnSecureToken": True}
    try:
        res = requests.post(url, data=payload)
        data = res.json()
        if res.status_code == 200:
            return data
        else:
            st.error(f"❌ Sign up failed: {data.get('error', {}).get('message', 'Unknown error')}")
            return None
    except Exception as e:
        st.error(f"❌ Network error during sign up: {e}")
        return None

def login_user(email, password):
    url = f"https://identitytoolkit.googleapis.com/v1/accounts:signInWithPassword?key={FIREBASE_API_KEY}"
    payload = {"email": email, "password": password, "returnSecureToken": True}
    try:
        res = requests.post(url, data=payload)
        data = res.json()
        if res.status_code == 200:
            return data
        else:
            st.error(f"❌ Login failed: {data.get('error', {}).get('message', 'Unknown error')}")
            return None
    except Exception as e:
        st.error(f"❌ Network error during login: {e}")
        return None

# ----------------------
# Firestore Functions
# ----------------------
def save_journal(user_id, text):
    try:
        db.collection("journals").add({
            "uid": user_id,
            "text": text,
            "timestamp": firestore.SERVER_TIMESTAMP,
        })
        st.success("✅ Journal entry saved")
    except Exception as e:
        st.error(f"Failed to save journal: {e}")

def get_journals(user_id):
    try:
        docs = db.collection("journals").where("uid", "==", user_id).limit(50).stream()
        journals = []
        for d in docs:
            data = d.to_dict()
            ts = data.get("timestamp")
            if ts:
                timestamp = ts.strftime("%Y-%m-%d %H:%M:%S") if isinstance(ts, datetime) else str(ts)
            else:
                timestamp = "Unknown time"
            journals.append({"text": data.get("text", ""), "timestamp": timestamp})
        # Sort descending
        journals.sort(key=lambda x: x["timestamp"], reverse=True)
        return journals
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
        docs = db.collection("chats").where("uid", "==", user_id).limit(50).stream()
        chats = []
        for d in docs:
            data = d.to_dict()
            chats.append({
                "role": data.get("role", "unknown"),
                "text": data.get("text", ""),
                "timestamp": data.get("timestamp")
            })
        chats.sort(key=lambda x: x["timestamp"] or datetime.min)
        return chats
    except Exception as e:
        st.warning(f"Could not fetch chats: {e}")
        return []

# ----------------------
# AI Mentor System Prompt
# ----------------------
AI_VOICES_SYSTEM_PROMPT = """
You are an AI Mentor integrating the voices and psychology of:
- Sigmund Freud (psychoanalysis, unconscious mind, dreams)
- Alfred Adler (individual psychology, encouragement, social interest)
- Carl Jung (archetypes, shadow, collective unconscious)
- Abraham Maslow (hierarchy of needs, self-actualization)
- Cognitive Behavioral Therapy (practical problem solving, thoughts/behaviors)
- Positive Psychology (strengths, optimism, well-being)

Respond thoughtfully and empathetically, blending these perspectives as guidance for the user.
"""

def generate_ai_reply(user_message):
    try:
        response = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": AI_VOICES_SYSTEM_PROMPT},
                {"role": "user", "content": user_message}
            ],
            max_tokens=300,
            temperature=0.7
        )
        reply = response['choices'][0]['message']['content'].strip()
        return reply
    except Exception as e:
        st.error(f"❌ AI generation error: {e}")
        return "Sorry, I couldn't generate a response right now."

# ----------------------
# Authentication UI
# ----------------------
st.subheader("🔐 Login / Sign Up")
auth_mode = st.radio("Select Action:", ["Login", "Sign Up"])

if st.session_state.user:
    st.write(f"Logged in as: {st.session_state.user['email']}")
    if st.button("Logout"):
        st.session_state.user = None
        st.success("✅ Logged out")
        st.rerun()
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
# Main App Features
# ----------------------
if st.session_state.user:
    uid = st.session_state.user["localId"]

    # Journal Section
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

    # Chat Section
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
