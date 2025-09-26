import streamlit as st
import firebase_admin
from firebase_admin import credentials, firestore
import requests
import json

# ----------------------
# Firebase Initialization
# ----------------------
if not firebase_admin._apps:
    if "firebase_service_account" in st.secrets:
        cred = credentials.Certificate(dict(st.secrets["firebase_service_account"]))
        firebase_admin.initialize_app(cred)
    else:
        raise ValueError("❌ Firebase initialization failed: firebase_service_account not set in secrets.toml")

db = firestore.client()

# ----------------------
# Firebase Auth (via REST API)
# ----------------------
FIREBASE_API_KEY = st.secrets["firebase"]["api_key"]

def firebase_sign_up(email, password):
    url = f"https://identitytoolkit.googleapis.com/v1/accounts:signUp?key={FIREBASE_API_KEY}"
    payload = {"email": email, "password": password, "returnSecureToken": True}
    res = requests.post(url, json=payload)
    return res.json() if res.status_code == 200 else None

def firebase_sign_in(email, password):
    url = f"https://identitytoolkit.googleapis.com/v1/accounts:signInWithPassword?key={FIREBASE_API_KEY}"
    payload = {"email": email, "password": password, "returnSecureToken": True}
    res = requests.post(url, json=payload)
    return res.json() if res.status_code == 200 else None

# ----------------------
# Journal Functions
# ----------------------
def save_journal_entry(user_id, text):
    db.collection("journals").add({
        "uid": user_id,
        "text": text,
        "timestamp": firestore.SERVER_TIMESTAMP,
    })

def get_journal_history(user_id):
    docs = (
        db.collection("journals")
        .where("uid", "==", user_id)
        .order_by("timestamp", direction=firestore.Query.DESCENDING)
        .limit(10)
        .stream()
    )
    return [
        {"text": d.to_dict()["text"], "timestamp": d.to_dict().get("timestamp")}
        for d in docs
    ]

# ----------------------
# Chat Functions
# ----------------------
def save_chat_message(user_id, role, text):
    db.collection("chats").add({
        "uid": user_id,
        "role": role,
        "text": text,
        "timestamp": firestore.SERVER_TIMESTAMP,
    })

def get_chat_history(user_id):
    docs = (
        db.collection("chats")
        .where("uid", "==", user_id)
        .order_by("timestamp", direction=firestore.Query.ASCENDING)
        .limit(20)
        .stream()
    )
    return [
        {"role": d.to_dict()["role"], "text": d.to_dict()["text"]}
        for d in docs
    ]

# ----------------------
# AI Reply (placeholder)
# ----------------------
def generate_ai_reply(user_message):
    # ✅ For now just return a supportive response
    return f"I hear you. It sounds important that you shared: '{user_message}'. You're not alone — keep reflecting, and we'll explore this together."
