"""Member referral code, ``/protected/member/referral_code/v2``.

The envelope and top-level ``referral_code`` keys were VERIFIED by a live
GET (2026-10). Display keys and referred-home item shapes aren't pinned, so
they stay ``JsonValue``. Unknown fields ride along in ``model_extra``.
"""

from pydantic import JsonValue

from casahome.models._base import CasaModel


class ReferralCode(CasaModel):
    code: str
    referral_url: str
    display: dict[str, JsonValue]
    referred_homes: list[JsonValue]


class ReferralCodeResponse(CasaModel):
    referral_code: ReferralCode
