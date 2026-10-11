"""Photo metadata only. These models never fetch their URL strings."""

from pydantic import RootModel

from casahome.models._base import CasaModel


class RoomImageCandidate(CasaModel):
    id: str
    image_url: str
    cache_key: str
    is_current: bool


class RoomMemberImage(CasaModel):
    """UNVERIFIED populated member image. Static Codable fields."""

    image_url: str | None = None
    cache_key: str | None = None


class RoomImageOptionsResponse(CasaModel):
    matterport_images: list[RoomImageCandidate]
    member_image: RoomMemberImage | None = None


class MatterportImage(CasaModel):
    id: str
    image_url: str
    cache_key: str
    is_home_hero_image: bool


class MatterportImagesResponse(RootModel[list[MatterportImage]]):
    """Bare list of populated image metadata."""


class MediaAttachment(CasaModel):
    """Observed on to-dos. created_at is static and wasn't present there."""

    id: str
    name: str
    mimetype: str
    size: int
    url: str
    cache_key: str
    thumbnail_url: str | None = None
    created_at: int | None = None
