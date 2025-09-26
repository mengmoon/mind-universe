import streamlit as st
import firebase_admin
from firebase_admin import credentials, firestore
import json
import requests

# --------------------------
# Firebase Initialization
# --------------------------
if not firebase_admin._apps:
    if "FIREBASE_CONFIG" in st.secrets:
        firebase_config = json.loads(st.secrets["FIREBASE_CONFIG"])
        cred = credentials.Certificate(firebase_config)
        firebase_admin.initialize_app(cred)
    else:
        raise ValueError("❌ FIREBASE_CONFIG missing in Streamlit secrets")

db = firestore.client()

# Firebase API key (for REST auth)
FIREBASE_API_KEY = st.secrets["FIREBASE_API_KEY"]

# OpenAI API key
OPENAI_API_KEY = st.secrets["OPENAI_API_KEY"]


# --------------------------
# Firestore Helpers
# --------------------------
def add_user(uid: str, user_data: dict):
    """Add or update user profile in Firestore."""
    try:
        db.collection("users").document(uid).set(user_data, merge=True)
        return True
    except Exception as e:
        st.error(f"Error adding user: {e}")
        return False


def get_user(uid: str):
    """Fetch a user profile by UID."""
    try:
        doc = db.collection("users").document(uid).get()
        if doc.exists:
            return doc.to_dict()
        return None
    except Exception as e:
        st.error(f"Error getting user: {e}")
        return None


def save_journal(uid: str, journal_data: dict):
    """Save a journal entry for a user."""
    try:
        db.collection("users").document(uid).collection("journals").add(journal_data)
        return True
    except Exception as e:
        st.error(f"Error saving journal: {e}")
        return False


def get_journals(uid: str):
    """Fetch all journal entries for a user."""
    try:
        docs = db.collection("users").document(uid).collection("journals").stream()
        return [doc.to_dict() | {"id": doc.id} for doc in docs]
    except Exception as e:
        st.error(f"Error getting journals: {e}")
        return []


# --------------------------
# Firebase Auth via REST API
# --------------------------
def signup_user(email: str, password: str):
    """Sign up a new user with email + password (Firebase Auth REST)."""
    url = f"https://identitytoolkit.googleapis.com/v1/accounts:signUp?key={FIREBASE_API_KEY}"
    payload = {"email": email, "password": password, "returnSecureToken": True}
    res = requests.post(url, data=payload)
    if res.status_code == 200:
        return res.json()
    else:
        st.error(res.json().get("error", {}).get("message", "Signup failed"))
        return None


def login_user(email: str, password: str):
    """Log in a user with email + password (Firebase Auth REST)."""
    url = f"https://identitytoolkit.googleapis.com/v1/accounts:signInWithPassword?key={FIREBASE_API_KEY}"
    payload = {"email": email, "password": password, "returnSecureToken": True}
    res = requests.post(url, data=payload)
    if res.status_code == 200:
        return res.json()
    else:
        st.error(res.json().get("error", {}).get("message", "Login failed"))
        return None


def verify_id_token(id_token: str):
    """Verify Firebase ID token via REST API."""
    url = f"https://identitytoolkit.googleapis.com/v1/accounts:lookup?key={FIREBASE_API_KEY}"
    payload = {"idToken": id_token}
    res = requests.post(url, data=payload)
    if res.status_code == 200:
        return res.json()
    else:
        st.error(res.json().get("error", {}).get("message", "Token verification failed"))
        return None
