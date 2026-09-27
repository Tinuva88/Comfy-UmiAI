"""Small extension hooks used by optional prompt-engine overlays."""

_ANIMA_EXTENSION = None


def register_anima_extension(extension):
    global _ANIMA_EXTENSION
    _ANIMA_EXTENSION = extension


def get_anima_extension():
    return _ANIMA_EXTENSION
