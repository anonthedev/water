"""Configuration constants for the Water framework."""

class Config:
    """
    Global configuration settings for the Water framework.

    Contains default values for execution parameters like loop iterations
    and timeout settings that can be referenced throughout the framework.
    """

    # Loop settings
    DEFAULT_MAX_ITERATIONS: int = 100

    # Execution settings
    DEFAULT_TIMEOUT_SECONDS: int = 300


# Module-level aliases for convenient imports
DEFAULT_MAX_ITERATIONS = Config.DEFAULT_MAX_ITERATIONS
DEFAULT_TIMEOUT_SECONDS = Config.DEFAULT_TIMEOUT_SECONDS
