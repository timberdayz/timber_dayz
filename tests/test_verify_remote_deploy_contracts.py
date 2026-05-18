from scripts.verify_remote_deploy_contracts import verify_remote_deploy_contracts


def test_remote_deploy_contracts_require_no_build_and_image_overrides():
    assert verify_remote_deploy_contracts() is True
