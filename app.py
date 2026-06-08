"""
Meditech Lab 2.0 — Flask app factory
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Wires together config, blueprints, and the dashboard shell. The browser
talks only to this app's JSON endpoints — Postgres/ES access is hidden
behind db.py / es.py so routes stay thin.

Run:  python app.py            (dev server on :5000)
  or: flask --app app run
"""

from flask import Flask, render_template, jsonify

import db
import es
from config import Config
from blueprints.patients import bp as patients_bp
from blueprints.extractor import bp as extractor_bp
from blueprints.coder import bp as coder_bp
from blueprints.pipeline import bp as pipeline_bp


def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)

    app.register_blueprint(patients_bp)
    app.register_blueprint(extractor_bp)
    app.register_blueprint(coder_bp)
    app.register_blueprint(pipeline_bp)

    @app.route("/")
    def index():
        return render_template("base.html")

    @app.route("/api/health")
    def health():
        return jsonify({"postgres": db.ping(), "es": es.ping()})

    return app


if __name__ == "__main__":
    create_app().run(debug=True)
