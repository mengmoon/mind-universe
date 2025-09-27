import streamlit as st
import firebase_admin
from firebase_admin import credentials, firestore
import requests
import json
from datetime import datetime
import openai

# ----------------------
# Page Config
# ----------------------
st.set_page_config(page_title="Mind Universe", page_icon="🧠", layout="wide")
st.title("🌌 Mind Universe")
st.write("Explore your inner world with AI mentors.")

# ----------------------
# Session State
# ----------------------
if "user" not in st.session_state:
    st.session_state.user = None
if "reload_flag" not in st.session_state:
    st.session_state.reload_flag = False

def safe_rerun():
    st.session_state.reload_flag = not st.session_state.reload_flag

# ----------------------
# Firebase Initialization
# ----------------------
try:
    firebase_config = json.loads(st.secrets["FIREBASE_CONFIG"])
except KeyError:
    st.error("Missing FIREBASE_CONFIG in secrets.toml")
    st.stop()
except json.JSONDecodeError:
    st.error("FIREBASE_CONFIG is not valid JSON")
    st.stop()

if not firebase_admin._apps:
    try:
        cred = credentials.Certificate(firebase_config)
        firebase_admin.initialize_app(cred)
        st.write("✅ Firebase Admin Initialized")
    except ValueError as e:
        st.error(f"Firebase initialization failed: {e}")
        st.stop()

db = firestore.client()

# ----------------------
# Firebase Auth
# ----------------------
try:
    FIREBASE_API_KEY = st.secrets["FIREBASE_API_KEY"]
except KeyError:
    st.error("Missing FIREBASE_API_KEY in secrets.toml")
    st.stop()

def signup_user(email, password):
    url = f"https://identitytoolkit.googleapis.com/v1/accounts:signUp?key={FIREBASE_API_KEY}"
    payload = {"email": email, "password": password, "returnSecureToken": True}
    res = requests.post(url, json=payload)
    if res.status_code == 200:
        return res.json()
    else:
        error = res.json().get("error", {}).get("message", "Unknown error")
        st.error(f"Sign up failed: {error}")
        return None

def login_user(email, password):
    url = f"https://identitytoolkit.googleapis.com/v1/accounts:signInWithPassword?key={FIREBASE_API_KEY}"
    payload = {"email": email, "password": password, "returnSecureToken": True}
    res = requests.post(url, json=payload)
    if res.status_code == 200:
        return res.json()
    else:
        error = res.json().get("error", {}).get("message", "Unknown error")
        st.error(f"Login failed: {error}")
        return None

# ----------------------
# Firestore Functions
# ----------------------
def save_journal(uid, text):
    db.collection("journals").add({
        "uid": uid,
        "text": text,
        "timestamp": firestore.SERVER_TIMESTAMP
    })

def get_journals(uid):
    docs = db.collection("journals").where("uid", "==", uid).stream()
    journals = []
    for d in docs:
        data = d.to_dict()
        ts = data.get("timestamp")
        # Convert Firestore timestamp to datetime safely
        if ts is not None:
            try:
                formatted_ts = ts.to_datetime().strftime("%Y-%m-%d %H:%M:%S")
            except Exception:
                formatted_ts = str(ts)
        else:
            formatted_ts = "Unknown"
        journals.append({"text": data.get("text", ""), "timestamp": formatted_ts})
    journals.sort(key=lambda x: x["timestamp"], reverse=True)
    return journals

def save_chat(uid, role, text):
    db.collection("chats").add({
        "uid": uid,
        "role": role,
        "text": text,
        "timestamp": firestore.SERVER_TIMESTAMP
    })

def get_chats(uid):
    docs = db.collection("chats").where("uid", "==", uid).stream()
    chats = []
    for d in docs:
        data = d.to_dict()
        chats.append({"role": data.get("role", ""), "text": data.get("text", "")})
    return chats

# ----------------------
# OpenAI GPT Setup
# ----------------------
try:
    openai.api_key = st.secrets["OPENAI_API_KEY"]
except KeyError:
    st.error("Missing OPENAI_API_KEY in secrets.toml")
    st.stop()

AI_SYSTEM_PROMPT = """
You are an AI mentor who can switch between these six voices:
- Freud: psychoanalysis, explore subconscious
- Adler: individual psychology, encouragement
- Jung: archetypes, shadow work
- Maslow: self-actualization guidance
- Positive Psychology: focus on strengths and well-being
- CBT: cognitive-behavioral therapy, practical advice

Always provide empathetic, insightful, and reflective responses.
"""

def generate_ai_reply(user_input):
    try:
        response = openai.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": AI_SYSTEM_PROMPT},
                {"role": "user", "content": user_input}
            ],
            temperature=0.7,
            max_tokens=500
        )
        return response.choices[0].message.content.strip()
    except openai.error.OpenAIError as e:
        status = getattr(e, "http_status", None)
        if status == 429:
            return "AI is temporarily unavailable due to quota limits. Please try again later."
        return f"AI failed to respond: {e}"
    except Exception as e:
        return f"Unexpected error: {e}"

# ----------------------
# Authentication UI
# ----------------------
st.subheader("🔐 Login / Sign Up")
auth_mode = st.radio("Select Action:", ["Login", "Sign Up"])

if st.session_state.user:
    st.write(f"Logged in as: {st.session_state.user['email']}")
    if st.button("Logout"):
        st.session_state.user = None
        st.success("Logged out")
        safe_rerun()
else:
    email = st.text_input("Email")
    password = st.text_input("Password", type="password")
    if st.button("Submit"):
        if auth_mode == "Sign Up":
            user = signup_user(email, password)
        else:
            user = login_user(email, password)
        if user:
            st.session_state.user = user
            st.success(f"Logged in as {email}")
            safe_rerun()

# ----------------------
# Main App Features
# ----------------------
if st.session_state.user:
    uid = st.session_state.user["localId"]

    # --- Journal ---
    st.subheader("📝 Journal")
    journal_text = st.text_area("Write your thoughts here...")
    if st.button("Save Journal"):
        if journal_text.strip():
            save_journal(uid, journal_text)
            st.success("Journal saved")
            safe_rerun()
        else:
            st.warning("Write something before saving.")

    st.subheader("📜 Journal History")
    for entry in get_journals(uid):
        st.markdown(f"- **{entry['timestamp']}**: {entry['text']}")

    # --- Chat ---
    st.subheader("🤖 AI Mentor Chat")
    user_msg = st.text_input("Say something to your AI mentor:")
    if st.button("Send"):
        if user_msg.strip():
            save_chat(uid, "user", user_msg)
            ai_reply = generate_ai_reply(user_msg)
            save_chat(uid, "ai", ai_reply)
            st.success(f"AI: {ai_reply}")
            safe_rerun()

    st.subheader("💬 Chat History")
    for msg in get_chats(uid):
        st.write(f"**{msg['role']}**: {msg['text']}")
