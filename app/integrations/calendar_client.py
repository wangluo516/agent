import httpx
from pydantic import ValidationError

from app.integrations.errors import IntegrationError
from app.integrations.models import FreeBusyRequest, FreeBusyResponse


class CalendarClient:
    def __init__(self, client: httpx.AsyncClient) -> None:
        self._client = client

    async def freebusy(self, request: FreeBusyRequest) -> FreeBusyResponse:
        try:
            response = await self._client.post(
                "/mock/calendar/freebusy", json=request.model_dump(mode="json")
            )
            response.raise_for_status()
            return FreeBusyResponse.model_validate(response.json())
        except (httpx.HTTPError, ValidationError, ValueError) as error:
            raise IntegrationError("calendar integration returned an invalid response") from error
