"""Project-specific exceptions."""


class PipelineError(RuntimeError):
    """Base pipeline error."""


class StageValidationError(PipelineError):
    """Raised when a stage artifact contract is not satisfied."""
