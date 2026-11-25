"""Shared helpers for text written by another person or their assistant."""
import re

_CONTROL = re.compile('[\x00-\x08\x0b-\x1f\x7f​-‏ -‮⁦-⁩]')
ID_PATTERN = re.compile(r'[A-Za-z0-9_-]{1,64}')


class CardError(Exception):
    """A request the mission card refuses. The message is safe to show to a model."""


def need(condition, message):
    if not condition:
        raise CardError(message)


def ident(value, what='identifier'):
    need(type(value) is str and ID_PATTERN.fullmatch(value) is not None, f'Invalid {what}')
    return value


def bounded(value, limit, what='text'):
    need(type(value) is str and value.strip() != '' and len(value.encode('utf-8')) <= limit,
         f'{what} must be non-empty and at most {limit} bytes')
    return value


def clean(value):
    """Remove control and direction-override characters before display."""
    return _CONTROL.sub('', value)
