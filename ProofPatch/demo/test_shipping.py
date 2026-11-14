from shipping import calculate_shipping


def test_free_shipping_at_threshold():
    assert calculate_shipping(50) == 0
