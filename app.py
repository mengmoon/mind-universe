# --- Mind Universe: A Digital Space for Mental Wellness and Self-Exploration ---
# Uses Streamlit for the UI, Firebase for secure data persistence, and
# Google Gemini API for AI chat (text only) and Journal Analysis/Prompts.

import streamlit as st
import requests
import json
import pandas as pd
from datetime import datetime
import hashlib
import time

# --- Streamlit Page Configuration ---
# Must be the first Streamlit command
st.set_page_config(
    page_title="Mind Universe",
    page_icon="🌌",
    layout="wide",
    initial_sidebar_state="expanded"
)

# --- Custom CSS for Styling ---
def inject_custom_css():
    """Injects custom CSS for theme, fonts, and layout enhancements."""
    st.markdown("""
        <style>
        /* General Theme & Typography */
        @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;600;700&display=swap');
        
        html, body, [class*="stApp"] {
            font-family: 'Inter', sans-serif;
            color: #333333; /* Darker text for readability */
        }
        
        /* Subtle Background Gradient for a "Universe" feel */
        .stApp {
            background-color: #F8F9FA; /* Light gray base */
            background-image: linear-gradient(135deg, #F8F9FA 0%, #E9ECEF 100%);
        }

        /* Titles and Headers */
        h1 {
            color: #4A90E2; /* Primary blue for key titles */
            font-weight: 700;
        }
        h2, h3 {
            color: #3C6382;
        }

        /* Sidebar Styling */
        .st-emotion-cache-1cypcdb { /* Targets the sidebar content container */
            background-color: #FFFFFF;
            border-right: 1px solid #DEE2E6;
        }
        
        /* Goal List Styling */
        .goal-item {
            padding: 8px;
            margin-bottom: 5px;
            border-radius: 8px;
            display: flex;
            align-items: center;
            border: 1px solid #E9ECEF;
            transition: all 0.2s ease;
        }
        .goal-item:hover {
            background-color: #F8F9FA;
            border-color: #DDEBF0;
        }
        .goal-completed {
            background-color: #E6F7E6; /* Light green for completed */
            color: #28A745;
            opacity: 0.8;
        }

        /* Center Content on Auth Page (using columns and margin) */
        .auth-container {
            max-width: 400px;
            margin: 50px auto;
            padding: 20px;
            background: white;
            border-radius: 12px;
            box-shadow: 0 4px 12px rgba(0,0,0,0.1);
        }

        /* Chat/Message Box Styling */
        .stChatMessage {
            border-radius: 12px;
            padding: 10px;
            margin: 5px 0;
            box-shadow: 0 1px 3px rgba(0,0,0,0.05);
        }
        
        /* Buttons */
        .stButton>button {
            border-radius: 8px;
            font-weight: 600;
        }
        </style>
        """, unsafe_allow_html=True)

# Call the CSS injector early
inject_custom_css()

# --- 1. Global Configuration and Secrets Loading ---
try:
    firebase_config_str = st.secrets["FIREBASE_CONFIG"]
    if isinstance(firebase_config_str, str):
        # Fix escaped newlines and clean up string format
        firebase_config_str = firebase_config_str.replace('\\\\n', '\\n').strip().strip('"').strip("'")
    firebaseConfig = json.loads(firebase_config_str)
except Exception as e:
    st.error(f"Failed to parse FIREBASE_CONFIG: {e}")
    st.stop()

GEMINI_API_KEY = st.secrets.get("GEMINI_API_KEY", "")
if not GEMINI_API_KEY:
    st.error("GEMINI_API_KEY not found in Streamlit secrets.")
    st.stop()

# --- 2. Firebase Initialization ---
@st.cache_resource
def initialize_firebase(config):
    """Initializes and returns the Firebase firestore client."""
    import firebase_admin
    from firebase_admin import credentials, firestore
    try:
        # Create service account credentials dictionary
        service_account_info = {
            "type": config["type"],
            "project_id": config["project_id"],
            "private_key_id": config["private_key_id"],
            "private_key": config["private_key"],
            "client_email": config["client_email"],
            "client_id": config["client_id"],
            "auth_uri": config["auth_uri"],
            "token_uri": config["token_uri"],
            "auth_provider_x509_cert_url": config["auth_provider_x509_cert_url"],
            "client_x509_cert_url": config["client_x509_cert_url"],
            "universe_domain": config["universe_domain"],
        }
        if not firebase_admin._apps:
            cred = credentials.Certificate(service_account_info)
            firebase_admin.initialize_app(cred)
        return firestore.client()
    except Exception as e:
        st.error(f"Failed to initialize Firebase: {e}")
        st.stop()

db = initialize_firebase(firebaseConfig)

# --- 3. Authentication & State Management ---
# Initialize all necessary session states
if 'logged_in' not in st.session_state:
    st.session_state.logged_in = False
if 'current_user_email' not in st.session_state:
    st.session_state.current_user_email = None
if 'user_data_loaded' not in st.session_state:
    st.session_state.user_data_loaded = False
if 'current_tab' not in st.session_state:
    st.session_state.current_tab = "💬 AI Mentor"
if 'chat_history' not in st.session_state:
    st.session_state.chat_history = []
if 'journal_entries' not in st.session_state:
    st.session_state.journal_entries = []
if 'goals' not in st.session_state:
    st.session_state.goals = []
if 'daily_prompt' not in st.session_state:
    st.session_state.daily_prompt = None
if 'mentor_persona' not in st.session_state:
    st.session_state.mentor_persona = "Default"
if 'confirm_delete' not in st.session_state:
    st.session_state.confirm_delete = False
if 'overall_insights_text' not in st.session_state:
    st.session_state.overall_insights_text = None

def hash_password(password):
    """Simple password hashing simulation using SHA-256."""
    return hashlib.sha256(password.encode()).hexdigest()

def get_users_collection_ref():
    """Returns the Firestore reference for the global users collection."""
    app_id = firebaseConfig["project_id"]
    return db.collection('artifacts').document(app_id).collection('public').document('data').collection('users')

def login_user(email, password):
    """Attempts to log in a user by checking credentials against Firestore."""
    try:
        user_doc_ref = get_users_collection_ref().document(email.lower())
        user_doc = user_doc_ref.get()
        if user_doc.exists:
            user_data = user_doc.to_dict()
            if user_data.get('password_hash') == hash_password(password):
                st.session_state.logged_in = True
                st.session_state.current_user_email = email.lower()
                st.session_state.user_data_loaded = False
                st.success("Login successful!")
                return True
            else:
                st.error("Invalid email or password.")
                return False
        else:
            st.error("User not found. Please sign up.")
            return False
    except Exception as e:
        st.error(f"Login error: {e}")
        return False

def sign_up(email, password):
    """Registers a new user in Firestore."""
    try:
        user_doc_ref = get_users_collection_ref().document(email.lower())
        if user_doc_ref.get().exists:
            st.error("Email already registered. Please log in.")
            return False
        if len(password) < 6:
            st.error("Password must be at least 6 characters long.")
            return False
        user_doc_ref.set({
            "email": email.lower(),
            "password_hash": hash_password(password),
            "created_at": datetime.now().timestamp()
        })
        st.success("Sign up successful! Please log in.")
        return True
    except Exception as e:
        st.error(f"Sign up error: {e}")
        return False

def logout():
    """Clears all session state variables."""
    st.session_state.logged_in = False
    st.session_state.current_user_email = None
    st.session_state.user_data_loaded = False
    st.session_state.current_tab = "💬 AI Mentor"
    # Clear data structures
    st.session_state.chat_history = []
    st.session_state.journal_entries = []
    st.session_state.goals = []
    st.session_state.daily_prompt = None
    st.session_state.mentor_persona = "Default"
    st.session_state.confirm_delete = False
    st.session_state.overall_insights_text = None
    st.info("You have been logged out.")
    st.rerun()

# --- 4. Firestore Data Persistence ---
def get_user_chat_collection_ref(user_id):
    """Returns the private collection ref for chat history."""
    app_id = firebaseConfig["project_id"]
    return db.collection('artifacts').document(app_id).collection('users').document(user_id).collection('chat_history')

def get_user_journal_collection_ref(user_id):
    """Returns the private collection ref for journal entries."""
    app_id = firebaseConfig["project_id"]
    return db.collection('artifacts').document(app_id).collection('users').document(user_id).collection('journal_entries')

def get_user_goal_collection_ref(user_id):
    """Returns the private collection ref for goals."""
    app_id = firebaseConfig["project_id"]
    return db.collection('artifacts').document(app_id).collection('users').document(user_id).collection('goals')

def load_data_from_firestore(user_id):
    """Loads all user data from Firestore."""
    try:
        # Load Chat History
        chat_ref = get_user_chat_collection_ref(user_id)
        chat_docs = chat_ref.stream()
        chat_data = [doc.to_dict() for doc in chat_docs]
        chat_data.sort(key=lambda x: x.get('timestamp', 0))

        # Load Journal Entries (sorted descending by timestamp)
        journal_ref = get_user_journal_collection_ref(user_id)
        journal_docs = journal_ref.stream()
        journal_data = [dict(doc.to_dict(), id=doc.id) for doc in journal_docs] # Include doc ID
        journal_data.sort(key=lambda x: x.get('timestamp', 0), reverse=True)

        # Load Goals (including doc ID for updates/deletion)
        goal_ref = get_user_goal_collection_ref(user_id)
        goal_docs = goal_ref.stream()
        goal_data = [dict(doc.to_dict(), id=doc.id) for doc in goal_docs]
        goal_data.sort(key=lambda x: x.get('timestamp', 0), reverse=True)
        
        return chat_data, journal_data, goal_data
    except Exception as e:
        st.error(f"Error loading data: {e}")
        return [], [], []

def save_chat_message(role, content):
    """Saves a chat message and updates session state."""
    timestamp = datetime.now().timestamp()
    message = {
        "role": role,
        "content": content,
        "timestamp": timestamp,
    }
    try:
        chat_ref = get_user_chat_collection_ref(st.session_state.current_user_email)
        chat_ref.add(message)
        st.session_state.chat_history.append(message)
    except Exception as e:
        st.error(f"Failed to save message: {e}")

def save_journal_entry(date, title, content, mood):
    """Saves a journal entry and reloads journal data."""
    entry = {
        "date": date,
        "title": title,
        "content": content,
        "mood": mood,
        "timestamp": datetime.now().timestamp()
    }
    try:
        journal_ref = get_user_journal_collection_ref(st.session_state.current_user_email)
        journal_ref.add(entry)
        # Reload journal data to update display immediately
        _, new_journal_data, _ = load_data_from_firestore(st.session_state.current_user_email)
        st.session_state.journal_entries = new_journal_data
        st.success("Journal entry saved!")
        # Clear insights as data has changed
        st.session_state.overall_insights_text = None 
    except Exception as e:
        st.error(f"Failed to save journal entry: {e}")

def save_goal(user_id, goal_text, deadline):
    """Saves a goal and reloads goal data."""
    try:
        goal_ref = get_user_goal_collection_ref(user_id)
        goal_ref.add({
            "text": goal_text,
            "deadline": deadline.strftime('%Y-%m-%d') if deadline else None,
            "completed": False,
            "timestamp": datetime.now().timestamp()
        })
        # Reload goal data to update display immediately
        _, _, goal_data = load_data_from_firestore(user_id)
        st.session_state.goals = goal_data
        st.success("Goal saved!")
    except Exception as e:
        st.error(f"Error saving goal: {e}")

def update_goal_status(user_id, goal_id, completed):
    """Updates the status of a specific goal and reloads goal data."""
    try:
        goal_ref = get_user_goal_collection_ref(user_id).document(goal_id)
        goal_ref.update({"completed": completed})
        # Reload goal data to update display immediately
        _, _, goal_data = load_data_from_firestore(user_id)
        st.session_state.goals = goal_data
        st.success("Goal status updated!")
    except Exception as e:
        st.error(f"Error updating goal: {e}")

# --- 5. Gemini API Functions ---
GEMINI_TEXT_MODEL = "gemini-2.5-flash"
GEMINI_API_URL = f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_TEXT_MODEL}:generateContent?key={GEMINI_API_KEY}"

def generate_journal_prompt():
    """Generates a concise self-reflection prompt using Gemini."""
    try:
        payload = {
            "contents": [{"role": "user", "parts": [{"text": "Generate a concise, insightful journal prompt for self-reflection. Example: 'What small victory are you celebrating today?'"}]}],
            "generationConfig": {"maxOutputTokens": 50, "temperature": 0.9}
        }
        response = requests.post(GEMINI_API_URL, headers={'Content-Type': 'application/json'}, data=json.dumps(payload))
        response.raise_for_status()
        result = response.json()
        text = result.get('candidates', [{}])[0].get('content', {}).get('parts', [{}])[0].get('text', '')
        return text.strip() if text else "No prompt generated."
    except Exception as e:
        st.error(f"Error generating prompt: {e}")
        return None

def analyze_journal_entry(content):
    """Analyzes a journal entry for sentiment and themes using Gemini."""
    try:
        payload = {
            "contents": [{"role": "user", "parts": [{"text": f"Analyze this journal entry for sentiment, key themes, and offer a gentle, encouraging observation (max 100 words): {content}"}]}],
            "generationConfig": {"maxOutputTokens": 100, "temperature": 0.7}
        }
        response = requests.post(GEMINI_API_URL, headers={'Content-Type': 'application/json'}, data=json.dumps(payload))
        response.raise_for_status()
        result = response.json()
        text = result.get('candidates', [{}])[0].get('content', {}).get('parts', [{}])[0].get('text', '')
        return text.strip() if text else "No analysis generated."
    except Exception as e:
        st.error(f"Error analyzing journal: {e}")
        return None

def generate_overall_insights(journal_entries):
    """Analyzes the last 10 journal entries for high-level themes and sentiment using Gemini."""
    if not journal_entries:
        return "No entries to analyze yet."

    # Analyze the last 10 entries for a high-level summary
    # NOTE: The list is sorted DESCENDING by timestamp, so [0:10] gives the 10 MOST RECENT entries.
    recent_entries = journal_entries[:10] 
    
    combined_text = "\n---\n".join([
        f"Date: {e.get('date', 'N/A')}, Mood: {e.get('mood', 'N/A')}. Content: {e.get('content', '')}" 
        for e in recent_entries
    ])

    user_query = (
        "Based on the following set of journal entries, provide a concise overall analysis (max 150 words). "
        "Identify the top 3 recurring themes (e.g., work-life balance, creativity, anxiety), the dominant sentiment (e.g., 'generally positive with recent stress'), "
        "and offer one forward-looking, actionable suggestion."
        f"\n\nJOURNAL DATA:\n{combined_text}"
    )

    try:
        max_retries = 3
        for attempt in range(max_retries):
            response = requests.post(GEMINI_API_URL, headers={'Content-Type': 'application/json'}, data=json.dumps({
                "contents": [{"role": "user", "parts": [{"text": user_query}]}],
                "generationConfig": {"maxOutputTokens": 200, "temperature": 0.7}
            }))
            
            try:
                response.raise_for_status()
            except requests.exceptions.HTTPError as e:
                if e.response.status_code == 429 and attempt < max_retries - 1:
                    time.sleep(2 ** attempt)
                    continue
                return f"API Error: {e.response.json().get('error', {}).get('message', str(e))}"
            
            result = response.json()
            text = result.get('candidates', [{}])[0].get('content', {}).get('parts', [{}])[0].get('text', '')
            
            if text:
                return text.strip()
            else:
                return "Analysis failed to generate content."
        return "Failed to generate analysis after multiple retries."
    except Exception as e:
        return f"Unexpected error during analysis API call: {e}"


def generate_ai_text_reply(user_prompt):
    """Handles the main chat generation with exponential backoff for retries."""
    # Build chat history for context
    chat_contents = [
        {"role": "user" if msg["role"] == "user" else "model", "parts": [{"text": msg["content"]}]}
        for msg in st.session_state.chat_history
    ]
    chat_contents.append({"role": "user", "parts": [{"text": user_prompt}]})
    
    # Define system prompt based on selected persona
    persona = st.session_state.mentor_persona
    
    # Base system instruction
    base_prompt = (
        "You are 'Mind Mentor', a compassionate, insightful AI focused on mental wellness. "
        "Your tone is gentle, encouraging, and non-judgemental. Offer supportive reflections, "
        "evidence-based coping strategies, and practical exercises. "
        "Keep responses concise, under 500 tokens."
    )
    
    # Custom persona instructions
    if persona == "Freud":
        system_prompt = base_prompt + " Focus your responses through a lens of psychodynamic principles (e.g., unconscious motives, early experiences)."
    elif persona == "Adler":
        system_prompt = base_prompt + " Focus on Individual Psychology (e.g., striving for superiority, social interest, lifestyle)."
    elif persona == "Jung":
        system_prompt = base_prompt + " Focus on analytical psychology (e.g., archetypes, collective unconscious, individuation)."
    elif persona == "Maslow":
        system_prompt = base_prompt + " Focus on humanistic principles and the Hierarchy of Needs (e.g., self-actualization, human potential)."
    elif persona == "Positive Psychology":
        system_prompt = base_prompt + " Focus on strengths, virtues, and optimal functioning (e.g., gratitude, flow, resilience)."
    elif persona == "CBT":
        system_prompt = base_prompt + " Focus on Cognitive Behavioral Therapy techniques (e.g., identifying thought patterns, challenging distortions, behavioral experiments)."
    else:
        system_prompt = base_prompt

    payload = {
        "contents": chat_contents,
        "systemInstruction": {"parts": [{"text": system_prompt}]},
        "generationConfig": {"maxOutputTokens": 500, "temperature": 0.8}
    }
    
    max_retries = 3
    for attempt in range(max_retries):
        try:
            response = requests.post(GEMINI_API_URL, headers={'Content-Type': 'application/json'}, data=json.dumps(payload))
            response.raise_for_status()
            result = response.json()
            text = result.get('candidates', [{}])[0].get('content', {}).get('parts', [{}])[0].get('text', '')
            
            if text:
                return text.strip()
            
            # Handle non-text responses (e.g., safety filters, max tokens)
            finish_reason = result.get('candidates', [{}])[0].get('finishReason', 'UNKNOWN')
            if finish_reason == 'SAFETY':
                st.error("Response filtered due to safety settings. Please rephrase your query.")
                return None
            elif finish_reason == 'MAX_TOKENS':
                st.warning("Response was cut short. Try a more specific question.")
                return result.get('candidates', [{}])[0].get('content', {}).get('parts', [{}])[0].get('text', 'Incomplete response.')
            else:
                st.error(f"Response empty or incomplete. Reason: {finish_reason}")
                return None
        
        except requests.exceptions.HTTPError as e:
            error_code = e.response.status_code if e.response else 0
            if error_code == 429 and attempt < max_retries - 1:
                # Apply exponential backoff
                time.sleep(2 ** attempt)
                continue
            st.error(f"API Error: {e.response.json().get('error', {}).get('message', str(e))}")
            return None
        except Exception as e:
            st.error(f"Unexpected error during API call: {e}")
            return None
    st.error("Failed after multiple retries to get a response.")
    return None

# --- 6. Utility Functions ---
def generate_export_content():
    """Generates a text string containing all user data for download."""
    export_text = f"--- Mind Universe Data Export for User: {st.session_state.current_user_email} ---\n"
    export_text += f"Export Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
    export_text += "============== JOURNAL ENTRIES ==============\n"
    if st.session_state.journal_entries:
        for entry in st.session_state.journal_entries:
            export_text += f"Date: {entry.get('date', 'N/A')}\n"
            export_text += f"Title: {entry.get('title', 'No Title')}\n"
            export_text += f"Mood: {entry.get('mood', 'N/A')}\n"
            export_text += f"Content:\n{entry.get('content', 'No content')}\n"
            export_text += "-" * 20 + "\n"
    else:
        export_text += "No journal entries found.\n\n"
    export_text += "\n============== CHAT HISTORY ==============\n"
    if st.session_state.chat_history:
        for message in sorted(st.session_state.chat_history, key=lambda x: x.get('timestamp', 0)):
            dt_object = datetime.fromtimestamp(message.get('timestamp', 0))
            time_str = dt_object.strftime('%Y-%m-%d %H:%M:%S')
            role = message.get('role', 'unknown').upper()
            content = message.get('content', '')
            export_text += f"[{time_str}] {role}: {content}\n"
    else:
        export_text += "No chat messages found.\n\n"
    export_text += "\n============== GOALS ==============\n"
    if st.session_state.goals:
        for goal in st.session_state.goals:
            status = "Completed" if goal["completed"] else "Pending"
            export_text += f"Goal: {goal.get('text', 'N/A')} (Due: {goal.get('deadline', 'None')}, Status: {status})\n"
    else:
        export_text += "No goals found.\n"
    return export_text.encode('utf-8')


# --- 7. UI Rendering Functions ---

def display_auth_page():
    """Displays the login and sign up forms with improved styling."""
    
    # Use columns to center the content
    col_l, col_center, col_r = st.columns([1, 2, 1])
    
    with col_center:
        st.markdown('<div class="auth-container">', unsafe_allow_html=True)
        st.title("🌌 Welcome to Mind Universe")
        st.subheader("Securely access your personal wellness space.")
        st.markdown("---")
        
        tab_login, tab_signup = st.tabs(["🔒 Login", "📝 Sign Up"])
        with tab_login:
            st.markdown("Enter your credentials to log in.")
            with st.form("login_form"):
                login_email = st.text_input("Email (Login)").lower()
                login_password = st.text_input("Password (Login)", type="password")
                login_submitted = st.form_submit_button("Login", type="primary")
                if login_submitted and login_email and login_password:
                    login_user(login_email, login_password)
                    if st.session_state.logged_in:
                        st.rerun()
                elif login_submitted:
                    st.warning("Please enter both email and password.")
        with tab_signup:
            st.markdown("Create a new account.")
            with st.form("signup_form"):
                signup_email = st.text_input("Email (Sign Up)").lower()
                signup_password = st.text_input("Password (Sign Up)", type="password")
                signup_submitted = st.form_submit_button("Sign Up", type="secondary")
                if signup_submitted and signup_email and signup_password:
                    if sign_up(signup_email, signup_password):
                        st.rerun()
                elif signup_submitted:
                    st.warning("Please enter a valid email and password (min 6 characters).")
        
        st.markdown('</div>', unsafe_allow_html=True)

def display_main_app():
    """Renders the main application UI after authentication."""
    # Initial data load
    if not st.session_state.user_data_loaded:
        with st.spinner("Loading your universe..."):
            chat_data, journal_data, goal_data = load_data_from_firestore(st.session_state.current_user_email)
            st.session_state.chat_history = chat_data
            st.session_state.journal_entries = journal_data
            st.session_state.goals = goal_data
            st.session_state.user_data_loaded = True

    st.title("🌌 Mind Universe")
    st.caption(f"Welcome, **{st.session_state.current_user_email}**")

    # --- Sidebar ---
    with st.sidebar:
        st.header("Account & Data")
        if st.button("Logout", type="secondary"):
            logout()
        st.divider()
        
        # --- Goal Setting ---
        st.subheader("🎯 Goal Setting")
        with st.form("goal_form", clear_on_submit=True):
            goal_text = st.text_input("Set a new goal", placeholder="e.g., Meditate for 10 minutes daily")
            deadline = st.date_input("Deadline (optional)", value=None)
            if st.form_submit_button("Add Goal", type="primary"):
                if goal_text:
                    save_goal(st.session_state.current_user_email, goal_text, deadline)
                    st.rerun()
                else:
                    st.warning("Please enter a goal.")
        
        st.subheader("Your Goals")
        if st.session_state.goals:
            for goal in st.session_state.goals:
                is_completed = goal["completed"]
                status_icon = "✅" if is_completed else "⏳"
                style_class = "goal-item goal-completed" if is_completed else "goal-item"

                # Use markdown with HTML for styling goals compactly
                st.markdown(
                    f'<div class="{style_class}">',
                    unsafe_allow_html=True
                )
                
                col_check, col_text = st.columns([0.8, 4])
                
                with col_check:
                    # Checkbox for status update
                    completed = st.checkbox(
                        "", 
                        value=is_completed, 
                        key=f"goal_check_{goal['id']}", 
                        label_visibility="hidden"
                    )
                    if completed != is_completed:
                        update_goal_status(st.session_state.current_user_email, goal["id"], completed)
                        st.rerun() # Rerun to re-render the list with updated styling

                with col_text:
                    text_style = "text-decoration: line-through; color: #666;" if is_completed else ""
                    st.markdown(
                        f'<p style="{text_style}; margin: 0;">{status_icon} **{goal["text"]}** <br> <span style="font-size: 0.8em; color: #888;">Due: {goal.get("deadline", "None")}</span></p>', 
                        unsafe_allow_html=True
                    )
                
                st.markdown('</div>', unsafe_allow_html=True)

        else:
            st.info("No goals set yet. Set your first goal above!")
            
        st.divider()

        st.subheader("Data Management")
        st.download_button(
            label="Download All Data (.txt)",
            data=generate_export_content(),
            file_name=f"mind_universe_export_{datetime.now().strftime('%Y%m%d')}.txt",
            mime="text/plain"
        )
        
        # --- Clear History ---
        st.subheader("⚠️ Clear History")
        if st.button("Clear All Data", help="Permanently deletes all data."):
            st.session_state.confirm_delete = True
        
        if st.session_state.confirm_delete:
            st.warning("Are you sure you want to PERMANENTLY delete ALL data?")
            col_yes, col_no = st.columns(2)
            with col_yes:
                if st.button("Yes, Delete All Data", key="confirm_delete_yes"):
                    with st.spinner("Deleting data..."):
                        try:
                            # Delete collections
                            for doc in get_user_chat_collection_ref(st.session_state.current_user_email).stream():
                                doc.reference.delete()
                            for doc in get_user_journal_collection_ref(st.session_state.current_user_email).stream():
                                doc.reference.delete()
                            for doc in get_user_goal_collection_ref(st.session_state.current_user_email).stream():
                                doc.reference.delete()
                            
                            st.session_state.user_data_loaded = False
                            st.session_state.confirm_delete = False
                            st.success("All data deleted. Reloading...")
                            st.rerun()
                        except Exception as e:
                            st.error(f"Deletion failed: {e}")
                            st.session_state.confirm_delete = False
            with col_no:
                if st.button("No, Cancel", key="confirm_delete_no"):
                    st.session_state.confirm_delete = False
                    st.rerun()


    # --- Navigation ---
    # ADDED "📊 Insights"
    view_options = ["✍️ Wellness Journal", "💬 AI Mentor", "📊 Insights"]
    selected_view = st.radio("Navigation", view_options, index=view_options.index(st.session_state.current_tab), horizontal=True, label_visibility="hidden")
    if selected_view != st.session_state.current_tab:
        st.session_state.current_tab = selected_view
        st.rerun()
    st.markdown("---") # Visual separator

    # --- Wellness Journal Tab ---
    if st.session_state.current_tab == "✍️ Wellness Journal":
        st.header("Reflect & Record")
        st.caption("Your private space for logging thoughts, feelings, and progress.")
        
        col_prompt, col_empty = st.columns([1, 4])
        with col_prompt:
            if st.button("✨ Get a Prompt", help="Generate a new idea for your entry."):
                st.session_state.daily_prompt = generate_journal_prompt()
        
        if st.session_state.daily_prompt:
            st.info(f"**Today's Reflection**: {st.session_state.daily_prompt}")
        
        with st.form("journal_form", clear_on_submit=True):
            col1, col2 = st.columns([1, 3])
            with col1:
                entry_date = st.date_input("Date", datetime.today())
            with col2:
                entry_title = st.text_input("Title (Optional)", placeholder="A brief summary of your entry")
            
            entry_content = st.text_area("What's on your mind today?", value=st.session_state.daily_prompt or "", height=200, placeholder="Write freely...")
            
            mood = st.selectbox("How are you feeling?", ["Happy", "Calm", "Excited", "Stressed", "Anxious", "Sad"])
            
            submitted = st.form_submit_button("Save Entry", type="primary")
            if submitted and entry_content:
                save_journal_entry(entry_date.strftime('%Y-%m-%d'), entry_title, entry_content, mood)
                # Clear prompt after saving
                st.session_state.daily_prompt = None
                st.rerun()
            elif submitted:
                st.warning("Please write some content before saving.")

        st.divider()
        
        # --- Journal History ---
        st.subheader("📖 Journal History")
        if st.session_state.journal_entries:
            for entry in st.session_state.journal_entries:
                with st.expander(f"**{entry.get('date')}** — {entry.get('title', 'Untitled Entry')} — Mood: {entry.get('mood', 'N/A')}"):
                    st.markdown(entry.get('content'))
                    
                    if st.button("AI Analyze Entry", key=f"analyze_{entry.get('timestamp')}"):
                        with st.spinner("Analyzing entry..."):
                            analysis = analyze_journal_entry(entry.get('content'))
                            if analysis:
                                st.success("Analysis Complete")
                                st.info(f"**AI Mentor Observation**: {analysis}")
        else:
            st.info("No journal entries found. Start writing above!")
            
        # --- Mood Trends Chart ---
        st.subheader("📈 Mood Trends")
        if st.session_state.journal_entries:
            # Mood mapping for chart scoring (higher is generally better)
            mood_scores = {"Happy": 5, "Excited": 4, "Calm": 3, "Anxious": 2, "Stressed": 1, "Sad": 0}
            
            # Sort entries chronologically (oldest first for trend line)
            chronological_entries = sorted(st.session_state.journal_entries, key=lambda x: x.get('timestamp', 0))

            chart_data_list = []
            for entry in chronological_entries:
                mood_label = entry.get("mood", "Calm")
                score = mood_scores.get(mood_label, 3)
                
                # Use a combined key (date + timestamp fraction) for potentially multiple entries on the same day
                entry_dt = datetime.fromtimestamp(entry.get('timestamp', 0))
                
                chart_data_list.append({
                    "Date": entry_dt,
                    "Mood Score": score,
                    "Mood Label": mood_label
                })

            if chart_data_list:
                df = pd.DataFrame(chart_data_list)
                # Set date as index for chronological charting
                df = df.set_index("Date") 
                
                # Updated color for better aesthetic
                st.line_chart(df, y="Mood Score", color="#6A0DAD")
                
                # Show key for scores
                st.markdown("Mood Score Key: **5=Happy**, **3=Calm**, **0=Sad**")
            else:
                st.info("Not enough data points to display mood trends.")
        else:
            st.info("No mood data to display yet.")
            
    # --- AI Mentor Tab ---
    elif st.session_state.current_tab == "💬 AI Mentor":
        st.header("Ask Your Mentor")
        st.caption("Chat with your supportive AI mentor for insights, coping strategies, and reflections.")
        
        # Mentor Persona Selector
        st.selectbox(
            "Select AI Mentor Persona", 
            ["Default", "Freud", "Adler", "Jung", "Maslow", "Positive Psychology", "CBT"], 
            key="mentor_persona",
            help="Selecting a persona will influence the advice given by the AI Mentor."
        )
        
        st.divider()
        
        # Display chat history
        # Reverse the list for display so the latest message is at the bottom of the visible area
        for message in st.session_state.chat_history:
            role = "user" if message["role"] == "user" else "assistant"
            avatar = "👤" if role == "user" else "🧠"
            with st.chat_message(role, avatar=avatar):
                st.markdown(message["content"])
        
        # Chat input and response logic
        if prompt := st.chat_input(f"Type your message to Mind Mentor ({st.session_state.mentor_persona} mode)..."):
            # 1. Display user message
            with st.chat_message("user", avatar="👤"):
                st.markdown(prompt)
            
            # 2. Save user message
            save_chat_message("user", prompt)
            
            # 3. Generate AI response
            with st.chat_message("assistant", avatar="🧠"):
                with st.spinner(f"Mind Mentor ({st.session_state.mentor_persona}) is reflecting..."):
                    ai_response_text = generate_ai_text_reply(prompt)
                    
                if ai_response_text:
                    st.markdown(ai_response_text)
                    # 4. Save AI response and Rerun
                    save_chat_message("model", ai_response_text)
                    st.rerun()

    # --- Insights Tab ---
    elif st.session_state.current_tab == "📊 Insights":
        st.header("Your Universe at a Glance")
        st.caption("High-level summaries of your progress and personal trends.")
        
        # --- Goal Summary ---
        st.subheader("🎯 Goal Progress Overview")
        if st.session_state.goals:
            total_goals = len(st.session_state.goals)
            completed_goals = sum(1 for goal in st.session_state.goals if goal["completed"])
            pending_goals = total_goals - completed_goals
            
            completion_rate = (completed_goals / total_goals) * 100 if total_goals > 0 else 0
            
            col_comp, col_pend, col_rate = st.columns(3)
            
            col_comp.metric("Completed Goals", completed_goals, help="Total goals marked as done.")
            col_pend.metric("Pending Goals", pending_goals, help="Total goals still in progress.")
            col_rate.metric("Completion Rate", f"{completion_rate:.1f}%", help="Percentage of goals completed.")
            
            st.progress(completion_rate / 100)
            
        else:
            st.info("Set some goals in the sidebar to track your progress here!")

        st.divider()

        # --- AI-Driven Journal Analysis ---
        st.subheader("🧠 Recent Journal Themes & Sentiment")
        if st.session_state.journal_entries:
            if st.button("Generate High-Level Analysis"):
                with st.spinner("Analyzing recent entries..."):
                    insights = generate_overall_insights(st.session_state.journal_entries)
                    st.session_state.overall_insights_text = insights
            
            if st.session_state.get('overall_insights_text'):
                st.info(st.session_state.overall_insights_text)
            else:
                st.info(f"Click **'Generate High-Level Analysis'** to view themes and sentiment from your {min(10, len(st.session_state.journal_entries))} most recent entries.")
        else:
            st.info("Write a few journal entries to unlock deep insights.")

        st.divider()

        # --- Mood Statistics ---
        st.subheader("📊 Mood Score Statistics")
        if st.session_state.journal_entries:
            mood_scores = {"Happy": 5, "Excited": 4, "Calm": 3, "Anxious": 2, "Stressed": 1, "Sad": 0}
            
            chart_data_list = []
            # We need to map mood scores for all entries, not just recent ones
            for entry in st.session_state.journal_entries:
                mood_label = entry.get("mood", "Calm")
                score = mood_scores.get(mood_label, 3)
                chart_data_list.append(score)
            
            if chart_data_list:
                df_scores = pd.Series(chart_data_list)
                
                # Find the label corresponding to the min/max score
                mood_labels_inv = {v: k for k, v in mood_scores.items()}
                
                # Since multiple moods might share the same score (e.g., Anxious/Stressed might be low), 
                # we just show the score's label
                min_score = df_scores.min()
                max_score = df_scores.max()
                
                max_mood_label = mood_labels_inv.get(max_score, 'N/A')
                min_mood_label = mood_labels_inv.get(min_score, 'N/A')
                
                col_max, col_min, col_avg = st.columns(3)
                
                col_max.metric("Highest Mood", f"{max_mood_label} ({max_score})")
                col_min.metric("Lowest Mood", f"{min_mood_label} ({min_score})")
                col_avg.metric("Average Score", f"{df_scores.mean():.2f}")
            
        else:
            st.info("Mood statistics will appear once you log entries.")


# --- Main Application Logic ---
if __name__ == '__main__':
    if st.session_state.logged_in:
        display_main_app()
    else:
        display_auth_page()
