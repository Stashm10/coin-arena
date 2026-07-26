from arena.features import FEATURE_NAMES, extract_features


def _scan(**overrides):
    findings = [
        {"check": "authorities", "severity": "PASS", "evidence": "",
         "data": {"mint_authority": False, "freeze_authority": False}},
        {"check": "holders", "severity": "WARNING", "evidence": "",
         "data": {"top10_share": 0.42, "max_single": 0.18, "owners": []}},
        {"check": "bundles", "severity": "DISQUALIFIER", "evidence": "",
         "data": {"max_buyers_one_slot": 9, "launch_buyers": 14}},
        {"check": "dev_record", "severity": "WARNING", "evidence": "",
         "data": {"prior_launches": 4, "creator": "Dev"}},
        {"check": "funding", "severity": "DISQUALIFIER", "evidence": "",
         "data": {"funder": "F"}},
        {"check": "vitals", "severity": "INFO", "evidence": "",
         "data": {"age_s": 300, "holder_count": 120, "liquidity_usd": 5000.0}},
    ]
    return findings


def test_feature_names_length_is_11():
    assert len(FEATURE_NAMES) == 11
    assert FEATURE_NAMES[0] == "mint_authority"
    assert FEATURE_NAMES[-1] == "liquidity_usd"


def test_extract_full_vector():
    v = extract_features(_scan())
    assert v == [0.0, 0.0, 0.42, 0.18, 9.0, 14.0, 4.0, 1.0, 300.0, 120.0, 5000.0]


def test_authority_active_is_one():
    f = _scan()
    f[0]["data"] = {"mint_authority": "SomeKey", "freeze_authority": None}
    v = extract_features(f)
    assert v[0] == 1.0 and v[1] == 0.0


def test_funding_non_disqualifier_is_zero():
    f = _scan()
    f[4] = {"check": "funding", "severity": "PASS", "evidence": "", "data": {"funder": "F"}}
    assert extract_features(f)[7] == 0.0


def test_missing_finding_and_keys_impute_zero():
    v = extract_features([{"check": "authorities", "severity": "PASS",
                           "evidence": "", "data": {}}])
    assert v == [0.0] * 11


def test_malformed_input_never_raises():
    assert extract_features([]) == [0.0] * 11
    assert extract_features([None, 42, "x", {"check": "holders"}]) == [0.0] * 11
    assert extract_features(None) == [0.0] * 11
