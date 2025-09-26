

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
# Load Secrets
# ----------------------
firebase_config = st.secrets["FIREBASE_CONFIG"].copy()
FIREBASE_API_KEY = firebase_config["FIREBASE_API_KEY"]
OPENAI_API_KEY = firebase_config["OPENAI_API_KEY"]

# Fix PEM format for Streamlit Cloud
if "-----BEGIN PRIVATE KEY-----" in firebase_config["private_key"]:
    firebase_config["private_key"] = firebase_config["private_key"].replace("\\n", "\n")

# ----------------------
# Firebase Initialization
# ----------------------
if not firebase_admin._apps:
    try:
        cred = credentials.Certificate(firebase_config)
        firebase_admin.initialize_app(cred)
    except Exception as e:
        st.error(f"❌ Firebase initialization failed: {e}")
        st.stop()

db = firestore.client()

# ----------------------
# Firebase Auth via REST API
# ----------------------
def signup_user(email, password):
    url = f"https://identitytoolkit.googleapis.com/v1/accounts:signUp?key={FIREBASE_API_KEY}"
    payload = {"email": email, "password": password, "returnSecureToken": True}
    try:
        res = requests.post(url, json=payload)
        if res.status_code == 200:
            return res.json()
        st.error(f"❌ Sign up failed: {res.json().get('error', {}).get('message')}")
    except Exception as e:
        st.error(f"❌ Network error during sign up: {e}")

def login_user(email, password):
    url = f"https://identitytoolkit.googleapis.com/v1/accounts:signInWithPassword?key={FIREBASE_API_KEY}"
    payload = {"email": email, "password": password, "returnSecureToken": True}
    try:
        res = requests.post(url, json=payload)
        if res.status_code == 200:
            return res.json()
        st.error(f"❌ Login failed: {res.json().get('error', {}).get('message')}")
    except Exception as e:
        st.error(f"❌ Network error during login: {e}")

# ----------------------
# Journal / Chat Functions
# ----------------------
def save_journal(uid, text):
    db.collection("journals").add({"uid": uid, "text": text, "timestamp": firestore.SERVER_TIMESTAMP})
    st.success("✅ Journal saved.")

def get_journals(uid):
    docs = db.collection("journals").where("uid", "==", uid).stream()
    entries = []
    for doc in docs:
        data = doc.to_dict()
        ts = data.get("timestamp")
        entries.append({"text": data.get("text"), "timestamp": ts})
    entries.sort(key=lambda x: x["timestamp"] or datetime.min, reverse=True)
    return entries[:10]

def save_chat(uid, role, text):
    db.collection("chats").add({"uid": uid, "role": role, "text": text, "timestamp": firestore.SERVER_TIMESTAMP})

def get_chats(uid):
    docs = db.collection("chats").where("uid", "==", uid).stream()
    chats = []
    for doc in docs:
        data = doc.to_dict()
        chats.append({"role": data.get("role"), "text": data.get("text")})
    return chats[-20:]

# ----------------------
# GPT AI Mentor
# ----------------------
openai.api_key = OPENAI_API_KEY
SYSTEM_PROMPT = """You are an AI Mentor integrating these six voices: Freud, Adler, Jung, Maslow, Positive Psychology, CBT.
Provide empathetic, insightful, and guidance-focused responses. Tailor advice and reflections using the perspectives of all six mentors."""

def generate_ai_reply(user_message):
    try:
        resp = openai.ChatCompletion.create(
            model="gpt-4",
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_message}
            ],
            temperature=0.7
        )
        return resp.choices[0].message.content.strip()
    except Exception as e:
        st.error(f"❌ GPT error: {e}")
        return "Sorry, I couldn't generate a response."

# ----------------------
# Session State
# ----------------------
if "user" not in st.session_state:
    st.session_state.user = None

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
# Main App Features
# ----------------------
if st.session_state.user:
    uid = st.session_state.user["localId"]

    # Journal
    st.subheader("📝 Journal")
    journal_text = st.text_area("Write your thoughts...")
    if st.button("Save Journal"):
        if journal_text.strip():
            save_journal(uid, journal_text)
        else:
            st.warning("⚠️ Write something before saving.")

    st.subheader("📜 Journal History")
    for entry in get_journals(uid):
        ts = entry["timestamp"].isoformat() if entry["timestamp"] else "Unknown"
        st.markdown(f"- **{ts}**: {entry['text']}")

    # Chat
    st.subheader("🤖 AI Mentor Chat")
    user_msg = st.text_input("Say something to your AI mentor:")
    if st.button("Send"):
        if user_msg.strip():
            save_chat(uid, "user", user_msg)
            reply = generate_ai_reply(user_msg)
            save_chat(uid, "ai", reply)
            st.success(f"AI: {reply}")

    st.subheader("💬 Chat History")
    for msg in get_chats(uid):
        st.write(f"**{msg['role']}**: {msg['text']}")
