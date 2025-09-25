import streamlit as st
import firebase_admin
from firebase_admin import auth
from utils import init_firebase
from analyzer import analyze_journal
from chat import psychodynamic_chat
import requests
import json
from datetime import datetime

st.set_page_config(page_title="Mind Universe", page_icon="🌌")

# Initialize Firebase
try:
    db, auth = init_firebase()
except ValueError as e:
    st.error(f"Firebase initialization failed: {e}")
    st.stop()

# Firebase Auth REST API endpoint
API_KEY = "your-correct-api-key-here"  # Replace with your actual apiKey
SIGN_IN_URL = f"https://identitytoolkit.googleapis.com/v1/accounts:signInWithPassword?key={API_KEY}"
SIGN_UP_URL = f"https://identitytoolkit.googleapis.com/v1/accounts:signUp?key={API_KEY}"

st.sidebar.title("Mind Universe")
menu = st.sidebar.radio("Navigate", ["Login", "Journal", "Chat"])

if menu == "Login":
    st.header("Welcome to Mind Universe 🌌")
    email = st.text_input("Email")
    password = st.text_input("Password", type="password")
    if st.button("Login"):
        try:
            response = requests.post(SIGN_IN_URL, json={
                "email": email,
                "password": password,
                "returnSecureToken": True
            })
            response.raise_for_status()
            user = response.json()
            st.success("Logged in!")
            st.session_state['user'] = user
        except requests.exceptions.RequestException as e:
            st.error(f"Login failed: {e}")
            st.write("Error details:", response.json())  # Show API error
    if st.button("Sign Up"):
        try:
            user = auth.create_user(email=email, password=password)
            st.success("Signed up!")
            st.session_state['user'] = {'localId': user.uid, 'email': email}
        except Exception as e:
            st.error(f"Sign up failed: {e}")

if menu == "Journal":
    st.header("Journal Your Thoughts")
    if 'user' not in st.session_state:
        st.warning("Please log in first.")
    else:
        entry = st.text_area("What's on your mind?")
        if st.button("Analyze"):
            analysis = analyze_journal(entry)
            # Save to Firestore
            user_id = st.session_state['user']['localId']
            journal_data = {
                'entry': entry,
                'analysis': analysis,
                'timestamp': datetime.now().isoformat()
            }
            db.collection('users').document(user_id).collection('journal').add(journal_data)
            st.write(analysis)
            st.success("Journal saved!")

if menu == "Chat":
    st.header("Talk to Mind Universe")
    if 'user' not in st.session_state:
        st.warning("Please log in first.")
    else:
        user_input = st.text_input("How can I help you?")
        if st.button("Send"):
            response = psychodynamic_chat(user_input)
            # Save to Firestore
            user_id = st.session_state['user']['localId']
            chat_data = {
                'input': user_input,
                'response': response,
                'timestamp': datetime.now().isoformat()
            }
            db.collection('users').document(user_id).collection('chat').add(chat_data)
            st.write(response)