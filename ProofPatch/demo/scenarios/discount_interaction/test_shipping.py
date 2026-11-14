from shipping import calculate_shipping


def test_case_0_total_0():
    assert calculate_shipping(0) == 5


def test_case_1_total_49():
    assert calculate_shipping(49) == 5


def test_case_2_total_50():
    assert calculate_shipping(50) == 0


def test_case_3_total_59():
    assert calculate_shipping(59) == 0


def test_case_4_total_60():
    assert calculate_shipping(60) == 0


def test_case_5_total_61():
    assert calculate_shipping(61) == 0
