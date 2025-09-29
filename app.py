import streamlit as st
from datetime import datetime
from utils import (
    login_user, 
    sign_up, 
    logout, 
    load_data_from_firestore, 
    generate_chat_response, 
    save_chat_message,
    render_wellness_journal_page, # <-- New import
    # Keeping placeholders for future pages
    # render_goals_tracker_page, 
    # render_dashboard_page 
)

# --- Streamlit Configuration ---
st.set_page_config(
    page_title="Mind Universe: AI Wellness Assistant",
    layout="wide",
    initial_sidebar_state="expanded"
)

# --- Session State Initialization ---
if 'logged_in' not in st.session_state:
    st.session_state.logged_in = False
if 'current_user_email' not in st.session_state:
    st.session_state.current_user_email = None
if 'page_selected' not in st.session_state:
    st.session_state.page_selected = 'Dashboard'
if 'user_data_loaded' not in st.session_state:
    st.session_state.user_data_loaded = False
# Data containers (will be populated from Firestore)
if 'chat_history' not in st.session_state:
    st.session_state.chat_history = []
if 'journal_entries' not in st.session_state:
    st.session_state.journal_entries = []
if 'goals' not in st.session_state:
    st.session_state.goals = []


# --- Helper Function: Load Data ---

def load_user_data():
    """Wrapper to load all necessary data only once after login."""
    if st.session_state.logged_in and not st.session_state.user_data_loaded:
        with st.spinner(f"Loading data for {st.session_state.current_user_email}..."):
            chat, journal, goals = load_data_from_firestore(st.session_state.current_user_email)
            
            st.session_state.chat_history = chat
            st.session_state.journal_entries = journal
            st.session_state.goals = goals
            st.session_state.user_data_loaded = True
            st.success("Data loaded successfully!")

# --- Page Rendering: Dashboard Placeholder ---
# NOTE: This will be replaced with a proper dashboard function later.
def render_dashboard_page():
    st.title("🚀 Dashboard & Insights (Coming Soon!)")
    st.markdown("---")
    st.info("Welcome to Mind Universe, your personalized AI wellness companion. Use the sidebar to chat with your Mind Mentor or write in your Journal.")
    
    st.subheader("Your Stats Snapshot")
    
    col1, col2, col3 = st.columns(3)
    
    # Simple data metrics
    col1.metric("Total Chats", len(st.session_state.chat_history))
    col2.metric("Journal Entries", len(st.session_state.journal_entries))
    col3.metric("Active Goals", len([g for g in st.session_state.goals if g.get('status') == 'active']))
    
    # Placeholder for trend data visualization
    st.subheader("Recent Wellness Trends")
    # You can call analyze_journal_trends here and use st.line_chart()
    st.warning("Trend analysis visualization is currently a placeholder.")


# --- Page Rendering: AI Chat ---

def render_chat_page():
    """Renders the Mind Mentor AI Chat interface."""
    st.title("💬 Mind Mentor Chat")
    st.markdown("---")
    
    st.markdown("Hello! I'm your Mind Mentor. I'm here to listen without judgment and help you explore your thoughts and feelings.")

    # Display chat history
    chat_container = st.container(height=500)
    with chat_container:
        for message in st.session_state.chat_history:
            with st.chat_message(message["role"]):
                st.markdown(message["content"])

    # Chat input
    if prompt := st.chat_input("Ask your Mind Mentor something..."):
        # 1. User message handling
        user_message = {
            "role": "user", 
            "content": prompt, 
            "timestamp": datetime.now().timestamp()
        }
        st.session_state.chat_history.append(user_message)
        save_chat_message(user_message)

        # Re-display user message immediately
        with chat_container:
            with st.chat_message("user"):
                st.markdown(prompt)

        # 2. AI response generation
        with st.spinner("Mind Mentor is thinking..."):
            ai_text = generate_chat_response(st.session_state.chat_history)

        if ai_text:
            ai_message = {
                "role": "model", 
                "content": ai_text, 
                "timestamp": datetime.now().timestamp()
            }
            st.session_state.chat_history.append(ai_message)
            save_chat_message(ai_message)
            
            # Display AI response
            with chat_container:
                with st.chat_message("model"):
                    st.markdown(ai_text)
            
            # Rerun to clear input box and ensure chat history display is updated correctly
            st.rerun()


# --- Main App Logic ---

def render_auth_page():
    """Renders the Login/Signup page."""
    st.title("Welcome to Mind Universe")
    st.markdown("Your personal AI companion for mental wellness.")
    
    st.image("https://placehold.co/600x200/5E548E/FFFFFF?text=Mind+Universe+Logo", use_column_width=True)

    tab1, tab2 = st.tabs(["Login", "Sign Up"])

    with tab1:
        st.subheader("Login")
        with st.form("login_form"):
            login_email = st.text_input("Email (Login)", key="login_email_input").strip()
            login_password = st.text_input("Password (Login)", type="password", key="login_password_input").strip()
            submitted = st.form_submit_button("Log In")
            
            if submitted:
                if login_user(login_email, login_password):
                    st.rerun()

    with tab2:
        st.subheader("Create Account")
        with st.form("signup_form"):
            signup_email = st.text_input("Email (Sign Up)", key="signup_email_input").strip()
            signup_password = st.text_input("Password (Sign Up)", type="password", key="signup_password_input").strip()
            submitted = st.form_submit_button("Sign Up")
            
            if submitted:
                if sign_up(signup_email, signup_password):
                    # After successful signup, user should log in via tab1
                    pass # Message already shown in utils.py


def render_authenticated_app():
    """Renders the main application interface after successful login."""
    
    # 1. Load data if it hasn't been loaded yet (runs only once after login)
    load_user_data()

    # 2. Sidebar Navigation
    st.sidebar.title("Mind Universe")
    st.sidebar.markdown(f"Welcome, **{st.session_state.current_user_email}**")
    st.sidebar.markdown("---")

    # Navigation options
    page_options = ['Dashboard', 'Chat', 'Journal', 'Goals (Coming Soon)']
    
    # Remove ' (Coming Soon)' for display but keep internal logic cleaner
    display_options = [p.split(' (')[0] for p in page_options]
    
    # Update selected page state when a new radio option is clicked
    selected = st.sidebar.radio("Navigation", display_options, index=display_options.index(st.session_state.page_selected) if st.session_state.page_selected in display_options else 0)
    st.session_state.page_selected = selected

    st.sidebar.markdown("---")
    st.sidebar.button("🔒 Logout", on_click=logout)

    # 3. Main Content Rendering
    if st.session_state.page_selected == 'Dashboard':
        render_dashboard_page()
    elif st.session_state.page_selected == 'Chat':
        render_chat_page()
    elif st.session_state.page_selected == 'Journal':
        # NEW PAGE INTEGRATION
        render_wellness_journal_page()
    elif st.session_state.page_selected == 'Goals':
        st.title("🎯 Goals Tracker (Under Development)")
        st.info("The Goals Tracker page will be ready soon!")
        # render_goals_tracker_page() # Placeholder for future function
    else:
        # Fallback
        render_dashboard_page()


# --- Application Entry Point ---

if __name__ == '__main__':
    if st.session_state.logged_in:
        render_authenticated_app()
    else:
        render_auth_page()
