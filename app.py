from flask import Flask, render_template, request, jsonify, send_file
from flask_cors import CORS
import openai, requests, json
from datetime import datetime
from io import BytesIO
import pdfkit
import os
from flask import Flask, render_template, request, jsonify, send_file, make_response

app = Flask(__name__)
CORS(app)

# Keys (for safety, load from env in real use)
openai.api_key = "YOUR_OPENAI_KEY"
APIFY_TOKEN    = "YOUR_APIFY_TOKEN"

latest_brief = {}

# ---------- Helpers ----------
def scrape_apify_googlemaps(query, location):
    run_url = (
        "https://api.apify.com/v2/actor-tasks/"
        "sleftdogceo~google-maps-scraper-task/run-sync-get-dataset-items"
        f"?token={APIFY_TOKEN}"
    )
    payload = {
        "searchStringsArray": [f"{query} in {location}"],
        "maxCrawledPlaces": 5
    }
    try:
        resp = requests.post(run_url, json=payload)
        data = resp.json()
        return [
            {
                "name":     p.get("title"),
                "address":  p.get("address"),
                "website":  p.get("website"),
                "rating":   p.get("totalScore")
            }
            for p in data if isinstance(p, dict) and p.get("title")
        ]
    except Exception as e:
        print("[SCRAPE ERROR]", e)
        return [{"name": f"Scrape failed: {e}"}]

# ---------- Routes ----------
@app.route("/")
def form():
    resp = make_response(render_template("index.html"))
    print("DEBUG Content‑Type sent by Flask:", resp.content_type)
    return resp

@app.route("/generate", methods=["POST"])
def generate():
    global latest_brief
    business_name = request.form["business_name"]
    website       = request.form["website"]
    category      = request.form["category"]
    location      = request.form["location"]
    user_input    = request.form.get("user_input", "")

    scrapped_strength = "Google reviews show an average rating of 4.7 stars."

    gpt_prompt = f"""
    Write a short, clear business summary at a 6th‑grade level.

    Business: {business_name}
    Type: {category}
    Location: {location}
    Goal: {user_input}

    ## What's Working
    {scrapped_strength}

    ## What To Do Next
    Give 1 short recommendation that could help make more money.

    ## People to Connect With
    List 2‑3 helpful business types or categories to partner with.
    """

    try:
        resp = openai.ChatCompletion.create(
            model="gpt-4",
            messages=[
                {"role": "system", "content": "You're a blunt business coach. Clear, simple, no fluff."},
                {"role": "user",    "content": gpt_prompt}
            ]
        )
        brief_text = resp.choices[0].message.content
    except Exception as e:
        brief_text = f"Mock Output:\n\n{gpt_prompt}\n\nError: {e}"

    # Connection keywords
    conn_prompt = f"""
    Suggest 2‑3 simple search keywords to find helpful local businesses for:

    Business Type: {category}
    Location: {location}
    Goal: {user_input}
    """
    try:
        conn_resp = openai.ChatCompletion.create(
            model="gpt-4",
            messages=[
                {"role": "system", "content": "You help generate Google Maps search terms for business partnerships."},
                {"role": "user",    "content": conn_prompt}
            ]
        )
        keywords = [
            line.strip("-• ").strip()
            for line in conn_resp.choices[0].message.content.splitlines()
            if line.strip()
        ]
    except Exception:
        keywords = ["SEO agency", "business coach", "coworking space"]

    # Scrape Google Maps
    connections = []
    for kw in keywords:
        connections.extend(scrape_apify_googlemaps(kw, location))

    # Store brief
    latest_brief = {
        "business":    business_name,
        "category":    category,
        "location":    location,
        "goal":        user_input,
        "summary":     brief_text,
        "connections": connections
    }
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    with open(f"brief_{business_name.replace(' ', '_')}_{ts}.json", "w") as f:
        json.dump(latest_brief, f, indent=2)

    return render_template(
        "brief.html",
        business_name=business_name,
        result=brief_text,
        connections=connections
    )

@app.route("/api/brief")
def api_latest_brief():
    return jsonify(latest_brief)

@app.route("/download")
def download_pdf():
    html = render_template(
        "brief.html",
        business_name=latest_brief.get("business", "Business"),
        result=latest_brief.get("summary", ""),
        connections=latest_brief.get("connections", [])
    )
    pdf = pdfkit.from_string(html, False)
    return send_file(BytesIO(pdf),
                     download_name="sleft_signals_brief.pdf",
                     as_attachment=True)

if __name__ == "__main__":
    app.run(debug=True, port=8000)
