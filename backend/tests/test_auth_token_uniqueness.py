from backend.services.auth_service import auth_service


def test_create_token_pair_generates_unique_tokens_for_same_user():
    pair1 = auth_service.create_token_pair(
        user_id=285,
        username="perf_load_admin",
        roles=["admin"],
    )
    pair2 = auth_service.create_token_pair(
        user_id=285,
        username="perf_load_admin",
        roles=["admin"],
    )

    assert pair1["access_token"] != pair2["access_token"]
    assert pair1["refresh_token"] != pair2["refresh_token"]
