"""Home feed cards, ``/protected/home/{home_id}/feed``.

VERIFIED by a live GET (2026-10) with ``app_build=698``: an envelope
``cards`` holding populated items. Every card had the keys modeled below.
``props`` varies by ``template_id`` (titles, captions, actions, images,
colors, ``visual_*`` styling, onboarding counts), so it stays a JSON dict.
``children`` was empty on every observed card. It's typed recursively on the
assumption children are cards too, which is UNVERIFIED. Unknown fields ride
along in ``model_extra``.
"""

from __future__ import annotations

from pydantic import Field, JsonValue

from casahome.models._base import CasaModel


class HomeFeedCard(CasaModel):
    id: str
    template_id: str
    name: str
    props: dict[str, JsonValue] = Field(default_factory=dict)
    show_starts_at_minutes_after_onboarding: int
    show_ends_at_minutes_after_onboarding: int | None = None
    children: list[HomeFeedCard] = Field(default_factory=list)


class HomeFeedResponse(CasaModel):
    cards: list[HomeFeedCard]
