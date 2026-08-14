from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from app.domain.availability import find_common_free_slots

SHANGHAI = ZoneInfo("Asia/Shanghai")


def at(hour: int, minute: int = 0) -> datetime:
    return datetime(2026, 8, 20, hour, minute, tzinfo=SHANGHAI)


def test_common_free_slots_merge_overlaps_and_honor_requested_duration() -> None:
    slots = find_common_free_slots(
        {
            "alice": ((at(9), at(10)), (at(11), at(11, 30))),
            "bob": ((at(9, 30), at(10, 30)),),
        },
        at(9),
        at(12),
        duration_minutes=30,
    )

    assert slots == ((at(10, 30), at(11)), (at(11, 30), at(12)))


def test_common_free_slots_rejects_naive_and_invalid_intervals() -> None:
    with pytest.raises(ValueError, match="timezone"):
        find_common_free_slots({}, datetime(2026, 8, 20, 9), at(10), 30)  # noqa: DTZ001
    with pytest.raises(ValueError, match="positive"):
        find_common_free_slots({}, at(10), at(9), 30)
    with pytest.raises(ValueError, match="positive"):
        find_common_free_slots({}, at(9), at(10), 0)
