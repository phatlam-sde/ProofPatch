def calculate_shipping(total):
    discount = 10 if total >= 50 else 0
    subtotal = total - discount
    return 0 if subtotal >= 50 else 5
