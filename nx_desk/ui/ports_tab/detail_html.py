import html
from typing import List

from ...catalog.ports import host_label, status_label, status_tone
from ...schemas.port import Port
from ...schemas.presentation import InfoField
from ..theme import COLORS
from .model import type_text


def detail_html(port: Port) -> str:
    c = COLORS
    status = status_label(status=port.status)
    info: List[InfoField] = [
        InfoField(key="Platform", value=port.platform, color=c["ink"]),
        InfoField(key="Type", value=type_text(port=port), color=c["ink"]),
        InfoField(key="Version", value=port.version or "-", color=c["ink"]),
        InfoField(key="Updated", value=port.updated or "-", color=c["ink"]),
        InfoField(key="Hosted on", value=host_label(host=port.host) or "-", color=c["ink"]),
        InfoField(key="Repository", value=port.id, color=c["ink"]),
    ]

    if status:
        info.append(InfoField(key="Status", value=status, color=c[status_tone(status=port.status)]))

    rows = "".join(
        f'<tr><td width="110" style="color:{c["muted"]}">{html.escape(s=field.key)}</td>'
        f'<td style="color:{field.color}">{html.escape(s=field.value)}</td></tr>'
        for field in info
    )
    heading = (
        f'<p style="color:{c["accent"]}; font-size:9pt; font-weight:bold; margin-top:4px; margin-bottom:4px">INFO</p>'
    )

    return f'<div style="color:{c["ink"]}">{heading}<table cellspacing="0" cellpadding="2">{rows}</table></div>'
