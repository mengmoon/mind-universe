import streamlit as st
import requests
import json
import pandas as pd
from datetime import datetime
import hashlib
from firebase_admin import credentials, firestore
import firebase_admin
import time # For exponential backoff

# --- Configuration and Initialization (Global) ---

# Load Firebase Config
try:
    firebase_config_str = st.secrets["FIREBASE_CONFIG"]
    if isinstance(firebase_config_str, str):
        firebase_config_str = firebase_config_str.replace('\\\\n', '\\n').replace('\\n','\\n')
        firebase_config_str = firebase_config_str.strip().strip('"').strip("'")
        
    firebaseConfig = json.loads(firebase_config_str)
    
except Exception as e:
    st.error(f"Failed to parse FIREBASE_CONFIG. Ensure the format is correct: {e}")
    st.stop()

# Load Gemini API Key
GEMINI_API_KEY = st.secrets.get("GEMINI_API_KEY", "")
if not GEMINI_API_KEY:
    st.error("GEMINI_API_KEY not found in Streamlit secrets.")
    st.stop()

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

# --- Firebase Initialization ---

@st.cache_resource
def initialize_firebase(config):
    """Initializes and returns the Firebase app and firestore objects."""
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
            "universe_domain": config.get("universe_domain", "") ,
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


# --- Authentication and State Management ---

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
    st.session_state.journal_analysis = None
    st.session_state.goals = []
    if 'chat_history' in st.session_state:
        st.session_state.chat_history = []
    if 'journal_entries' in st.session_state:
        st.session_state.journal_entries = []
    st.info("You have been logged out.")
    st.rerun()

# --- Firestore Data Path and Persistence ---

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
        goals_data = [{**doc.to_dict(), 'id': doc.id} for doc in goals_docs]
        goals_data.sort(key=lambda x: x.get('created_at', 0), reverse=True)

        return chat_data, journal_data, goals_data
    except Exception as e:
        st.error(f"Error loading data: {e}")
        return [], [], []

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
        if 'chat_history' not in st.session_state:
            st.session_state.chat_history = []
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
        
        # Reload and update session state (partial reload for only necessary data)
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
        "status": "Active"
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

def update_goal_status_worker(goal_id, new_status):
    """Updates the status of a specific goal in Firestore and updates the session state in place."""
    try:
        goals_ref = get_user_goals_collection_ref(st.session_state.current_user_email)
        goal_doc_ref = goals_ref.document(goal_id)
        
        goal_doc_ref.update({"status": new_status})
        
        title = "Goal"
        for goal in st.session_state.goals:
            if goal.get('id') == goal_id:
                goal['status'] = new_status
                title = goal.get('title', 'Goal')
                break
                
        st.success(f"Goal '{title}' updated to {new_status}!")
    except Exception as e:
        st.error(f"Failed to update goal status: {e}")

def delete_goal_worker(goal_id):
    """Deletes a specific goal from Firestore and updates the session state in place."""
    try:
        goals_ref = get_user_goals_collection_ref(st.session_state.current_user_email)
        goals_ref.document(goal_id).delete()
        
        st.session_state.goals = [g for g in st.session_state.goals if g.get('id') != goal_id]
        
        st.success("Goal deleted successfully.")
    except Exception as e:
        st.error(f"Failed to delete goal: {e}")


# --- Gemini API Calls ---

def call_gemini_api(payload, is_json_response=False):
    """Utility function to handle the API request with exponential backoff."""
    headers = {'Content-Type': 'application/json'}
    max_retries = 3
    
    for attempt in range(max_retries):
        try:
            response = requests.post(GEMINI_API_URL, headers=headers, data=json.dumps(payload))
            response.raise_for_status()
            result = response.json()
            candidates = result.get('candidates', [])
            if not candidates:
                return None
            candidate = candidates[0]
            
            if is_json_response:
                json_text = candidate.get('content', {}).get('parts', [{}])[0].get('text')
                if json_text:
                    cleaned = json_text.strip()
                    if cleaned.startswith('```') and cleaned.endswith('```'):
                        cleaned = cleaned.strip('`').strip('json')
                    try:
                        return json.loads(cleaned)
                    except json.JSONDecodeError:
                        import re
                        match = re.search(r"\{[\s\S]*\}", cleaned)
                        if match:
                            return json.loads(match.group(0))
                        return None
                return None
            else:
                return candidate.get('content', {}).get('parts', [{}])[0].get('text')

        except (requests.exceptions.RequestException, json.JSONDecodeError, Exception) as e:
            if attempt < max_retries - 1:
                wait_time = 2 ** attempt
                time.sleep(wait_time)
                continue
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
    
    return call_gemini_api(payload, is_json_response=False)
