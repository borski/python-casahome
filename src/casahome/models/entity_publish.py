"""Narrow inventory publish contract observed in app traffic.

Only a model name with empty props is accepted. Make selection, model IDs,
editable properties and clear semantics haven't been observed on this route.
"""

from pydantic import Field

from casahome.models._base import CasaModel
from casahome.models.home import EntityIdentity, EntityMake, EntityModel
from casahome.models.write_contracts import UpdateEntityProperty, _WriteModel, _WriteText


class EntityModelName(_WriteModel):
    """Observed name-only model input. No make, catalog ID or clear variant."""

    name: _WriteText


class SaveAndPublishEntityRequest(_WriteModel):
    """Only model.name and an explicitly empty props list are supported.

    The property codec is static and UNVERIFIED on this route. Nonempty props
    are rejected rather than expanding the observed contract.
    """

    model: EntityModelName
    props: list[UpdateEntityProperty] = Field(max_length=0)


class SaveAndPublishEntityResponse(CasaModel):
    """VERIFIED populated response. Status seen as published, identity as verified.

    Existing catalog/identity models preserve unknown response fields. Populated
    identity candidates and other status values remain UNVERIFIED.
    """

    entity_id: str
    status: str
    make: EntityMake
    model: EntityModel
    identity: EntityIdentity
