from __future__ import annotations

from http import HTTPStatus


class AppError(Exception):
    def __init__(self, message: str, status: int = HTTPStatus.BAD_REQUEST):
        super().__init__(message)
        self.message = message
        self.status = status

