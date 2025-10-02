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

# --- HELPER FUNCTION FOR NEW LOGIC ---
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
                # Silently ignore malformed pairs
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

        # STAGE 1: Deconstruction
        known_percentages = parse_known_percentages(known_percentages_str)
        st.write(f"**[DEBUG] Known Percentages Parsed:** `{known_percentages}`")
        
        profile = get_product_profile(product_name, ALL_DATA["product_profiles"])
        if not profile:
            st.error("Fatal Error: Could not retrieve a valid product profile. Analysis halted.")
            return None, None, None
            
        ingredients_with_percentages = estimate_percentages(inci_list, profile, ALL_DATA["one_percent_markers"], known_percentages)
        analyzed_ingredients = analyze_ingredient_functions(ingredients_with_percentages, ALL_DATA["ingredients"])
        product_roles = identify_product_roles(analyzed_ingredients, ALL_DATA["product_functions"])
        
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
                return profile
    st.warning("Could not automatically determine product type. Using 'Serum' as a default.")
    return profiles_data.get("Serum")

def estimate_percentages(inci_list, profile, markers, known_percentages):
    percentages = {name: 0.0 for name in inci_list}
    
    # 1. Anchor all known percentages first
    for name, perc in known_percentages.items():
        if name in percentages:
            percentages[name] = perc

    # 2. Distribute remaining percentage
    allocated_sum = sum(percentages.values())
    if allocated_sum > 100:
        st.error("Error: The sum of known percentages exceeds 100%. Please check your input.")
        raise ValueError("Sum of known percentages exceeds 100%.")
    
    remaining_to_distribute = 100.0 - allocated_sum
    unallocated_ingredients = [ing for ing in inci_list if percentages[ing] == 0.0]

    if unallocated_ingredients:
        # Simplified distribution for the remaining ingredients
        # Find 1% line within the unallocated ingredients
        one_percent_line_in_unallocated = next((i for i, ing in enumerate(unallocated_ingredients) if ing in markers.get("markers", [])), -1)
        if one_percent_line_in_unallocated == -1:
            one_percent_line_in_unallocated = int(len(unallocated_ingredients) * 0.7) # Fallback

        main_ingredients = unallocated_ingredients[:one_percent_line_in_unallocated]
        sub_one_ingredients = unallocated_ingredients[one_percent_line_in_unallocated:]

        # Allocate to main and sub-one groups
        main_total = remaining_to_distribute * 0.95
        sub_one_total = remaining_to_distribute * 0.05

        if main_ingredients:
            weights = list(reversed(range(1, len(main_ingredients) + 1)))
            total_weight = sum(weights)
            for i, ingredient in enumerate(main_ingredients):
                percentages[ingredient] = (weights[i] / total_weight) * main_total

        if sub_one_ingredients:
            share = sub_one_total / len(sub_one_ingredients)
            for ingredient in sub_one_ingredients:
                percentages[ingredient] = share
    
    # Final normalization
    current_total = sum(percentages.values())
    if current_total > 0:
        factor = 100.0 / current_total
        for ing in percentages: percentages[ing] *= factor
    
    st.write(f"**[DEBUG] Stage 2: Full Estimated Formula.**")
    sorted_percentages = sorted(percentages.items(), key=lambda item: item[1], reverse=True)
    st.text("\n".join([f"- {name}: {perc:.4f}%" for name, perc in sorted_percentages]))
    return [{"name": name, "estimated_percentage": perc} for name, perc in percentages.items()]

def analyze_ingredient_functions(ingredients_with_percentages, ingredients_data):
    ingredients_dict = {item['inci_name'].lower(): item for item in ingredients_data}
    annotated_list = []
    for item in ingredients_with_percentages:
        ingredient_name_lower = item['name'].lower()
        data = ingredients_dict.get(ingredient_name_lower)
        functions = []
        if data and isinstance(data.get('behaviors'), list):
            for behavior in data['behaviors']:
                if isinstance(behavior, dict) and behavior.get('functions'): functions.extend(behavior.get('functions', []))
        else:
            if "extract" in ingredient_name_lower: functions.extend(["Antioxidant", "Soothing"])
            if "ferment" in ingredient_name_lower: functions.extend(["Soothing", "Hydration"])
            if "gluconolactone" in ingredient_name_lower: functions.extend(["Exfoliation (mild)", "Humectant"])
            if "salicylate" in ingredient_name_lower: functions.extend(["Exfoliation (mild)"])
            if "polyglutamate" in ingredient_name_lower: functions.extend(["Hydration", "Humectant"])
        positive_functions = ["Hydration", "Soothing", "Antioxidant", "Brightening", "Anti-aging", "Exfoliation (mild)", "Barrier Support", "Sebum Regulation", "UV Protection", "Emollient", "Humectant"]
        classification = "Positive Impact" if any(pf in functions for pf in positive_functions) else "Neutral/Functional"
        item['functions'] = list(set(functions))
        item['classification'] = classification
        annotated_list.append(item)
    st.write(f"**[DEBUG] Stage 3: Ingredient Functions Analyzed.** Total functions found: {sum(len(ing.get('functions', [])) for ing in annotated_list)}")
    return annotated_list

def identify_product_roles(analyzed_ingredients, function_rules):
    product_functions = {func for ing in analyzed_ingredients for func in ing.get('functions', [])}
    matched_roles = []
    for role, rules in function_rules.items():
        if isinstance(rules, dict) and all(f in product_functions for f in rules.get('must_have_functions', [])):
            matched_roles.append(role)
    if not matched_roles: matched_roles.append("Unknown")
    st.write(f"**[DEBUG] Stage 4: Product Roles Identified.** Roles: **{', '.join(matched_roles)}**")
    return matched_roles

# --- STAGE 2 & 3 FUNCTIONS ---
def generate_analysis_output(analyzed_ingredients, templates, scoring_rules):
    ai_says_output = {}
    ingredient_percentages = {ing['name'].lower(): ing['estimated_percentage'] for ing in analyzed_ingredients}
    for category_name, rules in scoring_rules.get("categories", {}).items():
        points, star_ingredients_found = 0, []
        for star in rules.get("star_ingredients", []):
            star_name_lower = star["name"].lower()
            if star_name_lower in ingredient_percentages and ingredient_percentages[star_name_lower] >= star["min_effective_percent"]:
                points += star["points"]
                star_ingredients_found.append(star["name"].title())
        for support_name, support_points in rules.get("supporting_ingredients", {}).items():
            if support_name.lower() in ingredient_percentages:
                points += support_points
                if support_name.title() not in star_ingredients_found: star_ingredients_found.append(support_name.title())
        max_points = rules.get("max_points", 1)
        final_score = min(10, round((points / max_points) * 9) + 1 if max_points > 0 else 1)
        if final_score >= 8: template_key = "high_score"
        elif final_score >= 4: template_key = "medium_score"
        else: template_key = "low_score"
        narrative = templates.get(category_name, {}).get(template_key, "No narrative available.").replace("{star_ingredients}", ", ".join(star_ingredients_found[:2]))
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

