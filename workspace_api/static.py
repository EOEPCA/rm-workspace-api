# Copyright 2026, EOX (https://eox.at) and Versioneer (https://versioneer.at)
# SPDX-License-Identifier: Apache-2.0

import re

from starlette.datastructures import Headers
from starlette.exceptions import HTTPException
from starlette.responses import Response
from starlette.staticfiles import StaticFiles
from starlette.types import Scope

FINGERPRINTED_ASSET = re.compile(r"management/assets/[^/]+-[A-Za-z0-9_-]{8}\.[^/]+")


class UIStaticFiles(StaticFiles):
    """Revalidate UI entry files and cache assets with a content hash."""

    async def get_response(self, path: str, scope: Scope) -> Response:
        try:
            response = await super().get_response(path, scope)
        except HTTPException as error:
            error.headers = {**(error.headers or {}), "Cache-Control": "no-store"}
            raise
        if response.status_code >= 400:
            cache_control = "no-store"
        elif FINGERPRINTED_ASSET.fullmatch(path):
            cache_control = "public, max-age=31536000, immutable"
        else:
            cache_control = "no-cache"
        response.headers["Cache-Control"] = cache_control
        return response

    def is_not_modified(self, response_headers: Headers, request_headers: Headers) -> bool:
        # An ETag mismatch must take priority over the file date.
        if_none_match = request_headers.get("if-none-match")
        if if_none_match is not None:
            return if_none_match.strip() == "*" or response_headers["etag"] in (
                tag.strip().removeprefix("W/") for tag in if_none_match.split(",")
            )
        return super().is_not_modified(response_headers, request_headers)
