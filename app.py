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
st.markdown("Enter a product's name and its full ingredient (INCI) list. If you know the percentage of any ingredients, add them to the optional field.")

# --- Input Fields ---
col1, col2, col3 = st.columns(3)
with col1:
    product_name = st.text_input(
        "Product Name",
        placeholder="e.g., Glow Up Hydrating Serum"
    )

with col2:
    inci_list_str = st.text_area(
        "Ingredient (INCI) List",
        placeholder="Paste the full ingredient list here, separated by commas...",
        height=150
    )

with col3:
    known_percentages_str = st.text_area(
        "Known Percentages (Optional)",
        placeholder="e.g., Niacinamide: 5, Salicylic Acid: 2.0",
        height=150,
        help="Enter known ingredient concentrations, separated by commas. Format: Ingredient Name: Percentage"
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
            try:
                # This single function call runs the entire backend logic from engine.py
                # Updated to pass the new known_percentages_str
                ai_says_output, formula_breakdown, routine_matches = engine.run_full_analysis(
                    product_name, 
                    inci_list_str,
                    known_percentages_str 
                )

                # --- Display the Final Output ---
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
                            st.markdown("#####  neutral Neutral/Functional")
                            st.write(", ".join(formula_breakdown.get("Neutral/Functional", ["None"])))

                        st.subheader("📋 Routine Placements (Internal Use):")
                        if routine_matches:
                            st.code("\n".join(routine_matches), language=None)
                        else:
                            st.info("No perfect routine placements were found based on the analysis.")

            except Exception:
                st.error("An unexpected error occurred in the main application.")
                st.code(traceback.format_exc())

