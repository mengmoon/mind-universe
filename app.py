# --- Mind Universe: A Digital Space for Mental Wellness and Self-Exploration ---
# Uses Streamlit for the UI, Firebase for secure data persistence, and
# Google Gemini API for AI chat (text and text-to-speech).

import streamlit as st
import requests
import json
import pandas as pd
from datetime import datetime
import io
import base64
import re
import time # ADDED FOR EXPONENTIAL BACKOFF

# --- 1. Global Configuration and Secrets Loading ---
# Load secrets configuration from environment variables (Streamlit secrets)
# These variables are automatically injected by the environment.

# Load Firebase Config
try:
    # Attempt to load the Firebase config JSON from the environment variable.
    # It must be read as a string and parsed.
    firebase_config_str = st.secrets["FIREBASE_CONFIG"]

    # CRITICAL FIX for Private Key:
    # The private key often contains escaped newlines (\\n). We need to un-escape them 
    # to be single newlines (\n) before the Python Firebase SDK can use the certificate.
    # We also defensively strip surrounding quotes and whitespace.
    if isinstance(firebase_config_str, str):
        # 1. Replace doubly escaped newlines with singly escaped newlines
        firebase_config_str = firebase_config_str.replace('\\\\n', '\\n')
        # 2. Strip leading/trailing whitespace/quotes just in case of bad paste
        firebase_config_str = firebase_config_str.strip().strip('"').strip("'")
        
    firebaseConfig = json.loads(firebase_config_str)
    
except Exception as e:
    st.error(f"Failed to parse FIREBASE_CONFIG as JSON: {e}")
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
    """Initializes and returns the Firebase app, auth, and firestore objects."""
    import firebase_admin
    from firebase_admin import credentials, firestore, auth

    # To use service account credentials, we must convert the config dict
    # into a ServiceAccount credential object.
    try:
        # NOTE: The private_key must contain actual '\n' characters, which is handled
        # in the loading block above.
        
        # We need to construct a dictionary containing the service account info
        # from the larger firebaseConfig object.
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
        
        # Note: We cannot return the auth object directly from the initialized app 
        # because the Firebase Admin SDK does not expose the client-side Auth methods
        # that allow anonymous sign-in via st.experimental_user.email/uid.
        # We rely on st.experimental_user for basic authentication details, 
        # or we would need to implement a full client-side sign-in flow.
        return db

    except Exception as e:
        # This catches errors like "Invalid private key"
        st.error(f"Failed to initialize Firebase: {e}")
        st.stop()
        
db = initialize_firebase(firebaseConfig)

# Get current user ID (using Streamlit's experimental user feature for simplicity)
if 'user_id' not in st.session_state:
    # Safely retrieve user attributes using getattr to prevent AttributeError
    user_id = getattr(st.experimental_user, 'id', None)
    user_email = getattr(st.experimental_user, 'email', None)

    # Use retrieved attributes or fall back to anonymous defaults
    st.session_state.user_id = user_id if user_id else "anonymous_user"
    st.session_state.user_email = user_email if user_email else "Anonymous"

# --- 3. Firestore Data Path Configuration ---

# Use the user_id to define the secure, user-specific data path
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

# --- 4. State Management and Data Loading ---

# Initialize chat and journal states
if 'chat_history' not in st.session_state:
    st.session_state.chat_history = []
if 'journal_entries' not in st.session_state:
    st.session_state.journal_entries = []
if 'latest_wav_bytes' not in st.session_state:
    st.session_state.latest_wav_bytes = None

# Placeholder function to load data from Firestore (run once)
@st.cache_data(show_spinner="Loading data from the Universe...")
def load_data_from_firestore(user_id):
    """Loads all chat and journal data for the user."""
    
    # Load Chat History
    try:
        chat_ref = get_user_chat_collection_ref(user_id)
        chat_docs = chat_ref.stream()
        chat_data = [doc.to_dict() for doc in chat_docs]
        # Sort chat data by timestamp for correct display order
        chat_data.sort(key=lambda x: x.get('timestamp', 0))
        
        # Load Journal Entries
        journal_ref = get_user_journal_collection_ref(user_id)
        journal_docs = journal_ref.stream()
        journal_data = [doc.to_dict() for doc in journal_docs]
        # Sort journal entries by date
        journal_data.sort(key=lambda x: datetime.strptime(x.get('date', '1970-01-01'), '%Y-%m-%d'), reverse=True)

        return chat_data, journal_data
    except Exception as e:
        st.error(f"Error loading data: {e}")
        return [], []

# Load data on app startup
chat_data, journal_data = load_data_from_firestore(st.session_state.user_id)
st.session_state.chat_history = chat_data
st.session_state.journal_entries = journal_data

# --- 5. Firebase Write Functions ---

def save_chat_message(role, content):
    """Saves a single chat message to Firestore and updates session state."""
    timestamp = datetime.now().timestamp()
    message = {
        "role": role,
        "content": content,
        "timestamp": timestamp
    }
    try:
        chat_ref = get_user_chat_collection_ref(st.session_state.user_id)
        chat_ref.add(message)
        st.session_state.chat_history.append(message)
        # Clear the cache so new data is loaded on refresh/re-run
        load_data_from_firestore.clear()
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
        journal_ref = get_user_journal_collection_ref(st.session_state.user_id)
        journal_ref.add(entry)
        
        # Force reload journal data to reflect change and maintain sort order
        _, st.session_state.journal_entries = load_data_from_firestore(st.session_state.user_id)
        # Clear the cache so new data is loaded on refresh/re-run
        load_data_from_firestore.clear()
    except Exception as e:
        st.error(f"Failed to save journal entry: {e}")

# --- 6. LLM API Call Functions (Gemini) ---

GEMINI_TEXT_MODEL = "gemini-2.5-flash"
GEMINI_TTS_MODEL = "gemini-2.5-flash-preview-tts"
GEMINI_API_URL = f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_TEXT_MODEL}:generateContent?key={GEMINI_API_KEY}"
GEMINI_TTS_API_URL = f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_TTS_MODEL}:generateContent?key={GEMINI_API_KEY}"

def generate_ai_reply(user_prompt):
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
        
        # Check for safety filtering or length limits
        finish_reason = candidate.get('finishReason')
        if finish_reason == "SAFETY":
            st.error("The AI mentor's response was filtered due to safety settings. Please rephrase your query.")
            return None
        elif finish_reason == "MAX_TOKENS":
            st.error("The AI mentor's response was too long. Please try a more specific question.")
            return None
        
        # Extract the content
        text = candidate.get('content', {}).get('parts', [{}])[0].get('text')
        
        if not text:
            # Check if any content was returned but failed the finish reason check
            st.error(f"The AI mentor's response was empty or filtered. Finish Reason: {finish_reason}")
            return None
            
        return text

    except requests.exceptions.RequestException as e:
        st.error(f"API Request Failed: {e}")
        return None
    except Exception as e:
        st.error(f"An unexpected error occurred: {e}")
        return None

def pcm_to_wav(pcm_data, sample_rate=24000, channels=1, bits_per_sample=16):
    """Converts raw signed 16-bit PCM audio data to WAV format."""
    
    # 1. WAV Header (44 bytes)
    wav_header = io.BytesIO()

    # RIFF chunk descriptor
    wav_header.write(b'RIFF')  # Chunk ID
    data_size = len(pcm_data)
    chunk_size = 36 + data_size
    wav_header.write(chunk_size.to_bytes(4, 'little'))  # Chunk Size
    wav_header.write(b'WAVE')  # Format

    # fmt sub-chunk
    wav_header.write(b'fmt ')  # Sub-chunk 1 ID
    wav_header.write((16).to_bytes(4, 'little'))  # Sub-chunk 1 Size (16 for PCM)
    wav_header.write((1).to_bytes(2, 'little'))  # Audio Format (1 for PCM)
    wav_header.write(channels.to_bytes(2, 'little'))  # Num Channels
    wav_header.write(sample_rate.to_bytes(4, 'little'))  # Sample Rate
    
    byte_rate = sample_rate * channels * (bits_per_sample // 8)
    wav_header.write(byte_rate.to_bytes(4, 'little'))  # Byte Rate
    
    block_align = channels * (bits_per_sample // 8)
    wav_header.write(block_align.to_bytes(2, 'little'))  # Block Align
    wav_header.write(bits_per_sample.to_bytes(2, 'little'))  # Bits Per Sample

    # data sub-chunk
    wav_header.write(b'data')  # Sub-chunk 2 ID
    wav_header.write(data_size.to_bytes(4, 'little'))  # Sub-chunk 2 Size

    # 2. Combine Header and Data
    wav_bytes = wav_header.getvalue() + pcm_data

    return wav_bytes

def generate_tts_reply(user_prompt):
    """
    Calls the Gemini API for TTS generation with exponential backoff for retries.
    """
    
    # --- SIMPLIFIED SYSTEM PROMPT ---
    system_prompt = (
        "You are a concise CBT guide. Give short, practical, and calm advice in one or two sentences."
    )
    
    # --- VOICE CONFIGURATION (Changed from Kore to Puck) ---
    TTS_VOICE_NAME = "Puck" 

    payload = {
        "contents": [{"parts": [{"text": user_prompt}]}],
        "systemInstruction": {"parts": [{"text": system_prompt}]},
        "generationConfig": {
            "responseModalities": ["AUDIO"],
            "speechConfig": {
                "voiceConfig": {
                    "prebuiltVoiceConfig": { 
                        "voiceName": TTS_VOICE_NAME
                    }
                }
            }
        }
    }

    max_retries = 3
    for attempt in range(max_retries):
        try:
            response = requests.post(
                GEMINI_TTS_API_URL, 
                headers={'Content-Type': 'application/json'}, 
                data=json.dumps(payload)
            )
            
            # Check for success
            response.raise_for_status()
            
            # If successful, process and break the loop
            result = response.json()
            candidate = result.get('candidates', [{}])[0]
            
            # 1. Extract the text response (what the AI actually said)
            text_part = candidate.get('content', {}).get('parts', [])[0]
            tts_text = text_part.get('text', "")
            
            # 2. Extract the audio data
            audio_part = candidate.get('content', {}).get('parts', [])[-1]
            mime_type = audio_part.get('inlineData', {}).get('mimeType', "")
            audio_data_base64 = audio_part.get('inlineData', {}).get('data', "")
            
            if not tts_text or not audio_data_base64 or not mime_type.startswith("audio/L16"):
                # Handle cases where the API returns a 200 but content is missing
                st.error("Could not generate voice response: API returned insufficient data.")
                return None, None
                
            # 3. Get sample rate from mimeType (e.g., audio/L16;rate=24000)
            sample_rate_match = re.search(r'rate=(\d+)', mime_type)
            sample_rate = int(sample_rate_match.group(1)) if sample_rate_match else 24000

            # 4. Decode base64 to raw PCM bytes
            pcm_data = base64.b64decode(audio_data_base64)

            # 5. Convert PCM bytes to WAV format
            wav_bytes = pcm_to_wav(pcm_data, sample_rate=sample_rate)
            
            return tts_text, wav_bytes

        except requests.exceptions.RequestException as e:
            # Check for recoverable errors (500, 503)
            if response.status_code in [500, 503] and attempt < max_retries - 1:
                wait_time = 2 ** (attempt + 1)
                # We are removing the explicit Streamlit warning here as it's already in the console
                time.sleep(wait_time)
                continue # Go to the next attempt
            
            # If it's a non-recoverable error (e.g., 400) or last attempt failed
            error_message = f"TTS API Request Failed after {attempt + 1} attempts. Last status: {response.status_code}. Error: {e}"
            st.error(f"ERROR: Could not generate voice response. Details: {error_message}")
            return None, None
            
        except Exception as e:
            st.error(f"ERROR: An unexpected error occurred during TTS processing: {e}")
            return None, None
            
    return None, None # Should be caught by the loop, but for completeness

# --- 7. UI Components ---

st.set_page_config(layout="wide", page_title="Mind Universe: Wellness & AI")

# --- Header ---
st.title("🌌 Mind Universe")
st.caption(f"Welcome, {st.session_state.user_email} (ID: {st.session_state.user_id})")

# --- Sidebar (Data Management) ---
with st.sidebar:
    st.header("Data Management")
    st.caption("Securely store and manage your data with Firebase.")
    
    # --- Download/Export ---
    
    def generate_export_content():
        """Formats all chat and journal data into a comprehensive text file."""
        export_text = f"--- Mind Universe Data Export for User ID: {st.session_state.user_id} ---\n"
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
            # Sort chat history by timestamp for chronological order
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
        help="Downloads all journal entries and chat history into a single text file."
    )
    
    # --- Clear History ---
    st.subheader("⚠️ Clear History")
    
    if st.button("Clear All History", type="secondary", help="Permanently deletes all chat and journal data."):
        st.session_state.confirm_delete = True
        
    if st.session_state.get('confirm_delete', False):
        st.warning("Are you sure you want to PERMANENTLY delete ALL data?")
        col_yes, col_no = st.columns(2)
        
        with col_yes:
            if st.button("Yes, Delete All Data"):
                with st.spinner("Deleting data..."):
                    try:
                        # Delete Chat History
                        chat_ref = get_user_chat_collection_ref(st.session_state.user_id)
                        for doc in chat_ref.stream():
                            doc.reference.delete()
                        st.session_state.chat_history = []
                        
                        # Delete Journal Entries
                        journal_ref = get_user_journal_collection_ref(st.session_state.user_id)
                        for doc in journal_ref.stream():
                            doc.reference.delete()
                        st.session_state.journal_entries = []
                        
                        # Clear the cache
                        load_data_from_firestore.clear()
                        
                        st.success("All history has been permanently deleted.")
                        st.session_state.confirm_delete = False
                        st.rerun()
                        
                    except Exception as e:
                        st.error(f"Deletion failed: {e}")
                        st.session_state.confirm_delete = False

        with col_no:
            if st.button("No, Cancel"):
                st.session_state.confirm_delete = False
                st.info("Deletion cancelled.")
                st.rerun()

# --- 8. Tabbed Application Interface ---

tab_journal, tab_mentor, tab_voice = st.tabs(["✍️ Wellness Journal", "💬 AI Mentor", "🎤 Voice CBT"])

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
            st.success("Journal entry saved!")
        elif submitted and not entry_content:
            st.warning("Please write some content before saving.")

    st.divider()

    # Display History
    st.subheader("Journal History")
    if st.session_state.journal_entries:
        # Journal entries are loaded reverse chronologically
        for entry in st.session_state.journal_entries:
            with st.expander(f"**{entry.get('date')}** — {entry.get('title', 'Untitled Entry')}"):
                st.markdown(entry.get('content'))
                # NOTE: Deletion of individual entries is omitted for brevity but would require a Firestore delete call.
    else:
        st.info("No journal entries found. Start writing above!")

# --- Tab 2: AI Mentor (Text Chat) ---
with tab_mentor:
    st.header("Ask Your Mentor")
    st.caption("Chat with your supportive AI mentor for insights, coping strategies, and reflections.")

    # Display chat history
    for message in st.session_state.chat_history:
        role = "user" if message["role"] == "user" else "assistant"
        avatar = "👤" if role == "user" else "🧠"
        with st.chat_message(role, avatar=avatar):
            st.markdown(message["content"])

    # Chat input
    if prompt := st.chat_input("Ask your Mind Mentor a question..."):
        # Display user message and save
        with st.chat_message("user", avatar="👤"):
            st.markdown(prompt)
        save_chat_message("user", prompt)

        # Generate AI response
        with st.chat_message("assistant", avatar="🧠"):
            with st.spinner("Mind Mentor is reflecting..."):
                ai_response = generate_ai_reply(prompt)
                
            if ai_response:
                st.markdown(ai_response)
                save_chat_message("model", ai_response)
                # Force rerun to update the chat history display immediately
                st.rerun()

# --- Tab 3: Voice CBT ---
with tab_voice:
    st.header("CBT Voice Assistant")
    st.caption("Receive concise, verbal advice using Cognitive Behavioral Therapy principles.")
    
    # Display the last generated audio (if any)
    if st.session_state.latest_wav_bytes:
        st.audio(st.session_state.latest_wav_bytes, format='audio/wav')
        
    # Input for voice prompt
    voice_prompt = st.text_input(
        "Ask a CBT question", 
        placeholder="How can I reframe a negative thought about my work performance?",
        key="voice_input"
    )
    
    if st.button("Get Voice Advice", type="primary"):
        if voice_prompt:
            with st.spinner("Generating voice response..."):
                tts_text, wav_bytes = generate_tts_reply(voice_prompt)
                
            if wav_bytes:
                st.session_state.latest_wav_bytes = wav_bytes
                
                st.subheader("CBT Mentor Said:")
                st.markdown(f"*{tts_text}*")
                
                # We use st.rerun to display the st.audio component cleanly
                st.rerun()
            else:
                st.warning("Could not generate voice audio. Check console for API errors.")
        else:
            st.warning("Please enter a question for the CBT Voice Assistant.")
