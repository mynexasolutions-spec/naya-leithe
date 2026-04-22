# Naye Leithe - Flask Version

This is a Flask conversion of the Naye Leithe website.

## How to run locally

1. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

2. Run the application:
   ```bash
   python app.py
   ```

3. Open your browser and navigate to `http://127.0.0.1:5000`

## Structure

- `app.py`: Main Flask application with routes and product data.
- `templates/`: Jinja2 templates for the website pages.
- `static/`: Static assets including CSS, JS, and Images.
  - `static/css/style.css`: Combined CSS from all original React components.
