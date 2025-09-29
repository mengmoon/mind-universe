import streamlit as st
from datetime import datetime
from utils import (
    load_data_from_firestore, 
    login_user, 
    sign_up, 
    logout, 
    get_user_chat_collection_ref, 
    get_user_journal_collection_ref, 
    get_user_goals_collection_ref
)

# --- Global Page Configuration ---
st.set_page_config(layout="wide", page_title="Mind Universe: Wellness & AI")

# --- Session State Initialization ---
if 'logged_in' not in st.session_state:
    st.session_state.logged_in = False
if 'current_user_email' not in st.session_state:
    st.session_state.current_user_email = None
if 'user_data_loaded' not in st.session_state:
    st.session_state.user_data_loaded = False
if 'journal_analysis' not in st.session_state:
    st.session_state.journal_analysis = None
if 'goals' not in st.session_state:
    st.session_state.goals = [] 
if 'chat_history' not in st.session_state:
    st.session_state.chat_history = []
if 'journal_entries' not in st.session_state:
    st.session_state.journal_entries = []

# --- Authentication UI ---

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
            login_submitted = st.form_submit_button("Login")
            
            if login_submitted:
                if login_email and login_password:
                    if login_user(login_email, login_password):
                        # Force rerun to transition to the main app layout
                        st.rerun()
                else:
                    st.warning("Please enter both email and password.")
                    
    with tab_signup:
        st.markdown("Create a new account.")
        with st.form("signup_form"):
            signup_email = st.text_input("Email (Sign Up)").lower()
            signup_password = st.text_input("Password (Sign Up)", type="password")
            signup_submitted = st.form_submit_button("Sign Up")
            
            if signup_submitted:
                if signup_email and signup_password:
                    if sign_up(signup_email, signup_password):
                        st.rerun()
                else:
                    st.warning("Please enter a valid email and a password (min 6 characters).")

# --- Sidebar Content (Shared Across Pages) ---

def generate_export_content():
    """Generates the content for the data download button."""
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

def display_sidebar():
    """Displays the account and data management sidebar."""
    with st.sidebar:
        st.header("Account & Data")
        
        st.caption(f"Logged in as: **{st.session_state.current_user_email}**")

        if st.button("Logout", help="End your session"):
            logout()
            
        st.divider()
        st.subheader("Data Management")
        
        # Download/Export function
        st.download_button(
            label="Download All Data (TXT)",
            data=generate_export_content(),
            file_name=f"mind_universe_export_{datetime.now().strftime('%Y%m%d')}.txt",
            mime="text/plain",
            help="Downloads all journal entries, goals, and chat history."
        )
        
        # --- Clear History (Delete functionality) ---
        st.subheader("⚠️ Clear History")
        
        if st.button("Clear All History (Requires Reload)", key="clear_hist_button", help="Permanently deletes all chat, journal, and goal data."):
            st.session_state.confirm_delete = True
            
        if st.session_state.get('confirm_delete', False):
            st.warning("Are you sure you want to PERMANENTLY delete ALL data?")
            col_yes, col_no = st.columns(2)
            
            with col_yes:
                if st.button("Yes, Delete All Data", key="confirm_delete_yes"):
                    with st.spinner("Deleting data..."):
                        try:
                            # Delete Chat History
                            chat_ref = get_user_chat_collection_ref(st.session_state.current_user_email)
                            for doc in chat_ref.stream():
                                doc.reference.delete()
                            
                            # Delete Journal Entries
                            journal_ref = get_user_journal_collection_ref(st.session_state.current_user_email)
                            for doc in journal_ref.stream():
                                doc.reference.delete()
                            
                            # Delete Goals
                            goals_ref = get_user_goals_collection_ref(st.session_state.current_user_email)
                            for doc in goals_ref.stream():
                                doc.reference.delete()

                            st.success("All history has been permanently deleted. Reloading application...")
                            st.session_state.confirm_delete = False
                            logout() # Log out and reset state fully
                            
                        except Exception as e:
                            st.error(f"Deletion failed: {e}")
                            st.session_state.confirm_delete = False

            with col_no:
                if st.button("No, Cancel", key="confirm_delete_no"):
                    st.session_state.confirm_delete = False
                    st.info("Deletion cancelled.")
                    st.rerun()

# --- Main Logic ---

if st.session_state.logged_in:
    # 1. Load Data on first login (or when session state is cleared/reloaded)
    if not st.session_state.user_data_loaded:
        with st.spinner("Loading your universe..."):
            chat_data, journal_data, goals_data = load_data_from_firestore(st.session_state.current_user_email)
            st.session_state.chat_history = chat_data
            st.session_state.journal_entries = journal_data
            st.session_state.goals = goals_data 
            st.session_state.user_data_loaded = True
            st.rerun() # Rerun once data is loaded to ensure pages have access
            
    # 2. Display the Sidebar for all logged-in pages
    display_sidebar()
    
    # 3. Display the Feature Dashboard (The new landing page content)
    st.title("🌌 Mind Universe Dashboard")
    st.markdown("---")
    st.subheader("Explore Your Wellness Tools")
    st.markdown("Click any feature in the sidebar to begin your journey.")
    
    col1, col2 = st.columns(2)
    col3, col4 = st.columns(2)
    
    with col1:
        st.success("### 💬 AI Mentor")
        st.markdown("Have a private, non-judgmental chat. Get supportive reflections and coping strategies powered by Gemini.")
        
    with col2:
        st.warning("### ✍️ Wellness Journal")
        st.markdown("Record your daily thoughts and feelings. Entries are automatically analyzed for **sentiment** and **emotion**.")
        
    with col3:
        st.info("### 📊 Insights")
        st.markdown("Visualize your emotional trends over time. Generate a **deep AI summary** of your recurring themes and overall emotional state.")
        
    with col4:
        st.error("### 🎯 Goal Tracker")
        st.markdown("Set and monitor your personal wellness objectives. Easily mark goals as achieved and track your progress.")

else:
    display_auth_page()
