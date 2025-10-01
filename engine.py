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
    files_to_load = {
        "skin_types": "data/skin_types.json",
        "routines": "data/routines.json",
        "product_profiles": "data/product_profiles.json",
        "product_functions": "data/product_functions.json",
        "one_percent_markers": "data/one_percent_markers.json",
        "ingredients": "data/ingredients.json",
        "narrative_templates": "data/narrative_templates.json",
        "scoring_config": "data/scoring_config.json"
    }
    
    for name, path in files_to_load.items():
        try:
            with open(path, 'r', encoding='utf-8-sig') as f:
                data[name] = json.load(f)
        except FileNotFoundError:
            raise FileNotFoundError(f"Fatal Error: A required data file was not found at '{path}'. Please ensure your 'data' folder is correctly placed and the file is named correctly.")
        except json.JSONDecodeError as e:
            raise ValueError(f"Fatal Error: Error decoding JSON from file '{path}': {e}. Please validate the file's format.")
        except Exception as e:
            raise RuntimeError(f"An unexpected error occurred while loading '{path}': {e}")
            
    return data

try:
    ALL_DATA = load_all_data()
except (FileNotFoundError, ValueError, RuntimeError) as e:
    st.error(str(e))
    st.stop()

# --- MAIN ANALYSIS ORCHESTRATOR ---
def run_full_analysis(product_name, inci_list_str, selected_skin_type_id=None):
    try:
        st.write("---")
        st.write("### 🧠 AI Analysis Log")
        st.write("_[This log shows the AI's step-by-step reasoning]_")
        
        inci_list = [item.strip().lower() for item in inci_list_str.split(',') if item.strip()]
        st.write(f"**[DEBUG] Step 0: Pre-processing complete.** Found {len(inci_list)} ingredients.")

        # STAGE 1: Deconstruction
        profile = get_product_profile(product_name, ALL_DATA["product_profiles"])
        if not profile:
            st.error("Fatal Error: Could not retrieve a valid product profile. Analysis halted.")
            return None, None, None
            
        ingredients_with_percentages = estimate_percentages(inci_list, profile, ALL_DATA["one_percent_markers"])
        analyzed_ingredients = analyze_ingredient_functions(ingredients_with_percentages, ALL_DATA["ingredients"])
        product_role = identify_product_role(analyzed_ingredients, ALL_DATA["product_functions"])
        
        # STAGE 2: Narrative Generation
        ai_says_output, formula_breakdown = generate_analysis_output(analyzed_ingredients, ALL_DATA["narrative_templates"])
        
        # STAGE 3: Matching & Internal Output
        routine_matches = find_all_routine_matches(product_role, analyzed_ingredients, ALL_DATA)

        return ai_says_output, formula_breakdown, routine_matches

    except Exception as e:
        st.error("An unexpected error occurred during the analysis process.")
        st.code(traceback.format_exc())
        return None, None, None

# --- STAGE 1 FUNCTIONS (CORRECTED) ---
def get_product_profile(product_name, profiles_data):
    name_lower = product_name.lower()
    keyword_map = {
        "oil cleanser": "Cleanser (Oil-based)", "cleansing oil": "Cleanser (Oil-based)", "cleansing balm": "Cleanser (Oil-based)",
        "cream cleanser": "Cleanser (Cream)", "milk cleanser": "Cleanser (Cream)",
        "foaming cleanser": "Cleanser (Foaming)",
        "rich cream": "Moisturizer (Rich)", "barrier cream": "Moisturizer (Rich)", "night cream": "Moisturizer (Rich)",
        "lotion": "Moisturizer (Lightweight)", "gel cream": "Moisturizer (Lightweight)",
        "sunscreen": "Sunscreen", "spf": "Sunscreen",
        "serum": "Serum", "essence": "Essence", "toner": "Toner",
        "clay mask": "Mask (Clay)", "mask": "Mask (Wash-off Gel/Cream)",
        "face oil": "Face Oil", "eye cream": "Eye Cream", "lip balm": "Lip Balm", "mist": "Mist",
        "cleanser": "Cleanser (Foaming)", "cream": "Moisturizer (Rich)", "moisturizer": "Moisturizer (Lightweight)"
    }
    for keyword, profile_key in keyword_map.items():
        if keyword in name_lower:
            profile = profiles_data.get(profile_key)
            if profile:
                st.write(f"**[DEBUG] Stage 1: Product Profile Identified.** Keyword: `{keyword}`. Profile: **{profile_key}**")
                return profile
    st.warning("Could not automatically determine product type from the name. Using 'Serum' as a default profile.")
    default_profile = profiles_data.get("Serum")
    if not default_profile:
        st.error("CRITICAL ERROR: The default 'Serum' profile is missing from product_profiles.json!")
        return None
    return default_profile

def estimate_percentages(inci_list, profile, markers):
    if not profile:
        raise ValueError("Cannot estimate percentages without a valid product profile.")

    percentages = {name: 0.0 for name in inci_list}
    
    # 1. Find the true base solvent (Water/Aqua/Eau)
    base_solvent_name = None
    water_aliases = ["water/aqua/eau", "aqua", "water"]
    for alias in water_aliases:
        if alias in inci_list:
            base_solvent_name = alias
            break
    
    # Anchor the base solvent percentage, regardless of its position
    if base_solvent_name:
        base_percentage = sum(profile.get("base_solvent_range", [70, 85])) / 2.0
        percentages[base_solvent_name] = base_percentage
    else:
        # If no water is found (e.g., an oil), distribute 100% among all ingredients
        base_percentage = 0

    # 2. Find the 1% Line
    one_percent_line_index = next((i for i, ing in enumerate(inci_list) if ing in markers.get("markers", [])), -1)
    if one_percent_line_index == -1:
        one_percent_line_index = int(len(inci_list) * 0.5)  # Fallback guess

    # 3. Anchor sub-1% ingredients
    current_perc = 1.0
    sub_one_ingredients = [ing for ing in inci_list[one_percent_line_index:] if percentages[ing] == 0.0]
    for ing in sub_one_ingredients:
        percentages[ing] = current_perc
        current_perc = max(0.01, current_perc * 0.85)

    # 4. Distribute the remaining percentage among the 'middle' ingredients
    allocated_sum = sum(percentages.values())
    remaining_to_distribute = 100.0 - allocated_sum
    
    # Identify ingredients between the start and the 1% line that are not yet allocated
    unallocated_ingredients = [ing for ing in inci_list[:one_percent_line_index] if percentages[ing] == 0.0]

    if unallocated_ingredients and remaining_to_distribute > 0:
        # Simple distribution for MVP: divide equally then apply descending weight
        # This is a heuristic and can be improved, but it's more robust than the previous version
        num_unallocated = len(unallocated_ingredients)
        base_share = remaining_to_distribute / num_unallocated
        
        # Apply a simple descending weight to respect the order
        for i, ingredient in enumerate(unallocated_ingredients):
             # A simple linear decay, can be made more sophisticated
            decay_factor = (num_unallocated - i) / num_unallocated
            percentages[ingredient] = base_share * (1 + decay_factor)


    # 5. Normalize to 100%
    current_total = sum(percentages.values())
    if current_total > 0:
        factor = 100.0 / current_total
        for ing in percentages:
            percentages[ing] *= factor
    
    sorted_percentages = sorted(percentages.items(), key=lambda item: item[1], reverse=True)
    top_3_debug_msg = ", ".join([f'{name} ({perc:.2f}%)' for name, perc in sorted_percentages[:3]])
    st.write(f"**[DEBUG] Stage 2: Percentages Estimated.** Top 3: `{top_3_debug_msg}`")
    return [{"name": name, "estimated_percentage": perc} for name, perc in percentages.items()]


def analyze_ingredient_functions(ingredients_with_percentages, ingredients_data):
    ingredients_dict = {item['inci_name'].lower(): item for item in ingredients_data}
    annotated_list = []
    
    for item in ingredients_with_percentages:
        ingredient_name_lower = item['name'].lower()
        data = ingredients_dict.get(ingredient_name_lower, {})
        functions = []
        if data.get('behaviors'):
            for behavior in data['behaviors']:
                functions.extend(behavior.get('functions', []))
        
        positive_functions = ["Hydration", "Soothing", "Antioxidant", "Brightening", "Anti-aging", "Exfoliation (mild)", "Barrier Support", "Sebum Regulation", "UV Protection", "Emollient", "Humectant"]
        is_positive = any(pf in funcs for pf in positive_functions for funcs in functions)
        classification = "Positive Impact" if is_positive else "Neutral/Functional"

        item['functions'] = list(set(functions))
        item['classification'] = classification
        annotated_list.append(item)
        
    st.write(f"**[DEBUG] Stage 3: Ingredient Functions Analyzed.** Total functions found: {sum(len(ing.get('functions', [])) for ing in annotated_list)}")
    return annotated_list

def identify_product_role(analyzed_ingredients, function_rules):
    product_functions = {func for ing in analyzed_ingredients for func in ing.get('functions', [])}
    best_match, highest_score = "Unknown", 0

    for role, rules in function_rules.items():
        score = 0
        must_haves = rules.get('must_have_functions', [])
        if all(f in product_functions for f in must_haves):
            score += len(must_haves)
            if score > highest_score:
                highest_score, best_match = score, role
    
    st.write(f"**[DEBUG] Stage 4: Primary Product Role Identified.** Role: **{best_match}**")
    return best_match

# --- STAGE 2 & 3 FUNCTIONS ---
def generate_analysis_output(analyzed_ingredients, templates):
    analysis_categories = {
        "Hydration & Skin Barrier Support": ["Hydration", "Humectant", "Barrier Support", "Emollient", "Occlusive"],
        "Brightening & Even Skin Tone": ["Brightening", "Anti-pigmentation", "Exfoliation (mild)"],
        "Soothing & Redness Reduction": ["Soothing", "Anti-inflammatory"],
        "Pore Appearance & Texture Improvement": ["Exfoliation (mild)", "Sebum Regulation"],
        "Anti-aging & Wrinkle Reduction": ["Anti-aging", "Collagen Synthesis", "Antioxidant"]
    }
    
    ai_says_output = {}
    for category, funcs in analysis_categories.items():
        score = 0
        star_ingredients = []
        for ing in analyzed_ingredients:
            if any(f in ing.get('functions', []) for f in funcs):
                score += ing['estimated_percentage']
                if ing['classification'] == 'Positive Impact':
                    star_ingredients.append(ing['name'].title())
        
        final_score = min(10, int(score / 5) + 1)
        
        if final_score >= 8: template_key = "high_score"
        elif final_score >= 4: template_key = "medium_score"
        else: template_key = "low_score"
        
        narrative = templates.get(category, {}).get(template_key, "No narrative available.")
        narrative = narrative.replace("{star_ingredients}", ", ".join(list(set(star_ingredients[:2]))))
        
        ai_says_output[category] = {"score": final_score, "narrative": narrative}

    formula_breakdown = {
        "Positive Impact": sorted(list(set([ing['name'].title() for ing in analyzed_ingredients if ing['classification'] == 'Positive Impact']))),
        "Neutral/Functional": sorted(list(set([ing['name'].title() for ing in analyzed_ingredients if ing['classification'] == 'Neutral/Functional'])))
    }
    
    st.write("**[DEBUG] Stage 5: Narratives and Breakdowns Generated.**")
    return ai_says_output, formula_breakdown

def find_all_routine_matches(product_role, analyzed_ingredients, all_data):
    routine_matches = []
    product_functions = {func for ing in analyzed_ingredients for func in ing.get('functions', [])}
    scoring_config = all_data["scoring_config"]

    for type_id, skin_type in all_data["skin_types"].items():
        if any(bad_ing.lower() in [ing['name'] for ing in analyzed_ingredients] for bad_ing in skin_type.get('bad_for_ingredients', [])):
            continue

        for routine_key, routine_details in all_data["routines"].items():
            if routine_key.startswith(type_id):
                for step in routine_details.get("steps", []):
                    if step["product_function"] == product_role:
                        
                        base_score = scoring_config["function_match_scores"]["perfect_match_base_points"]
                        bonus_points = 0
                        max_bonus = 0
                        
                        for priority_func in skin_type.get("good_for_functions", []):
                            func_name = priority_func["function"]
                            priority = priority_func["priority"]
                            
                            bonus_value = scoring_config["priority_fulfillment_scores"].get(f"{priority}_priority_bonus", 0)
                            max_bonus += bonus_value
                            if func_name in product_functions:
                                bonus_points += bonus_value
                        
                        total_score = base_score + bonus_points
                        max_possible_score = base_score + max_bonus
                        match_percent = (total_score / max_possible_score) * 100 if max_possible_score > 0 else 0
                        
                        # Correctly extract the numeric part of the skin type ID
                        try:
                            skin_type_number = type_id.split(' ')[1]
                            match_str = f"ID {skin_type_number} Routine {routine_key} Step {step['step_number']} Match {match_percent:.0f}%"
                            routine_matches.append(match_str)
                        except IndexError:
                            # Handle cases where the type_id format might be unexpected
                            continue

    st.write(f"**[DEBUG] Stage 6: Routine Matching Complete.** Found **{len(routine_matches)}** placements.")
    return routine_matches

