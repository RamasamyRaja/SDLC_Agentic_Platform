import sys
import unittest
from unittest.mock import patch
from pathlib import Path

WORKTREE = "/workspaces/_dev/59d1bbad-10d6-4ae2-b66f-ea2b262a54e8/a1"
sys.path.insert(0, WORKTREE)

from app import app, db, User, Product
from flask_jwt_extended import create_access_token


class CheckoutQuantityTests(unittest.TestCase):
    def setUp(self):
        app.config["TESTING"] = True
        with app.app_context():
            self.token = create_access_token(
                identity="checkout-test@example.com"
            )
        self.client = app.test_client()
        self.headers = {"Authorization": f"Bearer {self.token}"}

    def test_invalid_quantities_rejected_before_side_effects(self):
        invalid_values = [0, -1, "abc", "", None, 1.5, True]

        for quantity in invalid_values:
            with self.subTest(quantity=quantity):
                with patch("app.razorpay_client.order.create") as razorpay:
                    response = self.client.post(
                        "/api/payments/create_order",
                        json={"product_id": 1, "quantity": quantity},
                        headers=self.headers,
                    )

                self.assertEqual(response.status_code, 400)
                self.assertEqual(
                    response.json["error"],
                    "Quantity must be a positive integer",
                )
                razorpay.assert_not_called()

    def test_omitted_quantity_defaults_to_one(self):
        with patch.object(User, "query") as user_query, \
             patch.object(Product, "query") as product_query, \
             patch("app.razorpay_client.order.create",
                   return_value={"id": "test_order_123"}) as razorpay, \
             patch.object(db.session, "add") as db_add, \
             patch.object(db.session, "commit") as db_commit:

            user_query.filter_by.return_value.first.return_value = type(
                "TestUser", (), {"id": 1}
            )()
            product_query.get.return_value = type(
                "TestProduct", (), {"id": 1, "price": 100.0}
            )()

            response = self.client.post(
                "/api/payments/create_order",
                json={"product_id": 1},
                headers=self.headers,
            )

            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json["amount"], 100.0)
            self.assertEqual(response.json["order_id"], "test_order_123")
            self.assertEqual(db_add.call_args.args[0].quantity, 1)
            razorpay.assert_called_once()
            db_commit.assert_called_once()


if __name__ == "__main__":
    unittest.main(verbosity=2)
