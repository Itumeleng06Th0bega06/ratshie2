"""System checks for Ratshie admin display configuration.

Registered under Django's default ``models`` tag, so ``manage.py check`` (and
CI) validates ``list_display``, ``list_display_links``, ``list_editable``,
``readonly_fields``, ``ordering``, ``search_fields`` and ``list_filter``
declarations across every registered ModelAdmin. Misconfiguration surfaces
here instead of as a 500 changelist on a live administrator's screen.
"""
from django.contrib import admin
from django.core import checks


def _strip_ordering_prefix(name):
    return name[1:] if isinstance(name, str) and name.startswith("-") else name


def _is_admin_method(admin_class, name):
    return callable(getattr(admin_class, name, None))


def _model_field(model, name):
    try:
        return model._meta.get_field(_strip_ordering_prefix(name))
    except Exception:
        return None


def _search_base(entry):
    return entry.split("__")[0] if isinstance(entry, str) else None


def _filter_base(entry):
    """Reduce a list_filter entry to the field name to validate."""
    if isinstance(entry, str):
        return entry.split("__")[0]
    if isinstance(entry, (list, tuple)) and entry:
        first = entry[0]
        return first.split("__")[0] if isinstance(first, str) else None
    return None


def _error(admin_class, label, name, model):
    return checks.Error(
        f"{admin_class.__name__}.{label} references '{name}', which is neither a "
        f"field on {model.__name__} nor a method/attribute on {admin_class.__name__}.",
        obj=admin_class,
        id="ratshie.admin.E001",
    )


def _display_reference_errors(model, admin_class):
    """Return check errors for one ModelAdmin declaration."""
    errors = []

    for label in ("list_display", "list_display_links"):
        for name in getattr(admin_class, label, ()) or ():
            if not (_is_admin_method(admin_class, name) or _model_field(model, name)):
                errors.append(_error(admin_class, label, name, model))

    # list_editable must reference editable MODEL fields, not admin methods.
    for name in getattr(admin_class, "list_editable", ()) or ():
        if not _model_field(model, name):
            errors.append(_error(admin_class, "list_editable", name, model))

    for name in getattr(admin_class, "readonly_fields", ()) or ():
        if not (_is_admin_method(admin_class, name) or _model_field(model, name)):
            errors.append(_error(admin_class, "readonly_fields", name, model))

    for name in getattr(admin_class, "ordering", ()) or ():
        if not _model_field(model, name):
            errors.append(_error(admin_class, "ordering", name, model))

    for entry in getattr(admin_class, "search_fields", ()) or ():
        base = _search_base(entry)
        if base and not _model_field(model, base):
            errors.append(_error(admin_class, "search_fields", entry, model))

    for entry in getattr(admin_class, "list_filter", ()) or ():
        base = _filter_base(entry)
        if base and not (_is_admin_method(admin_class, base) or _model_field(model, base)):
            errors.append(_error(admin_class, "list_filter", entry, model))

    return errors


@checks.register(checks.Tags.models)
def check_ratshie_admin_configuration(app_configs, **kwargs):
    """Validate every registered ModelAdmin's display/ordering declarations."""
    errors = []
    for model, admin_class in admin.site._registry.items():
        errors.extend(_display_reference_errors(model, admin_class))
    return errors