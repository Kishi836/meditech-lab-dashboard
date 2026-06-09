"""Pure ICD-10 + SNOMED CT coding logic.

Ported (and lightly expanded) from the Module 2 hands-on exercise
(`module2_hands_on_exercise.py`, Exercise 3 — Clinical Coding).

This module is intentionally PURE: module-level data plus pure functions
over it. No Flask, no database access, no network/file I/O.
"""

# ═══════════════════════════════════════════════════════════════════════════
# ICD-10 lookup table — code → {desc, chapter, block}
# ═══════════════════════════════════════════════════════════════════════════

ICD10 = {
    # Endocrine
    "E11.9":   {"desc": "Type 2 diabetes mellitus without complications",            "chapter": "E", "block": "E10-E14"},
    "E11.65":  {"desc": "Type 2 diabetes mellitus with hyperglycaemia & hyperlipidaemia", "chapter": "E", "block": "E10-E14"},
    "E11.22":  {"desc": "Type 2 diabetes mellitus with diabetic CKD stage 3",             "chapter": "E", "block": "E10-E14"},
    "E11.31":  {"desc": "Type 2 diabetes mellitus with diabetic retinopathy",             "chapter": "E", "block": "E10-E14"},
    "E11.641": {"desc": "Type 2 diabetes mellitus with diabetic polyneuropathy",          "chapter": "E", "block": "E10-E14"},
    "E10.9":   {"desc": "Type 1 diabetes mellitus without complications",                 "chapter": "E", "block": "E10-E14"},
    # Cardiovascular
    "I10":     {"desc": "Essential (primary) hypertension",           "chapter": "I", "block": "I10-I15"},
    "I50.9":   {"desc": "Heart failure, unspecified",                 "chapter": "I", "block": "I50"},
    "I63.9":   {"desc": "Cerebral infarction, unspecified",           "chapter": "I", "block": "I60-I69"},
    "I25.10":  {"desc": "Atherosclerotic heart disease, unspecified", "chapter": "I", "block": "I20-I25"},
    # Respiratory
    "J18.9":   {"desc": "Pneumonia, unspecified organism",            "chapter": "J", "block": "J10-J18"},
    "J45.909": {"desc": "Unspecified asthma, uncomplicated",          "chapter": "J", "block": "J40-J47"},
    "J44.1":   {"desc": "COPD with acute exacerbation",               "chapter": "J", "block": "J40-J47"},
    # Renal
    "N18.3":   {"desc": "Chronic kidney disease, stage 3",            "chapter": "N", "block": "N17-N19"},
    "N18.4":   {"desc": "Chronic kidney disease, stage 4",            "chapter": "N", "block": "N17-N19"},
    "N08":     {"desc": "Glomerular disorders in diseases elsewhere", "chapter": "N", "block": "N00-N08"},
    # Musculoskeletal
    "M79.3":   {"desc": "Panniculitis, unspecified",                  "chapter": "M", "block": "M70-M79"},
    "M54.5":   {"desc": "Low back pain",                              "chapter": "M", "block": "M50-M54"},
    # Injury
    "S72.001A": {"desc": "Fracture of unspecified part of femoral neck, init enc", "chapter": "S", "block": "S70-S79"},
    # Mental health
    "F32.9":   {"desc": "Major depressive disorder, single episode, unspecified", "chapter": "F", "block": "F30-F39"},
    # Pregnancy/childbirth
    "O24.419": {"desc": "Pre-existing T2DM, complicating pregnancy",  "chapter": "O", "block": "O24"},
}


# ═══════════════════════════════════════════════════════════════════════════
# SNOMED CT concept hierarchy — concept_id → {fsn, children?, attributes?}
# ═══════════════════════════════════════════════════════════════════════════

SNOMED_ROOT = 404684003

SNOMED = {
    404684003: {
        "fsn": "Clinical finding (finding)",
        "children": [362965005, 118234003, 50043002],
    },
    362965005: {
        "fsn": "Disorder of endocrine system (disorder)",
        "children": [73211009, 44054006],
    },
    73211009: {
        "fsn": "Diabetes mellitus (disorder)",
        "children": [44054006, 190331003, 81531005],
    },
    44054006: {
        "fsn": "Diabetes mellitus type 2 (disorder)",
        "children": [420789003, 421893009],
        "attributes": {
            "finding_site": "Structure of endocrine system (body structure)",
            "pathology":    "Metabolic pathology (morphologic abnormality)",
            "icd10_map":    "E11.9",
        },
    },
    420789003: {
        "fsn": "Diabetic retinopathy (disorder)",
        "attributes": {
            "finding_site": "Retinal structure (body structure)",
            "icd10_map":    "E11.31",
        },
    },
    421893009: {
        "fsn": "Diabetic nephropathy (disorder)",
        "attributes": {
            "finding_site": "Kidney structure (body structure)",
            # Deliberate compound/dual mapping (not a single valid ICD-10
            # code) — future consumers should split on " + " if needed.
            "icd10_map":    "N08 + E11.22",
        },
    },
    118234003: {
        "fsn": "Finding of cardiovascular system (finding)",
        "children": [84114007, 38341003],
    },
    84114007: {
        "fsn": "Heart failure (disorder)",
        "attributes": {"finding_site": "Heart structure", "icd10_map": "I50.9"},
    },
    38341003: {
        "fsn": "Hypertensive disorder (disorder)",
        "attributes": {"finding_site": "Systemic arterial structure", "icd10_map": "I10"},
    },
    190331003: {
        "fsn": "Type 1 diabetes mellitus (disorder)",
        "attributes": {"icd10_map": "E10.9"},
    },
    81531005: {
        "fsn": "Diabetes mellitus in mother, complicating pregnancy (disorder)",
        "attributes": {"icd10_map": "O24.419"},
    },
    233604007: {
        "fsn": "Pneumonia (disorder)",
        "attributes": {
            "finding_site": "Lung structure (body structure)",
            "icd10_map":    "J18.9",
        },
    },
    50043002: {
        "fsn": "Disorder of respiratory system (disorder)",
        "children": [233604007],
    },
}


# ═══════════════════════════════════════════════════════════════════════════
# ICD-10 functions
# ═══════════════════════════════════════════════════════════════════════════

def icd10_lookup(code: str) -> dict:
    """Look up an ICD-10 code.

    Tries an exact match first, then a prefix match (e.g. "E11" matches
    "E11.9"), and finally returns a not-found dict.
    """
    normalized = code.strip().upper()

    if normalized in ICD10:
        return {"found": True, "code": normalized, "note": None, **ICD10[normalized]}

    prefix_hits = [c for c in ICD10 if c.startswith(normalized)]
    if prefix_hits:
        match = sorted(prefix_hits)[0]
        return {
            "found": True,
            "code": match,
            "note": f"prefix match from '{normalized}'",
            **ICD10[match],
        }

    return {"found": False, "code": normalized, "desc": "UNKNOWN CODE", "chapter": "?", "block": "?", "note": None}


def icd10_search(q: str) -> list[dict]:
    """Search ICD-10 entries whose code or description contains `q`.

    Matching is case-insensitive. Returns a list of dicts shaped like
    `icd10_lookup` results (each with "found": True).
    """
    needle = q.strip().lower()
    if not needle:
        return []

    results = []
    for code, meta in ICD10.items():
        if needle in code.lower() or needle in meta["desc"].lower():
            results.append({"found": True, "code": code, **meta})
    return results


# ═══════════════════════════════════════════════════════════════════════════
# SNOMED functions
# ═══════════════════════════════════════════════════════════════════════════

def snomed_search(q: str) -> list[dict]:
    """Search SNOMED concepts whose FSN or numeric id contains `q`.

    Matching is case-insensitive against the FSN, or a substring match
    against `str(id)`. Returns a list of `{"id": <int>, "fsn": <str>}` dicts.
    """
    needle = q.strip().lower()
    if not needle:
        return []

    results = []
    for cid, concept in SNOMED.items():
        if needle in concept["fsn"].lower() or needle in str(cid):
            results.append({"id": cid, "fsn": concept["fsn"]})
    return results


def snomed_get(concept_id: int) -> dict | None:
    """Return the concept dict for `concept_id`, or None if unknown."""
    return SNOMED.get(concept_id)


def snomed_ancestors(concept_id: int) -> list[int]:
    """Return the parent chain for `concept_id`, from immediate parent to root.

    E.g. for a leaf two levels below the root, returns
    [immediate_parent, root]. The root concept and unknown concepts have
    no ancestors and return an empty list.
    """
    ancestors: list[int] = []
    current = concept_id

    while True:
        parent = None
        for cid, concept in SNOMED.items():
            if current in concept.get("children", []):
                parent = cid
                break
        if parent is None:
            break
        ancestors.append(parent)
        current = parent

    return ancestors


def snomed_to_icd10(concept_id: int) -> str | None:
    """Map a SNOMED concept to an ICD-10 code.

    Returns the concept's own `attributes["icd10_map"]` if present;
    otherwise recurses into its children looking for a mapped descendant;
    otherwise None.
    """
    concept = SNOMED.get(concept_id)
    if concept is None:
        return None

    icd10_map = concept.get("attributes", {}).get("icd10_map")
    if icd10_map is not None:
        return icd10_map

    for child_id in concept.get("children", []):
        mapped = snomed_to_icd10(child_id)
        if mapped is not None:
            return mapped

    return None
