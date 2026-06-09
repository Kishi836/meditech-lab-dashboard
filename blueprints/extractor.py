"""Extractor blueprint — clinical-note entity extraction JSON API.

Thin HTTP/validation wrapper around the pure logic in `domain/extract.py`.
The route is registered with the `/api` prefix here so the final path is
exactly `/api/extract` (the blueprint is mounted at `/api`).
"""

from flask import Blueprint, jsonify, request

from domain import extract

bp = Blueprint("extractor", __name__, url_prefix="/api")


def _require_text():
    """Pull `text` from the JSON body; return (value, error_response_or_None)."""
    body = request.get_json(silent=True)
    if not isinstance(body, dict):
        return None, (jsonify({"error": "missing or invalid JSON body"}), 400)

    text = body.get("text")
    if not isinstance(text, str) or not text.strip():
        return None, (jsonify({"error": "missing or empty required field 'text'"}), 400)

    return text, None


@bp.route("/extract", methods=["POST"])
def extract_note():
    text, err = _require_text()
    if err:
        return err

    lines = [
        {"text": line, "class": extract.classify_token(line)}
        for line in text.split("\n")
    ]

    return jsonify({
        "entities": extract.extract_entities(text),
        "lines": lines,
    })
