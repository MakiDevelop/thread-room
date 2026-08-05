from pathlib import Path

import pytest

from thread_room.models import make_message
from thread_room.store import StoreError, ThreadStore, create_meeting, load_room_yaml


def test_create_and_append(tmp_path: Path):
    meeting = create_meeting(tmp_path, title="T", cwd=str(tmp_path))
    store = ThreadStore(meeting)
    room = store.load()
    assert room.title == "T"
    msg = make_message(
        room, speaker="human", kind="human", type="utterance", text="hi @mock"
    )
    store.append(msg)
    store2 = ThreadStore(meeting)
    room2 = store2.load()
    assert len(store2.messages) == 1
    assert store2.messages[0].text == "hi @mock"
    assert room2.id == room.id


def test_closed_rejects(tmp_path: Path):
    meeting = create_meeting(tmp_path, title="T", cwd=str(tmp_path))
    store = ThreadStore(meeting)
    room = store.load()
    store.append(
        make_message(
            room,
            speaker="system",
            kind="system",
            type="system",
            text="closed",
            meta={"event": "close"},
        )
    )
    with pytest.raises(StoreError):
        store.append(
            make_message(
                room, speaker="human", kind="human", type="utterance", text="nope"
            )
        )


def test_room_yaml_roundtrip(tmp_path: Path):
    meeting = create_meeting(
        tmp_path, title='Hi "there"', cwd=str(tmp_path), agents=[("a", "mock")]
    )
    room = load_room_yaml(meeting / "room.yaml")
    assert room.title == 'Hi "there"'
    assert room.speakers[1].id == "a"
