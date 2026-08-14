from datetime import datetime
from zoneinfo import ZoneInfo

from app.domain.room_ranking import Room, RoomBusyInterval, rank_rooms

SHANGHAI = ZoneInfo("Asia/Shanghai")


def test_rank_rooms_filters_hard_requirements_and_is_deterministic() -> None:
    rooms = (
        Room(
            id="zeta",
            name="Zeta",
            capacity=8,
            features=("display", "whiteboard"),
            topics=("design",),
        ),
        Room(id="alpha", name="Alpha", capacity=6, features=("display",), topics=("design",)),
        Room(id="small", name="Small", capacity=3, features=("display",), topics=("design",)),
        Room(
            id="missing", name="Missing", capacity=10, features=("whiteboard",), topics=("design",)
        ),
    )

    ranked = rank_rooms(
        rooms,
        topic="design review",
        attendee_count=4,
        required_features=("display",),
        start_at=datetime(2026, 8, 20, 9, tzinfo=SHANGHAI),
        end_at=datetime(2026, 8, 20, 10, tzinfo=SHANGHAI),
    )

    assert [item.room.id for item in ranked] == ["alpha", "zeta"]
    assert ranked[0].score == 102
    assert ranked[0].reason == "matches topic 'design'; 2 spare seats; has display"


def test_rank_rooms_rejects_invalid_attendee_count() -> None:
    try:
        rank_rooms(
            (),
            topic="design",
            attendee_count=0,
            required_features=(),
            start_at=datetime(2026, 8, 20, 9, tzinfo=SHANGHAI),
            end_at=datetime(2026, 8, 20, 10, tzinfo=SHANGHAI),
        )
    except ValueError as error:
        assert str(error) == "attendee_count must be positive"
    else:
        raise AssertionError("expected ValueError")


def test_rank_rooms_excludes_busy_highest_scoring_room_before_ranking() -> None:
    rooms = (
        Room(
            id="busy-best",
            name="Busy Best",
            capacity=4,
            features=("display",),
            topics=("design",),
            busy_intervals=(
                RoomBusyInterval(
                    start_at=datetime(2026, 8, 20, 10, tzinfo=SHANGHAI),
                    end_at=datetime(2026, 8, 20, 11, tzinfo=SHANGHAI),
                ),
            ),
        ),
        Room(
            id="available", name="Available", capacity=6, features=("display",), topics=("design",)
        ),
    )

    ranked = rank_rooms(
        rooms,
        topic="design review",
        attendee_count=4,
        required_features=("display",),
        start_at=datetime(2026, 8, 20, 10, 30, tzinfo=SHANGHAI),
        end_at=datetime(2026, 8, 20, 11, 30, tzinfo=SHANGHAI),
    )

    assert [item.room.id for item in ranked] == ["available"]
