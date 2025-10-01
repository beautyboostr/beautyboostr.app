import streamlit as st
import json
import traceback

# --- DATA LOADING ---

@st.cache_data
def load_all_data():
    """
    Loads all necessary JSON data files from the 'data' folder with specific error handling.
    """
    data = {}
    files = {
        "skin_types": "data/skin_types.json",
        "routines": "data/routines.json",
        "product_profiles": "data/product_profiles.json",
        "product_functions": "data/product_functions.json",
        "one_percent_markers": "data/one_percent_markers.json",
        "ingredients": "data/ingredients.json",
        "narrative_templates": "data/narrative_templates.json",
        "scoring_config": "data/scoring_config.json"
    }
    for name, path in files.items():
        try:
            # The 'utf-8-sig' encoding handles the BOM character issue
            with open(path, 'r', encoding='utf-8-sig') as f:
                data[name] = json.load(f)
        except FileNotFoundError:
            # This error is critical and should stop the app
            raise FileNotFoundError(f"Fatal Error: A required data file was not found at '{path}'. Please ensure your 'data' folder is correctly placed.")
        except json.JSONDecodeError as e:
            # This error is also critical and should stop the app
            raise ValueError(f"Fatal Error: Error decoding JSON from file '{path}': {e}. Please validate the file format.")
        except Exception as e:
            # Catch any other unexpected errors during file loading
            raise RuntimeError(f"An unexpected error occurred loading '{path}': {e}")
            
    return data

# --- MAIN ANALYSIS ORCHESTRATOR ---

def run_full_analysis(product_name, inci_list_str, all_data):
    """
    The main orchestrator function that runs the entire analysis pipeline.
    """
    try:
        # --- 1. PRE-PROCESSING ---
        st.write("---")
        st.write("### 🧠 AI Analysis Log")
        st.write("_[This log shows the AI's step-by-step reasoning]_")
        
        inci_list = [item.strip().lower() for item in inci_list_str.split(',')]
        st.write(f"**[DEBUG] Step 0: Pre-processing complete.** Found {len(inci_list)} ingredients.")

        # --- 2. EXECUTE THE ALGORITHM ---
        
        # Stage 1: Product Deconstruction
        profile = get_product_profile(product_name, all_data["product_profiles"])
        
        # This is the corrected, more robust percentage estimation function
        ingredients_with_percentages = estimate_percentages(inci_list, profile, all_data["one_percent_markers"], all_data["ingredients"])
        st.write(f"**[DEBUG] Stage 2: Percentages Estimated.** Top 3 ingredients: `{', '.join([f'{ing[\"name\"]} ({ing[\"estimated_percentage\"]:.2f}%)' for ing in ingredients_with_percentages[:3]])}`")

        analyzed_ingredients = analyze_ingredient_functions(ingredients_with_percentages, all_data["ingredients"])
        st.write(f"**[DEBUG] Stage 3: Ingredient Functions Analyzed.** Total functions found: {sum(len(ing.get('functions', [])) for ing in analyzed_ingredients)}")

        product_role = identify_product_role(analyzed_ingredients, all_data["product_functions"])
        st.write(f"**[DEBUG] Stage 4: Primary Product Role Identified.** Role: **{product_role}**")
        
        # Stage 2: Narrative Generation
        ai_says_output, formula_breakdown = generate_analysis_output(analyzed_ingredients, all_data["narrative_templates"])
        st.write("**[DEBUG] Stage 5: Narratives and Breakdowns Generated.**")

        # Stage 3: Matching & Internal Output
        routine_matches = find_all_routine_matches(product_role, analyzed_ingredients, all_data)
        st.write(f"**[DEBUG] Stage 6: Routine Matching Complete.** Found **{len(routine_matches)}** perfect placements.")

        return ai_says_output, formula_breakdown, routine_matches

    except Exception as e:
        # This will catch any error during the analysis and display it clearly
        st.error(f"An unexpected error occurred during analysis: {e}")
        st.code(traceback.format_exc())
        return None, None, None


# --- STAGE 1: DECONSTRUCTION FUNCTIONS ---

def get_product_profile(product_name, profiles_data):
    """
    Identifies the product type from its name and returns the corresponding profile.
    """
    name_lower = product_name.lower()
    
    keyword_map = {
        "oil cleanser": "Cleanser (Oil-based)", "cleansing oil": "Cleanser (Oil-based)", "cleansing balm": "Cleanser (Oil-based)",
        "cream cleanser": "Cleanser (Cream)", "milk cleanser": "Cleanser (Cream)",
        "foaming cleanser": "Cleanser (Foaming)", "cleanser": "Cleanser (Foaming)",
        "rich cream": "Moisturizer (Rich)", "barrier cream": "Moisturizer (Rich)", "night cream": "Moisturizer (Rich)",
        "lotion": "Moisturizer (Lightweight)", "gel cream": "Moisturizer (Lightweight)",
        "cream": "Moisturizer (Rich)", "moisturizer": "Moisturizer (Lightweight)",
        "sunscreen": "Sunscreen", "spf": "Sunscreen",
        "serum": "Serum", "essence": "Essence", "toner": "Toner",
        "clay mask": "Mask (Clay)", "mask": "Mask (Wash-off Gel/Cream)",
        "face oil": "Face Oil", "eye cream": "Eye Cream", "lip balm": "Lip Balm", "mist": "Mist"
    }

    for keyword, profile_key in keyword_map.items():
        if keyword in name_lower:
            st.write(f"**[DEBUG] Stage 1: Product Profile Identified.** Keyword: `{keyword}`. Profile: **{profile_key}**")
            profile = profiles_data.get(profile_key)
            if profile:
                return profile
            else:
                st.warning(f"Keyword `{keyword}` matched, but profile key `{profile_key}` not found in `product_profiles.json`. Using default.")
                break # Stop searching if a keyword matched but profile was missing

    # Default fallback if no keywords match or if matched key is invalid
    st.warning("Could not automatically determine product type from name. Using 'Serum' as a default.")
    return profiles_data.get("Serum")


def estimate_percentages(inci_list, profile, markers, ingredients_data):
    """
    Estimates ingredient percentages based on INCI list, product profile, and markers.
    This is a more robust, rule-based heuristic model.
    """
    if not profile:
        raise ValueError("Cannot estimate percentages without a valid product profile.")

    percentages = {name: 0 for name in inci_list}
    
    # 1. Find the 1% Line
    one_percent_line_index = -1
    for i, ingredient in enumerate(inci_list):
        if ingredient in markers.get("markers", []):
            one_percent_line_index = i
            break
            
    # If no marker is found, guess it's around 60% of the way down the list for non-cleansers
    if one_percent_line_index == -1:
        if "cleanser" not in profile.get("notes", "").lower():
            one_percent_line_index = int(len(inci_list) * 0.6)
        else:
            # For cleansers, the line is often much earlier
            one_percent_line_index = int(len(inci_list) * 0.3)

    # 2. Anchor Key Ingredients
    # Anchor the base solvent
    base_solvent = inci_list[0]
    percentages[base_solvent] = sum(profile.get("base_solvent_range", [70, 85])) / 2

    # Assign small, decreasing percentages to everything at or after the 1% line
    current_perc = 1.0
    if one_percent_line_index != -1:
        for i in range(one_percent_line_index, len(inci_list)):
            percentages[inci_list[i]] = current_perc
            current_perc = max(0.01, current_perc * 0.8) # Decrease but don't go to zero
            
    # 3. Distribute the Remainder
    # Sum up what we've allocated so far
    allocated_sum = sum(percentages.values())
    remaining_percentage = 100 - allocated_sum
    
    # Identify the ingredients to distribute among (those between base and 1% line)
    to_distribute = [ing for ing in inci_list[1:one_percent_line_index] if percentages[ing] == 0]

    if to_distribute and remaining_percentage > 0:
        # Simple weighted distribution for MVP: give more to ingredients higher on the list
        weights = list(reversed(range(1, len(to_distribute) + 1)))
        total_weight = sum(weights)
        
        for i, ingredient in enumerate(to_distribute):
            percentages[ingredient] = (weights[i] / total_weight) * remaining_percentage
            
    # 4. Normalize to 100%
    current_total = sum(percentages.values())
    if current_total > 0:
        normalization_factor = 100 / current_total
        for ingredient in percentages:
            percentages[ingredient] *= normalization_factor

    # Final output format
    return [{"name": name, "estimated_percentage": perc} for name, perc in percentages.items()]


def analyze_ingredient_functions(ingredients_with_percentages, ingredients_data):
    """
    Looks up each ingredient, attaches its functions, and classifies it.
    """
    # Create a fast lookup dictionary for ingredients
    ingredients_dict = {item['inci_name'].lower(): item for item in ingredients_data}
    
    annotated_list = []
    for item in ingredients_with_percentages:
        ingredient_name_lower = item['name'].lower()
        data = ingredients_dict.get(ingredient_name_lower, {})
        
        # Simple function extraction for now; can be enhanced with behavior logic later
        functions = []
        if data.get('behaviors'):
            # For MVP, just take all functions regardless of conditions
            for behavior in data['behaviors']:
                functions.extend(behavior.get('functions', []))
        
        # Classify the ingredient
        positive_functions = ["Hydration", "Soothing", "Antioxidant", "Brightening", "Anti-aging", "Exfoliation (mild)", "Barrier Support", "Sebum Regulation", "UV Protection"]
        is_positive = any(pf in funcs for pf in positive_functions for funcs in functions)
        classification = "Positive Impact" if is_positive else "Neutral/Functional"

        item['functions'] = list(set(functions)) # Remove duplicates
        item['classification'] = classification
        annotated_list.append(item)
        
    return annotated_list

def identify_product_role(analyzed_ingredients, function_rules):
    """
    Determines the product's primary role based on its functions.
    """
    product_functions = set()
    for ing in analyzed_ingredients:
        product_functions.update(ing.get('functions', []))
        
    best_match = "Unknown"
    highest_score = 0

    for role, rules in function_rules.items():
        score = 0
        must_haves = rules.get('must_have_functions', [])
        good_to_haves = rules.get('good_to_have_functions', [])
        
        # Check if all must-haves are present
        if all(f in product_functions for f in must_haves):
            score += len(must_haves) * 2 # Give more weight to must-haves
            # Add points for good-to-haves
            for f in good_to_haves:
                if f in product_functions:
                    score += 1
            
            if score > highest_score:
                highest_score = score
                best_match = role
                
    return best_match

# --- STAGE 2: NARRATIVE & OUTPUT FUNCTIONS ---

def generate_analysis_output(analyzed_ingredients, templates):
    """
    Generates the 'AI Assistant Says' narratives and the formula breakdown.
    """
    # This is a placeholder for the full narrative generation logic
    ai_says_output = "Narrative generation is not fully implemented yet."
    
    formula_breakdown = {
        "Positive Impact": [ing['name'] for ing in analyzed_ingredients if ing['classification'] == 'Positive Impact'],
        "Neutral/Functional": [ing['name'] for ing in analyzed_ingredients if ing['classification'] == 'Neutral/Functional']
    }
    
    return ai_says_output, formula_breakdown

# --- STAGE 3: MATCHING FUNCTIONS ---

def find_all_routine_matches(product_role, analyzed_ingredients, all_data):
    """
    Finds all suitable skin types and routine placements for the product.
    """
    # This is a placeholder for the full matching and scoring logic
    routine_matches = ["Routine matching is not fully implemented yet."]
    
    return routine_matches

