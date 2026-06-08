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
