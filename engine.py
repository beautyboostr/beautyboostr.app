import streamlit as st
import json
import traceback
import re
from thefuzz import process

# --- DATA LOADING ---
@st.cache_data
def load_all_data():
    """
    Loads all necessary JSON data files from the 'data' folder.
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
        "category_scoring_rules": "data/category_scoring_rules.json",
        "usage_ranges": "data/ingredient_usage_ranges.json"
    }
    
    for name, path in files_to_load.items():
        try:
            with open(path, 'r', encoding='utf-8-sig') as f:
                data[name] = json.load(f)
        except FileNotFoundError:
            if name == "usage_ranges":
                st.warning(f"Optional data file not found at '{path}'. Estimation will be less accurate.")
                data[name] = {}
            else:
                raise FileNotFoundError(f"Fatal Error: A required data file was not found at '{path}'.")
        except json.JSONDecodeError as e:
            raise ValueError(f"Fatal Error: Error decoding JSON from file '{path}': {e}.")
            
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
        
        ingredients_with_percentages = estimate_percentages(inci_list, profile, ALL_DATA, known_percentages, profile_key)
        
        analyzed_ingredients = analyze_ingredient_functions(ingredients_with_percentages, ALL_DATA)
        product_roles = identify_product_roles(analyzed_ingredients, ALL_DATA["product_functions"], profile_key)
        
        ai_says_output, formula_breakdown, potential_concerns = generate_analysis_output(analyzed_ingredients, ALL_DATA["narrative_templates"], ALL_DATA["category_scoring_rules"], ALL_DATA["ingredients"])
        
        routine_matches = find_all_routine_matches(product_roles, analyzed_ingredients, ALL_DATA)

        return ai_says_output, formula_breakdown, routine_matches, potential_concerns

    except ValueError as e:
        st.error(f"Input Error: {e}")
        return None, None, None, None
    except Exception:
        st.error("An unexpected error occurred during the analysis process.")
        st.code(traceback.format_exc())
        return None, None, None, None

def check_for_prohibited(inci_list, prohibited_data):
    prohibited_set = set(ing.lower() for ing in prohibited_data.get("ingredients", []))
    for ingredient in inci_list:
        if ingredient in prohibited_set: return ingredient
    return None

def get_product_profile(product_name, profiles_data):
    name_lower = product_name.lower()
    keyword_map = {
        "oil cleanser": "Oil-based Cleanser", "cleansing oil": "Oil-based Cleanser", "cleansing balm": "Oil-based Cleanser",
        "cream cleanser": "Hydrating Cream Cleanser", "milk cleanser": "Hydrating Cream Cleanser", "foaming cleanser": "Gentle Foaming Cleanser", "purifying cleanser": "Gentle Foaming Cleanser",
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

# --- FINAL ROBUST VERSION: Iterative Search with Best-Result Tracking ---
def estimate_percentages(inci_list, profile, all_data, known_percentages, profile_key):
    """
    Estimates ingredient percentages using a robust iterative search model. This version
    tracks the result that is closest to a 100% sum across all iterations to ensure
    the best possible solution is returned, preventing >100% sums.
    """
    st.write("✅ **Running the definitive ITERATIVE SEARCH logic (Best Result Tracking).**")
    
    # --- Step 1: Pre-computation of constant values (anchors and below-1% zone) ---
    known_ingredients_map = {}
    last_known_perc = 101.0
    for i, name in enumerate(inci_list):
        for known_name, known_perc in known_percentages.items():
            if process.extractOne(known_name, [name])[1] > 95:
                if known_perc > last_known_perc:
                    raise ValueError("Your known percentages violate the descending order rule.")
                known_ingredients_map[name] = {'perc': known_perc, 'index': i}
                last_known_perc = known_perc
                break

    one_percent_markers = all_data.get("one_percent_markers", {}).get("markers", [])
    usage_ranges = all_data.get("usage_ranges", {})
    one_percent_line_index = next((i for i, ing in enumerate(inci_list) if ing in one_percent_markers and ing not in known_ingredients_map), len(inci_list))

    below_1_percs = {}
    for i in range(one_percent_line_index, len(inci_list)):
        ing = inci_list[i]
        if ing not in known_ingredients_map:
            ing_ranges = usage_ranges.get(ing.lower(), {})
            perc_range = ing_ranges.get(profile_key, ing_ranges.get("default", [0.05, 0.5]))
            below_1_percs[ing] = min(sum(perc_range) / 2, 1.0)
    
    # --- Step 2: The Iterative Search with Best-Result Tracking ---
    low_bound, high_bound = profile.get("base_solvent_range", [40, 98])
    
    # Variables to store the best result found during the search
    best_result = {}
    smallest_error = float('inf')

    # Increased iterations for better convergence on complex lists
    for _ in range(15):
        guess_start_perc = (low_bound + high_bound) / 2
        
        temp_percentages = {name: 0.0 for name in inci_list}
        temp_percentages.update({k: v['perc'] for k, v in known_ingredients_map.items()})
        temp_percentages.update(below_1_percs)
        
        # Run the trusted interpolation logic with the current guess
        anchors_above_1 = [a for a in known_ingredients_map.values() if a['index'] < one_percent_line_index]
        start_anchor = {'index': -1, 'perc': guess_start_perc}
        end_anchor = {'index': one_percent_line_index, 'perc': 1.0}
        all_anchors = sorted(list({v['index']: v for v in [start_anchor] + anchors_above_1 + [end_anchor]}.values()), key=lambda x: x['index'])

        for i in range(len(all_anchors) - 1):
            s_anchor, e_anchor = all_anchors[i], all_anchors[i+1]
            num_ingredients_in_segment = e_anchor['index'] - s_anchor['index'] - 1
            if num_ingredients_in_segment > 0:
                step_size = (s_anchor['perc'] - e_anchor['perc']) / (num_ingredients_in_segment + 1)
                for j in range(num_ingredients_in_segment):
                    ing_index = s_anchor['index'] + 1 + j
                    ing_name = inci_list[ing_index]
                    if ing_name not in known_ingredients_map:
                        temp_percentages[ing_name] = s_anchor['perc'] - (step_size * (j + 1))
        
        current_total = sum(temp_percentages.values())
        error = abs(100.0 - current_total)
        
        # ** THE FIX: Check if this iteration produced a better result (closer to 100) **
        if error < smallest_error:
            smallest_error = error
            best_result = temp_percentages
        
        # Refine the search space for the next iteration
        if current_total > 100.0:
            high_bound = guess_start_perc
        else:
            low_bound = guess_start_perc
            
    final_percentages = best_result

    # Final sanity check for negative values caused by edge cases
    for name in final_percentages:
        if final_percentages.get(name, 0) < 0:
            final_percentages[name] = 0.0

    st.write(f"**[DEBUG] Stage 2: Full Estimated Formula.**")
    st.text("\n".join([f"- {name}: {perc:.4f}%" for name, perc in final_percentages.items()]))
    
    return [{"name": name, "estimated_percentage": perc} for name, perc in final_percentages.items()]
    
def analyze_ingredient_functions(ingredients_with_percentages, all_data):
    db_names = all_data["ingredient_names_for_matching"]
    ingredients_dict = {item['inci_name'].lower(): item for item in all_data["ingredients"]}
    annotated_list = []
    
    for item in ingredients_with_percentages:
        ingredient_name_lower = item['name'].lower()
        if ingredient_name_lower == 'aqua': ingredient_name_lower = 'water'
        functions, source = [], "Heuristic"
        best_match = None

        if ingredient_name_lower in db_names: best_match = (ingredient_name_lower, 100)
        else: best_match = process.extractOne(ingredient_name_lower, db_names, score_cutoff=85)

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
            if "ferment" in ingredient_name_lower: functions.extend(["Soothing", "Hydration"])
            if "water" in ingredient_name_lower and "aqua" not in ingredient_name_lower: functions.extend(["Soothing", "Hydration"])

        positive_functions = ["Hydration", "Soothing", "Antioxidant", "Brightening", "Anti-aging", "Exfoliation (mild)", "Barrier Support", "Sebum Regulation", "UV Protection", "Emollient", "Humectant"]
        unique_functions = list(set(functions))
        classification = "Positive Impact" if any(pf in unique_functions for pf in positive_functions) else "Neutral/Functional"
        item.update({'functions': unique_functions, 'classification': classification, 'source': source})
        annotated_list.append(item)

    st.write(f"**[DEBUG] Stage 3: Ingredient Functions Analyzed.**")
    st.text("\n".join([f"- {ing['name']} ({ing['classification']}) (Source: {ing.get('source', 'N/A')}): {ing.get('functions', [])}" for ing in annotated_list]))
    return annotated_list

def identify_product_roles(analyzed_ingredients, function_rules, profile_key):
    product_functions = {func for ing in analyzed_ingredients for func in ing.get('functions', [])}
    matched_roles = []
    valid_roles_map = {
        "Toner": ["toner"], "Essence": ["essence"], "Serum": ["serum"], "Moisturizer (Lightweight)": ["moisturizer"], "Moisturizer (Rich)": ["moisturizer"],
        "Cleanser (Foaming)": ["cleanser"], "Cleanser (Cream)": ["cleanser"], "Cleanser (Oil-based)": ["cleanser"], "Mask (Wash-off Gel/Cream)": ["mask", "oil"],
        "Mask (Clay)": ["mask"], "Face Oil": ["oil", "mask"], "Eye Cream": ["eye cream"], "Sunscreen": ["spf", "sunscreen"], "Lip Balm": ["lip balm"], "Mist": ["mist"]
    }
    valid_keywords = valid_roles_map.get(profile_key, [])
    for role, rules in function_rules.items():
        if isinstance(rules, dict) and any(keyword in role.lower() for keyword in valid_keywords):
            if all(f in product_functions for f in rules.get('must_have_functions', [])): matched_roles.append(role)
    if not matched_roles and profile_key: matched_roles.append(profile_key)
    st.write(f"**[DEBUG] Stage 4: Product Roles Identified.** Roles: **{', '.join(list(set(matched_roles)))}**")
    return list(set(matched_roles))

def generate_analysis_output(analyzed_ingredients, templates, scoring_rules_data, ingredients_data):
    ai_says_output, formula_breakdown, potential_concerns = {}, {}, []
    ingredient_percentages = {ing['name'].lower(): ing['estimated_percentage'] for ing in analyzed_ingredients}
    scoring_rules = scoring_rules_data.get("categories", {})
    for category_name, rules in scoring_rules.items():
        points = 0
        star_ingredients_found, supporting_ingredients_found, generic_contributors_found = [], [], []
        for star_rule in rules.get("star_ingredients", []):
            star_name_lower = star_rule["name"].lower()
            match = process.extractOne(star_name_lower, ingredient_percentages.keys())
            if match and match[1] > 95 and ingredient_percentages.get(match[0], 0) >= star_rule["min_effective_percent"]:
                points += star_rule["points"]
                star_ingredients_found.append(star_rule["name"])
        supporting_rules = rules.get("supporting_ingredients", {})
        for ing_name, ing_points in supporting_rules.items():
            match = process.extractOne(ing_name.lower(), ingredient_percentages.keys())
            if match and match[1] > 95:
                points += ing_points
                supporting_ingredients_found.append(ing_name)
        generic_function_set = set(rules.get("generic_functions", []))
        bonus_points_per_match = 1.5
        for ingredient in analyzed_ingredients:
            ing_name_lower = ingredient['name'].lower()
            is_already_scored = any(process.extractOne(star['name'].lower(), [ing_name_lower])[1] > 95 for star in rules.get("star_ingredients", [])) or \
                                any(process.extractOne(sup.lower(), [ing_name_lower])[1] > 95 for sup in supporting_rules.keys())
            if not is_already_scored and generic_function_set.intersection(set(ingredient.get('functions', []))):
                points += bonus_points_per_match
                if ingredient['name'].title() not in generic_contributors_found:
                    generic_contributors_found.append(ingredient['name'].title())
        final_score = round(min(10, (points / rules.get("max_points", 100)) * 10), 1)
        if final_score > 0.5:
            template_set = templates.get(category_name, {})
            narrative = ""
            if final_score >= 7.5:
                if star_ingredients_found: narrative = template_set.get("high_score", "").format(star_ingredients=", ".join(star_ingredients_found), supporting_ingredients=", ".join(supporting_ingredients_found) if supporting_ingredients_found else "a blend of beneficial ingredients")
                else: narrative = template_set.get("high_score_generic", "").format(generic_contributors=", ".join(list(set(supporting_ingredients_found + generic_contributors_found))[:3]))
            elif final_score >= 4.0: narrative = template_set.get("medium_score", "").format(star_ingredients=", ".join(list(set(star_ingredients_found + supporting_ingredients_found + generic_contributors_found))[:3]) if (star_ingredients_found or supporting_ingredients_found or generic_contributors_found) else "some beneficial ingredients")
            else: narrative = template_set.get("low_score", "This formula does not focus on this category.")
            ai_says_output[category_name] = {"score": final_score, "narrative": narrative}
        contributors = {"Star Ingredients": star_ingredients_found, "Supporting Ingredients": supporting_ingredients_found, "Other Key Ingredients": generic_contributors_found}
        if any(v for v in contributors.values()): formula_breakdown[category_name] = {k: v for k, v in contributors.items() if v}
    if ai_says_output:
        top_two_categories = sorted(ai_says_output.items(), key=lambda item: item[1]['score'], reverse=True)[:2]
        if len(top_two_categories) >= 2:
            summary_text = f"**At a Glance:** This product appears to be strongest in **{top_two_categories[0][0]}** and **{top_two_categories[1][0]}**."
            summary_dict = {"Summary": {"score": "", "narrative": summary_text}}; summary_dict.update(ai_says_output); ai_says_output = summary_dict
    for ing in analyzed_ingredients:
        match = process.extractOne(ing['name'].lower(), [db_ing['inci_name'].lower() for db_ing in ALL_DATA["ingredients"]])
        if match and match[1] > 90:
            db_entry = next((item for item in ALL_DATA["ingredients"] if item['inci_name'].lower() == match[0]), None)
            if db_entry and db_entry.get("restrictions") and db_entry["restrictions"] != "Без обмежень":
                 potential_concerns.append(f"**{ing['name'].title()}:** {db_entry['restrictions']}")
    st.write("**[DEBUG] Stage 5: Narratives and Breakdowns Generated.**")
    return ai_says_output, formula_breakdown, potential_concerns

def find_all_routine_matches(product_roles, analyzed_ingredients, all_data):
    routine_matches, product_functions = [], {func for ing in analyzed_ingredients for func in ing.get('functions', [])}
    scoring_config = all_data["scoring_config"]
    for type_id, skin_type in all_data["skin_types"].items():
        product_ingredient_set = {ing['name'].lower() for ing in analyzed_ingredients}
        if any(bad_ing.lower() in product_ingredient_set for bad_ing in skin_type.get('bad_for_ingredients', [])): continue
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
                                        if func_name in product_functions: bonus_points += bonus_value
                        total_score = base_score + bonus_points
                        max_possible_score = base_score + max_bonus
                        match_percent = (total_score / max_possible_score) * 100 if max_possible_score > 0 else 0
                        if match_percent >= scoring_config.get("match_thresholds", {}).get("good_match_min_percent", 70):
                            try:
                                skin_type_number = type_id.split(' ')[1]
                                routine_matches.append(f"ID {skin_type_number} Routine {routine_key} Step {step['step_number']} Match {match_percent:.0f}%")
                            except IndexError: continue
    st.write(f"**[DEBUG] Stage 6: Routine Matching Complete.** Found **{len(routine_matches)}** placements.")
    return routine_matches

