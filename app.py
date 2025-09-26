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
# Session State
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
# Firebase Auth REST
# ----------------------
FIREBASE_API_KEY = st.secrets.get("FIREBASE_API_KEY", "")

def signup_user(email, password):
    if not FIREBASE_API_KEY:
        st.error("❌ Firebase API key not set")
        return None
    url = f"https://identitytoolkit.googleapis.com/v1/accounts:signUp?key={FIREBASE_API_KEY}"
    payload = {"email": email, "password": password, "returnSecureToken": True}
    try:
        res = requests.post(url, json=payload)
        if res.status_code == 200:
            return res.json()
        else:
            st.error(f"❌ Sign up failed: {res.json().get('error', {}).get('message', 'Unknown')}")
            return None
    except Exception as e:
        st.error(f"❌ Network error: {e}")
        return None

def login_user(email, password):
    if not FIREBASE_API_KEY:
        st.error("❌ Firebase API key not set")
        return None
    url = f"https://identitytoolkit.googleapis.com/v1/accounts:signInWithPassword?key={FIREBASE_API_KEY}"
    payload = {"email": email, "password": password, "returnSecureToken": True}
    try:
        res = requests.post(url, json=payload)
        if res.status_code == 200:
            return res.json()
        else:
            st.error(f"❌ Login failed: {res.json().get('error', {}).get('message', 'Unknown')}")
            return None
    except Exception as e:
        st.error(f"❌ Network error: {e}")
        return None

# ----------------------
# Firestore Functions
# ----------------------
def save_journal(user_id, text):
    try:
        print("Saving journal:", user_id, text)
        db.collection("journals").add({
            "uid": user_id,
            "text": text,
            "timestamp": firestore.SERVER_TIMESTAMP
        })
        st.success("✅ Journal saved")
    except Exception as e:
        st.error(f"Failed to save journal: {e}")

def get_journals(user_id):
    try:
        docs = db.collection("journals").where("uid", "==", user_id).limit(20).stream()
        journals = []
        for d in docs:
            data = d.to_dict()
            ts = data.get("timestamp")
            journals.append({
                "text": data.get("text", "[No Text]"),
                "timestamp": ts
            })
        # Sort descending
        journals.sort(key=lambda x: x["timestamp"] or datetime.min, reverse=True)
        formatted = []
        for j in journals[:10]:
            ts_str = j["timestamp"].strftime("%Y-%m-%d %H:%M:%S") if j["timestamp"] else "Unknown time"
            formatted.append({"text": j["text"], "timestamp": ts_str})
        return formatted
    except Exception as e:
        st.warning(f"Could not fetch journals: {e}")
        return []

def save_chat(user_id, role, text):
    try:
        print("Saving chat:", user_id, role, text)
        db.collection("chats").add({
            "uid": user_id,
            "role": role,
            "text": text,
            "timestamp": firestore.SERVER_TIMESTAMP
        })
    except Exception as e:
        st.error(f"Failed to save chat: {e}")

def get_chats(user_id):
    try:
        docs = db.collection("chats").where("uid", "==", user_id).limit(50).stream()
        chats = []
        for d in docs:
            data = d.to_dict()
            ts = data.get("timestamp")
            chats.append({
                "role": data.get("role", "unknown"),
                "text": data.get("text", "[No Text]"),
                "timestamp": ts
            })
        # Sort ascending
        chats.sort(key=lambda x: x["timestamp"] or datetime.min)
        formatted = []
        for c in chats[:20]:
            ts_str = c["timestamp"].strftime("%Y-%m-%d %H:%M:%S") if c["timestamp"] else "Unknown time"
            formatted.append({
                "role": c["role"],
                "text": c["text"],
                "timestamp": ts_str
            })
        return formatted
    except Exception as e:
        st.warning(f"Could not fetch chats: {e}")
        return []

# ----------------------
# AI Mentor Voices
# ----------------------
def freud_voice(msg):
    return f"Freud: This may reflect unconscious conflicts. What hidden feelings could be influencing you?"

def adler_voice(msg):
    return f"Adler: Consider how this relates to your sense of purpose and striving for significance."

def jung_voice(msg):
    return f"Jung: Perhaps this is connected to archetypes or your personal shadow. Reflect on your inner patterns."

def positive_psych_voice(msg):
    return f"Positive Psychology: Focus on your strengths and what went well today. You have the ability to grow."

def cbt_voice(msg):
    return f"CBT: Let's examine any distorted thoughts here. What evidence supports or contradicts this belief?"

def maslow_voice(msg):
    return f"Maslow: Consider your current needs hierarchy. Are you addressing basic, psychological, or self-actualization needs?"

def generate_ai_reply(user_message):
    replies = [
        freud_voice(user_message),
        adler_voice(user_message),
        jung_voice(user_message),
        positive_psych_voice(user_message),
        cbt_voice(user_message),
        maslow_voice(user_message)
    ]
    return "\n\n".join(replies)

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
# Main App
# ----------------------
if st.session_state.user:
    uid = st.session_state.user["localId"]

    # --- Journal ---
    st.subheader("📝 Journal")
    with st.form("journal_form"):
        journal_text = st.text_area("Write your thoughts here...")
        submitted = st.form_submit_button("Save Journal")
        if submitted:
            if len(journal_text) > 5000:
                st.warning("⚠️ Journal too long (max 5000 chars).")
            elif journal_text.strip():
                save_journal(uid, journal_text)
            else:
                st.warning("⚠️ Please write something before saving.")

    st.subheader("📜 Journal History")
    for entry in get_journals(uid):
        st.markdown(f"- **{entry['timestamp']}**: {entry['text']}")

    # --- AI Mentor Chat ---
    st.subheader("🤖 AI Mentor Chat (Freud, Adler, Jung, Positive Psychology, CBT, Maslow)")
    with st.form("chat_form", clear_on_submit=True):
        user_msg = st.text_input("Say something to your AI mentor:")
        submitted_chat = st.form_submit_button("Send")
        if submitted_chat:
            if len(user_msg) > 5000:
                st.warning("⚠️ Message too long (max 5000 chars).")
            elif user_msg.strip():
                save_chat(uid, "user", user_msg)
                ai_reply = generate_ai_reply(user_msg)
                save_chat(uid, "ai", ai_reply)
                st.text_area("AI Mentor Replies:", value=ai_reply, height=250)

    st.subheader("💬 Chat History")
    for msg in get_chats(uid):
        st.write(f"**{msg['role']}**: {msg['text']}")
