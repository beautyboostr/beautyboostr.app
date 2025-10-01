BeautyBoostr AI Product Analyzer
This project is a Streamlit web application that analyzes cosmetic ingredient lists to provide a detailed breakdown of a product's functions, its suitability for different skin types, and its ideal placement within a skincare routine.

Project Structure
app.py: The main Streamlit application file that runs the user interface (frontend).

engine.py: The core analysis engine containing all backend logic for product analysis and matching.

requirements.txt: A list of all Python libraries required to run the project.

data/: A directory containing all the JSON data files that power the analysis engine.

How to Run the Application
Clone the Repository:

git clone <your-repository-url>
cd beautyboostr-analyzer

Install Dependencies:
Make sure you have Python installed. Then, run the following command in your terminal:

pip install -r requirements.txt

Run the Streamlit App:
Once the dependencies are installed, run the following command:

streamlit run app.py

The application should open automatically in your web browser.

Data Files
The analysis is powered by a set of JSON files located in the data/ directory:

ingredients.json: The master database of cosmetic ingredients and their properties.

skin_types.json: Defines the 36 skin types, their problems, and ingredient preferences.

routines.json: Contains the step-by-step skincare routines for each skin type.

product_profiles.json: Defines the typical composition of different product categories (e.g., serum, cream).

product_functions.json: Maps ingredient functions to a standardized product role.

one_percent_markers.json: A list of ingredients used to identify the "1% line" in an INCI list.

narrative_templates.json: Templates for generating the "AI Assistant Says" text.

scoring_config.json: Configuration for the final percentage match score calculation.

