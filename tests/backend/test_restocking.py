"""
Tests for restocking recommendation and order endpoints.
"""
import pytest


@pytest.fixture(autouse=True)
def isolate_restocking_storage(tmp_path, monkeypatch):
    """Redirect restocking order persistence to a throwaway file for every test."""
    import restocking_store
    import main

    test_file = tmp_path / "restocking_orders.json"
    monkeypatch.setattr(restocking_store, "RESTOCKING_ORDERS_FILE", test_file)
    monkeypatch.setattr(main, "restocking_orders", [])
    yield


class TestRestockRecommendations:
    """Test suite for the restock recommendations endpoint."""

    def test_only_understocked_items_recommended(self, client):
        """Even with a huge budget, only items at/below reorder_point are recommended."""
        response = client.get("/api/restocking/recommendations?budget=1000000")
        assert response.status_code == 200

        data = response.json()
        skus = {item["sku"] for item in data["items"]}
        # Known understocked SKUs in the seed data (quantity_on_hand <= reorder_point)
        assert skus.issubset({"TMP-201", "SRV-301", "SRV-302", "PSU-508"})
        assert len(data["items"]) > 0

    def test_zero_budget_returns_no_items(self, client):
        """A budget of 0 can't afford any restock, so items should be empty."""
        response = client.get("/api/restocking/recommendations?budget=0")
        assert response.status_code == 200

        data = response.json()
        assert data["items"] == []
        assert data["total_cost"] == 0
        assert data["remaining_budget"] == 0

    def test_missing_budget_is_required(self, client):
        """Budget is a required query param."""
        response = client.get("/api/restocking/recommendations")
        assert response.status_code == 422

    def test_items_sorted_by_urgency_descending(self, client):
        """Recommended items should be ordered by urgency_score, highest first."""
        response = client.get("/api/restocking/recommendations?budget=1000000")
        data = response.json()

        scores = [item["urgency_score"] for item in data["items"]]
        assert scores == sorted(scores, reverse=True)

    def test_budget_caps_recommendations(self, client):
        """total_cost should never exceed the given budget."""
        response = client.get("/api/restocking/recommendations?budget=500")
        data = response.json()

        assert data["total_cost"] <= 500
        assert data["remaining_budget"] == round(500 - data["total_cost"], 2)
        for item in data["items"]:
            assert item["restock_cost"] > 0
            assert item["restock_quantity"] > 0

    def test_warehouse_filter_narrows_candidates(self, client):
        """Filtering by warehouse should only recommend items from that warehouse."""
        response = client.get("/api/restocking/recommendations?budget=1000000&warehouse=Tokyo")
        assert response.status_code == 200

        data = response.json()
        for item in data["items"]:
            assert item["warehouse"] == "Tokyo"

    def test_category_filter_narrows_candidates(self, client):
        """Filtering by category should only recommend items from that category."""
        response = client.get("/api/restocking/recommendations?budget=1000000&category=Actuators")
        assert response.status_code == 200

        data = response.json()
        for item in data["items"]:
            assert item["category"].lower() == "actuators"


class TestRestockingOrderSubmission:
    """Test suite for creating and retrieving restocking orders."""

    def _sample_items(self):
        return [
            {
                "sku": "SRV-301",
                "name": "Micro Servo Motor",
                "category": "Actuators",
                "warehouse": "Tokyo",
                "quantity": 20,
                "unit_cost": 445.0
            }
        ]

    def test_create_restocking_order_happy_path(self, client):
        """Submitting a valid order returns 201 with lead time and delivery date."""
        payload = {"budget": 10000, "items": self._sample_items()}
        response = client.post("/api/restocking/orders", json=payload)
        assert response.status_code == 201

        order = response.json()
        assert order["order_number"].startswith("RST-")
        assert 5 <= order["lead_time_days"] <= 15
        assert order["status"] == "Processing"
        assert order["total_cost"] == pytest.approx(20 * 445.0)

        from datetime import datetime
        order_date = datetime.fromisoformat(order["order_date"])
        expected_delivery = datetime.fromisoformat(order["expected_delivery"])
        assert (expected_delivery - order_date).days == order["lead_time_days"]

    def test_create_restocking_order_rejects_empty_items(self, client):
        """An order with no items should be rejected."""
        payload = {"budget": 10000, "items": []}
        response = client.post("/api/restocking/orders", json=payload)
        assert response.status_code == 400

    def test_get_restocking_orders_returns_created_order(self, client):
        """Submitted orders should be retrievable, most recent first."""
        client.post("/api/restocking/orders", json={"budget": 5000, "items": self._sample_items()})
        client.post("/api/restocking/orders", json={"budget": 8000, "items": self._sample_items()})

        response = client.get("/api/restocking/orders")
        assert response.status_code == 200

        orders = response.json()
        assert len(orders) == 2
        # Most recent first: second-created order's order_date >= first's
        assert orders[0]["order_date"] >= orders[1]["order_date"]

    def test_restocking_order_persists_to_disk(self, client):
        """A submitted order should be written to the (monkeypatched) storage file."""
        import restocking_store

        client.post("/api/restocking/orders", json={"budget": 5000, "items": self._sample_items()})

        persisted = restocking_store.read_all()
        assert len(persisted) == 1
        assert persisted[0]["items"][0]["sku"] == "SRV-301"
