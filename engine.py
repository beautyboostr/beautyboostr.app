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
            return None, None, None, None

        known_percentages = parse_known_percentages(known_percentages_str)
        st.write(f"**[DEBUG] Known Percentages Parsed:** `{known_percentages}`")

        profile, profile_key = get_product_profile(product_name, ALL_DATA["product_profiles"])
        if not profile:
            st.error("Fatal Error: Could not retrieve a valid product profile. Analysis halted.")
            return None, None, None, None

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
    # More specific keywords should come first
    keyword_map = {
        "oil cleanser": "Oil-based Cleanser", "cleansing oil": "Oil-based Cleanser", "cleansing balm": "Oil-based Cleanser",
        "cream cleanser": "Hydrating Cream Cleanser", "milk cleanser": "Hydrating Cream Cleanser", "foaming cleanser": "Gentle Foaming Cleanser",
        "rich cream": "Barrier Repair Moisturizer", "barrier cream": "Barrier Repair Moisturizer", "night cream": "Anti-aging Moisturizer",
        "lotion": "Lightweight Moisturizer", "gel cream": "Lightweight Moisturizer", "sunscreen": "SPF 30+", "spf": "SPF 30+",
        "serum": "Hydrating Serum", "essence": "Hydrating Essence", "toner": "Hydrating Toner", "clay mask": "Clay Mask", "mask": "Hydrating Mask or Oil",
        "face oil": "Face Oil", "eye cream": "Eye Cream", "lip balm": "Lip Balm", "mist": "Hydrating Mist",
        "cleanser": "Gentle Foaming Cleanser", "cream": "Barrier Repair Moisturizer", "moisturizer": "Lightweight Moisturizer"
    }
    for keyword, profile_key in keyword_map.items():
        if keyword in name_lower:
            profile = profiles_data.get(profile_key)
            if profile:
                st.write(f"**[DEBUG] Stage 1: Product Profile Identified.** Keyword: `{keyword}`. Profile: **{profile_key}**")
                return profile, profile_key
    st.warning("Could not automatically determine product type. Using 'Hydrating Serum' as a default.")
    return profiles_data.get("Hydrating Serum"), "Hydrating Serum"

def estimate_percentages(inci_list, profile, markers, known_percentages):
    percentages = {name: None for name in inci_list}
    # Use fuzzy matching to map known percentages to the inci list
    for name, perc in known_percentages.items():
        match = process.extractOne(name, inci_list)
        if match and match[1] > 90: # High confidence match
            percentages[match[0]] = float(perc)

    # Simple bottom-up estimation (can be improved later with profile data)
    one_percent_line_index = next((idx for idx, ing in enumerate(inci_list) if ing in markers.get("markers", [])), -1)

    if one_percent_line_index != -1:
        current_perc = 1.0
        for i in range(one_percent_line_index, len(inci_list)):
            ing = inci_list[i]
            if percentages[ing] is None:
                percentages[ing] = current_perc
                current_perc = max(0.001, current_perc * 0.9)

    for i in range(len(inci_list) - 1, -1, -1):
        if percentages[inci_list[i]] is not None:
            continue

        next_known_perc = 0.001
        for j in range(i + 1, len(inci_list)):
            if percentages[inci_list[j]] is not None:
                next_known_perc = percentages[inci_list[j]]
                break

        percentages[inci_list[i]] = next_known_perc * 1.1

    known_sum = sum(p for ing, p in percentages.items() if p is not None and ing in known_percentages)
    if known_sum > 100:
        st.error("Error: The sum of known percentages exceeds 100%.")
        raise ValueError("Sum of known percentages exceeds 100%.")

    estimated_ingredients = {ing: p for ing, p in percentages.items() if p is not None and ing not in known_percentages}
    estimated_sum = sum(estimated_ingredients.values())
    remaining_to_distribute = 100.0 - known_sum

    if estimated_sum > 0 and remaining_to_distribute > 0:
        factor = remaining_to_distribute / estimated_sum
        for ing in estimated_ingredients:
            percentages[ing] *= factor

    for ing in inci_list:
        if percentages[ing] is None:
            percentages[ing] = 0.001

    final_total = sum(percentages.values())
    if final_total > 0:
        final_factor = 100.0 / final_total
        for ing in percentages:
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

        if not functions: # Heuristic fallback
            if "extract" in ingredient_name_lower: functions.extend(["Antioxidant", "Soothing"])
            if "ferment" in ingredient_name_lower or "lactobacillus" in ingredient_name_lower: functions.extend(["Soothing", "Hydration", "Barrier Support"])
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
    
    for role, rules in function_rules.items():
        if isinstance(rules, dict):
            if all(f in product_functions for f in rules.get('must_have_functions', [])):
                matched_roles.append(role)
    
    if not matched_roles and profile_key: matched_roles.append(profile_key)
    if not matched_roles: matched_roles.append("General Skincare Product")
    
    st.write(f"**[DEBUG] Stage 4: Product Roles Identified.** Roles: **{', '.join(list(set(matched_roles)))}**")
    return list(set(matched_roles))

def generate_analysis_output(analyzed_ingredients, templates, scoring_rules_data, ingredients_data):
    ai_says_output = {}
    formula_breakdown = {}
    potential_concerns = []
    
    ingredient_percentages = {ing['name'].lower(): ing['estimated_percentage'] for ing in analyzed_ingredients}
    scoring_rules = scoring_rules_data.get("categories", {})

    # --- Main Scoring Loop ---
    for category_name, rules in scoring_rules.items():
        points = 0
        star_ingredients_found = []
        supporting_ingredients_found = []
        generic_contributors_found = []
        
        # 1. Check for Star Ingredients
        for star_rule in rules.get("star_ingredients", []):
            star_name_lower = star_rule["name"].lower()
            match = process.extractOne(star_name_lower, ingredient_percentages.keys())
            if match and match[1] > 95:
                if ingredient_percentages[match[0]] >= star_rule["min_effective_percent"]:
                    points += star_rule["points"]
                    star_ingredients_found.append(star_rule["name"])

        # 2. Check for Supporting Ingredients
        supporting_rules = rules.get("supporting_ingredients", {})
        for ing_name, ing_points in supporting_rules.items():
            match = process.extractOne(ing_name.lower(), ingredient_percentages.keys())
            if match and match[1] > 95:
                points += ing_points
                supporting_ingredients_found.append(ing_name)

        # 3. Add bonus points for generic functions
        product_functions = {func for ing in analyzed_ingredients for func in ing.get('functions', [])}
        for generic_func in rules.get("generic_functions", []):
            if generic_func in product_functions:
                points += rules.get("generic_function_bonus", 0)
                contributors = [ing['name'].title() for ing in analyzed_ingredients if generic_func in ing.get('functions', []) and ing['classification'] == 'Positive Impact']
                for c in contributors:
                     if c not in generic_contributors_found and c not in star_ingredients_found and c not in supporting_ingredients_found:
                         generic_contributors_found.append(c)

        final_score = round(min(10, (points / rules.get("max_points", 100)) * 10), 1)

        # --- Narrative Generation ---
        narrative = ""
        template_set = templates.get(category_name, {})
        
        if final_score >= 7.5:
            if star_ingredients_found:
                narrative = template_set.get("high_score", "").format(star_ingredients=", ".join(star_ingredients_found), supporting_ingredients=", ".join(supporting_ingredients_found) if supporting_ingredients_found else "a blend of beneficial ingredients")
            else:
                key_contributors = supporting_ingredients_found + generic_contributors_found
                narrative = template_set.get("high_score_generic", "").format(generic_contributors=", ".join(list(set(key_contributors))[:3]))
        elif final_score >= 4.0:
            key_ingredients = star_ingredients_found + supporting_ingredients_found
            narrative = template_set.get("medium_score", "").format(star_ingredients=", ".join(key_ingredients) if key_ingredients else "some beneficial ingredients")
        else:
            narrative = template_set.get("low_score", "This formula does not focus on this category.")

        if final_score > 0:
             ai_says_output[category_name] = {"score": final_score, "narrative": narrative}
        
        # --- Formula Breakdown ---
        contributors = {"Star Ingredients": star_ingredients_found, "Supporting Ingredients": supporting_ingredients_found, "Other Key Ingredients": generic_contributors_found}
        if any(v for v in contributors.values()):
            formula_breakdown[category_name] = {k: v for k, v in contributors.items() if v}

    # --- Summary & Concerns ---
    if ai_says_output:
        top_two_categories = sorted(ai_says_output.items(), key=lambda item: item[1]['score'], reverse=True)[:2]
        if len(top_two_categories) >= 2:
            summary_text = f"**At a Glance:** This product appears to be strongest in **{top_two_categories[0][0]}** and **{top_two_categories[1][0]}**."
            
            # CORRECTED: This is the compatible way to add the summary to the front
            summary_dict = {"Summary": {"score": "", "narrative": summary_text}}
            summary_dict.update(ai_says_output)
            ai_says_output = summary_dict

    for ing in analyzed_ingredients:
        match = process.extractOne(ing['name'].lower(), [db_ing['inci_name'].lower() for db_ing in ingredients_data])
        if match and match[1] > 90:
            db_entry = next((item for item in ingredients_data if item['inci_name'].lower() == match[0]), None)
            if db_entry and db_entry.get("restrictions") and db_entry["restrictions"] != "Без обмежень":
                 potential_concerns.append(f"**{ing['name'].title()}:** {db_entry['restrictions']}")
    
    st.write("**[DEBUG] Stage 5: Narratives and Breakdowns Generated.**")
    return ai_says_output, formula_breakdown, potential_concerns

def find_all_routine_matches(product_roles, analyzed_ingredients, all_data):
    routine_matches, product_functions = [], {func for ing in analyzed_ingredients for func in ing.get('functions', [])}
    scoring_config = all_data["scoring_config"]
    for type_id, skin_type in all_data["skin_types"].items():
        # Using a set for faster lookup of product ingredients
        product_ingredient_set = {ing['name'].lower() for ing in analyzed_ingredients}
        if any(bad_ing.lower() in product_ingredient_set for bad_ing in skin_type.get('bad_for_ingredients', [])):
            continue

        for routine_key, routine_details in all_data["routines"].items():
            if routine_key.startswith(type_id):
                for step in routine_details.get("steps", []):
                    if step["product_function"] in product_roles:
                        base_score = scoring_config["function_match_scores"]["perfect_match_base_points"]
                        bonus_points, max_bonus = 0, 0
                        
                        good_for_list = skin_type.get("good_for_functions", [])
                        if isinstance(good_for_list, list):
                            for priority_func in good_for_list:
                                if isinstance(priority_func, dict):
                                    func_name, priority = priority_func.get("function"), priority_func.get("priority")
                                    if func_name and priority:
                                        bonus_value = scoring_config["priority_fulfillment_scores"].get(f"{priority}_priority_bonus", 0)
                                        max_bonus += bonus_value
                                        if func_name in product_functions:
                                            bonus_points += bonus_value

                        total_score = base_score + bonus_points
                        max_possible_score = base_score + max_bonus
                        match_percent = (total_score / max_possible_score) * 100 if max_possible_score > 0 else 0
                        
                        if match_percent >= scoring_config.get("match_thresholds", {}).get("good_match_min_percent", 70):
                            try:
                                skin_type_number = type_id.split(' ')[1]
                                routine_matches.append(f"ID {skin_type_number} Routine {routine_key} Step {step['step_number']} Match {match_percent:.0f}%")
                            except IndexError:
                                continue

    st.write(f"**[DEBUG] Stage 6: Routine Matching Complete.** Found **{len(routine_matches)}** potential placements.")
    return routine_matches
