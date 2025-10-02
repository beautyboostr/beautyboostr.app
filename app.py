import streamlit as st
import engine  # Import our backend logic
import traceback

# --- Page Configuration ---
st.set_page_config(
    page_title="BeautyBoostr AI Engine",
    layout="wide",
    initial_sidebar_state="collapsed"
)

# --- Main App UI ---
st.title("✨ BeautyBoostr AI Product Analyzer")
st.markdown("Enter a product's name and its full ingredient (INCI) list to receive a detailed analysis and routine placement recommendation.")

# --- Input Fields ---
col1, col2 = st.columns(2)
with col1:
    product_name = st.text_input(
        "Product Name",
        placeholder="e.g., Glow Up Hydrating Serum"
    )

with col2:
    # Get the list of skin types for the dropdown
    try:
        skin_type_names = [f"{key}: {value['name']}" for key, value in engine.ALL_DATA["skin_types"].items()]
        selected_skin_type_str = st.selectbox(
            "Select Your Skin Type (Optional)",
            options=[""] + skin_type_names,
            help="Selecting a skin type provides a more personalized match score."
        )
        selected_skin_type_id = selected_skin_type_str.split(':')[0] if selected_skin_type_str else None
    except Exception as e:
        st.error(f"Could not load skin types for dropdown: {e}")
        selected_skin_type_id = None

inci_list_str = st.text_area(
    "Ingredient (INCI) List",
    placeholder="Paste the full ingredient list here, separated by commas...",
    height=150
)

analyze_button = st.button("Analyze Product", type="primary", use_container_width=True)

# This is where the output will be displayed
output_container = st.container()

# --- Main Workflow ---
if analyze_button:
    if not product_name or not inci_list_str:
        st.warning("Please provide both a product name and an ingredient list.")
    else:
        with st.spinner("🤖 AI is analyzing the formula... This may take a moment."):
            # The engine.py file now handles the full analysis, including the safety check.
            # If a prohibited ingredient is found, the engine will print an error and return None.
            ai_says_output, formula_breakdown, routine_matches = engine.run_full_analysis(
                product_name, 
                inci_list_str,
                selected_skin_type_id
            )

            # --- Display the Final Output ---
            # This block will only run if the analysis was successful (i.e., not stopped by a safety check or other error)
            if ai_says_output and formula_breakdown and routine_matches is not None:
                with output_container:
                    st.markdown("---")
                    st.subheader("🤖 AI Assistant Says:")
                    for category, details in ai_says_output.items():
                        st.markdown(f"**{category}:** Score {details['score']}/10")
                        st.write(details['narrative'])
                    
                    st.subheader("🔬 Formula Effectiveness Breakdown:")
                    col1_breakdown, col2_breakdown = st.columns(2)
                    with col1_breakdown:
                        st.markdown("##### ✅ Positive Impact")
                        st.write(", ".join(formula_breakdown.get("Positive Impact", ["None"])))
                    with col2_breakdown:
                        st.markdown("#####  neutrall Neutral/Functional")
                        st.write(", ".join(formula_breakdown.get("Neutral/Functional", ["None"])))

                    st.subheader("📋 Routine Placements (Internal Use):")
                    if routine_matches:
                        st.code("\n".join(routine_matches), language=None)
                    else:
                        st.info("No perfect routine placements were found based on the analysis.")

