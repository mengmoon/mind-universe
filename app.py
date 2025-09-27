import streamlit as st
import firebase_admin
from firebase_admin import credentials, firestore
import requests
import json
from datetime import datetime
import openai
from openai.error import OpenAIError  # Only import OpenAIError

# ----------------------
# Page Config
# ----------------------
st.set_page_config(page_title="Mind Universe", page_icon="🧠", layout="wide")
st.title("🌌 Mind Universe")
st.subheader("Explore your inner world with AI mentors.")

# ----------------------
# Session State
# ----------------------
if "user" not in st.session_state:
    st.session_state.user = None

def safe_rerun():
    st.experimental_rerun()

# ----------------------
# Firebase Initialization
# ----------------------
try:
    firebase_config = json.loads(st.secrets["FIREBASE_CONFIG"])
except KeyError as e:
    st.error(f"Missing secret key: {e}")
    st.stop()
except json.JSONDecodeError as e:
    st.error(f"Failed to parse FIREBASE_CONFIG as JSON: {e}")
    st.stop()

if not firebase_admin._apps:
    try:
        if "private_key" in firebase_config:
            firebase_config["private_key"] = firebase_config["private_key"].replace("\\n", "\n")
        cred = credentials.Certificate(firebase_config)
        firebase_admin.initialize_app(cred)
        st.success("Firebase Admin SDK Initialized")
    except ValueError as e:
        st.error(f"Failed to initialize Firebase: {e}")
        st.stop()

db = firestore.client()

# ----------------------
# Firebase Auth via REST API
# ----------------------
FIREBASE_API_KEY = st.secrets["FIREBASE_API_KEY"]

def signup_user(email, password):
    url = f"https://identitytoolkit.googleapis.com/v1/accounts:signUp?key={FIREBASE_API_KEY}"
    payload = {"email": email, "password": password, "returnSecureToken": True}
    res = requests.post(url, json=payload)
    if res.status_code == 200:
        return res.json(), None
    else:
        error = res.json().get("error", {}).get("message", "Unknown error")
        return None, error

def login_user(email, password):
    url = f"https://identitytoolkit.googleapis.com/v1/accounts:signInWithPassword?key={FIREBASE_API_KEY}"
    payload = {"email": email, "password": password, "returnSecureToken": True}
    res = requests.post(url, json=payload)
    if res.status_code == 200:
        return res.json(), None
    else:
        error = res.json().get("error", {}).get("message", "Unknown error")
        return None, error

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
        if ts is not None:
            try:
                formatted_ts = ts.astimezone().strftime("%Y-%m-%d %H:%M:%S")
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
    docs = db.collection("chats").where("uid", "==", uid).order_by("timestamp").stream()
    chats = []
    for d in docs:
        data = d.to_dict()
        chats.append({"role": data.get("role", ""), "text": data.get("text", "")})
    return chats

# ----------------------
# OpenAI GPT Setup
# ----------------------
openai.api_key = st.secrets["OPENAI_API_KEY"]

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
    except OpenAIError as e:
        msg = str(e)
        if "Rate limit" in msg:
            return "AI is temporarily unavailable due to quota limits. Please try again later."
        if "Invalid API key" in msg or "Unauthorized" in msg:
            return "Authentication error: Please check your OpenAI API key."
        return f"OpenAI API error: {msg}"
    except Exception as e:
        return f"Unexpected error: {type(e).__name__} - {e}"

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
            user, error = signup_user(email, password)
        else:
            user, error = login_user(email, password)
        if error:
            st.error(f"{auth_mode} failed: {error}")
        elif user:
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
        st.write(f"**{msg['role'].capitalize()}**: {msg['text']}")
