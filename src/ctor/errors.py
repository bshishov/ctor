from typing import Optional, List, Dict, Any

__all__ = ["ErrorInfo", "LoadError", "DumpError"]


class ErrorInfo:
    __slots__ = "code", "message", "target", "details"

    def __init__(
        self,
        message: str,
        code: str,
        target: Optional[str] = None,
        details: Optional[List["ErrorInfo"]] = None,
    ):
        self.message = message
        self.code = code
        self.target = target
        self.details = details if details is not None else []

    def to_dict(self) -> Dict[str, Any]:
        return {
            "code": self.code,
            "message": self.message,
            "target": self.target,
            "details": [error.to_dict() for error in self.details],
        }

    def to_readable_format(self, indent: int = 0) -> str:
        details_indent = "\t" * (indent + 1)

        if self.target:
            this_error = f"({self.target}): {self.message}"
        else:
            this_error = self.message

        if self.details:
            details = "\n".join(
                f"{details_indent}{error.to_readable_format(indent + 1)}"
                for error in self.details
            )
            return f"{this_error}\n{details}"
        else:
            return this_error

    @staticmethod
    def from_builtin_error(error: Exception) -> "ErrorInfo":
        return ErrorInfo(message=str(error), code=type(error).__name__)

    @staticmethod
    def invalid_type(
        expected: type, actual: type, target: Optional[str] = None
    ) -> "ErrorInfo":
        return ErrorInfo(
            message=f"Invalid type, expected {expected}, got {actual}",
            code="invalid_type",
            target=target,
        )


class BaseError(TypeError, ValueError):
    __slots__ = "info"

    def __init__(self, info: ErrorInfo):
        self.info = info
        super().__init__(self.message)

    @property
    def code(self) -> str:
        return self.info.code

    @property
    def message(self) -> str:
        return self.info.message

    @property
    def target(self) -> Optional[str]:
        return self.info.target

    def to_dict(self) -> Dict[str, Any]:
        return self.info.to_dict()

    def __str__(self) -> str:
        return self.info.to_readable_format()


class LoadError(BaseError):
    pass


class DumpError(BaseError):
    pass
