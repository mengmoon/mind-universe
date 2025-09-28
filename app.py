import streamlit as st
import firebase_admin
from firebase_admin import credentials, firestore
import requests
import json
from datetime import datetime
import time # Import for exponential backoff
import io # NEW: For handling audio data in memory
import base64 # NEW: For decoding audio data
import re # NEW: For extracting sample rate from mimeType

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

# TTS Configuration
TTS_MODEL = "gemini-2.5-flash-preview-tts"
TTS_VOICE = "Kore" # A clear, firm voice, suitable for CBT

# Initialize session state for user and chat messages
if "user" not in st.session_state:
    st.session_state.user = None
if "chat_messages" not in st.session_state:
    st.session_state.chat_messages = []
if "journals" not in st.session_state:
    st.session_state.journals = []
# State for the delete confirmation logic
if "confirm_delete" not in st.session_state:
    st.session_state.confirm_delete = False
# State to temporarily hold the latest generated audio for playback
if "latest_wav_bytes" not in st.session_state:
    st.session_state.latest_wav_bytes = None


# ----------------------
# Firebase Initialization
# ----------------------
try:
    # Load the entire Firebase config from Streamlit secrets
    firebase_config = json.loads(st.secrets["FIREBASE_CONFIG"])
except KeyError as e:
    st.error(f"Missing secret key: {e}. Please ensure FIREBASE_CONFIG is set in your Streamlit secrets.")
    st.stop()
except json.JSONDecodeError as e:
    st.error(f"Failed to parse FIREBASE_CONFIG as JSON: {e}")
    st.stop()

if not firebase_admin._apps:
    try:
        # --- ENHANCED FIX FOR "Invalid private key" ERROR ---
        if "private_key" in firebase_config:
            # 1. Aggressive newline replacement and stripping whitespace
            key = firebase_config["private_key"].replace("\\n", "\n").strip()
            
            # 2. Check and remove surrounding quotes, which often happen when copy/pasting
            if key.startswith('"') and key.endswith('"'):
                key = key[1:-1]
                
            firebase_config["private_key"] = key
            
            # Diagnostic Log: Print the start of the processed key to help diagnose the input format
            # This appears in the Streamlit console logs, not the UI.
            print(f"DEBUG: Processed Private Key Starts With: {firebase_config['private_key'][:50]}...")
            
        cred = credentials.Certificate(firebase_config)
        firebase_admin.initialize_app(cred)
    except ValueError as e:
        st.error(f"Failed to initialize Firebase: {e}")
        st.stop()
    except Exception as e:
        st.error(f"An unknown error occurred during Firebase initialization: {e}")
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

def delete_user_data(uid):
    """Deletes all chat and journal history for the user."""
    
    # 1. Delete Journals
    journal_docs = db.collection("journals").where("uid", "==", uid).stream()
    for doc in journal_docs:
        doc.reference.delete()
        
    # 2. Delete Chats
    chat_docs = db.collection("chats").where("uid", "==", uid).stream()
    for doc in chat_docs:
        doc.reference.delete()
        
    # 3. Clear session state
    st.session_state.chat_messages = []
    st.session_state.journals = []
    st.session_state.confirm_delete = False # Reset confirmation state
    
    st.toast("All history cleared successfully!", icon="🗑️")

# ----------------------
# History Export Function
# ----------------------
def export_history(journals, chats):
    """Formats chat and journal data into a downloadable string."""
    export_content = "--- Mind Universe Data Export ---\n\n"
    export_content += f"User: {st.session_state.user['email'] if st.session_state.user else 'Guest'}\n"
    export_content += f"Export Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
    export_content += "--------------------------------------\n\n"

    # Journals Section
    export_content += "=====================\n"
    export_content += "   JOURNAL ENTRIES\n"
    export_content += "=====================\n\n"
    
    if not journals:
        export_content += "No journal entries found.\n\n"
    
    for entry in journals:
        export_content += f"--- Entry Timestamp: {entry['timestamp']} ---\n"
        export_content += f"{entry['text']}\n\n"
    
    # Chats Section
    export_content += "\n=====================\n"
    export_content += "    CHAT HISTORY\n"
    export_content += "=====================\n\n"

    if not chats:
        export_content += "No chat history found.\n\n"

    for msg in chats:
        role_label = "USER" if msg['role'] == 'user' else "AI MENTOR"
        export_content += f"[{role_label}]: {msg['content']}\n"
    
    export_content += "\n--- END OF EXPORT ---\n"
    return export_content

# ----------------------
# Audio Utility Functions (For TTS)
# ----------------------

def pcm_to_wav(pcm_data, sample_rate, num_channels=1, bytes_per_sample=2):
    """
    Converts raw PCM 16-bit signed integer data (L16) into a WAV file format (bytes).
    This is necessary for the Streamlit audio player.
    """
    wav_file = io.BytesIO()
    
    # RIFF chunk descriptor
    wav_file.write(b'RIFF')
    
    # Chunk size (4 + (8 + subchunk1_size) + (8 + subchunk2_size))
    data_size = len(pcm_data)
    subchunk1_size = 16
    subchunk2_size = data_size
    chunk_size = 36 + subchunk2_size
    wav_file.write(chunk_size.to_bytes(4, byteorder='little'))
    wav_file.write(b'WAVE')
    
    # fmt sub-chunk
    wav_file.write(b'fmt ')
    wav_file.write(subchunk1_size.to_bytes(4, byteorder='little')) # Subchunk1 size (16 for PCM)
    wav_file.write(b'\x01\x00') # Audio format (1 for PCM)
    wav_file.write(num_channels.to_bytes(2, byteorder='little'))
    wav_file.write(sample_rate.to_bytes(4, byteorder='little'))
    
    byte_rate = sample_rate * num_channels * bytes_per_sample
    wav_file.write(byte_rate.to_bytes(4, byteorder='little'))
    
    block_align = num_channels * bytes_per_sample
    wav_file.write(block_align.to_bytes(2, byteorder='little'))
    wav_file.write((bytes_per_sample * 8).to_bytes(2, byteorder='little')) # Bits per sample (16)
    
    # data sub-chunk
    wav_file.write(b'data')
    wav_file.write(data_size.to_bytes(4, byteorder='little'))
    
    # Write the actual PCM data
    wav_file.write(pcm_data)
    
    return wav_file.getvalue()

# ----------------------
# Gemini API Functions 
# ----------------------
def generate_ai_reply(user_input, chat_history):
    """Generates an AI response using the standard Gemini REST API."""
    
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
                
                # Extract the primary candidate object
                candidate = result.get('candidates', [{}])[0]
                text = candidate.get('content', {}).get('parts', [{}])[0].get('text')
                
                if text:
                    return text
                else:
                    # Handle cases where API returns status 200 but content is empty or blocked
                    finish_reason = candidate.get('finishReason', 'UNKNOWN')
                    
                    if finish_reason == 'SAFETY':
                        safety_info = candidate.get('safetyRatings', 'N/A')
                        st.error(f"⚠️ Content Blocked: The AI response was filtered due to safety settings. Finish Reason: {finish_reason}. Safety Details: {safety_info}")
                        return "The AI mentor's response was filtered due to safety settings. Please rephrase your query to ensure it aligns with content guidelines."
                    
                    elif finish_reason == 'MAX_TOKENS':
                        st.error(f"⚠️ Response Too Long: The AI response was cut off because it reached the maximum token limit (500). Finish Reason: {finish_reason}.")
                        return "The AI mentor's response was too long. Please try a more specific question."
                        
                    else:
                        st.error(f"Gemini API returned no text. Finish Reason: {finish_reason}. Raw Candidate: {candidate}")
                        return "The AI mentor's response was empty or incomplete."


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

def generate_tts_reply(user_input, chat_history):
    """Generates an AI response using Gemini TTS and returns (text, WAV bytes)."""
    api_key = st.secrets.get("GEMINI_API_KEY")
    if not api_key:
        return None, "Gemini API key is missing. Please set 'GEMINI_API_KEY' in your Streamlit secrets."
    
    url = f"{GEMINI_BASE_URL}/{TTS_MODEL}:generateContent?key={api_key}"
    
    # We explicitly tell the AI to use CBT voice and keep the response concise.
    system_instruction = "You are an AI mentor specializing in CBT (cognitive-behavioral therapy). Provide a concise, practical, and encouraging response to the user's latest message, strictly using the CBT voice."
    
    # Prepare chat history for context
    contents = []
    # Add history for context, using 'model' for AI role
    # Note: Using [-6:] to keep context manageable for the TTS endpoint
    for msg in chat_history[-6:]: 
        role = 'model' if msg['role'] == 'ai' else msg['role']
        contents.append({"role": role, "parts": [{"text": msg['content']}]})
        
    # Add the current user input
    contents.append({"role": "user", "parts": [{"text": user_input}]})

    payload = {
        "contents": contents,
        "generationConfig": {
            "temperature": 0.7,
            "maxOutputTokens": 150 # Keep text short for quicker, focused voice response
        },
        "speechConfig": {
            "voiceConfig": {
                "prebuiltVoiceConfig": { "voiceName": TTS_VOICE }
            },
            "systemInstruction": {
                "parts": [{"text": system_instruction}]
            }
        }
    }
    
    headers = {'Content-Type': 'application/json'}
    max_retries = 3
    
    for attempt in range(max_retries):
        try:
            with st.spinner(f"🎤 Generating CBT Voice Reply... (Attempt {attempt + 1})"):
                response = requests.post(url, headers=headers, data=json.dumps(payload))
                response.raise_for_status() 
                
                result = response.json()
                candidate = result.get('candidates', [{}])[0]
                
                # TTS response has both text and inlineData (audio)
                content_parts = candidate.get('content', {}).get('parts', [{}])
                
                # Find text and audio parts
                text_part_content = next((p.get('text') for p in content_parts if p.get('text')), None)
                audio_part = next((p for p in content_parts if p.get('inlineData')), None)
                
                if text_part_content and audio_part and audio_part.get('inlineData'):
                    
                    audio_data_base64 = audio_part['inlineData']['data']
                    mime_type = audio_part['inlineData']['mimeType'] # e.g., audio/L16;rate=24000
                    
                    # Extract sample rate from mimeType
                    match = re.search(r'rate=(\d+)', mime_type)
                    sample_rate = int(match.group(1)) if match else 24000 
                    
                    # Decode base64 to raw PCM bytes
                    pcm_data = base64.b64decode(audio_data_base64)
                    
                    # Convert raw PCM to WAV format
                    wav_bytes = pcm_to_wav(pcm_data, sample_rate)
                    
                    # Return the AI-generated text and the playable WAV bytes
                    return text_part_content, wav_bytes
                
                else:
                    finish_reason = candidate.get('finishReason', 'UNKNOWN')
                    error_message = f"TTS API returned incomplete data. Finish Reason: {finish_reason}. Candidate: {candidate}"
                    return None, error_message

        except requests.exceptions.HTTPError as e:
            error_code = response.status_code
            error_data = response.json() if response.content else {}
            error_message = error_data.get('error', {}).get('message', str(e))
            
            if error_code == 429 and attempt < max_retries - 1:
                wait_time = 2 ** attempt
                time.sleep(wait_time)
                continue 
            
            return None, f"TTS API Error {error_code}: {error_message}"
            
        except Exception as e:
            return None, f"An unexpected error occurred during TTS: {str(e)}"

    return None, "TTS generation failed after multiple retries."


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

    # --- Sidebar Data Management Actions ---
    with st.sidebar:
        st.markdown("---")
        st.subheader("Data Management")

        # 1. Export Button
        export_data = export_history(st.session_state.journals, st.session_state.chat_messages)
        st.download_button(
            label="⬇️ Download History (TXT)",
            data=export_data,
            file_name=f"Mind_Universe_Export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt",
            mime="text/plain",
            key="export_button",
            help="Download all your journal and chat data as a single text file. (Recommended before clearing!)"
        )
        
        # 2. Delete Confirmation Logic
        if st.button("🗑️ Clear All History", key="initial_delete_button", type="primary"):
            # Set state to show confirmation buttons
            st.session_state.confirm_delete = True
        
        if st.session_state.confirm_delete:
            st.warning("ARE YOU SURE? This action is permanent.")
            
            col_yes, col_no = st.columns(2)
            
            with col_yes:
                if st.button("YES, Delete Everything", key="confirm_delete_yes", type="secondary"):
                    delete_user_data(uid)
                    st.rerun()
            
            with col_no:
                if st.button("Cancel", key="confirm_delete_no"):
                    st.session_state.confirm_delete = False
                    st.rerun()
    # --- Main Tabs ---
    tab_journal, tab_chat, tab_voice = st.tabs(["📝 Journaling", "🤖 AI Mentor", "🎤 Voice CBT"])

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
        if user_input := st.chat_input("Ask your AI mentor...", key="text_chat_input"):
            
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

    with tab_voice:
        st.subheader("Cognitive Behavioral Therapy (CBT) Voice Chat")
        st.info(f"Converse with the CBT mentor, who will reply using the **{TTS_VOICE}** voice. The AI will provide practical, concise responses to keep the audio short.")
        
        # Display Voice Chat History (uses the same chat_messages state)
        voice_chat_placeholder = st.container()
        with voice_chat_placeholder:
            if not st.session_state.chat_messages:
                st.info("Start talking about a distressing thought or situation to receive a CBT-based, voiced response.")

            for message in st.session_state.chat_messages:
                with st.chat_message(message["role"] if message["role"] == "user" else "assistant"):
                    st.write(message["content"])
                    
            # Placeholder for the audio player
            # We only play the latest generated audio that was stored in state
            if 'latest_wav_bytes' in st.session_state and st.session_state.latest_wav_bytes:
                st.audio(st.session_state.latest_wav_bytes, format='audio/wav', autoplay=True)
                # Clear audio bytes immediately so it doesn't replay on every refresh
                st.session_state.latest_wav_bytes = None 


        # Input for new voice message
        voice_user_input = st.chat_input("Speak your mind for a CBT response...", key="voice_chat_input")
        
        if voice_user_input:
            
            # 1. Append user message to state and save to Firestore
            st.session_state.chat_messages.append({"role": "user", "content": voice_user_input})
            save_chat(uid, "user", voice_user_input)

            # 2. Get AI reply (Text and Audio)
            ai_text_reply, error_or_wav_bytes = generate_tts_reply(voice_user_input, st.session_state.chat_messages)
            
            # 3. Handle response
            if ai_text_reply and isinstance(error_or_wav_bytes, bytes):
                wav_bytes = error_or_wav_bytes
                
                # Store text
                st.session_state.chat_messages.append({"role": "ai", "content": ai_text_reply})
                save_chat(uid, "ai", ai_text_reply) 
                
                # Store audio bytes in session state for instant playback after rerun
                st.session_state.latest_wav_bytes = wav_bytes

            else:
                # Handle error case
                st.error(f"Error generating voice response: {error_or_wav_bytes}")
                # Append error message to history to show user
                st.session_state.chat_messages.append({"role": "ai", "content": f"ERROR: Could not generate voice response. Details: {error_or_wav_bytes}"})
                save_chat(uid, "ai", f"ERROR: Could not generate voice response. Details: {error_or_wav_bytes}")


            # Rerun to update the chat history and trigger audio playback
            st.rerun()
