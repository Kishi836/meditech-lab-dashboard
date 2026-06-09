"""Coder blueprint — ICD-10 / SNOMED CT lookup & cross-mapping JSON API.

Thin HTTP/validation wrapper around the pure logic in `domain/coding.py`.
Routes are registered with no prefix here so the final paths are exactly
`/api/icd10`, `/api/snomed/search`, `/api/snomed/<int:id>`, and
`/api/crossmap/<int:id>` (the blueprint is mounted at `/api` in app.py).
"""

from flask import Blueprint, jsonify, request

from domain import coding

bp = Blueprint("coder", __name__, url_prefix="/api")


def _require_query_param():
    """Pull `q` from the query string; return (value, error_response_or_None)."""
    q = request.args.get("q", "")
    if not q.strip():
        return None, (jsonify({"error": "missing or empty required query parameter 'q'"}), 400)
    return q, None


@bp.route("/icd10")
def icd10_search():
    q, err = _require_query_param()
    if err:
        return err
    return jsonify(coding.icd10_search(q))


@bp.route("/snomed/search")
def snomed_search():
    q, err = _require_query_param()
    if err:
        return err

    return jsonify(coding.snomed_search(q))


@bp.route("/snomed/<int:concept_id>")
def snomed_detail(concept_id):
    concept = coding.snomed_get(concept_id)
    if concept is None:
        return jsonify({"error": f"unknown SNOMED concept id {concept_id}"}), 404

    ancestors = [
        {"id": aid, "fsn": coding.SNOMED[aid]["fsn"]}
        for aid in coding.snomed_ancestors(concept_id)
        if aid in coding.SNOMED
    ]
    children = [
        {"id": cid, "fsn": coding.SNOMED[cid]["fsn"]}
        for cid in concept.get("children", [])
        if cid in coding.SNOMED
    ]

    return jsonify({
        "id": concept_id,
        "fsn": concept["fsn"],
        "attributes": concept.get("attributes", {}),
        "ancestors": ancestors,
        "children": children,
    })


@bp.route("/crossmap/<int:concept_id>")
def crossmap(concept_id):
    if coding.snomed_get(concept_id) is None:
        return jsonify({"error": f"unknown SNOMED concept id {concept_id}"}), 404

    return jsonify({"snomed": concept_id, "icd10": coding.snomed_to_icd10(concept_id)})
