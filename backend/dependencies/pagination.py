from typing import Annotated

from fastapi import Depends, Query


DEFAULT_LIMIT = 50
MAX_LIMIT = 200


class PaginationParams:
    def __init__(
        self,
        limit: Annotated[int, Query(ge=1, le=MAX_LIMIT)] = (
            DEFAULT_LIMIT
        ),
        offset: Annotated[int, Query(ge=0)] = 0,
    ) -> None:
        self.limit = limit
        self.offset = offset


Pagination = Annotated[PaginationParams, Depends()]
