import streamlit as st
import requests
import json
import pandas as pd
from datetime import datetime
import hashlib 

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
    # Note: In a real Streamlit app, this would be st.error/st.exception
    # Here, we keep the original error handling for the Streamlit environment.
    st.error(f"Failed to parse FIREBASE_CONFIG as JSON. Ensure the format is correct: {e}")
    st.stop()

# Load Gemini API Key
GEMINI_API_KEY = st.secrets.get("GEMINI_API_KEY", "")
if not GEMINI_API_KEY:
    st.error("GEMINI_API_KEY not found in Streamlit secrets. Please configure it to use the AI Mentor and Insights.")
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
# Initialize tab tracking state
if 'current_tab' not in st.session_state:
    st.session_state.current_tab = "💬 AI Mentor"
if 'journal_analysis' not in st.session_state:
    st.session_state.journal_analysis = None # To store the analysis result

def hash_password(password):
    """Simple password hashing simulation using SHA-256."""
    return hashlib.sha256(password.encode()).hexdigest()

def get_users_collection_ref():
    """Returns the Firestore reference for the global users collection (public/data path)."""
    # Path: /artifacts/{appId}/public/data/users
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
    st.session_state.current_tab = "💬 AI Mentor" # Reset tab state
    st.session_state.journal_analysis = None
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
        st.session_state.journal_analysis = None # Clear previous analysis
        st.success("Journal entry saved!")
    except Exception as e:
        st.error(f"Failed to save journal entry: {e}")


# --- 5. LLM API Call Functions (Gemini Text) ---

GEMINI_TEXT_MODEL = "gemini-2.5-flash"
GEMINI_API_URL = f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_TEXT_MODEL}:generateContent?key={GEMINI_API_KEY}"

def generate_ai_text_reply(user_prompt, history):
    """Calls the Gemini API for standard text generation (AI Mentor)."""
    
    # Construct chat history for context
    chat_contents = [
        {"role": "user" if msg["role"] == "user" else "model", 
         "parts": [{"text": msg["content"]}]}
        for msg in history
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
        
        return text

    except requests.exceptions.RequestException as e:
        st.error(f"API Request Failed (Mentor Chat): {e}")
        return None
    except Exception as e:
        st.error(f"An unexpected error occurred (Mentor Chat): {e}")
        return None

def generate_journal_analysis(journal_text_block):
    """Calls the Gemini API for structured journal analysis (Insights)."""
    
    # Define the system prompt for the AI Analyst persona
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
        
        return text

    except requests.exceptions.RequestException as e:
        st.error(f"API Request Failed (Analysis): {e}")
        return "Analysis failed due to an API error."
    except Exception as e:
        st.error(f"An unexpected error occurred (Analysis): {e}")
        return "Analysis failed due to an unexpected error."


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
        
        # Download/Export function
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
    view_options = ["💬 AI Mentor", "✍️ Wellness Journal", "📊 Insights"]
    
    # Use st.radio to track the selected view
    selected_view = st.radio(
        "Navigation",
        view_options,
        index=view_options.index(st.session_state.current_tab),
        horizontal=True,
        label_visibility="hidden"
    )
    
    # Update session state if user manually clicks a new view
    if selected_view != st.session_state.current_tab:
        st.session_state.current_tab = selected_view
        st.rerun()
        
    st.divider()

    # --- Content Display based on selected_view ---
    
    # --- Content 1: AI Mentor (Text Chat) ---
    if st.session_state.current_tab == "💬 AI Mentor":
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
            # Display user message and save
            with st.chat_message("user", avatar="👤"):
                st.markdown(prompt)
            save_chat_message("user", prompt)

            # Generate AI response (Text only)
            with st.chat_message("assistant", avatar="🧠"):
                with st.spinner("Mind Mentor is reflecting..."):
                    ai_response_text = generate_ai_text_reply(prompt, st.session_state.chat_history)
                    
                if ai_response_text:
                    st.markdown(ai_response_text)
                    
                    # Save the response (text only)
                    save_chat_message("model", ai_response_text)
                    st.rerun() # Force rerun to update the chat history display immediately
                else:
                    st.error("Failed to receive a reply from the AI Mentor. Please try again.")

    # --- Content 2: Wellness Journal ---
    elif st.session_state.current_tab == "✍️ Wellness Journal":
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

    # --- Content 3: Insights (New Feature) ---
    elif st.session_state.current_tab == "📊 Insights":
        st.header("AI-Powered Insights")
        st.caption("Analyze your recent entries to discover emotional trends and recurring themes.")
        
        if not st.session_state.journal_entries:
            st.info("You need to write a few journal entries before generating insights.")
            
        else:
            # Prepare the journal content for analysis (using the last 10 entries)
            entries_to_analyze = st.session_state.journal_entries[:10]
            
            # Create a single block of text for the model to process
            journal_text_block = ""
            for i, entry in enumerate(entries_to_analyze):
                journal_text_block += f"=== Entry {i+1} ({entry.get('date', 'N/A')}): {entry.get('title', 'No Title')} ===\n"
                journal_text_block += f"{entry.get('content', '')}\n\n"
            
            # Button to trigger analysis
            if st.button(f"Generate Insights from Last {len(entries_to_analyze)} Entries", type="primary"):
                st.session_state.journal_analysis = None # Clear previous
                with st.spinner("Mind Analyst is reading your reflections..."):
                    analysis_result = generate_journal_analysis(journal_text_block)
                    st.session_state.journal_analysis = analysis_result
                    
            st.divider()
            
            # Display analysis result
            if st.session_state.journal_analysis:
                st.subheader("Analysis Results")
                st.markdown(st.session_state.journal_analysis)
            else:
                st.info("Click the button above to generate a new analysis of your recent journal entries.")


# --- Main Application Logic ---

if __name__ == '__main__':
    if st.session_state.logged_in:
        display_main_app()
    else:
        display_auth_page()
