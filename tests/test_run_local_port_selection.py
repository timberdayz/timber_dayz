import run


def test_choose_local_backend_port_skips_ports_that_are_connectable(monkeypatch):
    def fake_can_bind(port, host="127.0.0.1"):
        return True

    def fake_is_port_in_use(port, host="127.0.0.1"):
        return port == 8001

    monkeypatch.setattr(run, "_can_bind_local_port", fake_can_bind)
    monkeypatch.setattr(run, "_is_port_in_use", fake_is_port_in_use)

    assert run._choose_local_backend_port(8001, [18001, 18011]) == 18001


def test_choose_local_backend_port_returns_none_when_all_candidates_unusable(monkeypatch):
    def fake_can_bind(port, host="127.0.0.1"):
        return True

    def fake_is_port_in_use(port, host="127.0.0.1"):
        return port in {8001, 18001}

    monkeypatch.setattr(run, "_can_bind_local_port", fake_can_bind)
    monkeypatch.setattr(run, "_is_port_in_use", fake_is_port_in_use)

    assert run._choose_local_backend_port(8001, [18001]) is None
