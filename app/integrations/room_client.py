from datetime import datetime

import httpx
from pydantic import ValidationError

from app.domain.room_ranking import RankedRoom
from app.integrations.errors import IntegrationError
from app.integrations.models import RoomSearchRequest, RoomSearchResponse


class RoomClient:
    def __init__(self, client: httpx.AsyncClient) -> None:
        self._client = client

    async def search(
        self,
        topic: str,
        attendee_count: int,
        required_features: tuple[str, ...],
        start_at: datetime,
        end_at: datetime,
    ) -> tuple[RankedRoom, ...]:
        request = RoomSearchRequest(
            topic=topic,
            attendee_count=attendee_count,
            required_features=required_features,
            start_at=start_at,
            end_at=end_at,
        )
        try:
            response = await self._client.post(
                "/mock/rooms/search", json=request.model_dump(mode="json")
            )
            response.raise_for_status()
            return RoomSearchResponse.model_validate(response.json()).rooms
        except (httpx.HTTPError, ValidationError, ValueError) as error:
            raise IntegrationError("room integration returned an invalid response") from error
