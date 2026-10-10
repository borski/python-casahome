"""Constants observed in Casa iOS app traffic and bundle metadata."""

from __future__ import annotations

FOUNDATION_BASE_URL = "https://foundation.platform.casa"
UTILITY_CONNECT_BASE_URL = "https://utility-connect.platform.casa"  # not used in v0.1

# Firebase project the app authenticates against. The API key is a public client
# identifier shipped inside the iOS bundle (GoogleService-Info.plist), not a secret.
FIREBASE_API_KEY = "AIzaSyA4XygCbi-oW1M8lP5z51NSX19O2AX2j14"
FIREBASE_PROJECT_ID = "casa-technologies-inc"
FIREBASE_GMP_ID = "1:312296672090:ios:5a8ecec7caa297a05b4163"
FIREBASE_BUNDLE_ID = "casa-technologies.member-ios"
FIREBASE_CLIENT_VERSION = "iOS/FirebaseSDK/12.18.0/FirebaseCore-iOS"
SECURETOKEN_URL = "https://securetoken.googleapis.com/v1/token"

# App identity headers the Casa backend expects.
CASA_APP = "member-ios"
# The bootstrap body spells it with an underscore. Header uses a dash. Both VERIFIED.
CASA_DEVICE_APP = "member_ios"
CASA_APP_VERSION = "698"
APP_MARKETING_VERSION = "2026.38.2"
USER_AGENT = (
    f"Casa/{APP_MARKETING_VERSION} ({FIREBASE_BUNDLE_ID}; build:{CASA_APP_VERSION}; "
    "iOS 27.0.0) Alamofire/5.12.0"
)

TOKEN_REFRESH_LEEWAY_SECONDS = 120
DEFAULT_TIMEOUT_SECONDS = 30
