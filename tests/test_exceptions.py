from ws_api.exceptions import LoginFailedException, WSApiException


def test_wsapi_exception_init_and_str():
    response = {"error": "test_error"}
    exc = WSApiException("Test message", response=response)
    assert str(exc) == "Test message; Response: {'error': 'test_error'}"
    assert exc.response == response


def test_wsapi_exception_no_response():
    exc = WSApiException("Test message")
    assert str(exc) == "Test message; Response: None"
    assert exc.response is None


def test_login_failed_exception():
    response = {"error": "invalid_grant"}
    exc = LoginFailedException("Login failed", response=response)
    assert isinstance(exc, WSApiException)
    assert str(exc) == "Login failed; Response: {'error': 'invalid_grant'}"
