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
st.subheader("Explore your inner world with AI mentors.")

# ----------------------
# Constants and Initial State
# ----------------------
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

# Initialize session state for user and chat messages
if "user" not in st.session_state:
    st.session_state.user = None
if "chat_messages" not in st.session_state:
    st.session_state.chat_messages = []
if "journals" not in st.session_state:
    st.session_state.journals = []

# ----------------------
# Firebase Initialization
# ----------------------
try:
    firebase_config = json.loads(st.secrets["FIREBASE_CONFIG"])
except KeyError as e:
    st.error(f"Missing secret key: {e}. Please ensure FIREBASE_CONFIG is set in your Streamlit secrets.")
    st.stop()
except json.JSONDecodeError as e:
    st.error(f"Failed to parse FIREBASE_CONFIG as JSON: {e}")
    st.stop()

if not firebase_admin._apps:
    try:
        # Replace escaped newlines for certificate private key
        if "private_key" in firebase_config:
            firebase_config["private_key"] = firebase_config["private_key"].replace("\\n", "\n")
        cred = credentials.Certificate(firebase_config)
        firebase_admin.initialize_app(cred)
        # st.success("Firebase Admin SDK Initialized") # Commented out for cleaner UI
    except ValueError as e:
        st.error(f"Failed to initialize Firebase: {e}")
        st.stop()

db = firestore.client()
FIREBASE_API_KEY = st.secrets.get("FIREBASE_API_KEY")

# ----------------------
# Firebase Auth via REST API
# ----------------------
@st.cache_resource
def get_auth_url(endpoint):
    return f"https://identitytoolkit.googleapis.com/v1/accounts:{endpoint}?key={FIREBASE_API_KEY}"

def authenticate_user(email, password, mode):
    """Handles both sign up and login."""
    endpoint = "signUp" if mode == "Sign Up" else "signInWithPassword"
    url = get_auth_url(endpoint)
    payload = {"email": email, "password": password, "returnSecureToken": True}
    
    try:
        res = requests.post(url, json=payload)
        res.raise_for_status() # Raise HTTPError for bad responses (4xx or 5xx)
        return res.json(), None
    except requests.exceptions.HTTPError as e:
        try:
            error = res.json().get("error", {}).get("message", "Unknown error")
        except json.JSONDecodeError:
            error = f"Server returned status code {res.status_code}"
        return None, error
    except Exception as e:
        return None, f"Network/Request error: {e}"

# ----------------------
# Firestore Functions
# ----------------------
def fetch_journals(uid):
    """Fetches all journal entries for the user."""
    try:
        docs = db.collection("journals").where("uid", "==", uid).order_by("timestamp", direction=firestore.Query.DESCENDING).stream()
        journals = []
        for d in docs:
            data = d.to_dict()
            ts = data.get("timestamp")
            if ts:
                # Firestore Timestamp to string format
                formatted_ts = ts.strftime("%Y-%m-%d %H:%M:%S")
            else:
                formatted_ts = "Unknown"
            journals.append({"text": data.get("text", ""), "timestamp": formatted_ts})
        st.session_state.journals = journals
    except Exception as e:
        st.error(f"Error fetching journals: {e}")

def save_journal(uid, text):
    """Saves a new journal entry."""
    try:
        db.collection("journals").add({
            "uid": uid,
            "text": text,
            "timestamp": firestore.SERVER_TIMESTAMP
        })
        st.toast("Journal saved successfully!", icon="✅")
        # Re-fetch journals to update the history instantly (without full rerun)
        fetch_journals(uid)
    except Exception as e:
        st.error(f"Error saving journal: {e}")

def fetch_chats(uid):
    """Fetches all chat history for the user and loads it into session state."""
    try:
        docs = db.collection("chats").where("uid", "==", uid).order_by("timestamp").stream()
        chats = []
        for d in docs:
            data = d.to_dict()
            chats.append({"role": data.get("role", ""), "content": data.get("text", "")})
        st.session_state.chat_messages = chats
    except Exception as e:
        st.error(f"Error fetching chats: {e}")

def save_chat(uid, role, text):
    """Saves a single chat message."""
    try:
        db.collection("chats").add({
            "uid": uid,
            "role": role,
            "text": text,
            "timestamp": firestore.SERVER_TIMESTAMP
        })
    except Exception as e:
        st.error(f"Error saving chat message: {e}")

# ----------------------
# OpenAI GPT Functions
# ----------------------
def generate_ai_reply(user_input, chat_history):
    """Generates an AI response using the current chat context."""
    if not st.secrets.get("OPENAI_API_KEY"):
        return "OpenAI API key is missing. Please set it in your Streamlit secrets."
        
    openai.api_key = st.secrets["OPENAI_API_KEY"]
    
    # Construct message list for context, including the system prompt
    messages = [{"role": "system", "content": AI_SYSTEM_PROMPT}]
    # Add history, mapping our session state to the API format
    for msg in chat_history:
        # Skip the latest user message which is already included in `user_input` flow
        if msg['role'] == 'user' and msg['content'] == user_input:
            continue
        messages.append({"role": msg['role'], "content": msg['content']})

    # Add the current user input
    messages.append({"role": "user", "content": user_input})
    
    try:
        with st.spinner("🧠 AI Mentor is reflecting..."):
            response = openai.chat.completions.create(
                model="gpt-3.5-turbo",
                messages=messages,
                temperature=0.7,
                max_tokens=1,
            )
        return response.choices[0].message.content.strip()
    except openai.APIError as e:
        error_message = str(e)
        
        # 1. Check for Quota Error (429 - insufficient_quota)
        if "insufficient_quota" in error_message or "exceeded your current quota" in error_message:
            return "Quota Error: Your OpenAI API key has run out of credits. Please update your billing details on the OpenAI platform to continue using the AI mentor."
        
        # 2. Check for Authentication Errors (401)
        if "Invalid API key" in error_message or "Unauthorized" in error_message:
            return "Authentication Error: Please check your OpenAI API key in Streamlit secrets."
            
        # 3. Check for general Rate Limit (429)
        if "Rate limit" in error_message:
            return "AI is temporarily unavailable due to high usage. Please try again in a moment."
            
        # 4. Default for other API errors
        return f"OpenAI API Error: {error_message}"
        
    except Exception as e:
        return f"AI failed due to an unexpected non-API error: {str(e)}"

# ----------------------
# Authentication UI
# ----------------------
def authentication_ui():
    """Displays the login/signup form."""
    st.subheader("🔐 Login / Sign Up")
    auth_mode = st.radio("Select Action:", ["Login", "Sign Up"], key="auth_mode_radio")

    with st.form("auth_form"):
        email = st.text_input("Email", key="auth_email")
        password = st.text_input("Password", type="password", key="auth_password")
        submitted = st.form_submit_button(auth_mode)
        
        if submitted:
            if not email or not password:
                st.error("Please enter both email and password.")
                return

            user, error = authenticate_user(email, password, auth_mode)

            if error:
                st.error(f"{auth_mode} failed: {error}")
            elif user:
                st.session_state.user = user
                st.success(f"Successfully logged in as {email}")
                # Fetch data immediately after successful login
                fetch_journals(user["localId"])
                fetch_chats(user["localId"])
                st.rerun() # Use rerun only here to force UI refresh post-login

# ----------------------
# Main Application Flow
# ----------------------

if st.session_state.user is None:
    authentication_ui()
else:
    # User is logged in
    uid = st.session_state.user["localId"]
    st.sidebar.markdown(f"**Logged in as:** {st.session_state.user['email']}")
    
    if st.sidebar.button("Logout"):
        st.session_state.user = None
        st.session_state.chat_messages = []
        st.session_state.journals = []
        st.success("Logged out")
        st.rerun()

    # --- Main Tabs ---
    tab_journal, tab_chat = st.tabs(["📝 Journaling", "🤖 AI Mentor"])

    with tab_journal:
        st.subheader("Write Your Daily Reflections")
        journal_text = st.text_area("What's on your mind today?", key="current_journal_text", height=150)
        
        # Use a form to prevent input reset on button press
        with st.form("journal_form", clear_on_submit=True):
            save_button = st.form_submit_button("Save Journal Entry")
            if save_button and journal_text.strip():
                save_journal(uid, journal_text)
            elif save_button:
                st.warning("Please write something before saving.")

        st.subheader("Journal History")
        if not st.session_state.journals:
            st.info("No journal entries yet. Start writing!")
            # Re-fetch in case state was cleared but data exists
            fetch_journals(uid) 
            
        for entry in st.session_state.journals:
            with st.expander(f"**{entry['timestamp']}**"):
                st.write(entry['text'])

    with tab_chat:
        st.subheader("Converse with Your AI Mentor")

        # Display Chat History
        chat_placeholder = st.container()
        with chat_placeholder:
            if not st.session_state.chat_messages:
                st.info("Start a conversation with your AI mentor! Try asking them to adopt a specific voice, like 'Speak to me as Freud.'")
                # Re-fetch in case state was cleared but data exists
                fetch_chats(uid) 

            for message in st.session_state.chat_messages:
                # Use 'assistant' for the AI role
                with st.chat_message(message["role"] if message["role"] == "user" else "assistant"):
                    st.write(message["content"])

        # Input for new message
        if user_input := st.chat_input("Ask your AI mentor..."):
            
            # 1. Append user message to state and save to Firestore
            st.session_state.chat_messages.append({"role": "user", "content": user_input})
            save_chat(uid, "user", user_input)

            # 2. Get AI reply
            ai_reply = generate_ai_reply(user_input, st.session_state.chat_messages)
            
            # 3. Append AI message to state and save to Firestore
            if ai_reply:
                st.session_state.chat_messages.append({"role": "ai", "content": ai_reply})
                save_chat(uid, "ai", ai_reply)
            
            # Rerun to update the chat history with the new messages
            st.rerun()
