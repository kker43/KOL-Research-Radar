from kol_radar.normalization.subjects import normalize_subject


def test_nvda_aliases_normalize_to_same_key():
    assert normalize_subject("英伟达").key == "NVDA"
    assert normalize_subject("NVIDIA").key == "NVDA"
    assert normalize_subject("NVDA").key == "NVDA"


def test_unknown_subject_gets_stable_key():
    first = normalize_subject("某新主题")
    second = normalize_subject("某新主题")

    assert first.display_name == "某新主题"
    assert first.key
    assert first.key == second.key
