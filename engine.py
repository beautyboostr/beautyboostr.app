import streamlit as st
import json
import traceback
import re

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
        "scoring_config": "data/scoring_config.json",
        "prohibited_ingredients": "data/prohibited_ingredients.json",
        "category_scoring_rules": "data/category_scoring_rules.json"
    }
    
    for name, path in files_to_load.items():
        try:
            with open(path, 'r', encoding='utf-8-sig') as f:
                data[name] = json.load(f)
        except FileNotFoundError:
            raise FileNotFoundError(f"Fatal Error: A required data file was not found at '{path}'. Please ensure it's in the 'data' folder.")
        except json.JSONDecodeError as e:
            raise ValueError(f"Fatal Error: Error decoding JSON from file '{path}': {e}. Please validate the file's format.")
            
    return data

try:
    ALL_DATA = load_all_data()
except (FileNotFoundError, ValueError) as e:
    st.error(str(e))
    st.stop()

# --- HELPER FUNCTION ---
def parse_known_percentages(known_percentages_str):
    """Parses the user input for known percentages into a dictionary."""
    known_percentages = {}
    if not known_percentages_str:
        return known_percentages
    
    pairs = known_percentages_str.split(',')
    for pair in pairs:
        if ':' in pair:
            try:
                name, perc_str = pair.split(':', 1)
                name = name.strip().lower()
                perc = float(perc_str.strip())
                known_percentages[name] = perc
            except ValueError:
                continue
    return known_percentages

# --- MAIN ANALYSIS ORCHESTRATOR ---
def run_full_analysis(product_name, inci_list_str, known_percentages_str):
    """
    The main orchestrator function that runs the entire analysis pipeline.
    """
    try:
        st.write("---")
        st.write("### 🧠 AI Analysis Log")
        st.write("_[This log shows the AI's step-by-step reasoning]_")
        
        inci_list = [item.strip().lower() for item in inci_list_str.split(',') if item.strip()]
        st.write(f"**[DEBUG] Step 0: Pre-processing complete.** Found {len(inci_list)} ingredients.")

        # STAGE 0: Safety Check
        prohibited_found = check_for_prohibited(inci_list, ALL_DATA["prohibited_ingredients"])
        if prohibited_found:
            st.error(f"⚠️ **SAFETY ALERT:** This product contains a substance prohibited in cosmetic products in the EU: **{prohibited_found.title()}**. Analysis halted.")
            return None, None, None

        known_percentages = parse_known_percentages(known_percentages_str)
        st.write(f"**[DEBUG] Known Percentages Parsed:** `{known_percentages}`")
        
        profile, profile_key = get_product_profile(product_name, ALL_DATA["product_profiles"])
        if not profile:
            st.error("Fatal Error: Could not retrieve a valid product profile. Analysis halted.")
            return None, None, None
            
        ingredients_with_percentages = estimate_percentages(inci_list, profile, ALL_DATA["one_percent_markers"], known_percentages)
        analyzed_ingredients = analyze_ingredient_functions(ingredients_with_percentages, ALL_DATA["ingredients"])
        product_roles = identify_product_roles(analyzed_ingredients, ALL_DATA["product_functions"], profile_key)
        
        # STAGE 2: Narrative Generation with NEW SCORING
        ai_says_output, formula_breakdown = generate_analysis_output(analyzed_ingredients, ALL_DATA["narrative_templates"], ALL_DATA["category_scoring_rules"])
        
        # STAGE 3: Matching & Internal Output
        routine_matches = find_all_routine_matches(product_roles, analyzed_ingredients, ALL_DATA)

        return ai_says_output, formula_breakdown, routine_matches

    except Exception:
        st.error("An unexpected error occurred during the analysis process.")
        st.code(traceback.format_exc())
        return None, None, None

# --- STAGE 0 FUNCTION ---
def check_for_prohibited(inci_list, prohibited_data):
    prohibited_set = set(ing.lower() for ing in prohibited_data.get("ingredients", []))
    for ingredient in inci_list:
        if ingredient in prohibited_set:
            return ingredient
    return None

# --- STAGE 1 FUNCTIONS ---
def get_product_profile(product_name, profiles_data):
    name_lower = product_name.lower()
    keyword_map = {
        "oil cleanser": "Cleanser (Oil-based)", "cleansing oil": "Cleanser (Oil-based)", "cleansing balm": "Cleanser (Oil-based)",
        "cream cleanser": "Cleanser (Cream)", "milk cleanser": "Cleanser (Cream)", "foaming cleanser": "Cleanser (Foaming)",
        "rich cream": "Moisturizer (Rich)", "barrier cream": "Moisturizer (Rich)", "night cream": "Moisturizer (Rich)",
        "lotion": "Moisturizer (Lightweight)", "gel cream": "Moisturizer (Lightweight)", "sunscreen": "Sunscreen", "spf": "Sunscreen",
        "serum": "Serum", "essence": "Essence", "toner": "Toner", "clay mask": "Mask (Clay)", "mask": "Mask (Wash-off Gel/Cream)",
        "face oil": "Face Oil", "eye cream": "Eye Cream", "lip balm": "Lip Balm", "mist": "Mist",
        "cleanser": "Cleanser (Foaming)", "cream": "Moisturizer (Rich)", "moisturizer": "Moisturizer (Lightweight)"
    }
    for keyword, profile_key in keyword_map.items():
        if keyword in name_lower:
            profile = profiles_data.get(profile_key)
            if profile:
                st.write(f"**[DEBUG] Stage 1: Product Profile Identified.** Keyword: `{keyword}`. Profile: **{profile_key}**")
                return profile, profile_key
    st.warning("Could not automatically determine product type. Using 'Serum' as a default.")
    return profiles_data.get("Serum"), "Serum"

def estimate_percentages(inci_list, profile, markers, known_percentages):
    percentages = {name: None for name in inci_list}
    for name, perc in known_percentages.items():
        if name in percentages: percentages[name] = float(perc)
    
    for i in range(len(inci_list) - 1, -1, -1):
        current_ing = inci_list[i]
        if percentages[current_ing] is not None: continue
        floor_perc = 0.001
        if i + 1 < len(inci_list):
            next_ing = inci_list[i+1]
            if percentages[next_ing] is None:
                 raise ValueError("Estimation logic failed: encountered an un-estimated ingredient while moving backwards.")
            floor_perc = percentages[next_ing]
        estimated_perc = floor_perc * 1.1 + 0.01 
        one_percent_line_index = next((idx for idx, ing in enumerate(inci_list) if ing in markers.get("markers", [])), -1)
        if one_percent_line_index != -1 and i >= one_percent_line_index:
            estimated_perc = min(estimated_perc, 1.0)
        percentages[current_ing] = estimated_perc

    known_sum = sum(p for ing, p in percentages.items() if ing in known_percentages)
    if known_sum > 100:
        st.error("Error: The sum of known percentages exceeds 100%. Please check your input.")
        raise ValueError("Sum of known percentages exceeds 100%.")
    estimated_sum = sum(p for ing, p in percentages.items() if ing not in known_percentages)
    remaining_to_distribute = 100.0 - known_sum
    if estimated_sum > 0 and remaining_to_distribute > 0:
        factor = remaining_to_distribute / estimated_sum
        for ing in percentages:
            if ing not in known_percentages: percentages[ing] *= factor
    
    final_total = sum(percentages.values())
    if final_total > 0:
        final_factor = 100.0 / final_total
        for ing in percentages: percentages[ing] *= final_factor

    st.write(f"**[DEBUG] Stage 2: Full Estimated Formula.**")
    debug_percentage_list = [f"- {name}: {percentages[name]:.4f}%" for name in inci_list]
    st.text("\n".join(debug_percentage_list))
    return [{"name": name, "estimated_percentage": perc} for name, perc in percentages.items()]


def analyze_ingredient_functions(ingredients_with_percentages, ingredients_data):
    ingredients_dict = {item['inci_name'].lower(): item for item in ingredients_data}
    annotated_list = []
    for item in ingredients_with_percentages:
        ingredient_name_lower = item['name'].lower()
        data = ingredients_dict.get(ingredient_name_lower)
        functions = []
        source = "Heuristic" # Assume heuristic by default

        # Step 1: Prioritize the database. If found, use its data.
        if data and isinstance(data.get('behaviors'), list):
            for behavior in data['behaviors']:
                if isinstance(behavior, dict) and behavior.get('functions'):
                    functions.extend(behavior.get('functions', []))
            if functions: # If we found any functions in the DB
                source = "Database"

        # Step 2: If no functions were found in the database, use heuristics as a fallback.
        if not functions:
            if "extract" in ingredient_name_lower: functions.extend(["Antioxidant", "Soothing"])
            if "ferment" in ingredient_name_lower or "lactobacillus" in ingredient_name_lower: functions.extend(["Soothing", "Hydration"])
            if "water" in ingredient_name_lower and "aqua" not in ingredient_name_lower: functions.extend(["Soothing", "Hydration"]) # For hydrosols
            if "gluconolactone" in ingredient_name_lower: functions.extend(["Exfoliation (mild)", "Humectant"])
            if "salicylate" in ingredient_name_lower: functions.extend(["Exfoliation (mild)"])
            if "polyglutamate" in ingredient_name_lower: functions.extend(["Hydration", "Humectant"])

        # Step 3: Classify based on the final list of functions
        positive_functions = ["Hydration", "Soothing", "Antioxidant", "Brightening", "Anti-aging", "Exfoliation (mild)", "Barrier Support", "Sebum Regulation", "UV Protection", "Emollient", "Humectant"]
        unique_functions = list(set(functions))
        classification = "Positive Impact" if any(pf in unique_functions for pf in positive_functions) else "Neutral/Functional"
        
        item['functions'] = unique_functions
        item['classification'] = classification
        item['source'] = source # Add source for debugging
        annotated_list.append(item)

    st.write(f"**[DEBUG] Stage 3: Ingredient Functions Analyzed.**")
    debug_func_list = [f"- {ing['name']} (Source: {ing.get('source', 'N/A')}): {ing.get('functions', [])}" for ing in annotated_list if ing['classification'] == 'Positive Impact']
    st.text("\n".join(debug_func_list))
    return annotated_list

def identify_product_roles(analyzed_ingredients, function_rules, profile_key):
    product_functions = {func for ing in analyzed_ingredients for func in ing.get('functions', [])}
    matched_roles = []
    valid_roles_map = {
        "Toner": ["toner"], "Essence": ["essence"], "Serum": ["serum"],
        "Moisturizer (Lightweight)": ["moisturizer"], "Moisturizer (Rich)": ["moisturizer"],
        "Cleanser (Foaming)": ["cleanser"], "Cleanser (Cream)": ["cleanser"], "Cleanser (Oil-based)": ["cleanser"],
        "Mask (Wash-off Gel/Cream)": ["mask", "oil"], "Mask (Clay)": ["mask"], "Face Oil": ["oil", "mask"],
        "Eye Cream": ["eye cream"], "Sunscreen": ["spf", "sunscreen"], "Lip Balm": ["lip balm"], "Mist": ["mist"]
    }
    valid_keywords = valid_roles_map.get(profile_key, [])
    for role, rules in function_rules.items():
        if not isinstance(rules, dict): continue
        is_valid_type = any(keyword in role.lower() for keyword in valid_keywords)
        if not is_valid_type: continue
        must_haves = rules.get('must_have_functions', [])
        if all(f in product_functions for f in must_haves):
            matched_roles.append(role)
    if not matched_roles and profile_key: matched_roles.append(profile_key)
    st.write(f"**[DEBUG] Stage 4: Product Roles Identified.** Roles: **{', '.join(list(set(matched_roles)))}**")
    return list(set(matched_roles))

# --- STAGE 2 & 3 FUNCTIONS (UPGRADED) ---
def generate_analysis_output(analyzed_ingredients, templates, scoring_rules_data):
    ai_says_output = {}
    ingredient_percentages = {ing['name'].lower(): ing['estimated_percentage'] for ing in analyzed_ingredients}
    scoring_rules = scoring_rules_data.get("categories", {})

    for category_name, rules in scoring_rules.items():
        points, star_ingredients_found = 0, []
        supporting_ingredients_found = []
        generic_contributors_found = []

        # Layer 1: Score named "star" ingredients
        for star in rules.get("star_ingredients", []):
            star_name_lower = star["name"].lower()
            if star_name_lower in ingredient_percentages and ingredient_percentages[star_name_lower] >= star["min_effective_percent"]:
                points += star["points"]
                star_ingredients_found.append(star["name"].title())
        
        # Layer 2: Score named "supporting" ingredients
        for support_name, support_points in rules.get("supporting_ingredients", {}).items():
            support_name_lower = support_name.lower()
            if support_name_lower in ingredient_percentages:
                points += support_points
                if support_name.title() not in star_ingredients_found:
                    supporting_ingredients_found.append(support_name.title())

        # Layer 3: Score generic function contributors
        category_functions = rules.get("generic_functions", [])
        generic_bonus_points = rules.get("generic_function_bonus", 2)
        all_named_contributors = star_ingredients_found + supporting_ingredients_found
        for ing in analyzed_ingredients:
            if ing['classification'] == 'Positive Impact' and ing['name'].title() not in all_named_contributors:
                if any(func in category_functions for func in ing.get('functions', [])):
                    points += generic_bonus_points
                    generic_contributors_found.append(ing['name'].title())

        # Normalize score to 1-10
        max_points = rules.get("max_points", 1)
        final_score = min(10, round((points / max_points) * 9) + 1 if max_points > 0 else 1)
        
        # Generate Narrative
        if final_score >= 8: template_key = "high_score_generic" if not star_ingredients_found else "high_score"
        elif final_score >= 4: template_key = "medium_score"
        else: template_key = "low_score"
        
        narrative = templates.get(category_name, {}).get(template_key, "No narrative available.")
        
        all_contributors = star_ingredients_found + supporting_ingredients_found + generic_contributors_found
        unique_contributors = sorted(list(set(all_contributors)), key=lambda x: all_contributors.index(x))
        
        narrative = narrative.replace("{star_ingredients}", ", ".join(unique_contributors[:1]))
        narrative = narrative.replace("{supporting_ingredients}", ", ".join(unique_contributors[1:3]))
        narrative = narrative.replace("{generic_contributors}", ", ".join(unique_contributors[:2]))
        
        ai_says_output[category_name] = {"score": final_score, "narrative": narrative}

    formula_breakdown = {
        "Positive Impact": sorted(list(set([ing['name'].title() for ing in analyzed_ingredients if ing['classification'] == 'Positive Impact']))),
        "Neutral/Functional": sorted(list(set([ing['name'].title() for ing in analyzed_ingredients if ing['classification'] == 'Neutral/Functional'])))
    }
    
    st.write("**[DEBUG] Stage 5: Narratives and Breakdowns Generated.**")
    return ai_says_output, formula_breakdown


def find_all_routine_matches(product_roles, analyzed_ingredients, all_data):
    routine_matches, product_functions = [], {func for ing in analyzed_ingredients for func in ing.get('functions', [])}
    scoring_config = all_data["scoring_config"]
    for type_id, skin_type in all_data["skin_types"].items():
        if any(bad_ing.lower() in [ing['name'] for ing in analyzed_ingredients] for bad_ing in skin_type.get('bad_for_ingredients', [])): continue
        for routine_key, routine_details in all_data["routines"].items():
            if routine_key.startswith(type_id):
                for step in routine_details.get("steps", []):
                    if step["product_function"] in product_roles:
                        base_score, bonus_points, max_bonus = scoring_config["function_match_scores"]["perfect_match_base_points"], 0, 0
                        for priority_func in skin_type.get("good_for_functions", []):
                            func_name, priority = priority_func["function"], priority_func["priority"]
                            bonus_value = scoring_config["priority_fulfillment_scores"].get(f"{priority}_priority_bonus", 0)
                            max_bonus += bonus_value
                            if func_name in product_functions: bonus_points += bonus_value
                        total_score = base_score + bonus_points
                        max_possible_score = base_score + max_bonus
                        match_percent = (total_score / max_possible_score) * 100 if max_possible_score > 0 else 0
                        try:
                            skin_type_number = type_id.split(' ')[1]
                            routine_matches.append(f"ID {skin_type_number} Routine {routine_key} Step {step['step_number']} Match {match_percent:.0f}%")
                        except IndexError: continue
    st.write(f"**[DEBUG] Stage 6: Routine Matching Complete.** Found **{len(routine_matches)}** placements.")
    return routine_matches

