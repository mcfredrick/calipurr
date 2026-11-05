class Hiss(Exception):
    """A user-correctable problem, reported with its reason in plain words."""


class NeedsConfirmation(Hiss):
    """Something looks wrong, but the user may know better and can confirm it."""
