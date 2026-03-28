"""
The Good Neighbor Guard — LYLO Mechanic
Christopher Hughes · Sacramento, CA
AI Collaborators: Claude · GPT · Gemini · Groq
Truth · Safety · We Got Your Back
"""

from flask import Flask
from flask_cors import CORS
from api.routes.session import session_bp
from api.routes.diagnose import diagnose_bp
from api.routes.scenarios import scenarios_bp
from api.routes.tutorial import tutorial_bp

app = Flask(__name__, template_folder="../frontend/templates", static_folder="../frontend/static")
CORS(app)

app.register_blueprint(session_bp, url_prefix="/api/v1/session")
app.register_blueprint(diagnose_bp, url_prefix="/api/v1/diagnose")
app.register_blueprint(scenarios_bp, url_prefix="/api/v1/scenarios")
app.register_blueprint(tutorial_bp, url_prefix="/api/v1/tutorial")

@app.route("/")
def index():
    from flask import render_template
    return render_template("index.html")

@app.route("/health")
def health():
    return {"status": "ok", "system": "LYLO Mechanic", "version": "1.0.0"}

if __name__ == "__main__":
   app.run(host="0.0.0.0", port=5055, debug=False)
