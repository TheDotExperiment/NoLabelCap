"""
Integration point with nodogsplash (the engine behind RaspAP's captive
portal plugin — often shorthanded "nosplashdog" / "nodogsplash").

This app is meant to run ON the Raspberry Pi itself, alongside RaspAP, so
instead of relying on nodogsplash's redirect-based FAS auth flow, we call
`ndsctl` directly as a local subprocess once a guest is verified (code
redeemed, or Stripe payment confirmed). That gives us one call that both
authorizes the client's MAC *and* sets its per-tier session length and
bandwidth caps.

IMPORTANT — verify before relying on this in production:
`ndsctl auth` syntax has changed across nodogsplash releases. Run
`ndsctl --help` and `man ndsctl` on your actual Pi image and confirm the
argument order below matches (sessionlength is minutes on recent builds;
older builds differ). Treat GRANT_CMD_TEMPLATE as the one line you may
need to adjust after checking your installed version.
"""

import subprocess
import logging

import config

logger = logging.getLogger("nds_client")


class GrantError(Exception):
    pass


def grant_access(mac_address: str, duration_minutes: int,
                  download_kbits: int, upload_kbits: int) -> bool:
    """
    Authorizes a client MAC on nodogsplash with a specific session length
    and rate limits. Returns True on success.

    If config.NDS_ENABLE_LIVE_GRANT is False (default), this is a no-op
    that just logs — useful for developing/testing the splash page and
    payment flow off-Pi before wiring it to the real router.
    """
    if not mac_address:
        raise GrantError("No client MAC address on this request — are you "
                          "testing off the actual router/LAN? nodogsplash "
                          "supplies clientmac as a query param on redirect.")

    if not config.NDS_ENABLE_LIVE_GRANT:
        logger.info(
            "[DRY RUN] would grant mac=%s minutes=%s down=%skbit up=%skbit",
            mac_address, duration_minutes, download_kbits, upload_kbits,
        )
        return True

    cmd = [
        "sudo", config.NDSCTL_PATH, "auth", mac_address,
        f"sessionlength={duration_minutes}",
        f"uploadrate={upload_kbits}",
        f"downloadrate={download_kbits}",
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
    except Exception as e:
        raise GrantError(f"Failed to invoke ndsctl: {e}") from e

    if result.returncode != 0:
        raise GrantError(
            f"ndsctl exited {result.returncode}: {result.stderr or result.stdout}"
        )
    return True
