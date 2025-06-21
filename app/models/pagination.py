from typing import TypeVar, Generic

from pydantic import BaseModel

T = TypeVar('T')

class PaginatedResponse(BaseModel, Generic[T]):
    data: list[T]
    current_page: int
    per_page: int
    total_items: int
    total_pages: int
    has_next: bool
    has_prev: bool


class CursorResponse(BaseModel, Generic[T]):
    data: list[T]
    next_cursor: str | None = None
    size: int


class HybridResponse(BaseModel, Generic[T]):
    data: list[T]
    page: int | None = None
    size: int
    total: int | None = None
    next_cursor: str | None = None
    pagination_type: str
