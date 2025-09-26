import streamlit as st
import firebase_admin
from firebase_admin import credentials, firestore
import requests
import json
import os

# ----------------------
# Page Config
# ----------------------
st.set_page_config(page_title="Mind Universe", page_icon="🧠", layout="wide")
st.title("🌌 Mind Universe")
st.write("Explore your inner world with AI mentors.")

# ----------------------
# Firebase Initialization
# ----------------------
if not firebase_admin._apps:
    try:
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
    except Exception as e:
        st.error(f"Firebase initialization error: {e}")
        st.stop()

db = firestore.client()

# ----------------------
# Firebase Auth (REST API)
# ----------------------
FIREBASE_API_KEY = st.secrets.get("FIREBASE_API_KEY")

def signup_user(email, password):
    url = f"https://identitytoolkit.googleapis.com/v1/accounts:signUp?key={FIREBASE_API_KEY}"
    payload = {"email": email, "password": password, "returnSecureToken": True}
    res = requests.post(url, data=payload)
    return res.json() if res.status_code == 200 else None

def login_user(email, password):
    url = f"https://identitytoolkit.googleapis.com/v1/accounts:signInWithPassword?key={FIREBASE_API_KEY}"
    payload = {"email": email, "password": password, "returnSecureToken": True}
    res = requests.post(url, data=payload)
    return res.json() if res.status_code == 200 else None

# ----------------------
# Journal Functions
# ----------------------
def save_journal(user_id, text):
    db.collection("journals").add({
        "uid": user_id,
        "text": text,
        "timestamp": firestore.SERVER_TIMESTAMP,
    })

def get_journals(user_id):
    try:
        docs = db.collection("journals").where("uid", "==", user_id)\
            .order_by("timestamp", direction=firestore.Query.DESCENDING).limit(10).stream()
        return [{"text": d.to_dict()["text"], "timestamp": d.to_dict().get("timestamp")} for d in docs]
    except Exception as e:
        st.error(f"Failed to fetch journals: {e}")
        return []

# ----------------------
# Chat Functions
# ----------------------
def save_chat(user_id, role, text):
    db.collection("chats").add({
        "uid": user_id,
        "role": role,
        "text": text,
        "timestamp": firestore.SERVER_TIMESTAMP,
    })

def get_chats(user_id):
    try:
        docs = db.collection("chats").where("uid", "==", user_id)\
            .order_by("timestamp", direction=firestore.Query.ASCENDING).limit(20).stream()
        return [{"role": d.to_dict()["role"], "text": d.to_dict()["text"]} for d in docs]
    except Exception as e:
        st.error(f"Failed to fetch chats: {e}")
        return []

# ----------------------
# AI Reply (placeholder)
# ----------------------
def generate_ai_reply(user_message):
    return f"I hear you. You shared: '{user_message}'. You're not alone — keep reflecting, and we'll explore this together."

# ----------------------
# Authentication UI
# ----------------------
st.subheader("🔐 Login / Sign Up")
auth_mode = st.radio("Select Action:", ["Login", "Sign Up"])

email = st.text_input("Email")
password = st.text_input("Password", type="password")

user = None
if st.button("Submit"):
    if auth_mode == "Sign Up":
        user = signup_user(email, password)
        if user:
            st.success(f"✅ Signed up as {email}")
        else:
            st.error("❌ Sign up failed")
    else:
        user = login_user(email, password)
        if user:
            st.success(f"✅ Logged in as {email}")
        else:
            st.error("❌ Login failed")

if user:
    uid = user["localId"]

    # ----------------------
    # Journal UI
    # ----------------------
    st.subheader("📝 Journal")
    journal_text = st.text_area("Write your thoughts here...")

    if st.button("Save Journal"):
        if journal_text.strip():
            save_journal(uid, journal_text)
            st.success("✅ Journal entry saved")
        else:
            st.warning("⚠️ Please write something before saving.")

    st.subheader("📜 Journal History")
    for entry in get_journals(uid):
        ts = entry["timestamp"].isoformat() if entry["timestamp"] else "Unknown time"
        st.write(f"- {ts}: {entry['text']}")

    # ----------------------
    # Chat UI
    # ----------------------
    st.subheader("🤖 AI Mentor Chat")
    user_msg = st.text_input("Say something to your AI mentor:")

    if st.button("Send"):
        if user_msg.strip():
            save_chat(uid, "user", user_msg)
            ai_reply = generate_ai_reply(user_msg)
            save_chat(uid, "ai", ai_reply)
            st.success(f"AI: {ai_reply}")
        else:
            st.warning("⚠️ Type a message before sending.")

    st.subheader("💬 Chat History")
    for msg in get_chats(uid):
        st.write(f"**{msg['role']}**: {msg['text']}")
