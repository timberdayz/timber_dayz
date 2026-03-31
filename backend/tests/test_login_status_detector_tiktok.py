from modules.utils.login_status_detector import LoginStatus, LoginStatusDetector


def test_tiktok_login_detector_does_not_treat_root_login_domain_as_logged_in() -> None:
    detector = LoginStatusDetector(platform="tiktok", debug=False)

    result = detector._check_url("https://seller.tiktokglobalshop.com")

    assert result.status is not LoginStatus.LOGGED_IN


def test_tiktok_login_detector_treats_account_login_url_as_not_logged_in() -> None:
    detector = LoginStatusDetector(platform="tiktok", debug=False)

    result = detector._check_url("https://seller.tiktokshopglobalselling.com/account/login")

    assert result.status is LoginStatus.NOT_LOGGED_IN


def test_tiktok_login_detector_treats_homepage_as_logged_in() -> None:
    detector = LoginStatusDetector(platform="tiktok", debug=False)

    result = detector._check_url("https://seller.tiktokshopglobalselling.com/homepage?shop_region=SG")

    assert result.status is LoginStatus.LOGGED_IN
