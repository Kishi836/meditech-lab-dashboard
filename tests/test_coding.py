"""Tests for the pure ICD-10 + SNOMED coding logic in domain.coding.

These exercise only pure functions over module-level data — no Flask,
no DB, no I/O.
"""

from domain import coding


# ── icd10_lookup ──────────────────────────────────────────────────────────

def test_icd10_lookup_exact_match():
    result = coding.icd10_lookup("E11.65")
    assert result["found"] is True
    assert result["code"] == "E11.65"
    assert "hyperglycaemia" in result["desc"].lower()
    assert result["note"] is None


def test_icd10_lookup_prefix_match():
    result = coding.icd10_lookup("E11")
    assert result["found"] is True
    assert result["code"].startswith("E11")
    assert isinstance(result["note"], str)


def test_icd10_lookup_prefix_match_is_deterministic_alphabetical_winner():
    # Multiple E11.x codes exist (E11.22, E11.31, E11.641, E11.65, E11.9).
    # The match must be the alphabetically-first code, not whatever happens
    # to be first in dict insertion order — pin the exact value so future
    # data reordering can't silently change the chosen winner.
    result = coding.icd10_lookup("E11")
    assert result["code"] == "E11.22"


def test_icd10_lookup_not_found():
    result = coding.icd10_lookup("ZZZ")
    assert result["found"] is False
    assert result["code"] == "ZZZ"
    assert result["note"] is None


def test_icd10_lookup_is_case_insensitive_and_strips_whitespace():
    result = coding.icd10_lookup("  e11.65  ")
    assert result["found"] is True
    assert result["code"] == "E11.65"


# ── icd10_search ──────────────────────────────────────────────────────────

def test_icd10_search_by_description_returns_diabetes_codes():
    results = coding.icd10_search("diabetes")
    assert len(results) >= 1
    assert any(r["code"].startswith("E11") for r in results)


def test_icd10_search_by_code_fragment():
    results = coding.icd10_search("I50")
    assert len(results) >= 1
    assert any(r["code"] == "I50.9" for r in results)


def test_icd10_search_is_case_insensitive():
    lower = coding.icd10_search("pneumonia")
    upper = coding.icd10_search("PNEUMONIA")
    assert lower == upper
    assert len(lower) >= 1


def test_icd10_search_no_match_returns_empty_list():
    assert coding.icd10_search("nonexistent-condition-xyz") == []


import pytest


@pytest.mark.parametrize("term, expected_code", [
    ("hypertension", "I10"),
    ("asthma", "J45.909"),
    ("fracture", "S72.001A"),
    ("copd", "J44.9"),
    ("depress", "F32.9"),
    ("anxiety", "F41.1"),
    ("pneumonia", "J18.9"),
    ("migraine", "G43.909"),
    ("osteoporosis", "M81.0"),
    ("sepsis", "A41.9"),
    ("urinary tract", "N39.0"),
    ("breast", "C50.919"),
])
def test_icd10_search_covers_common_conditions(term, expected_code):
    # The expanded code set must return hits for arbitrary common terms,
    # not just "diabetes" (plan.md §8 item 1).
    results = coding.icd10_search(term)
    assert any(r["code"] == expected_code for r in results), \
        f"expected {expected_code} in results for '{term}'"


# ── snomed_search ─────────────────────────────────────────────────────────

def test_snomed_search_by_fsn_returns_diabetes_concepts():
    results = coding.snomed_search("diabetes")
    assert len(results) >= 1
    assert any(r["id"] == 44054006 for r in results)


def test_snomed_search_is_case_insensitive():
    lower = coding.snomed_search("diabetes")
    upper = coding.snomed_search("DIABETES")
    assert lower == upper
    assert len(lower) >= 1


def test_snomed_search_by_id_substring():
    results = coding.snomed_search("44054006")
    assert any(r["id"] == 44054006 for r in results)


def test_snomed_search_no_match_returns_empty_list():
    assert coding.snomed_search("nonexistent-condition-xyz") == []


# ── snomed_get ────────────────────────────────────────────────────────────

def test_snomed_get_known_concept():
    concept = coding.snomed_get(44054006)
    assert concept is not None
    assert "diabetes mellitus type 2" in concept["fsn"].lower()


def test_snomed_get_unknown_concept_returns_none():
    assert coding.snomed_get(999999999) is None


# ── snomed_ancestors ──────────────────────────────────────────────────────

def test_snomed_ancestors_ends_at_root():
    ancestors = coding.snomed_ancestors(421893009)
    assert len(ancestors) > 0
    assert ancestors[-1] == 404684003


def test_snomed_ancestors_pneumonia_reaches_root():
    ancestors = coding.snomed_ancestors(233604007)
    assert len(ancestors) > 0
    assert ancestors[-1] == 404684003


def test_snomed_ancestors_of_root_is_empty():
    assert coding.snomed_ancestors(404684003) == []


def test_snomed_ancestors_of_unknown_concept_is_empty():
    assert coding.snomed_ancestors(999999999) == []


# ── snomed_to_icd10 ───────────────────────────────────────────────────────

def test_snomed_to_icd10_direct_map_diabetes():
    assert coding.snomed_to_icd10(44054006) == "E11.9"


def test_snomed_to_icd10_direct_map_heart_failure():
    assert coding.snomed_to_icd10(84114007) == "I50.9"


def test_snomed_to_icd10_direct_map_pneumonia():
    assert coding.snomed_to_icd10(233604007) == "J18.9"


def test_snomed_to_icd10_recurses_into_children():
    # 362965005 (Disorder of endocrine system) has no own icd10_map but
    # has a child chain that eventually maps to one — recursion should
    # find a mapped descendant rather than returning None outright.
    result = coding.snomed_to_icd10(362965005)
    assert result is not None


def test_snomed_to_icd10_unknown_concept_returns_none():
    assert coding.snomed_to_icd10(999999999) is None


@pytest.mark.parametrize("concept_id, expected_icd10", [
    (195967001, "J45.909"),  # Asthma
    (38341003,  "I10"),      # Hypertensive disorder
    (13645005,  "J44.9"),    # COPD
    (35489007,  "F32.9"),    # Depressive disorder
    (69896004,  "M06.9"),    # Rheumatoid arthritis
    (840539006, "U07.1"),    # COVID-19
])
def test_snomed_to_icd10_expanded_concepts(concept_id, expected_icd10):
    assert coding.snomed_to_icd10(concept_id) == expected_icd10


@pytest.mark.parametrize("term, expected_id", [
    ("asthma", 195967001),
    ("hypertensive", 38341003),
    ("rheumatoid", 69896004),
    ("schizophrenia", 58214004),
])
def test_snomed_search_covers_expanded_concepts(term, expected_id):
    results = coding.snomed_search(term)
    assert any(r["id"] == expected_id for r in results)


# ── hierarchy integrity (catches dangling child / orphan references) ────────

def test_every_snomed_child_reference_resolves():
    for cid, concept in coding.SNOMED.items():
        for child in concept.get("children", []):
            assert child in coding.SNOMED, f"{cid} references missing child {child}"


def test_every_snomed_concept_reaches_root():
    for cid in coding.SNOMED:
        if cid == coding.SNOMED_ROOT:
            continue
        assert coding.snomed_ancestors(cid)[-1] == coding.SNOMED_ROOT, \
            f"{cid} does not chain up to the root"


def test_every_snomed_icd10_map_exists_in_icd10_table():
    for cid, concept in coding.SNOMED.items():
        mapped = concept.get("attributes", {}).get("icd10_map")
        if not mapped:
            continue
        # Compound maps (e.g. "N08 + E11.22") split on " + "; each part
        # must resolve in the ICD-10 table.
        for code in mapped.split(" + "):
            assert coding.icd10_lookup(code)["found"], \
                f"{cid} maps to unknown ICD-10 code {code!r}"
