import html
from typing import List, Sequence

from ...schemas.presentation import InfoField
from ...schemas.snapshot import ModRow
from ...utils.sizes import format_size
from ..theme import COLORS


def detail_html(item: ModRow) -> str:
    c = COLORS

    def text(value: str) -> str:
        return html.escape(s=value).replace("\n", "<br>")

    def heading(title: str) -> str:
        return (
            f'<p style="color:{c["accent"]}; font-size:9pt; font-weight:bold; margin-top:14px; margin-bottom:4px">'
            f"{html.escape(s=title.upper())}</p>"
        )

    def body(value: str) -> str:
        return f'<p style="margin-top:0; margin-bottom:6px">{text(value=value)}</p>'

    def bullets(title: str, values: Sequence[str], mark: str, color: str) -> str:
        if not values:
            return ""

        lines = "".join(
            f'<tr><td width="18" style="color:{color}">{mark}</td><td>{text(value=value)}</td></tr>' for value in values
        )

        return heading(title=title) + f'<table cellspacing="0" cellpadding="2">{lines}</table>'

    parts = []

    if item.tagline:
        parts.append(f'<p style="font-size:11pt; margin-top:0; margin-bottom:8px">{text(value=item.tagline)}</p>')

    if item.tags:
        chips = "&nbsp;&nbsp;".join(
            f'<span style="background-color:{c["panel"]}; font-size:9pt">&nbsp;{html.escape(s=tag)}&nbsp;</span>'
            for tag in item.tags
        )
        parts.append(f'<p style="margin-top:0; line-height:150%">{chips}</p>')

    info: List[InfoField] = [
        InfoField(key=key, value=value, color=None)
        for key, value in (
            ("Developer", item.developer),
            ("Released", item.release),
            ("Translated by", item.translator),
        )
        if value
    ]
    info.append(InfoField(key="Mod version", value=item.version or "-", color=None))
    info.append(
        InfoField(
            key="Game version",
            value=item.game_version or "Miss",
            color=None if item.game_version else c["miss"],
        ),
    )
    info.append(InfoField(key="Title ID", value=item.title_id, color=None))
    info.append(InfoField(key="Download size", value=format_size(value=item.size), color=None))
    rows = "".join(
        f'<tr><td width="128" style="color:{c["muted"]}">{html.escape(s=field.key)}</td>'
        f'<td style="color:{field.color or c["ink"]}">{text(value=field.value)}</td></tr>'
        for field in info
    )
    parts.append(heading(title="Info") + f'<table cellspacing="0" cellpadding="2">{rows}</table>')

    if item.description:
        parts.append(heading(title="About") + "".join(body(value=line) for line in item.description))

    if item.highlights:
        lines = []

        for entry in item.highlights:
            if entry.title:
                lines.append(
                    f'<p style="margin-top:0; margin-bottom:2px; font-weight:bold">{text(value=entry.title)}</p>',
                )

            if entry.text:
                lines.append(body(value=entry.text))

        parts.append(heading(title="Highlights") + "".join(lines))

    parts.append(bullets(title="Translated", values=item.done, mark="✓", color=c["ok"]))
    parts.append(bullets(title="Kept", values=item.kept, mark="–", color=c["muted"]))

    if item.changelog:
        parts.append(heading(title="Notes") + body(value=item.changelog))

    if item.credit:
        parts.append(heading(title="Credit") + body(value=item.credit))

    return f'<div style="color:{c["ink"]}">{"".join(parts)}</div>'
