import streamlit as st
import firebase_admin
from firebase_admin import credentials, firestore
import requests
import json
import os
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
    if "FIREBASE_CONFIG" in st.secrets:
        firebase_config = json.loads(st.secrets["FIREBASE_CONFIG"])
        cred = credentials.Certificate(firebase_config)
        firebase_admin.initialize_app(cred)
    elif os.path.exists("serviceAccountKey.json"):
        cred = credentials.Certificate("serviceAccountKey.json")
        firebase_admin.initialize_app(cred)
    else:
        st.error("❌ Firebase initialization failed: FIREBASE_CONFIG not set")
        st.stop()

db = firestore.client()

# ----------------------
# Firebase Auth (REST API)
# ----------------------
FIREBASE_API_KEY = st.secrets.get("FIREBASE_API_KEY", "")

def signup_user(email, password):
    if not FIREBASE_API_KEY:
        st.error("❌ Firebase API key not set")
        return None
    url = f"https://identitytoolkit.googleapis.com/v1/accounts:signUp?key={FIREBASE_API_KEY}"
    payload = {"email": email, "password": password, "returnSecureToken": True}
    try:
        res = requests.post(url, data=payload)
        if res.status_code == 200:
            return res.json()
        else:
            error = res.json().get("error", {})
            st.error(f"❌ Sign up failed: {error.get('message', 'Unknown error')}")
            return None
    except Exception as e:
        st.error(f"❌ Network error during sign up: {e}")
        return None

def login_user(email, password):
    if not FIREBASE_API_KEY:
        st.error("❌ Firebase API key not set")
        return None
    url = f"https://identitytoolkit.googleapis.com/v1/accounts:signInWithPassword?key={FIREBASE_API_KEY}"
    payload = {"email": email, "password": password, "returnSecureToken": True}
    try:
        res = requests.post(url, data=payload)
        if res.status_code == 200:
            return res.json()
        else:
            error = res.json().get("error", {})
            st.error(f"❌ Login failed: {error.get('message', 'Unknown error')}")
            return None
    except Exception as e:
        st.error(f"❌ Network error during login: {e}")
        return None

# ----------------------
# Journal Functions
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
        # Fetch without order_by to avoid index dependency
        docs = db.collection("journals").where("uid", "==", user_id).limit(10).stream()
        journals = []
        for d in docs:
            data = d.to_dict()
            timestamp = data.get("timestamp")
            journals.append({
                "text": data.get("text", "[No Text]"),
                "timestamp": timestamp
            })
        # Sort client-side by timestamp (descending)
        journals.sort(key=lambda x: x["timestamp"] or datetime.min if x["timestamp"] else datetime.min, reverse=True)
        # Format for display
        formatted_journals = []
        for entry in journals[:10]:  # Limit after sorting
            formatted_time = entry["timestamp"].to_datetime().strftime("%Y-%m-%d %H:%M:%S") if entry["timestamp"] else "Unknown time"
            formatted_journals.append({
                "text": entry["text"],
                "timestamp": formatted_time
            })
        return formatted_journals
    except Exception as e:
        st.warning(f"Could not fetch journals: {e}. If this persists, ensure Firestore indexes are set up in your Firebase console.")
        return []

# ----------------------
# Chat Functions
# ----------------------
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
        # Fetch without order_by to avoid index dependency
        docs = db.collection("chats").where("uid", "==", user_id).limit(20).stream()
        chats = []
        for d in docs:
            data = d.to_dict()
            timestamp = data.get("timestamp")
            chats.append({
                "role": data.get("role", "unknown"),
                "text": data.get("text", "[No Text]"),
                "timestamp": timestamp
            })
        # Sort client-side by timestamp (ascending)
        chats.sort(key=lambda x: x["timestamp"] or datetime.min if x["timestamp"] else datetime.min)
        # Format for display
        formatted_chats = []
        for msg in chats[:20]:  # Limit after sorting
            formatted_chats.append({
                "role": msg["role"],
                "text": msg["text"]
            })
        return formatted_chats
    except Exception as e:
        st.warning(f"Could not fetch chats: {e}. If this persists, ensure Firestore indexes are set up in your Firebase console.")
        return []

# ----------------------
# AI Reply (placeholder)
# ----------------------
def generate_ai_reply(user_message):
    return f"I hear you. You shared: '{user_message}'. You're not alone — keep reflecting."

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
        if len(journal_text) > 5000:
            st.warning("⚠️ Journal entry too long (max 5000 characters).")
        elif journal_text.strip():
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
        if len(user_msg) > 5000:
            st.warning("⚠️ Message too long (max 5000 characters).")
        elif user_msg.strip():
            save_chat(uid, "user", user_msg)
            ai_reply = generate_ai_reply(user_msg)
            save_chat(uid, "ai", ai_reply)
            st.success(f"AI: {ai_reply}")

    st.subheader("💬 Chat History")
    for msg in get_chats(uid):
        st.write(f"**{msg['role']}**: {msg['text']}")