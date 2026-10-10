"""Print a summary of your Casa account.

    CASA_REFRESH_TOKEN=... uv run examples/bootstrap.py [--show-token]
    op run --env-file=.env -- uv run examples/bootstrap.py

Only calls the Firebase token endpoint and the VERIFIED bootstrap endpoint.
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys

from casahome import CasaApi, CasaError


async def main(show_token: bool) -> int:
    token = os.environ.get("CASA_REFRESH_TOKEN", "").strip()
    if not token:
        print("Set CASA_REFRESH_TOKEN", file=sys.stderr)
        return 2
    try:
        async with CasaApi.create(token) as api:
            me = await api.bootstrap()
            rotated = api.client.auth.refresh_token
    except CasaError as err:
        print(f"{type(err).__name__}: {err}", file=sys.stderr)
        return 1

    print(f"Hi {me.first_name}. {len(me.homes)} home(s).")
    for home in me.homes:
        print(f"  {home.id}: status={home.status} plan_state={home.plan_state}")
        if home.badge_counts:
            print(f"    badges: {home.badge_counts.features} (total {home.badge_counts.total})")
        if home.pending_agreements:
            names = ", ".join(a.name for a in home.pending_agreements)
            print(f"    pending agreements: {names}")
    if me.app_update:
        print(f"App update required: {me.app_update.force_update_required}")
    if show_token:
        changed = "rotated" if rotated != token else "unchanged"
        print(f"Refresh token ({changed}): {rotated}")
    elif rotated != token:
        print("Note: Firebase rotated the refresh token. Rerun with --show-token to see it.")
    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--show-token", action="store_true")
    sys.exit(asyncio.run(main(parser.parse_args().show_token)))
