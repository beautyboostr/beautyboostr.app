# --- REPLACEMENT for analyze_ingredient_functions in engine.py ---
def analyze_ingredient_functions(ingredients_with_percentages, all_data):
    db_names = all_data["ingredient_names_for_matching"]
    ingredients_dict = {item['inci_name'].lower(): item for item in all_data["ingredients"]}
    annotated_list = []
    
    for item in ingredients_with_percentages:
        ingredient_name_lower = item['name'].lower()
        # Handle the common case of "Aqua" by standardizing it to "water"
        if ingredient_name_lower == 'aqua':
            ingredient_name_lower = 'water'
            
        functions, source = [], "Heuristic"
        best_match = None

        # --- CORRECTED LOGIC ---
        # 1. Prioritize a direct, exact match before using fuzzy logic.
        if ingredient_name_lower in db_names:
            best_match = (ingredient_name_lower, 100)  # Simulate a perfect match
        # 2. If no exact match, THEN use fuzzy matching as a fallback.
        else:
            best_match = process.extractOne(ingredient_name_lower, db_names, score_cutoff=85)
        # --- END OF CORRECTION ---

        if best_match:
            matched_name = best_match[0]
            data = ingredients_dict.get(matched_name)
            if data and isinstance(data.get('behaviors'), list):
                for behavior in data['behaviors']:
                    if isinstance(behavior, dict) and behavior.get('functions'):
                        functions.extend(behavior.get('functions', []))
                if functions:
                    source = f"Database (Match: {matched_name})"

        if source == "Heuristic": # Heuristic fallback if DB lookup fails
            if "extract" in ingredient_name_lower: functions.extend(["Antioxidant", "Soothing"])
            if "ferment" in ingredient_name_lower or "lactobacillus" in ingredient_name_lower: functions.extend(["Soothing", "Hydration"])
            if "water" in ingredient_name_lower and "aqua" not in ingredient_name_lower: functions.extend(["Soothing", "Hydration"])

        positive_functions = ["Hydration", "Soothing", "Antioxidant", "Brightening", "Anti-aging", "Exfoliation (mild)", "Barrier Support", "Sebum Regulation", "UV Protection", "Emollient", "Humectant"]
        unique_functions = list(set(functions))
        classification = "Positive Impact" if any(pf in unique_functions for pf in positive_functions) else "Neutral/Functional"
        
        item.update({'functions': unique_functions, 'classification': classification, 'source': source})
        annotated_list.append(item)

    st.write(f"**[DEBUG] Stage 3: Ingredient Functions Analyzed.**")
    st.text("\n".join([f"- {ing['name']} (Source: {ing.get('source', 'N/A')}): {ing.get('functions', [])}" for ing in annotated_list if ing['classification'] == 'Positive Impact']))
    return annotated_list
