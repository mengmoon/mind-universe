import streamlit as st
import firebase_admin
from firebase_admin import credentials, firestore
import requests
import json
from datetime import datetime
import time # Import for exponential backoff

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
# Configuration for the Gemini API
GEMINI_MODEL = "gemini-2.5-flash-preview-05-20"
GEMINI_BASE_URL = "https://generativelanguage.googleapis.com/v1beta/models"

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
# NOTE: The Firebase setup remains the same as it uses the service account key.
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
    except ValueError as e:
        st.error(f"Failed to initialize Firebase: {e}")
        st.stop()

db = firestore.client()
FIREBASE_API_KEY = st.secrets.get("FIREBASE_API_KEY")

# ----------------------
# Firebase Auth via REST API (No changes needed here)
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
# Firestore Functions (No changes needed here)
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
            # The Gemini API uses 'model' for the AI role, let's normalize to 'ai' for session state
            role = data.get("role", "")
            if role == 'model':
                role = 'ai'
            chats.append({"role": role, "content": data.get("text", "")})
        st.session_state.chat_messages = chats
    except Exception as e:
        st.error(f"Error fetching chats: {e}")

def save_chat(uid, role, text):
    """Saves a single chat message. We use 'model' for the AI role when saving to match Gemini API naming."""
    # When saving AI messages, we use 'model' to align with the Gemini response structure,
    # but we display it as 'ai' in the frontend.
    save_role = 'model' if role == 'ai' else role 
    try:
        db.collection("chats").add({
            "uid": uid,
            "role": save_role,
            "text": text,
            "timestamp": firestore.SERVER_TIMESTAMP
        })
    except Exception as e:
        st.error(f"Error saving chat message: {e}")

# ----------------------
# Gemini API Functions (UPDATED FIX)
# ----------------------
def generate_ai_reply(user_input, chat_history):
    """Generates an AI response using the Gemini REST API."""
    
    # Check for the key provided by the user in Streamlit secrets
    api_key = st.secrets.get("GEMINI_API_KEY")
    if not api_key:
        return "Gemini API key is missing. Please set 'GEMINI_API_KEY' in your Streamlit secrets."
    
    # Construct the API URL
    url = f"{GEMINI_BASE_URL}/{GEMINI_MODEL}:generateContent?key={api_key}"
    
    # Construct message list for context
    messages = []
    
    # 1. Add System Instruction
    messages.append({
        "role": "user", 
        "parts": [{"text": AI_SYSTEM_PROMPT}] # System instructions are usually added to the first user turn's parts
    })
    
    # 2. Add History
    for msg in chat_history:
        # The Gemini API expects roles to be 'user' and 'model'
        role = 'model' if msg['role'] == 'ai' else msg['role']
        
        # We only need the history up to the current user input
        if msg['role'] == 'user' and msg['content'] == user_input:
            continue
            
        messages.append({"role": role, "parts": [{"text": msg['content']}]})

    # 3. Add the current user input
    messages.append({"role": "user", "parts": [{"text": user_input}]})

    payload = {
        "contents": messages,
        # *** FIX APPLIED HERE: Changed 'config' to 'generationConfig' ***
        "generationConfig": {
            "temperature": 0.7,
            "maxOutputTokens": 500
        }
    }
    
    headers = {'Content-Type': 'application/json'}
    
    # Use exponential backoff for transient errors
    max_retries = 3
    
    for attempt in range(max_retries):
        try:
            with st.spinner(f"🧠 AI Mentor is reflecting... (Attempt {attempt + 1})"):
                response = requests.post(url, headers=headers, data=json.dumps(payload))
                response.raise_for_status() # Raise HTTPError for bad responses (4xx or 5xx)
                
                result = response.json()
                
                # Extract text from the response
                candidate = result.get('candidates', [{}])[0]
                text = candidate.get('content', {}).get('parts', [{}])[0].get('text')
                
                if text:
                    return text
                else:
                    # Handle cases where API returns status 200 but content is empty or blocked
                    safety_ratings = candidate.get('safetyRatings', 'N/A')
                    st.error(f"Gemini API returned no text. Safety Check: {safety_ratings}")
                    return "The AI mentor's response was filtered due to safety settings or was empty."

        except requests.exceptions.HTTPError as e:
            error_code = response.status_code
            error_data = {}
            try:
                error_data = response.json()
            except json.JSONDecodeError:
                pass
            
            error_message = error_data.get('error', {}).get('message', str(e))
            
            # Check for API-specific errors (e.g., rate limits, invalid key)
            if error_code == 400:
                if "API key not valid" in error_message or "API_KEY_INVALID" in error_message:
                    return "Authentication Error: Please check your 'GEMINI_API_KEY' in Streamlit secrets. It appears to be invalid."
                return f"Bad Request Error (400): {error_message}"
            
            elif error_code == 429:
                # Rate limit error
                if attempt < max_retries - 1:
                    wait_time = 2 ** attempt
                    time.sleep(wait_time)
                    continue # Retry
                return "Rate Limit Exceeded: AI is temporarily unavailable due to high usage. Please try again in a moment."
            
            # For other 4xx/5xx errors
            return f"Gemini API Error {error_code}: {error_message}"
            
        except requests.exceptions.RequestException as e:
            # Handle general request errors (network issues, DNS failure, etc.)
            return f"Network Error: Could not connect to Gemini API. Check your internet connection or URL. Details: {str(e)}"
        
        except Exception as e:
            # Catch other unexpected errors
            return f"An unexpected error occurred while generating the AI response: {str(e)}"

    # If all retries fail
    return "AI generation failed after multiple retries due to rate limiting or transient errors."


# ----------------------
# Authentication UI (No changes needed here)
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
# Main Application Flow (Minor adjustments for new role name)
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
                # Use 'assistant' for the AI role, which is mapped from 'ai'
                with st.chat_message(message["role"] if message["role"] == "user" else "assistant"):
                    st.write(message["content"])

        # Input for new message
        if user_input := st.chat_input("Ask your AI mentor..."):
            
            # 1. Append user message to state and save to Firestore
            st.session_state.chat_messages.append({"role": "user", "content": user_input})
            save_chat(uid, "user", user_input)

            # 2. Get AI reply
            # We pass the full history for context
            ai_reply = generate_ai_reply(user_input, st.session_state.chat_messages)
            
            # 3. Append AI message to state and save to Firestore
            if ai_reply:
                # Use 'ai' role for session state/display
                st.session_state.chat_messages.append({"role": "ai", "content": ai_reply})
                # Use 'ai' role for saving (it's mapped to 'model' inside save_chat)
                save_chat(uid, "ai", ai_reply) 
            
            # Rerun to update the chat history with the new messages
            st.rerun()
