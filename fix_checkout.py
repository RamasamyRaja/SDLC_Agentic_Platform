from pathlib import Path

p = Path("/workspaces/_dev/59d1bbad-10d6-4ae2-b66f-ea2b262a54e8/a1/app.py")
s = p.read_text()

old = """    data = request.json
    product_id = data.get('product_id')
    quantity = quantity = int(data.get('quantity', 1))"""

new = """    data = request.get_json(silent=True) or {}
    product_id = data.get('product_id')
    raw_quantity = data.get('quantity', 1)

    if isinstance(raw_quantity, bool) or not isinstance(raw_quantity, (int, str)):
        return jsonify({'error': 'Quantity must be a positive integer'}), 400

    if isinstance(raw_quantity, str) and not raw_quantity.strip().isdigit():
        return jsonify({'error': 'Quantity must be a positive integer'}), 400

    quantity = int(raw_quantity)
    if quantity <= 0:
        return jsonify({'error': 'Quantity must be a positive integer'}), 400"""

assert old in s, "Expected code not found; no changes made"
p.write_text(s.replace(old, new, 1))
print("Checkout quantity validation updated")
