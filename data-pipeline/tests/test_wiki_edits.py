import pytest

from producer.cursor import CursorStore
from producer.wiki_edits import publish_and_checkpoint


class FakeProducer:
    def __init__(self, error=None, remaining=0):
        self.error = error
        self.remaining = remaining
        self.callback = None

    def produce(self, topic, key, value, on_delivery):
        self.callback = on_delivery

    def flush(self, timeout):
        if self.callback is not None:
            self.callback(self.error, object())
        return self.remaining


def test_acknowledged_event_advances_cursor(tmp_path):
    path = tmp_path / "cursor.json"
    publish_and_checkpoint(
        FakeProducer(), topic="wiki.edits", key=b"k", value=b"v",
        event_id="event-7", cursor=CursorStore(path),
    )
    assert CursorStore(path).load() == "event-7"


@pytest.mark.parametrize(
    "producer",
    [FakeProducer(error=RuntimeError("delivery failed")), FakeProducer(remaining=1)],
)
def test_failed_delivery_does_not_advance_cursor(tmp_path, producer):
    path = tmp_path / "cursor.json"
    with pytest.raises(RuntimeError):
        publish_and_checkpoint(
            producer, topic="wiki.edits", key=b"k", value=b"v",
            event_id="event-7", cursor=CursorStore(path),
        )
    assert not path.exists()
