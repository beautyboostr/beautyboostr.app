import json

# --- STAGE 0: DATA LOADING ---

def load_all_data():
    """
    Loads all necessary JSON data files from the 'data' subfolder.
    This function is called once at the start of the Streamlit app.
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
    try:
        for name, path in files_to_load.items():
            # CORRECTED: Changed encoding to 'utf-8-sig' to handle BOM
            with open(path, 'r', encoding='utf-8-sig') as f:
                data[name] = json.load(f)
        return data
    except FileNotFoundError as e:
        raise FileNotFoundError(f"A required data file was not found: {e}. Ensure it is in the 'data' folder.")
    except json.JSONDecodeError as e:
        raise ValueError(f"Error decoding JSON from a file: {e}. Please validate the file format.")

# --- STAGE 1: PRODUCT DECONSTRUCTION ---

def get_product_profile(product_name, profiles_data):
    """Identifies the product type from its name and returns the corresponding profile."""
    # (Implementation from previous step)
    name_lower = product_name.lower()
    keyword_map = {
        "oil cleanser": "Cleanser (Oil-based)", "cleansing oil": "Cleanser (Oil-based)",
        "cleansing balm": "Cleanser (Oil-based)", "cream cleanser": "Cleanser (Cream)",
        "milk cleanser": "Cleanser (Cream)", "foaming cleanser": "Cleanser (Foaming)",
        "cleanser": "Cleanser (Foaming)", "rich cream": "Moisturizer (Rich)",
        "heavy cream": "Moisturizer (Rich)", "barrier cream": "Moisturizer (Rich)",
        "night cream": "Moisturizer (Rich)", "lotion": "Moisturizer (Lightweight)",
        "lightweight moisturizer": "Moisturizer (Lightweight)", "gel cream": "Moisturizer (Lightweight)",
        "cream": "Moisturizer (Rich)", "moisturizer": "Moisturizer (Lightweight)",
        "sunscreen": "Sunscreen", "spf": "Sunscreen", "serum": "Serum", "essence": "Essence",
        "toner": "Toner", "clay mask": "Mask (Clay)", "mask": "Mask (Wash-off Gel/Cream)",
        "face oil": "Face Oil", "eye cream": "Eye Cream", "lip balm": "Lip Balm", "mist": "Mist"
    }
    for keyword, profile_key in keyword_map.items():
        if keyword in name_lower:
            return profiles_data.get(profile_key)
    return profiles_data.get("Serum") # Default profile

def estimate_percentages(inci_list, profile, markers, ingredients_data):
    """
    [CORRECTED ALGORITHM]
    Estimates ingredient percentages using a rule-based heuristic model.
    """
    num_ingredients = len(inci_list)
    if num_ingredients == 0:
        return []

    # Initialize a list of objects to hold our data
    estimated_list = [{"name": name, "percentage": 0.0, "is_anchored": False} for name in inci_list]
    ingredient_lookup = {item['inci_name'].lower(): item for item in ingredients_data}

    # 1. Find the 1% Line
    one_percent_line_index = num_ingredients
    for i, item in enumerate(estimated_list):
        if item["name"].lower() in [m.lower() for m in markers["markers"]]:
            one_percent_line_index = i
            break

    # 2. Anchor Key Ingredients
    # Anchor Base Solvent (usually Aqua)
    base_solvent_percent = sum(profile["base_solvent_range"]) / 2
    estimated_list[0]["percentage"] = base_solvent_percent
    estimated_list[0]["is_anchored"] = True

    # Anchor ingredients at or below the 1% line
    sub_one_percent_total = 0
    for i in range(one_percent_line_index, num_ingredients):
        # A simple decreasing assignment for an MVP of this advanced logic
        percent = max(0.9 - (i - one_percent_line_index) * 0.1, 0.05)
        estimated_list[i]["percentage"] = percent
        estimated_list[i]["is_anchored"] = True
        sub_one_percent_total += percent

    # 3. Distribute Remainder
    # Calculate what's left to distribute above the 1% line
    total_anchored = base_solvent_percent + sub_one_percent_total
    remaining_percent_to_distribute = 100 - total_anchored
    
    # Identify items that need percentages assigned
    items_to_estimate = estimated_list[1:one_percent_line_index]
    num_to_estimate = len(items_to_estimate)

    if num_to_estimate > 0:
        # Use a simple linear decay for distribution
        # Example: if 3 items, they might get 50%, 30%, 20% of the remainder
        weights = list(range(num_to_estimate, 0, -1))
        total_weight = sum(weights)
        
        for i, item in enumerate(items_to_estimate):
            share = (weights[i] / total_weight) * remaining_percent_to_distribute if total_weight > 0 else 0
            item["percentage"] = share

    # 4. Normalize and Finalize
    # Ensure descending order is respected and total is 100%
    current_total = sum(item["percentage"] for item in estimated_list)
    if current_total != 100:
        # For this version, we adjust the base solvent to force 100%
        # A more advanced model would adjust all non-anchored values
        diff = 100 - current_total
        estimated_list[0]["percentage"] += diff

    # Final rounding
    for item in estimated_list:
        item["estimated_percentage"] = round(item["percentage"], 3)
        del item["percentage"] # clean up temporary keys
        del item["is_anchored"]
        
    return estimated_list


def analyze_ingredient_functions(ingredients_with_percentages, ingredients_data):
    """Looks up each ingredient to find its functions and classification."""
    annotated_ingredients = []
    all_functions = set()
    positive_impact_list = []
    neutral_functional_list = []

    ingredient_lookup = {item['inci_name'].lower(): item for item in ingredients_data}

    for item in ingredients_with_percentages:
        ingredient_name = item['name'].lower()
        if ingredient_name in ingredient_lookup:
            ing_data = ingredient_lookup[ingredient_name]
            functions = []
            is_positive = False
            for behavior in ing_data.get("behaviors", []):
                current_functions = behavior.get("functions", [])
                functions.extend(current_functions)
                all_functions.update(current_functions)
                
                positive_keywords = ["Hydration", "Soothing", "Antioxidant", "Brightening", "Anti-aging", "Barrier Support", "Exfoliation", "Emollient", "Humectant"]
                if any(keyword in func for keyword in positive_keywords for func in current_functions):
                    is_positive = True
            
            item['functions'] = functions
            annotated_ingredients.append(item)
            
            if is_positive:
                positive_impact_list.append(item['name'])
            else:
                neutral_functional_list.append(item['name'])
    
    formula_breakdown = {
        "positive_impact": positive_impact_list,
        "neutral_functional": neutral_functional_list
    }

    return annotated_ingredients, list(all_functions), formula_breakdown


def identify_product_role(product_functions, function_rules):
    """Determines the product's primary role based on its functions."""
    best_match_score = -1
    best_match_role = "General Skincare Product" # A safe default

    for role, rules in function_rules.items():
        score = 0
        # Check for incompatible functions first
        if any(func in product_functions for func in rules.get("incompatible_functions", [])):
            continue

        must_haves = rules.get("must_have_functions", [])
        if all(func in product_functions for func in must_haves):
            score += len(must_haves) * 2  # Strong weight for must-haves
            
            good_to_haves = rules.get("good_to_have_functions", [])
            for func in good_to_haves:
                if func in product_functions:
                    score += 1
            
            if score > best_match_score:
                best_match_score = score
                best_match_role = role
    return best_match_role

# --- STAGE 2: NARRATIVE GENERATION ---

def generate_analysis_output(annotated_ingredients, templates):
    """Generates the 'AI Assistant Says' narratives. MVP version."""
    # This is a simplified scoring logic for the MVP
    narratives = []
    category_map = {
        "Hydration & Skin Barrier Support": ["Hydration", "Humectant", "Barrier Support", "Emollient", "Occlusive"],
        "Brightening & Even Skin Tone": ["Brightening", "Anti-pigmentation"],
        "Soothing & Redness Reduction": ["Soothing", "Anti-inflammatory"],
        "Pore Appearance & Texture Improvement": ["Exfoliation (mild)", "Sebum Regulation", "Comedolytic"],
        "Anti-aging & Wrinkle Reduction": ["Anti-aging", "Collagen Synthesis"]
    }

    for category, funcs in category_map.items():
        score = 0
        star_ingredients = []
        for ing in annotated_ingredients:
            if any(f in funcs for f in ing['functions']):
                score += ing['estimated_percentage']
                if ing['name'] not in [s[0] for s in star_ingredients]:
                     star_ingredients.append((ing['name'], ing['estimated_percentage']))
        
        # Normalize score to 1-10
        score_10 = min(10, int(score / 5) + 5) if score > 1 else int(score * 5)
        
        if score_10 >= 5:
            star_ingredients.sort(key=lambda x: x[1], reverse=True)
            stars_str = ", ".join([s[0] for s in star_ingredients[:2]])
            template = templates[category]['medium_score'] if score_10 < 8 else templates[category]['high_score']
            narratives.append(f"{category}: Score {score_10}/10 ✅\n" + template.format(star_ingredients=stars_str))

    return "\n\n".join(narratives) if narratives else "This product has a general-purpose formula suitable for maintaining skin health."


# --- STAGE 3: MATCHING ---

def find_all_routine_matches(product_role, product_functions, all_data):
    """Finds all routine placements and calculates a match score for each."""
    matches = []
    
    for type_id, skin_type in all_data["skin_types"].items():
        # Disqualification Check
        # For simplicity, this MVP assumes no bad ingredients are found.
        # A full implementation would check the product's INCI list here.
        is_suitable = True 
        
        if is_suitable:
            for routine_key, routine in all_data["routines"].items():
                if routine_key.startswith(type_id):
                    for step in routine["steps"]:
                        # Check for a function match
                        is_perfect_match = (step["product_function"] == product_role)
                        partial_match_list = all_data["scoring_config"]["partial_match_map"].get(step["product_function"], [])
                        is_partial_match = (product_role in partial_match_list)

                        if is_perfect_match or is_partial_match:
                            # Calculate Score
                            base_score = all_data["scoring_config"]["function_match_scores"]["perfect_match_base_points"] if is_perfect_match else all_data["scoring_config"]["function_match_scores"]["partial_match_base_points"]
                            
                            bonus_points = 0
                            max_bonus = 0
                            
                            for func_needed in skin_type["good_for_functions"]:
                                priority = func_needed['priority']
                                bonus_value = all_data["scoring_config"]["priority_fulfillment_scores"][f"{priority}_priority_bonus"]
                                max_bonus += bonus_value
                                if func_needed['function'] in product_functions:
                                    bonus_points += bonus_value
                            
                            total_score = base_score + bonus_points
                            max_possible_score = all_data["scoring_config"]["function_match_scores"]["perfect_match_base_points"] + max_bonus
                            match_percent = int((total_score / max_possible_score) * 100) if max_possible_score > 0 else 0
                            
                            # Add to list if it's a good match
                            if match_percent >= all_data["scoring_config"]["match_thresholds"]["good_match_min_percent"]:
                                match_string = f"ID {type_id.split(' ')[1]} Routine {routine_key} Step {step['step_number']} Match {match_percent}%"
                                matches.append(match_string)
    return matches


# --- MAIN ORCHESTRATOR ---

def run_full_analysis(product_name, inci_list, all_data):
    """
    The main function that runs the entire analysis pipeline.
    """
    # Stage 1: Deconstruction
    profile = get_product_profile(product_name, all_data["product_profiles"])
    # Note the added argument to the function call below
    ingredients_with_percentages = estimate_percentages(inci_list, profile, all_data["one_percent_markers"], all_data["ingredients"])
    
    # Stage 2: Functional Analysis
    annotated_ingredients, product_functions, formula_breakdown = analyze_ingredient_functions(ingredients_with_percentages, all_data["ingredients"])
    product_role = identify_product_role(product_functions, all_data["product_functions"])
    
    # Stage 3: Narrative and Match Generation
    ai_says_output = generate_analysis_output(annotated_ingredients, all_data["narrative_templates"])
    routine_matches = find_all_routine_matches(product_role, product_functions, all_data)
    
    return ai_says_output, formula_breakdown, routine_matches

