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
st.markdown("Enter a product's name, its full ingredient (INCI) list, and any known ingredient percentages.")

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
                # MODIFIED: Function call now unpacks the new 'potential_concerns' variable
                ai_says_output, formula_breakdown, routine_matches, potential_concerns = engine.run_full_analysis(
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
                            # Don't show a score for the summary
                            score_display = f"**Score {details['score']}/10**" if details['score'] else ""
                            st.markdown(f"**{category}:** {score_display}")
                            st.write(details['narrative'])

                        # REPLACED: New breakdown section using expanders and showing concerns
                        st.subheader("🔬 Formula Effectiveness Breakdown:")
                        # Sort categories by score to show the most relevant first
                        sorted_categories = sorted(
                            [item for item in ai_says_output.items() if item[0] != "Summary"],
                            key=lambda item: item[1]['score'],
                            reverse=True
                        )

                        for category_name, details in sorted_categories:
                            # Only show for relevant categories with a score above 3.0
                            if details['score'] > 3.0 and category_name in formula_breakdown:
                                with st.expander(f"**{category_name} (Score: {details['score']}/10)**"):
                                    for list_name, ingredients in formula_breakdown[category_name].items():
                                        if ingredients: # Only show if the list is not empty
                                            st.markdown(f"**{list_name}:**")
                                            st.write(" • " + " • ".join(ingredients))

                        # Display Potential Concerns if any were found
                        if potential_concerns:
                            st.subheader("⚠️ Potential Concerns & Usage Notes:")
                            for concern in potential_concerns:
                                st.warning(concern)


                        st.subheader("📋 Routine Placements (Internal Use):")
                        if routine_matches:
                            st.code("\n".join(routine_matches), language=None)
                        else:
                            st.info("No perfect routine placements were found based on the analysis.")

            except Exception:
                st.error("An unexpected error occurred in the main application.")
                st.code(traceback.format_exc())
