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
    # ── Certain infectious & parasitic diseases (A00–B99) ──
    "A09":     {"desc": "Infectious gastroenteritis and colitis, unspecified", "chapter": "A", "block": "A00-A09"},
    "A41.9":   {"desc": "Sepsis, unspecified organism",                        "chapter": "A", "block": "A30-A49"},
    "B34.9":   {"desc": "Viral infection, unspecified",                        "chapter": "B", "block": "B25-B34"},
    "U07.1":   {"desc": "COVID-19, virus identified",                          "chapter": "U", "block": "U00-U49"},

    # ── Neoplasms (C00–D49) ──
    "C18.9":   {"desc": "Malignant neoplasm of colon, unspecified", "chapter": "C", "block": "C15-C26"},
    "C34.90":  {"desc": "Malignant neoplasm of unspecified lung",   "chapter": "C", "block": "C30-C39"},
    "C50.919": {"desc": "Malignant neoplasm of unspecified breast", "chapter": "C", "block": "C50-C50"},
    "C61":     {"desc": "Malignant neoplasm of prostate",           "chapter": "C", "block": "C60-C63"},

    # ── Blood & blood-forming organs (D50–D89) ──
    "D50.9":   {"desc": "Iron deficiency anaemia, unspecified", "chapter": "D", "block": "D50-D53"},
    "D64.9":   {"desc": "Anaemia, unspecified",                 "chapter": "D", "block": "D60-D64"},

    # ── Endocrine, nutritional & metabolic (E00–E89) ──
    "E03.9":   {"desc": "Hypothyroidism, unspecified",                                    "chapter": "E", "block": "E00-E07"},
    "E05.90":  {"desc": "Thyrotoxicosis (hyperthyroidism), unspecified",                  "chapter": "E", "block": "E00-E07"},
    "E10.9":   {"desc": "Type 1 diabetes mellitus without complications",                 "chapter": "E", "block": "E08-E13"},
    "E11.9":   {"desc": "Type 2 diabetes mellitus without complications",                 "chapter": "E", "block": "E08-E13"},
    "E11.22":  {"desc": "Type 2 diabetes mellitus with diabetic CKD stage 3",             "chapter": "E", "block": "E08-E13"},
    "E11.31":  {"desc": "Type 2 diabetes mellitus with diabetic retinopathy",             "chapter": "E", "block": "E08-E13"},
    "E11.641": {"desc": "Type 2 diabetes mellitus with diabetic polyneuropathy",          "chapter": "E", "block": "E08-E13"},
    "E11.65":  {"desc": "Type 2 diabetes mellitus with hyperglycaemia & hyperlipidaemia", "chapter": "E", "block": "E08-E13"},
    "E66.9":   {"desc": "Obesity, unspecified",                                           "chapter": "E", "block": "E65-E68"},
    "E78.5":   {"desc": "Hyperlipidaemia, unspecified",                                   "chapter": "E", "block": "E70-E88"},
    "E86.0":   {"desc": "Dehydration",                                                    "chapter": "E", "block": "E70-E88"},

    # ── Mental & behavioural (F01–F99) ──
    "F20.9":   {"desc": "Schizophrenia, unspecified",                             "chapter": "F", "block": "F20-F29"},
    "F32.9":   {"desc": "Major depressive disorder, single episode, unspecified", "chapter": "F", "block": "F30-F39"},
    "F33.1":   {"desc": "Major depressive disorder, recurrent, moderate",         "chapter": "F", "block": "F30-F39"},
    "F41.1":   {"desc": "Generalized anxiety disorder",                           "chapter": "F", "block": "F40-F48"},

    # ── Nervous system (G00–G99) ──
    "G20":     {"desc": "Parkinson's disease",                    "chapter": "G", "block": "G20-G26"},
    "G30.9":   {"desc": "Alzheimer's disease, unspecified",       "chapter": "G", "block": "G30-G32"},
    "G35":     {"desc": "Multiple sclerosis",                     "chapter": "G", "block": "G35-G37"},
    "G40.909": {"desc": "Epilepsy, unspecified, not intractable", "chapter": "G", "block": "G40-G47"},
    "G43.909": {"desc": "Migraine, unspecified, not intractable", "chapter": "G", "block": "G40-G47"},

    # ── Eye & ear (H00–H95) ──
    "H25.9":   {"desc": "Age-related cataract, unspecified",          "chapter": "H", "block": "H25-H28"},
    "H40.9":   {"desc": "Glaucoma, unspecified",                      "chapter": "H", "block": "H40-H42"},
    "H66.90":  {"desc": "Otitis media, unspecified, unspecified ear", "chapter": "H", "block": "H65-H75"},

    # ── Circulatory (I00–I99) ──
    "I10":     {"desc": "Essential (primary) hypertension",                  "chapter": "I", "block": "I10-I16"},
    "I11.9":   {"desc": "Hypertensive heart disease without heart failure",  "chapter": "I", "block": "I10-I16"},
    "I21.3":   {"desc": "ST elevation myocardial infarction, unspec. site",  "chapter": "I", "block": "I20-I25"},
    "I25.10":  {"desc": "Atherosclerotic heart disease, unspecified",        "chapter": "I", "block": "I20-I25"},
    "I48.91":  {"desc": "Atrial fibrillation, unspecified",                  "chapter": "I", "block": "I30-I52"},
    "I50.9":   {"desc": "Heart failure, unspecified",                        "chapter": "I", "block": "I30-I52"},
    "I63.9":   {"desc": "Cerebral infarction, unspecified",                  "chapter": "I", "block": "I60-I69"},
    "I82.40":  {"desc": "Acute embolism & thrombosis of unspec. deep veins of lower extremity", "chapter": "I", "block": "I80-I89"},

    # ── Respiratory (J00–J99) ──
    "J02.9":   {"desc": "Acute pharyngitis, unspecified",                "chapter": "J", "block": "J00-J06"},
    "J06.9":   {"desc": "Acute upper respiratory infection, unspecified", "chapter": "J", "block": "J00-J06"},
    "J18.9":   {"desc": "Pneumonia, unspecified organism",               "chapter": "J", "block": "J09-J18"},
    "J20.9":   {"desc": "Acute bronchitis, unspecified",                 "chapter": "J", "block": "J20-J22"},
    "J44.1":   {"desc": "COPD with acute exacerbation",                  "chapter": "J", "block": "J40-J47"},
    "J44.9":   {"desc": "Chronic obstructive pulmonary disease (COPD), unspecified", "chapter": "J", "block": "J40-J47"},
    "J45.909": {"desc": "Unspecified asthma, uncomplicated",             "chapter": "J", "block": "J40-J47"},

    # ── Digestive (K00–K95) ──
    "K21.9":   {"desc": "Gastro-oesophageal reflux disease without oesophagitis", "chapter": "K", "block": "K20-K31"},
    "K29.70":  {"desc": "Gastritis, unspecified, without bleeding",               "chapter": "K", "block": "K20-K31"},
    "K35.80":  {"desc": "Acute appendicitis, unspecified",                        "chapter": "K", "block": "K35-K38"},
    "K70.30":  {"desc": "Alcoholic cirrhosis of liver without ascites",           "chapter": "K", "block": "K70-K77"},
    "K80.20":  {"desc": "Calculus of gallbladder without cholecystitis",          "chapter": "K", "block": "K80-K87"},

    # ── Skin (L00–L99) ──
    "L03.90":  {"desc": "Cellulitis, unspecified",        "chapter": "L", "block": "L00-L08"},
    "L20.9":   {"desc": "Atopic dermatitis, unspecified", "chapter": "L", "block": "L20-L30"},
    "L40.0":   {"desc": "Psoriasis vulgaris",             "chapter": "L", "block": "L40-L45"},

    # ── Musculoskeletal (M00–M99) ──
    "M06.9":   {"desc": "Rheumatoid arthritis, unspecified",        "chapter": "M", "block": "M05-M14"},
    "M17.0":   {"desc": "Bilateral primary osteoarthritis of knee", "chapter": "M", "block": "M15-M19"},
    "M19.90":  {"desc": "Osteoarthritis, unspecified site",         "chapter": "M", "block": "M15-M19"},
    "M54.5":   {"desc": "Low back pain",                            "chapter": "M", "block": "M50-M54"},
    "M81.0":   {"desc": "Age-related osteoporosis w/o current pathological fracture", "chapter": "M", "block": "M80-M85"},

    # ── Genitourinary (N00–N99) ──
    "N08":     {"desc": "Glomerular disorders in diseases classified elsewhere", "chapter": "N", "block": "N00-N08"},
    "N18.3":   {"desc": "Chronic kidney disease, stage 3",                        "chapter": "N", "block": "N17-N19"},
    "N18.4":   {"desc": "Chronic kidney disease, stage 4",                        "chapter": "N", "block": "N17-N19"},
    "N20.0":   {"desc": "Calculus of kidney",                                     "chapter": "N", "block": "N20-N23"},
    "N39.0":   {"desc": "Urinary tract infection, site not specified",            "chapter": "N", "block": "N30-N39"},
    "N40.0":   {"desc": "Benign prostatic hyperplasia without LUTS",              "chapter": "N", "block": "N40-N53"},

    # ── Pregnancy & childbirth (O00–O9A) ──
    "O24.419": {"desc": "Pre-existing type 2 diabetes mellitus in pregnancy, unspecified trimester", "chapter": "O", "block": "O20-O29"},

    # ── Symptoms & signs (R00–R99) ──
    "R05.9":   {"desc": "Cough, unspecified",         "chapter": "R", "block": "R00-R09"},
    "R07.9":   {"desc": "Chest pain, unspecified",    "chapter": "R", "block": "R00-R09"},
    "R10.9":   {"desc": "Unspecified abdominal pain", "chapter": "R", "block": "R10-R19"},
    "R50.9":   {"desc": "Fever, unspecified",         "chapter": "R", "block": "R50-R69"},
    "R51.9":   {"desc": "Headache, unspecified",      "chapter": "R", "block": "R50-R69"},
    "R53.83":  {"desc": "Other fatigue",              "chapter": "R", "block": "R50-R69"},

    # ── Injury & poisoning (S00–T88) ──
    "S52.501A": {"desc": "Fracture of unspecified part of lower end of radius, init enc", "chapter": "S", "block": "S50-S59"},
    "S72.001A": {"desc": "Fracture of unspecified part of femoral neck, init enc",        "chapter": "S", "block": "S70-S79"},
    "S82.001A": {"desc": "Fracture of unspecified part of right patella, init enc",       "chapter": "S", "block": "S80-S89"},
    "T78.40XA": {"desc": "Allergy, unspecified, initial encounter",                       "chapter": "T", "block": "T78-T78"},

    # ── Factors influencing health status (Z00–Z99) ──
    "Z00.00":  {"desc": "General adult medical examination without abnormal findings", "chapter": "Z", "block": "Z00-Z13"},
}


# ═══════════════════════════════════════════════════════════════════════════
# SNOMED CT concept hierarchy — concept_id → {fsn, children?, attributes?}
# ═══════════════════════════════════════════════════════════════════════════

SNOMED_ROOT = 404684003

SNOMED = {
    404684003: {
        "fsn": "Clinical finding (finding)",
        "children": [
            362965005,  # endocrine
            118234003,  # cardiovascular
            50043002,   # respiratory
            118940003,  # nervous system
            53619000,   # digestive system
            42030000,   # urinary system
            928000,     # musculoskeletal
            95320005,   # skin
            363346000,  # malignant neoplastic disease
            40733004,   # infectious disease
            74732009,   # mental disorder
        ],
    },

    # ── Endocrine ──────────────────────────────────────────────────────────
    362965005: {
        "fsn": "Disorder of endocrine system (disorder)",
        "children": [73211009, 40930008, 34486009, 55822004, 414916001],
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
    190331003: {
        "fsn": "Type 1 diabetes mellitus (disorder)",
        "attributes": {"icd10_map": "E10.9"},
    },
    81531005: {
        "fsn": "Diabetes mellitus in mother, complicating pregnancy (disorder)",
        "attributes": {"icd10_map": "O24.419"},
    },
    40930008: {
        "fsn": "Hypothyroidism (disorder)",
        "attributes": {"finding_site": "Thyroid structure", "icd10_map": "E03.9"},
    },
    34486009: {
        "fsn": "Hyperthyroidism (disorder)",
        "attributes": {"finding_site": "Thyroid structure", "icd10_map": "E05.90"},
    },
    55822004: {
        "fsn": "Hyperlipidaemia (disorder)",
        "attributes": {"icd10_map": "E78.5"},
    },
    414916001: {
        "fsn": "Obesity (disorder)",
        "attributes": {"icd10_map": "E66.9"},
    },

    # ── Cardiovascular ─────────────────────────────────────────────────────
    118234003: {
        "fsn": "Finding of cardiovascular system (finding)",
        "children": [84114007, 38341003, 22298006, 49436004],
    },
    84114007: {
        "fsn": "Heart failure (disorder)",
        "attributes": {"finding_site": "Heart structure", "icd10_map": "I50.9"},
    },
    38341003: {
        "fsn": "Hypertensive disorder (disorder)",
        "attributes": {"finding_site": "Systemic arterial structure", "icd10_map": "I10"},
    },
    22298006: {
        "fsn": "Myocardial infarction (disorder)",
        "attributes": {"finding_site": "Myocardium structure", "icd10_map": "I21.3"},
    },
    49436004: {
        "fsn": "Atrial fibrillation (disorder)",
        "attributes": {"finding_site": "Cardiac atrium structure", "icd10_map": "I48.91"},
    },

    # ── Respiratory ────────────────────────────────────────────────────────
    50043002: {
        "fsn": "Disorder of respiratory system (disorder)",
        "children": [233604007, 195967001, 13645005, 444814009],
    },
    233604007: {
        "fsn": "Pneumonia (disorder)",
        "attributes": {
            "finding_site": "Lung structure (body structure)",
            "icd10_map":    "J18.9",
        },
    },
    195967001: {
        "fsn": "Asthma (disorder)",
        "attributes": {"finding_site": "Bronchial structure", "icd10_map": "J45.909"},
    },
    13645005: {
        "fsn": "Chronic obstructive pulmonary disease (disorder)",
        "attributes": {"finding_site": "Lung structure", "icd10_map": "J44.9"},
    },
    444814009: {
        "fsn": "Viral upper respiratory tract infection (disorder)",
        "attributes": {"icd10_map": "J06.9"},
    },

    # ── Nervous system ─────────────────────────────────────────────────────
    118940003: {
        "fsn": "Disorder of nervous system (disorder)",
        "children": [84757009, 37796009, 49049000, 26929004, 24700007],
    },
    84757009: {
        "fsn": "Epilepsy (disorder)",
        "attributes": {"finding_site": "Brain structure", "icd10_map": "G40.909"},
    },
    37796009: {
        "fsn": "Migraine (disorder)",
        "attributes": {"icd10_map": "G43.909"},
    },
    49049000: {
        "fsn": "Parkinson's disease (disorder)",
        "attributes": {"finding_site": "Brain structure", "icd10_map": "G20"},
    },
    26929004: {
        "fsn": "Alzheimer's disease (disorder)",
        "attributes": {"finding_site": "Brain structure", "icd10_map": "G30.9"},
    },
    24700007: {
        "fsn": "Multiple sclerosis (disorder)",
        "attributes": {"finding_site": "Central nervous system structure", "icd10_map": "G35"},
    },

    # ── Digestive system ───────────────────────────────────────────────────
    53619000: {
        "fsn": "Disorder of digestive system (disorder)",
        "children": [235595009, 4556007, 74400008, 235919008, 19943007],
    },
    235595009: {
        "fsn": "Gastro-oesophageal reflux disease (disorder)",
        "attributes": {"finding_site": "Oesophageal structure", "icd10_map": "K21.9"},
    },
    4556007: {
        "fsn": "Gastritis (disorder)",
        "attributes": {"finding_site": "Gastric structure", "icd10_map": "K29.70"},
    },
    74400008: {
        "fsn": "Appendicitis (disorder)",
        "attributes": {"finding_site": "Appendix structure", "icd10_map": "K35.80"},
    },
    235919008: {
        "fsn": "Cholelithiasis (disorder)",
        "attributes": {"finding_site": "Gallbladder structure", "icd10_map": "K80.20"},
    },
    19943007: {
        "fsn": "Cirrhosis of liver (disorder)",
        "attributes": {"finding_site": "Liver structure", "icd10_map": "K70.30"},
    },

    # ── Urinary system ─────────────────────────────────────────────────────
    42030000: {
        "fsn": "Disorder of urinary system (disorder)",
        "children": [90688005, 68566005, 95570007, 266569009],
    },
    90688005: {
        "fsn": "Chronic kidney disease (disorder)",
        "attributes": {"finding_site": "Kidney structure", "icd10_map": "N18.3"},
    },
    68566005: {
        "fsn": "Urinary tract infectious disease (disorder)",
        "attributes": {"finding_site": "Urinary tract structure", "icd10_map": "N39.0"},
    },
    95570007: {
        "fsn": "Renal calculus (disorder)",
        "attributes": {"finding_site": "Kidney structure", "icd10_map": "N20.0"},
    },
    266569009: {
        "fsn": "Benign prostatic hyperplasia (disorder)",
        "attributes": {"finding_site": "Prostatic structure", "icd10_map": "N40.0"},
    },

    # ── Musculoskeletal ────────────────────────────────────────────────────
    928000: {
        "fsn": "Disorder of musculoskeletal system (disorder)",
        "children": [69896004, 396275006, 64859006, 278860009],
    },
    69896004: {
        "fsn": "Rheumatoid arthritis (disorder)",
        "attributes": {"icd10_map": "M06.9"},
    },
    396275006: {
        "fsn": "Osteoarthritis (disorder)",
        "attributes": {"icd10_map": "M19.90"},
    },
    64859006: {
        "fsn": "Osteoporosis (disorder)",
        "attributes": {"icd10_map": "M81.0"},
    },
    278860009: {
        "fsn": "Chronic low back pain (finding)",
        "attributes": {"finding_site": "Lumbar spine structure", "icd10_map": "M54.5"},
    },

    # ── Skin ───────────────────────────────────────────────────────────────
    95320005: {
        "fsn": "Disorder of skin (disorder)",
        "children": [128045006, 24079001, 9014002],
    },
    128045006: {
        "fsn": "Cellulitis (disorder)",
        "attributes": {"finding_site": "Skin structure", "icd10_map": "L03.90"},
    },
    24079001: {
        "fsn": "Atopic dermatitis (disorder)",
        "attributes": {"finding_site": "Skin structure", "icd10_map": "L20.9"},
    },
    9014002: {
        "fsn": "Psoriasis (disorder)",
        "attributes": {"finding_site": "Skin structure", "icd10_map": "L40.0"},
    },

    # ── Malignant neoplastic disease ───────────────────────────────────────
    363346000: {
        "fsn": "Malignant neoplastic disease (disorder)",
        "children": [363406005, 363358000, 254837009, 399068003],
    },
    363406005: {
        "fsn": "Malignant tumour of colon (disorder)",
        "attributes": {"finding_site": "Colon structure", "icd10_map": "C18.9"},
    },
    363358000: {
        "fsn": "Malignant tumour of lung (disorder)",
        "attributes": {"finding_site": "Lung structure", "icd10_map": "C34.90"},
    },
    254837009: {
        "fsn": "Malignant tumour of breast (disorder)",
        "attributes": {"finding_site": "Breast structure", "icd10_map": "C50.919"},
    },
    399068003: {
        "fsn": "Malignant tumour of prostate (disorder)",
        "attributes": {"finding_site": "Prostatic structure", "icd10_map": "C61"},
    },

    # ── Infectious disease ─────────────────────────────────────────────────
    40733004: {
        "fsn": "Infectious disease (disorder)",
        "children": [840539006, 91302008, 25374005],
    },
    840539006: {
        "fsn": "Disease caused by SARS-CoV-2 (COVID-19) (disorder)",
        "attributes": {"icd10_map": "U07.1"},
    },
    91302008: {
        "fsn": "Sepsis (disorder)",
        "attributes": {"icd10_map": "A41.9"},
    },
    25374005: {
        "fsn": "Gastroenteritis (disorder)",
        "attributes": {"finding_site": "Gastrointestinal tract structure", "icd10_map": "A09"},
    },

    # ── Mental disorder ────────────────────────────────────────────────────
    74732009: {
        "fsn": "Mental disorder (disorder)",
        "children": [35489007, 21897009, 58214004],
    },
    35489007: {
        "fsn": "Depressive disorder (disorder)",
        "attributes": {"icd10_map": "F32.9"},
    },
    21897009: {
        "fsn": "Generalized anxiety disorder (disorder)",
        "attributes": {"icd10_map": "F41.1"},
    },
    58214004: {
        "fsn": "Schizophrenia (disorder)",
        "attributes": {"icd10_map": "F20.9"},
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
