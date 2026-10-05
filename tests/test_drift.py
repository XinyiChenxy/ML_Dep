import pandas as pd
import pytest

from monitoring.drift import ALERT_THRESHOLD, compare, psi


def test_psi_is_zero_for_identical_windows():
    values = pd.Series(range(100), dtype=float).to_numpy()
    assert psi(values, values) == pytest.approx(0.0)


def test_injected_shift_crosses_justified_threshold():
    reference = pd.DataFrame({"temp_c": list(range(100))})
    current = pd.DataFrame({"temp_c": [value + 30 for value in range(100)]})
    result = compare(reference, current, ["temp_c"])[0]
    assert result.psi >= ALERT_THRESHOLD
    assert result.verdict == "significant"


def test_missing_feature_is_treated_as_pipeline_breakage():
    reference = pd.DataFrame({"temp_c": [1.0, 2.0]})
    with pytest.raises(ValueError, match="missing required features"):
        compare(reference, pd.DataFrame({"other": [1.0, 2.0]}), ["temp_c"])
