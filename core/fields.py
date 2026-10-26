"""Reusable model fields for HackFlow."""

from django.db import models


class HTTPSURLField(models.URLField):
    """URLField whose generated forms default to ``https``.

    Django 5.2 warns when ``forms.URLField`` is instantiated without an explicit
    ``assume_scheme`` (the default changes to ``https`` in Django 6.0). Passing
    it here silences that warning without enabling the deprecated
    ``FORMS_URLFIELD_ASSUME_HTTPS`` transitional setting.

    ``deconstruct`` keeps migrations identical to a regular ``URLField``.
    """

    def formfield(self, **kwargs):
        kwargs.setdefault("assume_scheme", "https")
        return super().formfield(**kwargs)

    def deconstruct(self):
        name, path, args, kwargs = super().deconstruct()
        return name, "django.db.models.URLField", args, kwargs
