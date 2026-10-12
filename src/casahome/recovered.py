"""Opt-in offline reconstructions. No Casa backend validation or MCP exposure."""

from __future__ import annotations

from collections.abc import Sequence

from casahome._common import _parse, _write_home, _write_id, unverified
from casahome.client import CasaClient
from casahome.models.documents import SavedResponse
from casahome.models.recovered_contracts import (
    DismissDocumentStructureSuggestionBody,
    HomeDocumentDeleteResponse,
    RetailerDiscountsResponse,
    SupportRequestBody,
    SupportRequestResponse,
    TransferToConciergeResponse,
    UpdateRequestDetailBody,
    UpdateRequestDetailResponse,
    UpdateRoomPropertiesBody,
    UpdateStoryBody,
    UpdateTaskResponse,
    UpdateTaskScalarBody,
    VisitConversationReadResponse,
)
from casahome.models.write_contracts import BasicMessageResponse, _write_payload
from casahome.writes import _body, _sequence


class RecoveredContractsMixin:
    """Independently callable SDK contracts, each write sent exactly once."""

    client: CasaClient

    @unverified
    async def update_request_detail(
        self, home_id: str, request_id: str, body: UpdateRequestDetailBody
    ) -> UpdateRequestDetailResponse:
        """PATCH optional title/read_state. No clear and no empty PATCH.

        Returns the direct six-field result, not the GET thread envelope.
        """
        path = f"{_write_home(home_id)}/requests/{_write_id(request_id)}"
        payload = _write_payload(body, UpdateRequestDetailBody)
        return _parse(UpdateRequestDetailResponse, await self.client.patch(path, json=payload))

    @unverified
    async def dismiss_document_structure_suggestion(
        self, home_id: str, document_id: str, suggestion_id: str, expected_values: Sequence[str]
    ) -> SavedResponse:
        """POST dismissed and the required, caller-supplied expected_values guard.

        Doesn't refetch, resolve conflicts, retry or change legacy acceptance.
        """
        path = (
            f"{_write_home(home_id)}/documents/{_write_id(document_id)}"
            f"/structure_suggestions/{_write_id(suggestion_id)}/respond"
        )
        payload = _body(
            DismissDocumentStructureSuggestionBody,
            {"expected_values": _sequence(expected_values, "expected_values")},
            exclude_none=True,
        )
        return _parse(SavedResponse, await self.client.post(path, json=payload))

    @unverified
    async def update_task(
        self, home_id: str, task_id: str, body: UpdateTaskScalarBody
    ) -> UpdateTaskResponse:
        """PATCH scalar edits only. Nested response variants remain provisional."""
        path = f"{_write_home(home_id)}/tasks/{_write_id(task_id)}"
        payload = _write_payload(body, UpdateTaskScalarBody)
        return _parse(UpdateTaskResponse, await self.client.patch(path, json=payload))

    @unverified
    async def delete_task(self, home_id: str, task_id: str) -> BasicMessageResponse:
        """Bodyless DELETE. Message text alone doesn't prove deletion."""
        path = f"{_write_home(home_id)}/tasks/{_write_id(task_id)}"
        return _parse(BasicMessageResponse, await self.client.delete(path))

    @unverified
    async def transfer_task_to_concierge(
        self, home_id: str, task_id: str
    ) -> TransferToConciergeResponse:
        """Bodyless POST, no implicit target or deduplication assumption."""
        path = f"{_write_home(home_id)}/tasks/{_write_id(task_id)}/transfer_to_concierge"
        return _parse(TransferToConciergeResponse, await self.client.post(path))

    @unverified
    async def delete_document(self, home_id: str, document_id: str) -> HomeDocumentDeleteResponse:
        """Bodyless DELETE. Preserve deleted=false on HTTP success."""
        path = f"{_write_home(home_id)}/documents/{_write_id(document_id)}"
        return _parse(HomeDocumentDeleteResponse, await self.client.delete(path))

    @unverified
    async def update_room_properties(
        self, home_id: str, room_id: str, body: UpdateRoomPropertiesBody
    ) -> BasicMessageResponse:
        """PATCH required props array, omitting absent values. No clear semantics."""
        path = f"{_write_home(home_id, member=True)}/room/{_write_id(room_id)}/props"
        payload = _write_payload(body, UpdateRoomPropertiesBody)
        return _parse(BasicMessageResponse, await self.client.patch(path, json=payload))

    @unverified
    async def update_story(
        self, home_id: str, story_id: str, body: UpdateStoryBody
    ) -> BasicMessageResponse:
        """PATCH optional name/floor number; absent fields omitted, no clear."""
        path = f"{_write_home(home_id, member=True)}/story/{_write_id(story_id)}"
        payload = _write_payload(body, UpdateStoryBody)
        return _parse(BasicMessageResponse, await self.client.patch(path, json=payload))

    @unverified
    async def retailer_discounts(self, home_id: str) -> RetailerDiscountsResponse:
        """GET discount metadata only. Doesn't fetch image or website URLs."""
        path = f"{_write_home(home_id)}/retailer_discounts"
        return _parse(RetailerDiscountsResponse, await self.client.get(path))

    @unverified
    async def create_support_request(
        self, home_id: str, body: SupportRequestBody
    ) -> SupportRequestResponse:
        """Text-only POST may contact a human. No attachments or auto-dispatch logic."""
        path = f"{_write_home(home_id)}/support_requests"
        payload = _write_payload(body, SupportRequestBody)
        return _parse(SupportRequestResponse, await self.client.post(path, json=payload))

    @unverified
    async def mark_vendor_visit_conversation_read(
        self, home_id: str, visit_id: str
    ) -> VisitConversationReadResponse:
        """Bodyless PATCH. Preserve ok=false on HTTP success."""
        path = f"{_write_home(home_id)}/vendor_visits/{_write_id(visit_id)}/conversation/read"
        return _parse(VisitConversationReadResponse, await self.client.patch(path))
