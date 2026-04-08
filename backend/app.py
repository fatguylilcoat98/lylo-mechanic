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
from api.routes.live import live_bp
from api.routes.persona import persona_bp
from api.routes.quick_check import quick_check_bp
from api.routes.obd2 import obd2_bp
from api.routes.billing import billing_bp
from api.routes.analyze import analyze_bp
from api.routes.truth import truth_bp

app = Flask(__name__, template_folder="../frontend/templates", static_folder="../frontend/static")
CORS(app)

app.register_blueprint(session_bp, url_prefix="/api/v1/session")
app.register_blueprint(diagnose_bp, url_prefix="/api/v1/diagnose")
app.register_blueprint(scenarios_bp, url_prefix="/api/v1/scenarios")
app.register_blueprint(tutorial_bp, url_prefix="/api/v1/tutorial")
app.register_blueprint(live_bp, url_prefix="/api/v1/live")
app.register_blueprint(persona_bp, url_prefix="/api/v1/persona")
app.register_blueprint(quick_check_bp, url_prefix="/api/v1/quick")
app.register_blueprint(obd2_bp, url_prefix="/obd2")
app.register_blueprint(billing_bp, url_prefix="/api/v1/billing")
app.register_blueprint(analyze_bp, url_prefix="/api/v1/analyze")
app.register_blueprint(truth_bp, url_prefix="/api/v1")

@app.route("/")
def index():
    from flask import render_template
    return render_template("mvp.html")

@app.route("/dashboard")
def dashboard():
    from flask import render_template
    return render_template("index.html")

@app.route("/health")
def health():
    return {"status": "ok", "system": "LYLO Mechanic", "version": "1.0.0"}

if __name__ == "__main__":
    import os
    port = int(os.environ.get('PORT', 5000))
    app.run(debug=False, host='0.0.0.0', port=port)
