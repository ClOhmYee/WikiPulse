from producer.sse import SSEClient, SSEEvent


class Response:
    def iter_lines(self, decode_unicode=True):
        return iter(["id: event-7", 'data: {"wiki":"enwiki"}', ""])


def test_parser_returns_payload_with_event_id():
    client = SSEClient("https://example.invalid", user_agent="test")
    events = client._parse_frames(Response())
    assert next(events) == SSEEvent('{"wiki":"enwiki"}', "event-7")


def test_last_event_id_moves_only_after_caller_finishes_event():
    client = SSEClient("https://example.invalid", user_agent="test")
    events = client._parse_frames(Response())
    next(events)
    assert client.last_event_id is None
    list(events)
    assert client.last_event_id == "event-7"


def test_initial_cursor_is_sent_as_last_event_id_header():
    client = SSEClient(
        "https://example.invalid",
        user_agent="test",
        last_event_id="event-6",
    )
    assert client._headers()["Last-Event-ID"] == "event-6"
