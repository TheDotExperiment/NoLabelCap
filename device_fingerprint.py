"""
Parses the request's User-Agent into the OS / device / browser fields we
store per signup. Uses the `user-agents` library if installed, otherwise
falls back to a small set of regexes so the app never hard-fails on this.
"""

import re

try:
    from user_agents import parse as ua_parse
    HAVE_UA_LIB = True
except ImportError:
    HAVE_UA_LIB = False


def fingerprint(user_agent_string: str) -> dict:
    ua_string = user_agent_string or ""

    if HAVE_UA_LIB:
        ua = ua_parse(ua_string)
        device_type = (
            "mobile" if ua.is_mobile else
            "tablet" if ua.is_tablet else
            "desktop/laptop" if ua.is_pc else
            "bot" if ua.is_bot else
            "other"
        )
        return {
            "os_type": ua.os.family or "unknown",
            "os_version": ua.os.version_string or "",
            "device_type": device_type,
            "device_brand": ua.device.brand or "",
            "browser": f"{ua.browser.family} {ua.browser.version_string}".strip(),
        }

    # --- fallback, no library ---
    os_type = "unknown"
    for pattern, name in [
        (r"iPhone|iPad|iPod", "iOS"),
        (r"Android", "Android"),
        (r"Windows NT", "Windows"),
        (r"Mac OS X", "macOS"),
        (r"Linux", "Linux"),
    ]:
        if re.search(pattern, ua_string, re.I):
            os_type = name
            break

    device_type = "mobile" if re.search(r"Mobi|Android", ua_string, re.I) else \
                  "tablet" if re.search(r"iPad|Tablet", ua_string, re.I) else \
                  "desktop/laptop"

    return {
        "os_type": os_type,
        "os_version": "",
        "device_type": device_type,
        "device_brand": "",
        "browser": "unknown",
    }
