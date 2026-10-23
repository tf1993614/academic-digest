"""Errors that the CLI turns into actionable messages and exit codes."""


class ConfigError(Exception):
    """The configuration is missing or invalid.

    ``field`` is a dotted path such as ``topics[0].terms`` so the user can jump
    straight to the broken line.
    """

    def __init__(self, field: str, message: str) -> None:
        super().__init__(f"{field}: {message}")
        self.field = field
        self.message = message


class SourceError(Exception):
    """A data source could not be read or parsed."""
