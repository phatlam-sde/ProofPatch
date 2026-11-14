from shipping import calculate_shipping


def test_case_0_total_49():
    assert calculate_shipping(49) == 5


def test_case_1_total_50():
    assert calculate_shipping(50) == 0


def test_case_2_total_51():
    assert calculate_shipping(51) == 0
