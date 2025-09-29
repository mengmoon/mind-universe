import streamlit as st
from datetime import datetime
from utils import save_new_goal, update_goal_status_worker, delete_goal_worker

# --- Local Action Handlers (using on_click) ---

def handle_achieve_goal(goal_id):
    """Marks a goal as Achieved and triggers a rerun to update the UI."""
    update_goal_status_worker(goal_id, 'Achieved')
    # Use st.rerun to refresh the page state after data is updated in Firestore
    st.rerun()

def handle_delete_goal(goal_id):
    """Deletes a goal and triggers a rerun to update the UI."""
    delete_goal_worker(goal_id)
    # Use st.rerun to refresh the page state after data is updated in Firestore
    st.rerun()

# ---------------------------------------------

def app():
    if not st.session_state.logged_in:
        st.warning("Please log in via the Home page to track your goals.")
        return

    st.header("🎯 Goal Tracker")
    st.caption("Set measurable wellness objectives and track your progress.")

    # --- Goal Creation Form ---
    with st.form("goal_form", clear_on_submit=True):
        st.subheader("Create a New Goal")
        goal_title = st.text_input("Goal Title (e.g., 'Practice mindfulness 15 mins daily')")
        goal_description = st.text_area("Details & Why (e.g., 'To reduce anxiety and increase focus.')", height=100)
        
        submitted = st.form_submit_button("Add Goal")
        
        if submitted and goal_title and goal_description:
            save_new_goal(goal_title, goal_description)
            st.rerun()
        elif submitted and (not goal_title or not goal_description):
            st.warning("Please provide both a title and description for your goal.")

    st.divider()

    # --- Active Goals Display ---
    st.subheader("Active Goals 🚀")
    active_goals = [g for g in st.session_state.goals if g.get('status') == 'Active']
    
    if active_goals:
        for goal in active_goals:
            col_content, col_button = st.columns([4, 1])
            with col_content:
                st.markdown(f"**{goal.get('title', 'Untitled Goal')}**")
                st.markdown(f"*{goal.get('description', 'No description')}*")
            
            with col_button:
                # Use on_click callback to process the goal status change
                st.button(
                    "Achieved", 
                    key=f"achieve_goal_{goal['id']}", 
                    on_click=handle_achieve_goal,
                    args=(goal['id'],),
                    help="Mark this goal as completed.",
                    use_container_width=True
                )
    else:
        st.info("You currently have no active goals. Set one above!")
        
    st.divider()

    # --- Achieved Goals Display ---
    st.subheader("Achieved Goals 🎉")
    achieved_goals = [g for g in st.session_state.goals if g.get('status') == 'Achieved']
    
    if achieved_goals:
        for goal in achieved_goals:
            col_content, col_button = st.columns([4, 1])
            with col_content:
                st.markdown(f"~~{goal.get('title', 'Untitled Goal')}~~")
                creation_time = datetime.fromtimestamp(goal.get('created_at', 0)).strftime('%Y-%m-%d')
                st.caption(f"Completed goal created on: {creation_time}") 
            
            with col_button:
                # Use on_click callback to process the goal deletion
                st.button(
                    "Delete", 
                    key=f"delete_goal_{goal['id']}", 
                    on_click=handle_delete_goal,
                    args=(goal['id'],),
                    help="Permanently delete this goal record.",
                    type="secondary",
                    use_container_width=True
                )
    else:
        st.info("No goals achieved yet. Keep striving!")


