from backend.services.inventory.layer_consumption_service import consume_layers_fifo


def test_consume_layers_fifo_uses_oldest_layer_first():
    layers = [
        {"layer_id": 1, "remaining_qty": 10, "age_days": 20},
        {"layer_id": 2, "remaining_qty": 8, "age_days": 5},
    ]
    consumptions = consume_layers_fifo(layers=layers, requested_qty=12)

    assert consumptions[0]["layer_id"] == 1
    assert consumptions[0]["consumed_qty"] == 10
    assert consumptions[1]["layer_id"] == 2
    assert consumptions[1]["consumed_qty"] == 2
