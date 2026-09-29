from django.http import QueryDict

from django import template

register = template.Library()


@register.simple_tag(takes_context=True)
def query_string(context, **kwargs):
    """Preserva los parámetros GET actuales y sobrescribe los pasados."""
    request = context["request"]
    query = request.GET.copy()
    for key, value in kwargs.items():
        if value is None:
            query.pop(key, None)
        else:
            query[key] = value
    return query.urlencode()
