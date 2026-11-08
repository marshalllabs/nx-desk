import html

from ...catalog.ports import host_label, status_label, status_tone
from ...schemas.port import Port
from ..theme import COLORS
from .model import type_text


def detail_html(port: Port) -> str:
    c = COLORS
    status = status_label(status=port.status)
    info: list[tuple[str, str, str]] = [
        ("Platform", port.platform, c["ink"]),
        ("Type", type_text(port=port), c["ink"]),
        ("Version", port.version or "-", c["ink"]),
        ("Updated", port.updated or "-", c["ink"]),
        ("Hosted on", host_label(host=port.host) or "-", c["ink"]),
        ("Repository", port.id, c["ink"]),
    ]

    if status:
        info.append(("Status", status, c[status_tone(status=port.status)]))

    rows = "".join(
        f'<tr><td width="110" style="color:{c["muted"]}">{html.escape(s=key)}</td>'
        f'<td style="color:{color}">{html.escape(s=value)}</td></tr>'
        for key, value, color in info
    )
    heading = (
        f'<p style="color:{c["accent"]}; font-size:9pt; font-weight:bold; margin-top:4px; margin-bottom:4px">INFO</p>'
    )

    return f'<div style="color:{c["ink"]}">{heading}<table cellspacing="0" cellpadding="2">{rows}</table></div>'
