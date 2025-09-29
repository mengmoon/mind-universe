import streamlit as st
import requests
import json
import pandas as pd
from datetime import datetime
import hashlib 

# --- 1. Global Configuration and Secrets Loading ---

# Load Firebase Config
try:
    firebase_config_str = st.secrets["FIREBASE_CONFIG"]
    if isinstance(firebase_config_str, str):
        # Fix for escaped newlines in the private key string
        firebase_config_str = firebase_config_str.replace('\\\\n', '\\n')
        firebase_config_str = firebase_config_str.strip().strip('"').strip("'")
        
    firebaseConfig = json.loads(firebase_config_str)
    
except Exception as e:
    st.error(f"Failed to parse FIREBASE_CONFIG as JSON. Ensure the format is correct: {e}")
    st.stop()

# Load Gemini API Key
GEMINI_API_KEY = st.secrets.get("GEMINI_API_KEY", "")
if not GEMINI_API_KEY:
    st.error("GEMINI_API_KEY not found in Streamlit secrets. Please configure it to use the AI features.")
    st.stop()

# --- 2. Firebase Initialization and Authentication ---

# Use st.cache_resource for resources that should be initialized once
@st.cache_resource
def initialize_firebase(config):
    """Initializes and returns the Firebase app and firestore objects."""
    import firebase_admin
    from firebase_admin import credentials, firestore

    try:
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
        
        db = firestore.client()
        return db

    except Exception as e:
        st.error(f"Failed to initialize Firebase: {e}")
        st.stop()
        
db = initialize_firebase(firebaseConfig)

# --- 3. Authentication & State Management Functions ---

if 'logged_in' not in st.session_state:
    st.session_state.logged_in = False
if 'current_user_email' not in st.session_state:
    st.session_state.current_user_email = None
if 'user_data_loaded' not in st.session_state:
    st.session_state.user_data_loaded = False
if 'current_tab' not in st.session_state:
    st.session_state.current_tab = "💬 AI Mentor"
if 'journal_analysis' not in st.session_state:
    st.session_state.journal_analysis = None
if 'goals' not in st.session_state:
    st.session_state.goals = [] 

def hash_password(password):
    """Simple password hashing simulation using SHA-256."""
    return hashlib.sha256(password.encode()).hexdigest()

def get_users_collection_ref():
    """Returns the Firestore reference for the global users collection (public/data path)."""
    app_id = firebaseConfig["project_id"]
    return db.collection('artifacts').document(app_id).collection('public').document('data').collection('users')

def login_user(email, password):
    """Attempts to log in a user by checking credentials against Firestore."""
    try:
        user_doc_ref = get_users_collection_ref().document(email.lower())
        user_doc = user_doc_ref.get()

        if user_doc.exists:
            user_data = user_doc.to_dict()
            hashed_input = hash_password(password)
            
            if user_data.get('password_hash') == hashed_input:
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
        st.error(f"An error occurred during login: {e}")
        return False

def sign_up(email, password):
    """Registers a new user in Firestore."""
    try:
        user_doc_ref = get_users_collection_ref().document(email.lower())
        
        if user_doc_ref.get().exists:
            st.error("This email is already registered. Please log in.")
            return False
        
        if len(password) < 6:
            st.error("Password must be at least 6 characters long.")
            return False

        hashed_password = hash_password(password)
        
        user_doc_ref.set({
            "email": email.lower(),
            "password_hash": hashed_password,
            "created_at": datetime.now().timestamp()
        })
        
        st.success("Sign up successful! Please log in.")
        return True

    except Exception as e:
        st.error(f"An error occurred during sign up: {e}")
        return False

def logout():
    """Clears session state and logs the user out."""
    st.session_state.logged_in = False
    st.session_state.current_user_email = None
    st.session_state.user_data_loaded = False
    st.session_state.current_tab = "💬 AI Mentor" 
    st.session_state.journal_analysis = None
    st.session_state.goals = []
    if 'chat_history' in st.session_state:
        st.session_state.chat_history = []
    if 'journal_entries' in st.session_state:
        st.session_state.journal_entries = []
    st.info("You have been logged out.")
    st.rerun()

# --- 4. Firestore Data Path and Persistence ---

def get_user_chat_collection_ref(user_id):
    """Returns the Firestore reference for the user's chat history."""
    app_id = firebaseConfig["project_id"]
    return db.collection('artifacts').document(app_id).collection('users').document(user_id).collection('chat_history')

def get_user_journal_collection_ref(user_id):
    """Returns the Firestore reference for the user's journal entries."""
    app_id = firebaseConfig["project_id"]
    return db.collection('artifacts').document(app_id).collection('users').document(user_id).collection('journal_entries')

def get_user_goals_collection_ref(user_id):
    """Returns the Firestore reference for the user's goals."""
    app_id = firebaseConfig["project_id"]
    return db.collection('artifacts').document(app_id).collection('users').document(user_id).collection('goals')

def load_data_from_firestore(user_id):
    """Loads all chat, journal, and goal data for the authenticated user."""
    
    try:
        # Load Chat History
        chat_ref = get_user_chat_collection_ref(user_id)
        chat_docs = chat_ref.stream()
        chat_data = [doc.to_dict() for doc in chat_docs]
        chat_data.sort(key=lambda x: x.get('timestamp', 0))
        
        # Load Journal Entries
        journal_ref = get_user_journal_collection_ref(user_id)
        journal_docs = journal_ref.stream()
        journal_data = [doc.to_dict() for doc in journal_docs]
        journal_data.sort(key=lambda x: datetime.strptime(x.get('date', '1970-01-01'), '%Y-%m-%d'), reverse=True) 
        
        # Load Goals
        goals_ref = get_user_goals_collection_ref(user_id)
        goals_docs = goals_ref.stream()
        # Include doc.id to enable updates/deletes
        goals_data = [{**doc.to_dict(), 'id': doc.id} for doc in goals_docs]
        goals_data.sort(key=lambda x: x.get('created_at', 0), reverse=True)

        return chat_data, journal_data, goals_data
    except Exception as e:
        st.error(f"Error loading data: {e}")
        return [], [], [] # Return empty lists for all data types

def save_chat_message(role, content):
    """Saves a single chat message to Firestore and updates session state."""
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

def save_journal_entry(date, title, content):
    """Saves a journal entry to Firestore, analyzing sentiment first."""
    
    with st.spinner("Analyzing entry sentiment..."):
        sentiment_data = generate_sentiment_score(content)

    entry = {
        "date": date,
        "title": title,
        "content": content,
        "timestamp": datetime.now().timestamp(),
        "sentiment": sentiment_data.get('score', 0.0), 
        "emotion": sentiment_data.get('emotion_keyword', 'Neutral') 
    }
    
    try:
        journal_ref = get_user_journal_collection_ref(st.session_state.current_user_email)
        journal_ref.add(entry)
        
        # Reload and update session state
        _, new_journal_data, _ = load_data_from_firestore(st.session_state.current_user_email)
        st.session_state.journal_entries = new_journal_data
        st.session_state.journal_analysis = None 
        st.success(f"Journal entry saved! Sentiment detected: {entry['emotion']} ({entry['sentiment']:.2f})")
    except Exception as e:
        st.error(f"Failed to save journal entry: {e}")

def save_new_goal(title, description):
    """Adds a new goal to Firestore."""
    goal = {
        "title": title,
        "description": description,
        "created_at": datetime.now().timestamp(),
        "status": "Active" # Goals start as Active
    }
    try:
        goals_ref = get_user_goals_collection_ref(st.session_state.current_user_email)
        goals_ref.add(goal)
        st.success("New goal created!")
        # Force reload goals
        _, _, new_goals_data = load_data_from_firestore(st.session_state.current_user_email)
        st.session_state.goals = new_goals_data
    except Exception as e:
        st.error(f"Failed to save goal: {e}")

def update_goal_status(goal_id, new_status):
    """
    Updates the status of a specific goal in Firestore and updates the session state in place.
    NOTE: Removed explicit st.rerun().
    """
    try:
        goals_ref = get_user_goals_collection_ref(st.session_state.current_user_email)
        goal_doc_ref = goals_ref.document(goal_id)
        
        # 1. Update Firestore
        goal_doc_ref.update({"status": new_status})
        
        # 2. Update Session State in place (Critical for avoiding button key conflict)
        for goal in st.session_state.goals:
            if goal.get('id') == goal_id:
                goal['status'] = new_status
                break
                
        st.success(f"Goal status updated to {new_status}!")
        # The change in st.session_state.goals will automatically trigger a clean rerun.
    except Exception as e:
        st.error(f"Failed to update goal status: {e}")

def delete_goal(goal_id):
    """
    Deletes a specific goal from Firestore and updates the session state in place.
    NOTE: Removed explicit st.rerun().
    """
    try:
        goals_ref = get_user_goals_collection_ref(st.session_state.current_user_email)
        
        # 1. Delete from Firestore
        goals_ref.document(goal_id).delete()
        
        # 2. Update Session State in place (Critical for avoiding button key conflict)
        st.session_state.goals = [g for g in st.session_state.goals if g.get('id') != goal_id]
        
        st.success("Goal deleted successfully.")
        # The change in st.session_state.goals will automatically trigger a clean rerun.
    except Exception as e:
        st.error(f"Failed to delete goal: {e}")

# --- 5. Streamlit Callback Wrappers (Fixing the Button Error) ---

def handle_achieve_goal_click(goal_id):
    """Wrapper for 'Mark Achieved' button click."""
    update_goal_status(goal_id, "Achieved")

def handle_delete_goal_click(goal_id):
    """Wrapper for 'Delete' button click."""
    delete_goal(goal_id)

# --- 6. LLM API Call Functions (Gemini Text and Structured Output) ---

GEMINI_TEXT_MODEL = "gemini-2.5-flash"
GEMINI_API_URL = f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_TEXT_MODEL}:generateContent?key={GEMINI_API_KEY}"

SENTIMENT_SCHEMA = {
    "type": "OBJECT",
    "properties": {
        "score": {
            "type": "NUMBER",
            "description": "A precise sentiment score between -1.0 (extremely negative) and 1.0 (extremely positive). Use two decimal places."
        },
        "emotion_keyword": {
            "type": "STRING",
            "description": "The single most dominant emotion detected (e.g., Anxiety, Joy, Calmness, Stress, Excitement)."
        }
    },
    "required": ["score", "emotion_keyword"]
}

def call_gemini_api(payload, is_json_response=False):
    """Utility function to handle the API request with exponential backoff."""
    headers = {'Content-Type': 'application/json'}
    max_retries = 3
    
    for attempt in range(max_retries):
        try:
            response = requests.post(GEMINI_API_URL, headers=headers, data=json.dumps(payload))
            response.raise_for_status()
            result = response.json()
            candidate = result.get('candidates', [{}])[0]
            
            if is_json_response:
                json_text = candidate.get('content', {}).get('parts', [{}])[0].get('text')
                if json_text:
                    return json.loads(json_text)
                return None
            else:
                return candidate.get('content', {}).get('parts', [{}])[0].get('text')

        except (requests.exceptions.RequestException, json.JSONDecodeError, Exception) as e:
            if attempt < max_retries - 1:
                import time
                wait_time = 2 ** attempt
                time.sleep(wait_time)
                continue # Retry
            else:
                st.error(f"API Request failed after {max_retries} attempts: {e}")
                return None

def generate_sentiment_score(content):
    """Calls the Gemini API to get structured sentiment and emotion."""
    
    system_prompt = (
        "You are 'Sentiment Analyzer'. Analyze the following text and return a precise sentiment score "
        "between -1.0 (negative) and 1.0 (positive) and the dominant emotion keyword, strictly in the requested JSON format. "
        "Do not include any other text or markdown."
    )
    
    payload = {
        "contents": [{"role": "user", "parts": [{"text": f"Analyze this journal entry: {content}"}]}],
        "systemInstruction": {"parts": [{"text": system_prompt}]},
        "generationConfig": {
            "responseMimeType": "application/json",
            "responseSchema": SENTIMENT_SCHEMA,
            "maxOutputTokens": 100, 
            "temperature": 0.0 
        }
    }
    
    return call_gemini_api(payload, is_json_response=True) or {"score": 0.0, "emotion_keyword": "Neutral"}

def generate_ai_text_reply(user_prompt, history):
    """Calls the Gemini API for standard text generation (AI Mentor)."""
    
    chat_contents = [
        {"role": "user" if msg["role"] == "user" else "model", 
         "parts": [{"text": msg["content"]}]}
        for msg in history
    ]
    chat_contents.append({"role": "user", "parts": [{"text": user_prompt}]})

    system_prompt = (
        "You are 'Mind Mentor', a compassionate, insightful AI focused on mental wellness. "
        "Your tone is gentle, encouraging, and non-judgemental. Offer supportive reflections, "
        "evidence-based coping strategies, and practical exercises. "
        "Keep your responses concise, aiming for under 500 tokens to ensure a full reply."
    )
    
    payload = {
        "contents": chat_contents,
        "systemInstruction": {"parts": [{"text": system_prompt}]},
        "generationConfig": {
            "maxOutputTokens": 500,
            "temperature": 0.8
        }
    }

    return call_gemini_api(payload, is_json_response=False)

def generate_journal_analysis(journal_text_block):
    """Calls the Gemini API for unstructured journal analysis (Summary)."""
    
    system_prompt = (
        "You are 'Mind Analyst', an objective yet gentle AI. Your task is to analyze the user's "
        "journal entries to identify the primary **Sentiment Trend** (e.g., Mixed, Generally Positive), "
        "extract **3-5 Key Recurring Themes** (e.g., career, family, health), and generate a **One-Paragraph Summary of Overall Emotional State**. "
        "Respond ONLY with a clear, formatted summary using Markdown headings for clarity, and be objective yet gentle. "
        "DO NOT use a conversational opening or closing. Just provide the analysis."
    )
    
    user_prompt = f"Analyze the following block of journal entries:\n\n---\n{journal_text_block}"
    
    payload = {
        "contents": [{"role": "user", "parts": [{"text": user_prompt}]}],
        "systemInstruction": {"parts": [{"text": system_prompt}]},
        "generationConfig": {
            "maxOutputTokens": 800,
            "temperature": 0.5
        }
    }
    
    return call_gemini_api(payload, is_json_response=False) or "Analysis failed to complete."


# --- 7. UI Components and Pages ---

st.set_page_config(layout="wide", page_title="Mind Universe: Wellness & AI")

def display_auth_page():
    """Displays the login and sign up forms."""
    st.title("🌌 Welcome to Mind Universe")
    st.subheader("Securely access your personal wellness space.")
    
    tab_login, tab_signup = st.tabs(["🔒 Login", "📝 Sign Up"])
    
    with tab_login:
        st.markdown("Enter your credentials to log in.")
        with st.form("login_form"):
            login_email = st.text_input("Email (Login)").lower()
            login_password = st.text_input("Password (Login)", type="password")
            login_submitted = st.form_submit_button("Login", type="primary")
            
            if login_submitted:
                if login_email and login_password:
                    login_user(login_email, login_password)
                    if st.session_state.logged_in:
                        st.rerun()
                else:
                    st.warning("Please enter both email and password.")
                    
    with tab_signup:
        st.markdown("Create a new account.")
        with st.form("signup_form"):
            signup_email = st.text_input("Email (Sign Up)").lower()
            signup_password = st.text_input("Password (Sign Up)", type="password")
            signup_submitted = st.form_submit_button("Sign Up", type="secondary")
            
            if signup_submitted:
                if signup_email and signup_password:
                    if sign_up(signup_email, signup_password):
                        st.rerun()
                else:
                    st.warning("Please enter a valid email and a password (min 6 characters).")

def display_main_app():
    """Displays the main application content after successful login."""
    
    # Load data if not already loaded in the current session
    if not st.session_state.user_data_loaded:
        with st.spinner("Loading your universe..."):
            chat_data, journal_data, goals_data = load_data_from_firestore(st.session_state.current_user_email)
            st.session_state.chat_history = chat_data
            st.session_state.journal_entries = journal_data
            st.session_state.goals = goals_data # Load goals
            st.session_state.user_data_loaded = True
    
    # --- Header ---
    st.title("🌌 Mind Universe")
    st.caption(f"Welcome, {st.session_state.current_user_email} (ID: {st.session_state.current_user_email})")

    # --- Sidebar (Data Management) ---
    with st.sidebar:
        st.header("Account & Data")
        if st.button("Logout", type="secondary", help="End your session"):
            logout()
            
        st.divider()
        st.subheader("Data Management")
        
        # Download/Export function
        def generate_export_content():
            export_text = f"--- Mind Universe Data Export for User: {st.session_state.current_user_email} ---\n"
            export_text += f"Export Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
            
            # 1. Journal Entries
            export_text += "============== JOURNAL ENTRIES ==============\n"
            if st.session_state.journal_entries:
                for entry in st.session_state.journal_entries:
                    export_text += f"Date: {entry.get('date', 'N/A')} (Sentiment: {entry.get('sentiment', 'N/A')}, Emotion: {entry.get('emotion', 'N/A')})\n"
                    export_text += f"Title: {entry.get('title', 'No Title')}\n"
                    export_text += f"Content:\n{entry.get('content', 'No content')}\n"
                    export_text += "-" * 20 + "\n"
            else:
                export_text += "No journal entries found.\n\n"
                
            # 2. Goals
            export_text += "\n============== GOAL TRACKER ==============\n"
            if st.session_state.goals:
                for goal in st.session_state.goals:
                    export_text += f"Goal: {goal.get('title', 'N/A')}\n"
                    export_text += f"Status: {goal.get('status', 'N/A')}\n"
                    export_text += f"Details:\n{goal.get('description', 'No description')}\n"
                    export_text += "-" * 20 + "\n"
            else:
                export_text += "No goals found.\n\n"
                
            # 3. Chat History
            export_text += "\n============== CHAT HISTORY ==============\n"
            if st.session_state.chat_history:
                sorted_chat = sorted(st.session_state.chat_history, key=lambda x: x.get('timestamp', 0))
                for message in sorted_chat:
                    dt_object = datetime.fromtimestamp(message.get('timestamp', 0))
                    time_str = dt_object.strftime('%Y-%m-%d %H:%M:%S')
                    role = message.get('role', 'unknown').upper()
                    content = message.get('content', '')
                    export_text += f"[{time_str}] {role}: {content}\n"
            else:
                export_text += "No chat messages found.\n"
                
            return export_text.encode('utf-8')

        st.download_button(
            label="Download History (TXT)",
            data=generate_export_content(),
            file_name=f"mind_universe_export_{datetime.now().strftime('%Y%m%d')}.txt",
            mime="text/plain",
            help="Downloads all journal entries, goals, and chat history into a single text file."
        )
        
        # --- Clear History (Delete functionality) ---
        st.subheader("⚠️ Clear History")
        
        if st.button("Clear All History (Requires Reload)", type="secondary", help="Permanently deletes all chat and journal data."):
            st.session_state.confirm_delete = True
            
        if st.session_state.get('confirm_delete', False):
            st.warning("Are you sure you want to PERMANENTLY delete ALL data?")
            col_yes, col_no = st.columns(2)
            
            with col_yes:
                if st.button("Yes, Delete All Data"):
                    with st.spinner("Deleting data..."):
                        try:
                            # Delete Chat History
                            chat_ref = get_user_chat_collection_ref(st.session_state.current_user_email)
                            for doc in chat_ref.stream():
                                doc.reference.delete()
                            st.session_state.chat_history = []
                            
                            # Delete Journal Entries
                            journal_ref = get_user_journal_collection_ref(st.session_state.current_user_email)
                            for doc in journal_ref.stream():
                                doc.reference.delete()
                            st.session_state.journal_entries = []
                            
                            # Delete Goals
                            goals_ref = get_user_goals_collection_ref(st.session_state.current_user_email)
                            for doc in goals_ref.stream():
                                doc.reference.delete()
                            st.session_state.goals = []

                            st.success("All history has been permanently deleted. Reloading application...")
                            st.session_state.confirm_delete = False
                            st.session_state.user_data_loaded = False
                            st.rerun()
                            
                        except Exception as e:
                            st.error(f"Deletion failed: {e}")
                            st.session_state.confirm_delete = False

            with col_no:
                if st.button("No, Cancel"):
                    st.session_state.confirm_delete = False
                    st.info("Deletion cancelled.")
                    st.rerun()

    # --- Navigation ---
    view_options = ["💬 AI Mentor", "✍️ Wellness Journal", "📊 Insights", "🎯 Goal Tracker"]
    
    selected_view = st.radio(
        "Navigation",
        view_options,
        index=view_options.index(st.session_state.current_tab),
        horizontal=True,
        label_visibility="hidden"
    )
    
    if selected_view != st.session_state.current_tab:
        st.session_state.current_tab = selected_view
        st.rerun()
        
    st.divider()

    # --- Content Display based on selected_view ---
    
    if st.session_state.current_tab == "💬 AI Mentor":
        # Content 1: AI Mentor (Chat)
        st.header("Ask Your Mentor")
        st.caption("Chat with your supportive AI mentor for insights, coping strategies, and reflections.")
        st.divider()

        # Display chat history
        for message in st.session_state.chat_history:
            role = "user" if message["role"] == "user" else "assistant"
            avatar = "👤" if role == "user" else "🧠"
            with st.chat_message(role, avatar=avatar):
                st.markdown(message["content"])

        # Chat input
        if prompt := st.chat_input("Type your message to Mind Mentor..."):
            with st.chat_message("user", avatar="👤"):
                st.markdown(prompt)
            save_chat_message("user", prompt)

            with st.chat_message("assistant", avatar="🧠"):
                with st.spinner("Mind Mentor is reflecting..."):
                    ai_response_text = generate_ai_text_reply(prompt, st.session_state.chat_history)
                    
                if ai_response_text:
                    st.markdown(ai_response_text)
                    save_chat_message("model", ai_response_text)
                    st.rerun()
                else:
                    st.error("Failed to receive a reply from the AI Mentor. Please try again.")

    elif st.session_state.current_tab == "✍️ Wellness Journal":
        # Content 2: Wellness Journal
        st.header("Reflect & Record")
        st.caption("Your private space for logging thoughts, feelings, and progress.")

        # Entry Form
        with st.form("journal_form", clear_on_submit=True):
            col1, col2 = st.columns([1, 3])
            with col1:
                entry_date = st.date_input("Date", datetime.today())
            with col2:
                entry_title = st.text_input("Title (Optional)", placeholder="A brief summary of your entry")
            
            entry_content = st.text_area("What's on your mind today?", height=200, placeholder="Write freely about your day, challenges, or gratitude.")
            
            submitted = st.form_submit_button("Save Entry", type="primary")
            
            if submitted and entry_content:
                save_journal_entry(entry_date.strftime('%Y-%m-%d'), entry_title, entry_content)
                st.rerun() 
            elif submitted and not entry_content:
                st.warning("Please write some content before saving.")

        st.divider()

        # Display History
        st.subheader("Journal History")
        if st.session_state.journal_entries:
            for entry in st.session_state.journal_entries:
                sentiment_text = f" | Sentiment: **{entry.get('emotion', 'N/A')} ({entry.get('sentiment', 0.0):.2f})**"
                with st.expander(f"**{entry.get('date')}** — {entry.get('title', 'Untitled Entry')}{sentiment_text}"):
                    st.markdown(entry.get('content'))
        else:
            st.info("No journal entries found. Start writing above!")


    elif st.session_state.current_tab == "📊 Insights":
        # Content 3: Insights (Enhanced with Tabs)
        st.header("AI-Powered Insights & Visualization")
        st.caption("Review long-term trends and get deep summaries from your journal history.")
        
        if not st.session_state.journal_entries:
            st.info("You need to write a few journal entries before generating insights.")
            return

        # New Sub-Tabs for Visualization and Summary
        tab_trends, tab_frequency, tab_summary = st.tabs(["📉 Sentiment Trend", "📊 Emotion Frequency", "🧠 Deep Summary"])

        # --- 3.1 Data Preparation ---
        chart_data = [
            {'date': datetime.strptime(e['date'], '%Y-%m-%d'), 'sentiment': e.get('sentiment'), 'emotion': e.get('emotion')}
            for e in st.session_state.journal_entries
            if e.get('sentiment') is not None
        ]
        
        if chart_data:
            chart_data.sort(key=lambda x: x['date'])
            df = pd.DataFrame(chart_data)
            df.set_index('date', inplace=True)
        
        # --- 3.2 Sentiment Trend Chart (Line Chart) ---
        with tab_trends:
            st.subheader("Overall Emotional Score Over Time")
            
            if chart_data:
                st.markdown("**(Range: -1.0 Negative to 1.0 Positive)**")
                # Ensure the y-axis is fixed for better comparison
                st.line_chart(df[['sentiment']], height=300, y_min=-1.0, y_max=1.0)
            else:
                st.warning("No entries with sentiment data found. Save new journal entries to chart your trend.")

        # --- 3.3 Emotion Frequency (Bar Chart - NEW) ---
        with tab_frequency:
            st.subheader("Frequency of Detected Emotions")
            
            if chart_data:
                # Group by emotion keyword and count
                emotion_counts = df['emotion'].value_counts().reset_index()
                emotion_counts.columns = ['Emotion', 'Count']
                
                st.bar_chart(emotion_counts, x='Emotion', y='Count')
                st.markdown("This chart shows the most frequent emotional keywords detected by the AI in your entries. Understanding which emotions are dominant can reveal underlying patterns in your life.")
            else:
                st.info("Write more journal entries to generate this frequency chart.")


        # --- 3.4 General Analysis Summary ---
        with tab_summary:
            st.subheader("AI-Generated Journal Summary")

            entries_to_analyze = st.session_state.journal_entries[:10]
            journal_text_block = ""
            for i, entry in enumerate(entries_to_analyze):
                journal_text_block += f"=== Entry {i+1} ({entry.get('date', 'N/A')}): {entry.get('title', 'No Title')} ===\n"
                journal_text_block += f"{entry.get('content', '')}\n\n"
            
            if st.button(f"Generate Summary from Last {len(entries_to_analyze)} Entries", type="primary"):
                st.session_state.journal_analysis = None 
                with st.spinner("Mind Analyst is reading your reflections..."):
                    analysis_result = generate_journal_analysis(journal_text_block)
                    st.session_state.journal_analysis = analysis_result
                    
            if st.session_state.journal_analysis:
                st.markdown(st.session_state.journal_analysis)
            else:
                st.info("Click the button above to generate a new analysis of your recent journal entries.")


    elif st.session_state.current_tab == "🎯 Goal Tracker":
        # Content 4: Goal Setting (NEW PAGE)
        st.header("Achieve Your Aspirations")
        st.caption("Set goals, track progress, and celebrate your successes!")
        
        # --- Goal Creation Form ---
        with st.expander("➕ Create a New Goal", expanded=False):
            with st.form("goal_form", clear_on_submit=True):
                goal_title = st.text_input("Goal Title (e.g., Meditate daily for 15 mins)")
                goal_description = st.text_area("Detailed Plan/Description")
                submitted = st.form_submit_button("Set Goal", type="primary")

                if submitted and goal_title:
                    save_new_goal(goal_title, goal_description)
                    st.rerun()
                elif submitted and not goal_title:
                    st.warning("Please provide a title for your goal.")

        st.divider()

        # --- Goal Lists ---
        active_goals = [g for g in st.session_state.goals if g.get('status') == 'Active']
        achieved_goals = [g for g in st.session_state.goals if g.get('status') == 'Achieved']

        # Active Goals
        st.subheader(f"🚀 Active Goals ({len(active_goals)})")
        if active_goals:
            for goal in active_goals:
                with st.container(border=True):
                    col_title, col_button = st.columns([4, 1])
                    with col_title:
                        st.markdown(f"**{goal.get('title')}**")
                        created_at_dt = datetime.fromtimestamp(goal.get('created_at', datetime.now().timestamp()))
                        st.caption(f"Started: {created_at_dt.strftime('%Y-%m-%d')}")
                        if goal.get('description'):
                            st.markdown(f"> *{goal.get('description')}*")
                    with col_button:
                        st.button(
                            "Mark Achieved 🎉", 
                            key=f"achieve_{goal['id']}", 
                            type="success",
                            on_click=handle_achieve_goal_click,
                            args=(goal['id'],) 
                        )
        else:
            st.info("You currently have no active goals. Time to set one!")

        st.divider()

        # Achieved Goals
        st.subheader(f"✅ Achieved Goals ({len(achieved_goals)})")
        if achieved_goals:
            st.balloons() # Celebrate achievements!
            for goal in achieved_goals:
                with st.container(border=True):
                    col_achieved, col_delete = st.columns([5, 1])
                    with col_achieved:
                        st.markdown(f"**{goal.get('title')}** (Achieved)")
                    with col_delete:
                        st.button(
                            "Delete", 
                            key=f"delete_{goal['id']}", 
                            type="secondary",
                            on_click=handle_delete_goal_click,
                            args=(goal['id'],) 
                        )
        else:
            st.info("Keep working! Achieved goals will appear here.")


# --- Main Application Logic ---

if __name__ == '__main__':
    if st.session_state.logged_in:
        display_main_app()
    else:
        display_auth_page()
