from modules.utils.login_status_detector import LoginStatus, LoginStatusDetector


def test_miaoshou_detector_treats_redirect_to_welcome_shell_as_logged_in():
    detector = LoginStatusDetector(platform="miaoshou", debug=False)

    result = detector._check_url(
        "https://erp.91miaoshou.com/?redirect=%2Fwelcome/welcome"
    )

    assert result.status == LoginStatus.LOGGED_IN
    assert result.confidence >= 0.85

