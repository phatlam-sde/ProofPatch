from checkout import checkout_total


def test_free_shipping_after_discount():
    assert checkout_total(60) == 50
