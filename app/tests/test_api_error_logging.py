import asyncio
import logging
from io import StringIO

import pytest
from fastapi import Request, Response

from src.main import api_error_logger, log_unsuccessful_api_responses


@pytest.fixture
def captured_api_error_logs():
    original_handlers = list(api_error_logger.handlers)
    stream = StringIO()
    handler = logging.StreamHandler(stream)

    for original_handler in original_handlers:
        api_error_logger.removeHandler(original_handler)
    api_error_logger.addHandler(handler)

    yield stream

    api_error_logger.removeHandler(handler)
    for original_handler in original_handlers:
        api_error_logger.addHandler(original_handler)


def _request() -> Request:
    return Request(
        {
            "type": "http",
            "method": "GET",
            "path": "/logging-test",
            "headers": [],
            "client": ("testclient", 50000),
        }
    )


async def _response_with_status(_: Request, status_code: int) -> Response:
    return Response(status_code=status_code)


@pytest.mark.parametrize("status_code", [400, 401, 404, 422])
def test_does_not_log_client_errors(captured_api_error_logs: StringIO, status_code: int):
    asyncio.run(
        log_unsuccessful_api_responses(
            _request(),
            lambda request: _response_with_status(request, status_code),
        )
    )

    assert captured_api_error_logs.getvalue() == ""


@pytest.mark.parametrize("status_code", [500, 502, 503])
def test_logs_server_errors(captured_api_error_logs: StringIO, status_code: int):
    asyncio.run(
        log_unsuccessful_api_responses(
            _request(),
            lambda request: _response_with_status(request, status_code),
        )
    )

    log_output = captured_api_error_logs.getvalue()
    assert f"status={status_code}" in log_output
    assert "path=/logging-test" in log_output
