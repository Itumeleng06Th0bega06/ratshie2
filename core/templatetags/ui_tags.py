"""UI template tags: page-scoped Django messages and toast mapping."""
from django import template

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