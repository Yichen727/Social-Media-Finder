from unittest.mock import Mock

import pytest

from finder.models import Query
from finder.search_engine import DDGSSearchEngine, classify_error


@pytest.mark.parametrize("exc,kind", [
    (TimeoutError("timed out"), "timeout"), (RuntimeError("RatelimitException: 429"), "rate_limit"),
    (RuntimeError("HTTP 500"), "http"), (ConnectionError("DNS resolve failed"), "network"),
    (RuntimeError("CAPTCHA 403"), "access"), (RuntimeError("TLS certificate error"), "tls"),
    (RuntimeError("unknown DDGSException"), "provider"),
    (RuntimeError("DNSError: request for https://search.example > DNS error"), "network"),
    (RuntimeError("HTTPError: Bad Gateway"), "http"),
])
def test_distinct_error_types(exc, kind):
    assert classify_error(exc).kind == kind


def engine_with_client(client):
    factory, sleep = Mock(return_value=client), Mock()
    return DDGSSearchEngine(client_factory=factory, sleep=sleep), factory, sleep


def test_timeout_retries_then_recovers_with_auto_backend():
    client = Mock()
    client.text.side_effect = [TimeoutError("timeout"), [{"title": "Name", "href": "https://x.com/name", "body": "Bio"}]]
    engine, factory, sleep = engine_with_client(client)
    result = engine.search(Query("Broad", "query"))
    assert result.error is None and result.attempts == 2
    assert result.hits[0].snippet == "Bio"
    assert factory.call_args.kwargs["timeout"] == 8
    assert client.text.call_args.kwargs["backend"] == "auto"
    assert client.text.call_args.kwargs["region"] == "us-en"
    sleep.assert_called_once_with(0.8)


def test_exhausted_timeout_is_failure_not_empty_success():
    client = Mock()
    client.text.side_effect = TimeoutError("timeout")
    engine, _, _ = engine_with_client(client)
    result = engine.search(Query("Broad", "query"))
    assert result.error.kind == "timeout"
    assert result.attempts == 2 and result.hits == []


def test_access_restriction_is_not_retried():
    client = Mock()
    client.text.side_effect = RuntimeError("403 CAPTCHA")
    engine, _, sleep = engine_with_client(client)
    result = engine.search(Query("Broad", "query"))
    assert result.error.kind == "access" and result.attempts == 1
    sleep.assert_not_called()


def test_empty_success_stays_success():
    engine, _, _ = engine_with_client(Mock(text=Mock(return_value=[])))
    result = engine.search(Query("Broad", "query"))
    assert result.error is None and result.hits == []


def test_ddgs_explicit_no_results_signal_is_empty_success_without_retry():
    from ddgs.exceptions import DDGSException
    client = Mock(text=Mock(side_effect=DDGSException("No results found.")))
    engine, _, sleep = engine_with_client(client)
    result = engine.search(Query("Broad", "query"))
    assert result.error is None and result.hits == []
    assert result.attempts == 1
    sleep.assert_not_called()


def test_no_results_words_inside_provider_error_are_not_masked():
    from ddgs.exceptions import DDGSException
    client = Mock(text=Mock(side_effect=DDGSException("HTTP 500: No results found.")))
    engine, _, _ = engine_with_client(client)
    result = engine.search(Query("Broad", "query"))
    assert result.error is not None and result.error.kind == "http"
