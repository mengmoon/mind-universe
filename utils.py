import streamlit as st
import firebase_admin
from firebase_admin import credentials, firestore
import requests
import json

# ----------------------
# Firebase Initialization
# ----------------------
if not firebase_admin._apps:
    if "FIREBASE_CONFIG" in st.secrets:
        firebase_config = json.loads(st.secrets["FIREBASE_CONFIG"])
        cred = credentials.Certificate(firebase_config)
        firebase_admin.initialize_app(cred)
    else:
        raise ValueError("❌ Firebase initialization failed: FIREBASE_CONFIG not set")

db = firestore.client()

# ----------------------
# Firebase Auth (via REST API)
# ----------------------
FIREBASE_API_KEY = st.secrets.get("FIREBASE_API_KEY")


def signup_user(email, password):
    """Register a new user in Firebase Auth"""
    url = f"https://identitytoolkit.googleapis.com/v1/accounts:signUp?key={FIREBASE_API_KEY}"
    payload = {"email": email, "password": password, "returnSecureToken": True}
    res = requests.post(url, data=payload)
    if res.status_code == 200:
        return res.json()
    return None


def login_user(email, password):
    """Login existing user with Firebase Auth"""
    url = f"https://identitytoolkit.googleapis.com/v1/accounts:signInWithPassword?key={FIREBASE_API_KEY}"
    payload = {"email": email, "password": password, "returnSecureToken": True}
    res = requests.post(url, data=payload)
    if res.status_code == 200:
        return res.json()
    return None


# ----------------------
# Journal Functions
# ----------------------
def save_journal(user_id, text):
    """Save a journal entry to Firestore"""
    db.collection("journals").add({
        "uid": user_id,
        "text": text,
        "timestamp": firestore.SERVER_TIMESTAMP,
    })


def get_journals(user_id):
    """Retrieve last 10 journal entries for a user"""
    docs = (
        db.collection("journals")
        .where("uid", "==", user_id)
        .order_by("timestamp", direction=firestore.Query.DESCENDING)
        .limit(10)
        .stream()
    )
    return [{"text": d.to_dict()["text"], "timestamp": d.to_dict().get("timestamp")} for d in docs]


# ----------------------
# Chat Functions
# ----------------------
def save_chat(user_id, role, text):
    """Save a chat message to Firestore"""
    db.collection("chats").add({
        "uid": user_id,
        "role": role,
        "text": text,
        "timestamp": firestore.SERVER_TIMESTAMP,
    })


def get_chats(user_id):
    """Retrieve last 20 chat messages for a user"""
    docs = (
        db.collection("chats")
        .where("uid", "==", user_id)
        .order_by("timestamp", direction=firestore.Query.ASCENDING)
        .limit(20)
        .stream()
    )
    return [{"role": d.to_dict()["role"], "text": d.to_dict()["text"]} for d in docs]


# ----------------------
# AI Reply (placeholder)
# ----------------------
def generate_ai_reply(user_message):
    """Generate an AI reply (placeholder for OpenAI integration)"""
    return f"I hear you. It sounds important that you shared: '{user_message}'. You're not alone — keep reflecting, and we'll explore this together."
