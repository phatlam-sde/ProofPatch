from shipping import calculate_shipping


def test_case_0_total_50():
    assert calculate_shipping(50) == 0
