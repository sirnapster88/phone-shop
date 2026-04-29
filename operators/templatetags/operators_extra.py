from django import template

register = template.Library()

@register.filter
def get_item(dictionary, key):
    """Получить значение из словаря по ключу"""
    try:
        return dictionary.get(key)
    except (AttributeError, KeyError):
        return None

@register.filter
def multiply(value, arg):
    """Умножение"""
    try:
        return float(value) * float(arg)
    except (ValueError, TypeError):
        return 0