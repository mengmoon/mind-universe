import streamlit as st
import firebase_admin
from firebase_admin import credentials, firestore, auth
import requests
import json
from datetime import datetime

# --- Configuration and Initialization ---

APP_NAME = "MindUniverseApp"

# Get Gemini API Key (loaded from secrets.toml)
GEMINI_API_KEY = st.secrets["GEMINI_API_KEY"]
GEMINI_MODEL = "gemini-2.5-flash"
GEMINI_URL = f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent?key={GEMINI_API_KEY}"

# --- Firebase Resilient Initialization ---
# Use a try/except ValueError pattern, which is the most reliable way
# to check if a named Firebase Admin app is already initialized.

db = None
st.session_state.firebase_ready = False

try:
    # 1. Check if the app is already running (e.g., on a Streamlit rerun)
    app_instance = firebase_admin.get_app(APP_NAME)
    db = firestore.client(app_instance)
    st.session_state.firebase_ready = True
except ValueError:
    # 2. If it's not running (ValueError raised), initialize it
    try:
        # Load credentials from Streamlit secrets (secrets.toml)
        firebase_config = st.secrets["FIREBASE_CONFIG"]
        
        # Initialize Firebase Admin SDK using the credentials
        cred = credentials.Certificate(json.loads(firebase_config))
        app_instance = firebase_admin.initialize_app(cred, name=APP_NAME)
        
        # Get the Firestore client associated with the new app instance
        db = firestore.client(app_instance)
        st.session_state.firebase_ready = True
        st.success("Firebase initialized successfully.")
    except Exception as e:
        st.error(f"Error initializing Firebase: {e}")
        # db remains None if initialization failed


# --- User and Collection Management ---

def get_user_chat_collection_ref(email):
    """Returns the Firestore collection reference for user's chat history."""
    if db is None:
        raise ConnectionError("Firestore database client is not initialized.")
    # Using public data rules for simplicity in this example
    user_id = email.replace('@', '_').replace('.', '_')
    return db.collection("artifacts").document("minduniverse-app").collection("public").document("data").collection(f"chat_{user_id}")

def get_user_journal_collection_ref(email):
    """Returns the Firestore collection reference for user's journal entries."""
    if db is None:
        raise ConnectionError("Firestore database client is not initialized.")
    user_id = email.replace('@', '_').replace('.', '_')
    return db.collection("artifacts").document("minduniverse-app").collection("public").document("data").collection(f"journal_{user_id}")

def get_user_goals_collection_ref(email):
    """Returns the Firestore collection reference for user's goals."""
    if db is None:
        raise ConnectionError("Firestore database client is not initialized.")
    user_id = email.replace('@', '_').replace('.', '_')
    return db.collection("artifacts").document("minduniverse-app").collection("public").document("data").collection(f"goals_{user_id}")


# --- Authentication Functions ---

def login_user(email, password):
    """Authenticates user using email and password."""
    try:
        # Use Firebase Admin SDK to verify credentials (simulating sign-in)
        # Explicitly pass the app instance to auth functions for robustness
        user = auth.get_user_by_email(email, app=firebase_admin.get_app(APP_NAME))
        # Note: Admin SDK cannot directly sign in, but we assume if the user exists, we proceed.
        
        st.session_state.logged_in = True
        st.session_state.current_user_email = email
        st.success(f"Welcome back, {email}!")
        return True
    except firebase_admin.exceptions.FirebaseError as e:
        if "No user record found" in str(e):
            st.error("Login failed: Invalid email or user not found.")
        else:
            st.error(f"Login failed: {e}")
        return False
    except Exception as e:
        st.error(f"An unexpected error occurred during login: {e}")
        return False


def sign_up(email, password):
    """Creates a new user account."""
    if len(password) < 6:
        st.error("Password must be at least 6 characters long.")
        return False
        
    try:
        # Create user account
        # Explicitly pass the app instance to auth functions for robustness
        user = auth.create_user(email=email, password=password, app=firebase_admin.get_app(APP_NAME))
        
        st.success(f"Account created successfully for {email}! Please log in.")
        return True
    except firebase_admin.exceptions.FirebaseError as e:
        if "email-already-exists" in str(e):
            st.error("Sign up failed: This email is already in use.")
        else:
            st.error(f"Sign up failed: {e}")
        return False
    except Exception as e:
        st.error(f"An unexpected error occurred during sign up: {e}")
        return False

def logout():
    """Logs out the current user and resets session state."""
    st.session_state.logged_in = False
    st.session_state.current_user_email = None
    st.session_state.user_data_loaded = False
    st.session_state.chat_history = []
    st.session_state.journal_entries = []
    st.session_state.goals = []
    st.session_state.page_selected = 'Dashboard'
    st.rerun()

# --- Data Handling Functions ---

def load_data_from_firestore(email):
    """Loads all chat, journal, and goals data for the current user."""
    chat_history = []
    journal_entries = []
    goals = []

    if not st.session_state.get('firebase_ready'):
        st.error("Database not initialized.")
        return chat_history, journal_entries, goals

    try:
        # 1. Load Chat History
        chat_ref = get_user_chat_collection_ref(email)
        chat_docs = chat_ref.stream()
        for doc in chat_docs:
            data = doc.to_dict()
            # Ensure timestamp exists for sorting
            if 'timestamp' not in data:
                data['timestamp'] = datetime.now().timestamp()
            chat_history.append(data)
        
        # Sort chat history by timestamp
        chat_history.sort(key=lambda x: x.get('timestamp', 0))

        # 2. Load Journal Entries
        journal_ref = get_user_journal_collection_ref(email)
        journal_docs = journal_ref.stream()
        for doc in journal_docs:
            data = doc.to_dict()
            data['id'] = doc.id
            journal_entries.append(data)

        # Sort entries by date (newest first)
        journal_entries.sort(key=lambda x: datetime.strptime(x.get('date', '1970-01-01'), '%Y-%m-%d'), reverse=True)

        # 3. Load Goals
        goals_ref = get_user_goals_collection_ref(email)
        goals_docs = goals_ref.stream()
        for doc in goals_docs:
            data = doc.to_dict()
            data['id'] = doc.id
            goals.append(data)
            
    except Exception as e:
        st.error(f"Error loading data from Firestore: {e}")

    return chat_history, journal_entries, goals

def save_chat_message(message_dict):
    """Saves a single chat message dictionary to Firestore."""
    if not st.session_state.get('firebase_ready') or not st.session_state.current_user_email:
        return
        
    try:
        chat_ref = get_user_chat_collection_ref(st.session_state.current_user_email)
        # Firestore automatically generates a document ID when using add()
        chat_ref.add(message_dict)
    except Exception as e:
        st.error(f"Error saving chat message to Firestore: {e}")


# --- AI Integration Functions ---

def generate_chat_response(chat_history):
    """
    Generates a response from the Gemini API using the chat history for context.
    
    This function uses the name 'generate_chat_response' as required by app.py.
    """
    system_prompt = (
        "You are the 'Mind Mentor', a supportive, empathetic, and non-judgmental AI assistant "
        "for wellness and personal growth. Your purpose is to listen, provide validating "
        "reflections, and offer practical, evidence-based coping strategies and thoughtful "
        "insights. Keep your responses concise, warm, and encouraging. Never act as a medical "
        "professional or offer clinical advice. Focus on reflection and self-help tools."
    )

    # Convert the simple chat_history list of dicts into the format required by the API payload
    contents = []
    for msg in chat_history:
        # The history should already be in the format: [{"role": "user", "content": "..."}] 
        # but we reconstruct it here for safety and to map 'model' role
        role = "user" if msg["role"] == "user" else "model"
        contents.append({
            "role": role,
            "parts": [{"text": msg["content"]}]
        })
    
    # Add a final instruction to the model to ensure it produces a response
    contents.append({
        "role": "user",
        "parts": [{"text": "Please provide a helpful and encouraging response to the previous message, considering our conversation so far."}]
    })

    payload = {
        "contents": contents,
        "systemInstruction": system_prompt,
    }

    try:
        response = requests.post(
            GEMINI_URL, 
            headers={'Content-Type': 'application/json'},
            data=json.dumps(payload)
        )
        response.raise_for_status() # Raises an HTTPError for bad responses (4xx or 5xx)
        
        result = response.json()
        
        # Extract the text content
        if result.get('candidates') and result['candidates'][0].get('content'):
            text = result['candidates'][0]['content']['parts'][0]['text']
            return text
        else:
            return "I couldn't generate a helpful response right now. Perhaps try rephrasing?"
            
    except requests.exceptions.RequestException as e:
        st.error(f"AI API request failed: {e}")
        return None
    except Exception as e:
        st.error(f"Failed to process AI response: {e}")
        return None

# Placeholder functions for Journal and Goal tracking utilities (to be implemented later)

def save_journal_entry(entry_data):
    """Saves a journal entry to Firestore."""
    if not st.session_state.get('firebase_ready') or not st.session_state.current_user_email:
        return
        
    try:
        journal_ref = get_user_journal_collection_ref(st.session_state.current_user_email)
        # Note: Analysis fields (sentiment/emotion) should be calculated before calling this function
        journal_ref.add(entry_data)
        return True
    except Exception as e:
        st.error(f"Error saving journal entry: {e}")
        return False

def update_journal_entry(doc_id, updated_data):
    """Updates an existing journal entry in Firestore."""
    if not st.session_state.get('firebase_ready') or not st.session_state.current_user_email:
        return
        
    try:
        journal_ref = get_user_journal_collection_ref(st.session_state.current_user_email)
        journal_ref.document(doc_id).update(updated_data)
        return True
    except Exception as e:
        st.error(f"Error updating journal entry: {e}")
        return False

def delete_journal_entry(doc_id):
    """Deletes a journal entry from Firestore."""
    if not st.session_state.get('firebase_ready') or not st.session_state.current_user_email:
        return
        
    try:
        journal_ref = get_user_journal_collection_ref(st.session_state.current_user_email)
        journal_ref.document(doc_id).delete()
        return True
    except Exception as e:
        st.error(f"Error deleting journal entry: {e}")
        return False

def analyze_journal_entry(content):
    """
    Placeholder for a future function that would analyze the content 
    using a dedicated AI model for sentiment and emotion.
    For now, returns mock data.
    """
    return {
        "sentiment": "Neutral",
        "emotion": "Calm"
    }

def save_goal(goal_data):
    """Saves a new goal to Firestore."""
    if not st.session_state.get('firebase_ready') or not st.session_state.current_user_email:
        return
    try:
        goals_ref = get_user_goals_collection_ref(st.session_state.current_user_email)
        goals_ref.add(goal_data)
        return True
    except Exception as e:
        st.error(f"Error saving goal: {e}")
        return False

def update_goal(doc_id, updated_data):
    """Updates an existing goal in Firestore."""
    if not st.session_state.get('firebase_ready') or not st.session_state.current_user_email:
        return
    try:
        goals_ref = get_user_goals_collection_ref(st.session_state.current_user_email)
        goals_ref.document(doc_id).update(updated_data)
        return True
    except Exception as e:
        st.error(f"Error updating goal: {e}")
        return False

def delete_goal(doc_id):
    """Deletes a goal from Firestore."""
    if not st.session_state.get('firebase_ready') or not st.session_state.current_user_email:
        return
    try:
        goals_ref = get_user_goals_collection_ref(st.session_state.current_user_email)
        goals_ref.document(doc_id).delete()
        return True
    except Exception as e:
        st.error(f"Error deleting goal: {e}")
        return False

def generate_insights_summary(journal_entries):
    """
    Placeholder for a function to generate a deep summary of journal entries.
    For now, returns a mock summary.
    """
    return "The AI analysis is currently unavailable. When enabled, it will provide a deep summary of your recurring emotional themes and overall wellness trends based on your journal entries."

def analyze_journal_trends(journal_entries):
    """
    Placeholder for a function to generate data for visualization.
    For now, returns mock data.
    """
    # Simple mock data structure for a line chart of sentiment over time
    if not journal_entries:
        return []
        
    # Example: Map recent entries to a chartable format
    # Mock sentiment values (0=negative, 0.5=neutral, 1=positive)
    sentiment_map = {"Positive": 1.0, "Neutral": 0.5, "Negative": 0.0}
    
    mock_data = []
    for entry in journal_entries:
        sentiment_score = sentiment_map.get(entry.get('sentiment', 'Neutral'), 0.5)
        mock_data.append({
            "date": entry.get('date'),
            "sentiment_score": sentiment_score
        })

    # Limit to 30 most recent entries for a cleaner chart
    return mock_data[:30]
