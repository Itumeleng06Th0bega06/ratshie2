"""UI template tags: page-scoped Django messages and toast mapping."""
from django import template
from django.utils.html import escape
from django.utils.safestring import mark_safe

register = template.Library()

_SCOPE_PREFIX = "scope:"


@register.filter
def render_messages(messages, request):
    """Return only messages that belong to this page.

    Messages may carry a ``scope:<url_name>`` extra tag. Untagged messages
    render everywhere; scoped messages render only when the current resolver
    url_name matches, so an action's feedback never leaks onto unrelated pages.
    """
    url_name = None
    try:
        if request and getattr(request, "resolver_match", None):
            url_name = request.resolver_match.url_name
    except Exception:
        url_name = None

    out = []
    for message in messages or []:
        scoped_to = None
        for tag in (message.extra_tags or "").split():
            if tag.startswith(_SCOPE_PREFIX):
                scoped_to = tag[len(_SCOPE_PREFIX):]
                break
        if scoped_to and scoped_to != url_name:
            continue
        out.append(message)
    return out


_KIND_MAP = {
    "success": "success",
    "info": "info",
    "warning": "warning",
    "warn": "warning",
    "error": "error",
    "debug": "info",
}


@register.filter
def toast_kind(level_tag):
    return _KIND_MAP.get(str(level_tag or "").lower(), "info")


_ICON_MAP = {"success": "i-check", "error": "i-alert", "warning": "i-bell", "info": "i-info"}


@register.filter
def toast_icon(level_tag):
    kind = _KIND_MAP.get(str(level_tag or "").lower(), "info")
    return _ICON_MAP.get(kind, "i-info")


@register.filter(name="label_cells")
def label_cells(row, headers):
    """Tag every changelist cell with its column label (``data-label``).

    Django builds each cell as an HTML string, so the column header is the
    only place a label can come from. CSS reads it back with
    ``::before { content: attr(data-label) }`` to turn table rows into
    stacked label/value cards on narrow screens.
    """
    headers = list(headers or [])
    out = []
    for index, cell in enumerate(row):
        label = ""
        if index < len(headers):
            header = headers[index]
            if isinstance(header, dict):
                text = header.get("text", "")
            else:
                text = getattr(header, "text", "")
            text = str(text)
            # Headers that already carry markup (the select-all checkbox)
            # have no readable label to reuse.
            if text and "<" not in text:
                label = escape(text)
        if label and isinstance(cell, str):
            if cell.startswith("<td"):
                cell = mark_safe('<td data-label="%s"%s' % (label, cell[3:]))
            elif cell.startswith("<th"):
                cell = mark_safe('<th data-label="%s"%s' % (label, cell[3:]))
        out.append(cell)
    return out