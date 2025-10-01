import streamlit as st
import engine  # Import our backend logic

# --- Page Configuration ---
st.set_page_config(
    page_title="BeautyBoostr AI Analyzer",
    page_icon="✨",
    layout="wide"
)

# --- Main App UI ---
st.title("✨ BeautyBoostr AI Product Analyzer")
st.markdown("Enter a product's name and its ingredient list to get a complete analysis.")

# --- Data Loading ---
# Load all data at the start and cache it. Handle potential errors gracefully.
try:
    # The @st.cache_data decorator in the engine file will handle caching
    ALL_DATA = engine.load_all_data()
except (FileNotFoundError, ValueError) as e:
    st.error(f"Fatal Error: Could not load data files. Please ensure all .json files are in a 'data' subfolder. Details: {e}")
    st.stop() # Stop the app if data can't be loaded

# --- Input Form ---
with st.form("product_form"):
    product_name = st.text_input(
        "Product Name",
        placeholder="e.g., Glow Up Hydrating Serum"
    )
    inci_list_str = st.text_area(
        "Ingredient (INCI) List",
        placeholder="Paste the full ingredient list here, with each ingredient separated by a comma.",
        height=200
    )
    submitted = st.form_submit_button("Analyze Product", type="primary")

# --- Analysis and Output ---
if submitted:
    if not product_name or not inci_list_str:
        st.warning("Please provide both a product name and an ingredient list.")
    else:
        with st.spinner("🤖 AI is analyzing the formula... This may take a moment."):
            try:
                # Prepare inputs
                inci_list = [item.strip() for item in inci_list_str.split(',')]
                
                # --- Run the full analysis by calling the engine ---
                ai_says_output, formula_breakdown, routine_matches = engine.run_full_analysis(
                    product_name, inci_list, ALL_DATA
                )

                # --- Display the results ---
                st.markdown("---")
                
                # User-facing Output
                st.subheader("🤖 AI Assistant Says:")
                st.markdown(ai_says_output)
                
                st.subheader("🔬 Formula Effectiveness Breakdown:")
                st.markdown("**Positive Impact Ingredients:**")
                st.info(", ".join(formula_breakdown.get("positive_impact", ["None identified."])))
                
                st.markdown("**Neutral/Functional Ingredients:**")
                st.info(", ".join(formula_breakdown.get("neutral_functional", ["None identified."])))

                # Internal Database Output
                st.markdown("---")
                st.subheader("📋 Routine Placements (For Internal Database)")
                if routine_matches:
                    # Use an expander to keep the UI clean
                    with st.expander(f"Found {len(routine_matches)} suitable routine placements. Click to view."):
                        # Displaying as a code block makes it easy to copy-paste
                        st.code("\n".join(routine_matches))
                else:
                    st.warning("No perfect routine placements found for this product based on the current rules.")

            except Exception as e:
                st.error(f"An unexpected error occurred during analysis: {e}")


