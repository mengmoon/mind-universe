# --- Mind Universe: A Digital Space for Mental Wellness and Self-Exploration ---
# Uses Streamlit for the UI, Firebase for secure data persistence, and
# Google Gemini API for AI chat (text only) and Text-to-Speech (TTS).

import streamlit as st
import requests
import json
import pandas as pd
from datetime import datetime
import hashlib # Used for simple password hashing simulation
import base64 # Needed for handling TTS base64 audio data

# --- 1. Global Configuration and Secrets Loading ---
# Load secrets configuration from environment variables (Streamlit secrets)

# Load Firebase Config
try:
    # Attempt to load the Firebase config JSON from the environment variable.
    firebase_config_str = st.secrets["FIREBASE_CONFIG"]

    # CRITICAL FIX for Private Key: Un-escape escaped newlines
    if isinstance(firebase_config_str, str):
        firebase_config_str = firebase_config_str.replace('\\\\n', '\\n')
        firebase_config_str = firebase_config_str.strip().strip('"').strip("'")
        
    firebaseConfig = json.loads(firebase_config_str)
    
except Exception as e:
    st.error(f"Failed to parse FIREBASE_CONFIG as JSON. Ensure the format is correct: {e}")
    st.stop()

# Load Gemini API Key
GEMINI_API_KEY = st.secrets.get("GEMINI_API_KEY", "")
if not GEMINI_API_KEY:
    st.error("GEMINI_API_KEY not found in Streamlit secrets. Please configure it to use the AI Mentor.")
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
        
        # Check if the app is already initialized
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

# Initialize authentication state
if 'logged_in' not in st.session_state:
    st.session_state.logged_in = False
if 'current_user_email' not in st.session_state:
    st.session_state.current_user_email = None
if 'user_data_loaded' not in st.session_state:
    st.session_state.user_data_loaded = False
if 'use_tts' not in st.session_state:
    st.session_state.use_tts = False


def hash_password(password):
    """Simple password hashing simulation using SHA-256."""
    return hashlib.sha256(password.encode()).hexdigest()

def get_users_collection_ref():
    """Returns the Firestore reference for the global users collection (public/data path)."""
    # This is a general collection for all app users
    app_id = firebaseConfig["project_id"]
    # Path: /artifacts/{appId}/public/data/users
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
                st.session_state.user_data_loaded = False # Force reload data
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
    if 'chat_history' in st.session_state:
        st.session_state.chat_history = []
    if 'journal_entries' in st.session_state:
        st.session_state.journal_entries = []
    st.info("You have been logged out.")
    st.rerun()

# --- 4. Firestore Data Path and Persistence ---

# Use the user's email as the user_id for private data path
def get_user_chat_collection_ref(user_id):
    """Returns the Firestore reference for the user's chat history."""
    # Private data path: /artifacts/{appId}/users/{userId}/chat_history
    app_id = firebaseConfig["project_id"]
    return db.collection('artifacts').document(app_id).collection('users').document(user_id).collection('chat_history')

def get_user_journal_collection_ref(user_id):
    """Returns the Firestore reference for the user's journal entries."""
    # Private data path: /artifacts/{appId}/users/{userId}/journal_entries
    app_id = firebaseConfig["project_id"]
    return db.collection('artifacts').document(app_id).collection('users').document(user_id).collection('journal_entries')

# Data loading function
def load_data_from_firestore(user_id):
    """Loads all chat and journal data for the authenticated user."""
    
    # Load Chat History
    try:
        chat_ref = get_user_chat_collection_ref(user_id)
        chat_docs = chat_ref.stream()
        chat_data = [doc.to_dict() for doc in chat_docs]
        chat_data.sort(key=lambda x: x.get('timestamp', 0))
        
        # Load Journal Entries
        journal_ref = get_user_journal_collection_ref(user_id)
        journal_docs = journal_ref.stream()
        journal_data = [doc.to_dict() for doc in journal_docs]
        journal_data.sort(key=lambda x: datetime.strptime(x.get('date', '1970-01-01'), '%Y-%m-%d'), reverse=True)

        return chat_data, journal_data
    except Exception as e:
        st.error(f"Error loading data: {e}")
        return [], []

# Firebase Write Functions
def save_chat_message(role, content, audio_data=None):
    """Saves a single chat message to Firestore and updates session state."""
    timestamp = datetime.now().timestamp()
    message = {
        "role": role,
        "content": content,
        "timestamp": timestamp,
        "audio_data": audio_data # Save audio data if available
    }
    try:
        chat_ref = get_user_chat_collection_ref(st.session_state.current_user_email)
        chat_ref.add(message)
        st.session_state.chat_history.append(message)
    except Exception as e:
        st.error(f"Failed to save message: {e}")

def save_journal_entry(date, title, content):
    """Saves a journal entry to Firestore and updates session state."""
    entry = {
        "date": date,
        "title": title,
        "content": content,
        "timestamp": datetime.now().timestamp()
    }
    try:
        journal_ref = get_user_journal_collection_ref(st.session_state.current_user_email)
        journal_ref.add(entry)
        
        # Force reload and update session state
        _, new_journal_data = load_data_from_firestore(st.session_state.current_user_email)
        st.session_state.journal_entries = new_journal_data
        st.success("Journal entry saved!")
    except Exception as e:
        st.error(f"Failed to save journal entry: {e}")


# --- 5. LLM API Call Functions (Gemini Text and TTS) ---

GEMINI_TEXT_MODEL = "gemini-2.5-flash"
GEMINI_TTS_MODEL = "gemini-2.5-flash-preview-tts"
TTS_VOICE_NAME = "Kore" # Using a clear voice (Kore: Firm)

GEMINI_API_URL = f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_TEXT_MODEL}:generateContent?key={GEMINI_API_KEY}"
GEMINI_TTS_API_URL = f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_TTS_MODEL}:generateContent?key={GEMINI_API_KEY}"

def generate_ai_text_reply(user_prompt):
    """Calls the Gemini API for text generation."""
    
    # Construct chat history for context
    chat_contents = [
        {"role": "user" if msg["role"] == "user" else "model", 
         "parts": [{"text": msg["content"]}]}
        for msg in st.session_state.chat_history
    ]
    chat_contents.append({"role": "user", "parts": [{"text": user_prompt}]})

    # Define the system prompt for the AI Mentor persona
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

    try:
        response = requests.post(
            GEMINI_API_URL, 
            headers={'Content-Type': 'application/json'}, 
            data=json.dumps(payload)
        )
        response.raise_for_status()
        result = response.json()
        
        candidate = result.get('candidates', [{}])[0]
        text = candidate.get('content', {}).get('parts', [{}])[0].get('text')
        
        if not text:
            st.error("The AI mentor's response was empty or filtered.")
            return None
            
        return text

    except requests.exceptions.RequestException as e:
        st.error(f"API Request Failed (Text): {e}")
        return None
    except Exception as e:
        st.error(f"An unexpected error occurred (Text): {e}")
        return None

def generate_tts_audio(text_to_speak):
    """Calls the Gemini TTS API and returns base64 audio data."""
    
    payload = {
        "contents": [{
            "parts": [{ "text": text_to_speak }]
        }],
        "generationConfig": {
            "responseModalities": ["AUDIO"],
            "speechConfig": {
                "voiceConfig": {
                    "prebuiltVoiceConfig": { "voiceName": TTS_VOICE_NAME }
                }
            }
        },
        "model": GEMINI_TTS_MODEL
    }

    try:
        tts_response = requests.post(
            GEMINI_TTS_API_URL, 
            headers={'Content-Type': 'application/json'}, 
            data=json.dumps(payload)
        )
        tts_response.raise_for_status()
        tts_result = tts_response.json()

        part = tts_result.get('candidates', [{}])[0].get('content', {}).get('parts', [{}])[0]
        audio_data_base64 = part.get('inlineData', {}).get('data')
        
        return audio_data_base64

    except requests.exceptions.RequestException as e:
        st.warning(f"TTS API Request Failed: {e}")
        return None
    except Exception as e:
        st.warning(f"An unexpected error occurred (TTS): {e}")
        return None

# --- 6. UI Components ---

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
            chat_data, journal_data = load_data_from_firestore(st.session_state.current_user_email)
            st.session_state.chat_history = chat_data
            st.session_state.journal_entries = journal_data
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
        st.caption("Securely store and manage your data with Firebase.")
        
        # Download/Export function remains the same
        def generate_export_content():
            export_text = f"--- Mind Universe Data Export for User: {st.session_state.current_user_email} ---\n"
            export_text += f"Export Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
            
            # 1. Journal Entries
            export_text += "============== JOURNAL ENTRIES ==============\n"
            if st.session_state.journal_entries:
                for entry in st.session_state.journal_entries:
                    export_text += f"Date: {entry.get('date', 'N/A')}\n"
                    export_text += f"Title: {entry.get('title', 'No Title')}\n"
                    export_text += f"Content:\n{entry.get('content', 'No content')}\n"
                    export_text += "-" * 20 + "\n"
            else:
                export_text += "No journal entries found.\n\n"
                
            # 2. Chat History
            export_text += "\n============== CHAT HISTORY ==============\n"
            if st.session_state.chat_history:
                sorted_chat = sorted(st.session_state.chat_history, key=lambda x: x.get('timestamp', 0))
                for message in sorted_chat:
                    dt_object = datetime.fromtimestamp(message.get('timestamp', 0))
                    time_str = dt_object.strftime('%Y-%m-%d %H:%M:%S')
                    role = message.get('role', 'unknown').upper()
                    content = message.get('content', '')
                    export_text += f"[{time_str}] {role}: {content}\n"
                    if message.get('audio_data'):
                        export_text += f"[-- AUDIO DATA STORED --]\n"
            else:
                export_text += "No chat messages found.\n"
                
            return export_text.encode('utf-8')

        st.download_button(
            label="Download History (TXT)",
            data=generate_export_content(),
            file_name=f"mind_universe_export_{datetime.now().strftime('%Y%m%d')}.txt",
            mime="text/plain",
            help="Downloads all journal entries and chat history into a single text file."
        )
        
        # --- Clear History (Delete functionality remains) ---
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

    # --- Tabbed Application Interface ---

    tab_journal, tab_mentor, tab_voice = st.tabs(["✍️ Wellness Journal", "💬 AI Mentor", "🎙️ Voice Input"])

    # --- Tab 1: Wellness Journal ---
    with tab_journal:
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
                st.rerun() # Rerun to display the newly saved entry
            elif submitted and not entry_content:
                st.warning("Please write some content before saving.")

        st.divider()

        # Display History
        st.subheader("Journal History")
        if st.session_state.journal_entries:
            for entry in st.session_state.journal_entries:
                with st.expander(f"**{entry.get('date')}** — {entry.get('title', 'Untitled Entry')}"):
                    st.markdown(entry.get('content'))
        else:
            st.info("No journal entries found. Start writing above!")

    # --- Tab 2: AI Mentor (Text Chat) ---
    with tab_mentor:
        st.header("Ask Your Mentor")
        st.caption("Chat with your supportive AI mentor for insights, coping strategies, and reflections.")
        
        # TTS Toggle and Warning
        st.session_state.use_tts = st.checkbox("Enable AI Voice Response (TTS)", value=st.session_state.use_tts)
        if st.session_state.use_tts:
            st.warning("⚠️ The TTS API returns raw audio data (PCM). Playback in this Streamlit environment may not work correctly without browser-side conversion. Functionality is included to demonstrate integration.")
        
        st.divider()

        # Display chat history
        for message in st.session_state.chat_history:
            role = "user" if message["role"] == "user" else "assistant"
            avatar = "👤" if role == "user" else "🧠"
            with st.chat_message(role, avatar=avatar):
                st.markdown(message["content"])
                
                # Display audio if available and role is assistant
                if message.get("audio_data") and role == "assistant":
                    audio_base64 = message["audio_data"]
                    # Use a data URI for the audio tag. Mime type for raw PCM is audio/L16.
                    # We use audio/wav as a general fallback for browser rendering, though conversion is still needed.
                    audio_html = f"""
                    <audio controls autoplay style="width: 100%;">
                        <source src="data:audio/wav;base64,{audio_base64}" type="audio/wav">
                        Your browser does not support the audio element.
                    </audio>
                    """
                    st.markdown(audio_html, unsafe_allow_html=True)


        # Chat input
        if prompt := st.chat_input("Type your message to Mind Mentor..."):
            # Display user message and save
            with st.chat_message("user", avatar="👤"):
                st.markdown(prompt)
            save_chat_message("user", prompt)

            # Generate AI response (Text first)
            with st.chat_message("assistant", avatar="🧠"):
                with st.spinner("Mind Mentor is reflecting..."):
                    ai_response_text = generate_ai_text_reply(prompt)
                    ai_response_audio = None
                    
                    if ai_response_text and st.session_state.use_tts:
                        # Generate TTS Audio
                        with st.spinner("Generating voice response..."):
                            # Only send the text response for speaking
                            ai_response_audio = generate_tts_audio(ai_response_text)
                    
                if ai_response_text:
                    st.markdown(ai_response_text)
                    
                    # Display the audio player if audio data was generated (for the current turn only)
                    if ai_response_audio:
                        audio_html = f"""
                        <audio controls autoplay style="width: 100%;">
                            <source src="data:audio/wav;base64,{ai_response_audio}" type="audio/wav">
                            Your browser does not support the audio element.
                        </audio>
                        """
                        st.markdown(audio_html, unsafe_allow_html=True)
                        
                    # Save the response (text and optional audio)
                    save_chat_message("model", ai_response_text, ai_response_audio)
                    st.rerun() # Force rerun to update the chat history display immediately

    # --- Tab 3: Voice Input ---
    with tab_voice:
        st.header("🎙️ Voice Input (Push-to-Talk Simulation)")
        st.caption("Interact with Mind Mentor hands-free. The response will be visible in the 'AI Mentor' tab.")
        
        st.info("Since Streamlit runs on a Python server, we cannot directly access your microphone for Speech-to-Text (STT). We'll simulate the process by having you type what you would have spoken into the box below.")
        
        with st.form("voice_input_form", clear_on_submit=True):
            # This simulates the transcribed text from an STT model
            spoken_prompt = st.text_area(
                "1. Type your transcribed voice message here:", 
                height=150,
                placeholder="E.g., 'Mind Mentor, I'm feeling stressed about my work deadlines. What's a quick coping technique?'"
            )

            # This simulates the "release" of the push-to-talk button
            voice_submitted = st.form_submit_button("2. Send Spoken Message to Mentor (Simulated STT)", type="primary")

            if voice_submitted and spoken_prompt:
                
                # Execute the chat logic:
                # 1. Save user prompt
                save_chat_message("user", spoken_prompt)

                with st.spinner("Mind Mentor is reflecting on your spoken words..."):
                    # 2. Generate text reply
                    ai_response_text = generate_ai_text_reply(spoken_prompt)
                    ai_response_audio = None
                    
                    if ai_response_text and st.session_state.use_tts:
                        # 3. Generate TTS Audio if enabled
                        with st.spinner("Generating voice response..."):
                            ai_response_audio = generate_tts_audio(ai_response_text)
                            
                if ai_response_text:
                    # 4. Save the response (text and optional audio)
                    save_chat_message("model", ai_response_text, ai_response_audio)
                    
                    st.success("Message sent! Check the 'AI Mentor' tab for the response (and audio if TTS is enabled).")
                    
                    st.rerun()
                
            elif voice_submitted and not spoken_prompt:
                st.warning("Please type your simulated spoken message.")
# --- Main Application Logic ---

if __name__ == '__main__':
    if st.session_state.logged_in:
        display_main_app()
    else:
        display_auth_page()
