from typing import Optional, Sequence


class PresentableError(Exception):
    """Failure carrying a stable code and optional Host presentation data."""

    def __init__(
        self,
        code: str,
        presentation: Optional[str],
        *,
        diagnostic: Optional[str] = None,
        arguments: Sequence[object] = (),
        recovery_path: Optional[str] = None,
        message: Optional[str] = None,
    ) -> None:
        super().__init__((presentation or code) if message is None else message)
        self.code = code
        self.presentation = presentation
        self.diagnostic = diagnostic
        self.arguments = list(arguments)
        self.recovery_path = recovery_path


class CoreSaveError(PresentableError, RuntimeError):
    """Core Save failure with a Host localization key and technical detail."""

    code: str
    presentation_key: str

    def __init__(self, message: str, *, arguments: Sequence[str] = (), recovery_path: Optional[str] = None) -> None:
        super().__init__(
            self.code,
            self.presentation_key,
            diagnostic=message,
            arguments=arguments,
            recovery_path=recovery_path,
            message=message,
        )
