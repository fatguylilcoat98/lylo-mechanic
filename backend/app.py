"""
The Good Neighbor Guard — LYLO Mechanic
Christopher Hughes · Sacramento, CA
AI Collaborators: Claude · GPT · Gemini · Groq
Truth · Safety · We Got Your Back
"""

import logging
import os
import resource
import signal
import sys
import time
import traceback

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s [pid=%(process)d]: %(message)s",
    stream=sys.stdout,
    force=True,
)
boot_logger = logging.getLogger("lylo.boot")
req_logger = logging.getLogger("lylo.request")

boot_logger.info("=== WORKER BOOT START pid=%s ===", os.getpid())


def _rss_mb() -> float:
    # ru_maxrss is KB on Linux, bytes on macOS. Render is Linux.
    return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024.0


def _install_signal_logging():
    def handler(signum, frame):
        req_logger.error("SIGNAL RECEIVED signum=%s pid=%s rss_mb=%.1f", signum, os.getpid(), _rss_mb())
        # Re-raise default so gunicorn's own handling still runs
        signal.signal(signum, signal.SIG_DFL)
        os.kill(os.getpid(), signum)
    for sig in (signal.SIGTERM, signal.SIGABRT, signal.SIGUSR1):
        try:
            signal.signal(sig, handler)
        except (ValueError, OSError):
            pass


_install_signal_logging()

from flask import Flask, g, request
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

boot_logger.info("=== BLUEPRINTS IMPORTED rss_mb=%.1f ===", _rss_mb())

app = Flask(__name__, template_folder="../frontend/templates", static_folder="../frontend/static")
CORS(app)


@app.before_request
def _log_request_start():
    g._req_start = time.time()
    g._req_rss_start = _rss_mb()
    try:
        body_len = request.content_length or 0
    except Exception:
        body_len = -1
    req_logger.info(
        "REQ START %s %s remote=%s body_len=%s rss_mb=%.1f",
        request.method, request.path, request.remote_addr, body_len, g._req_rss_start,
    )


@app.after_request
def _log_request_end(response):
    dur_ms = (time.time() - getattr(g, "_req_start", time.time())) * 1000
    rss_now = _rss_mb()
    delta = rss_now - getattr(g, "_req_rss_start", rss_now)
    req_logger.info(
        "REQ END   %s %s status=%s dur_ms=%.1f rss_mb=%.1f delta_mb=%+.1f",
        request.method, request.path, response.status_code, dur_ms, rss_now, delta,
    )
    return response


@app.teardown_request
def _log_request_teardown(exc):
    if exc is None:
        return
    rss_now = _rss_mb()
    req_logger.error(
        "REQ TEARDOWN with exception %s %s exc_type=%s exc=%s rss_mb=%.1f",
        request.method, request.path, type(exc).__name__, exc, rss_now,
    )
    req_logger.error("Traceback:\n%s", traceback.format_exc())


@app.errorhandler(Exception)
def _unhandled(exc):
    req_logger.error(
        "UNHANDLED %s %s exc_type=%s exc=%s rss_mb=%.1f",
        request.method, request.path, type(exc).__name__, exc, _rss_mb(),
    )
    req_logger.error("Traceback:\n%s", traceback.format_exc())
    from flask import jsonify
    return jsonify({"error": str(exc), "exception_type": type(exc).__name__}), 500

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

boot_logger.info("=== WORKER BOOT COMPLETE rss_mb=%.1f ===", _rss_mb())

@app.route("/")
def index():
    from flask import render_template
    return render_template("mvp.html")

@app.route("/home")
def lylo_home():
    """Premium LYLO landing page — showcases all 4 truth layers."""
    from flask import render_template, make_response
    resp = make_response(render_template("lylo_home.html"))
    resp.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    resp.headers["Pragma"] = "no-cache"
    resp.headers["Expires"] = "0"
    return resp

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
