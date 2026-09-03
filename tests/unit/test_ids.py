import uuid

from retpack_core.ids import new_id


def test_new_id_is_uuid_v7():
    value = new_id()
    parsed = uuid.UUID(value)
    assert parsed.version == 7
    assert len(value) == 36


def test_ids_are_time_ordered():
    ids = [new_id() for _ in range(500)]
    assert ids == sorted(ids)
    assert len(set(ids)) == 500
