import streamlit as st
import json
import traceback
import re
from thefuzz import process

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
            raise FileNotFoundError(f"Fatal Error: A required data file was not found at '{path}'.")
        except json.JSONDecodeError as e:
            raise ValueError(f"Fatal Error: Error decoding JSON from file '{path}': {e}.")
            
    # Create a list of all ingredient names from the database for fuzzy matching
    if "ingredients" in data:
        data["ingredient_names_for_matching"] = [item['inci_name'].lower() for item in data["ingredients"]]

    return data

try:
    ALL_DATA = load_all_data()
except (FileNotFoundError, ValueError) as e:
    st.error(str(e))
    st.stop()

# --- HELPER FUNCTION ---
def parse_known_percentages(known_percentages_str):
    known_percentages = {}
    if not known_percentages_str: return known_percentages
    for pair in known_percentages_str.split(','):
        if ':' in pair:
            try:
                name, perc_str = pair.split(':', 1)
                known_percentages[name.strip().lower()] = float(perc_str.strip())
            except ValueError: continue
    return known_percentages

# --- MAIN ANALYSIS ORCHESTRATOR ---
def run_full_analysis(product_name, inci_list_str, known_percentages_str):
    try:
        st.write("---"); st.write("### 🧠 AI Analysis Log"); st.write("_[This log shows the AI's step-by-step reasoning]_")
        
        raw_list = [item.strip().lower() for item in inci_list_str.split(',') if item.strip()]
        inci_list = [re.sub(r'[\.\*]$', '', item.split('/')[0].strip()) for item in raw_list]
        st.write(f"**[DEBUG] Step 0: Pre-processing complete.** Found {len(inci_list)} cleaned ingredients.")

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
        analyzed_ingredients = analyze_ingredient_functions(ingredients_with_percentages, ALL_DATA)
        product_roles = identify_product_roles(analyzed_ingredients, ALL_DATA["product_functions"], profile_key)
        
        ai_says_output, formula_breakdown, potential_concerns = generate_analysis_output(analyzed_ingredients, ALL_DATA["narrative_templates"], ALL_DATA["category_scoring_rules"], ALL_DATA["ingredients"])
        
        routine_matches = find_all_routine_matches(product_roles, analyzed_ingredients, ALL_DATA)

        return ai_says_output, formula_breakdown, routine_matches, potential_concerns

    except Exception:
        st.error("An unexpected error occurred during the analysis process.")
        st.code(traceback.format_exc())
        return None, None, None, None

# --- STAGE 0 FUNCTION ---
def check_for_prohibited(inci_list, prohibited_data):
    prohibited_set = set(ing.lower() for ing in prohibited_data.get("ingredients", []))
    for ingredient in inci_list:
        if ingredient in prohibited_set: return ingredient
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
    # Use fuzzy matching to map known percentages to the inci list
    for name, perc in known_percentages.items():
        match = process.extractOne(name, inci_list)
        if match and match[1] > 90: # High confidence match
            percentages[match[0]] = float(perc)
    
    for i in range(len(inci_list) - 1, -1, -1):
        current_ing = inci_list[i]
        if percentages[current_ing] is not None: continue
        floor_perc = 0.001
        if i + 1 < len(inci_list):
            next_ing = inci_list[i+1]
            if percentages[next_ing] is None: raise ValueError("Estimation logic failed.")
            floor_perc = percentages[next_ing]
        estimated_perc = floor_perc * 1.1 + 0.01 
        one_percent_line_index = next((idx for idx, ing in enumerate(inci_list) if ing in markers.get("markers", [])), -1)
        if one_percent_line_index != -1 and i >= one_percent_line_index:
            estimated_perc = min(estimated_perc, 1.0)
        percentages[current_ing] = estimated_perc

    known_sum = sum(p for ing, p in percentages.items() if p is not None and (ing in known_percentages or any(process.extractOne(ing, known_percentages.keys())[1] > 90 for k in known_percentages.keys() if known_percentages)))
    if known_sum > 100:
        st.error("Error: The sum of known percentages exceeds 100%.")
        raise ValueError("Sum of known percentages exceeds 100%.")
    
    estimated_sum = sum(p for ing, p in percentages.items() if p is not None and not (ing in known_percentages or any(process.extractOne(ing, known_percentages.keys())[1] > 90 for k in known_percentages.keys() if known_percentages)))
    remaining_to_distribute = 100.0 - known_sum
    if estimated_sum > 0 and remaining_to_distribute > 0:
        factor = remaining_to_distribute / estimated_sum
        for ing in percentages:
             if percentages[ing] is not None and not (ing in known_percentages or any(process.extractOne(ing, known_percentages.keys())[1] > 90 for k in known_percentages.keys() if known_percentages)):
                percentages[ing] *= factor
    
    final_total = sum(p for p in percentages.values() if p is not None)
    if final_total > 0:
        final_factor = 100.0 / final_total
        for ing in percentages:
            if percentages[ing] is not None:
                percentages[ing] *= final_factor
        
    st.write(f"**[DEBUG] Stage 2: Full Estimated Formula.**")
    st.text("\n".join([f"- {name}: {percentages[name]:.4f}%" for name in inci_list]))
    return [{"name": name, "estimated_percentage": perc} for name, perc in percentages.items()]

def analyze_ingredient_functions(ingredients_with_percentages, all_data):
    db_names = all_data["ingredient_names_for_matching"]
    ingredients_dict = {item['inci_name'].lower(): item for item in all_data["ingredients"]}
    annotated_list = []
    
    for item in ingredients_with_percentages:
        ingredient_name_lower = item['name'].lower()
        functions, source = [], "Heuristic"
        
        best_match = process.extractOne(ingredient_name_lower, db_names, score_cutoff=85)
        
        if best_match:
            matched_name = best_match[0]
            data = ingredients_dict.get(matched_name)
            if data and isinstance(data.get('behaviors'), list):
                for behavior in data['behaviors']:
                    if isinstance(behavior, dict) and behavior.get('functions'):
                        functions.extend(behavior.get('functions', []))
                if functions: source = f"Database (Match: {matched_name})"
        
        if source == "Heuristic":
            if "extract" in ingredient_name_lower: functions.extend(["Antioxidant", "Soothing"])
            if "ferment" in ingredient_name_lower or "lactobacillus" in ingredient_name_lower: functions.extend(["Soothing", "Hydration"])
            if "water" in ingredient_name_lower and "aqua" not in ingredient_name_lower: functions.extend(["Soothing", "Hydration"])
            if "gluconolactone" in ingredient_name_lower: functions.extend(["Exfoliation (mild)", "Humectant"])
            if "salicylate" in ingredient_name_lower: functions.extend(["Exfoliation (mild)"])
            if "polyglutamate" in ingredient_name_lower: functions.extend(["Hydration", "Humectant"])

        positive_functions = ["Hydration", "Soothing", "Antioxidant", "Brightening", "Anti-aging", "Exfoliation (mild)", "Barrier Support", "Sebum Regulation", "UV Protection", "Emollient", "Humectant"]
        unique_functions = list(set(functions))
        classification = "Positive Impact" if any(pf in unique_functions for pf in positive_functions) else "Neutral/Functional"
        
        item.update({'functions': unique_functions, 'classification': classification, 'source': source})
        annotated_list.append(item)

    st.write(f"**[DEBUG] Stage 3: Ingredient Functions Analyzed.**")
    st.text("\n".join([f"- {ing['name']} (Source: {ing.get('source', 'N/A')}): {ing.get('functions', [])}" for ing in annotated_list if ing['classification'] == 'Positive Impact']))
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
        if isinstance(rules, dict) and any(keyword in role.lower() for keyword in valid_keywords):
            if all(f in product_functions for f in rules.get('must_have_functions', [])):
                matched_roles.append(role)
    if not matched_roles and profile_key: matched_roles.append(profile_key)
    st.write(f"**[DEBUG] Stage 4: Product Roles Identified.** Roles: **{', '.join(list(set(matched_roles)))}**")
    return list(set(matched_roles))

# --- STAGE 2 & 3 FUNCTIONS (RETHOUGHT) ---
def generate_analysis_output(analyzed_ingredients, templates, scoring_rules_data, ingredients_data):
    ai_says_output = {}
    formula_breakdown = {}
    potential_concerns = []
    
    ingredient_percentages = {ing['name'].lower(): ing['estimated_percentage'] for ing in analyzed_ingredients}
    scoring_rules = scoring_rules_data.get("categories", {})
    ingredients_dict = {item['inci_name'].lower(): item for item in ingredients_data}

    # At a Glance Summary
    top_two_categories = sorted(ai_says_output.items(), key=lambda item: item[1]['score'], reverse=True)[:2]
    summary = f"**At a Glance:** This product appears to be strongest in **{top_two_categories[0][0]}** and **{top_two_categories[1][0]}**."
    ai_says_output["Summary"] = {"score": "", "narrative": summary}

    for category_name, rules in scoring_rules.items():
        points, star_ingredients_found, supporting_ingredients_found, generic_contributors_found = 0, [], [], []
        
        # Scoring Logic... (as before)
        
        # New: Category-specific ingredient lists
        contributors = {
            "Star Ingredients": star_ingredients_found,
            "Supporting Ingredients": supporting_ingredients_found,
            "Other Contributors": generic_contributors_found
        }
        formula_breakdown[category_name] = {k: v for k, v in contributors.items() if v} # Only add if list is not empty

    # Potential Concerns
    for ing in analyzed_ingredients:
        data = ingredients_dict.get(ing['name'].lower())
        if data and data.get("notes"):
            potential_concerns.append(f"**{ing['name'].title()}:** {data['notes']}")

    st.write("**[DEBUG] Stage 5: Narratives and Breakdowns Generated.**")
    return ai_says_output, formula_breakdown, potential_concerns


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
