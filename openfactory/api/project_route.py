"""A panel route whose path names a project logs about that project (#681).

With `OPENFACTORY_LOG_FORMAT=json` a line carries `project` and `product` when the record concerns
one (`observability/logs.py`). A route like `/api/board/{project}` concerns exactly one, and so does
every warning its handler and the libraries below it write while it runs — so the route says it
once, around the handler, rather than each `log.warning` repeating it.

THE APP'S ROUTE CLASS, NOT A LIST OF ROUTES: `app.py` makes this the class every route is built
with, so a route added tomorrow that takes `{project}` is tagged without anybody remembering it.
A route that names no project is built exactly as FastAPI builds it.
"""

from __future__ import annotations

from collections.abc import Callable, Coroutine
from typing import Any

from fastapi import Request, Response
from fastapi.routing import APIRoute

from openfactory.observability import logs


class AboutItsProject(APIRoute):
    """An `APIRoute` whose handler runs inside `logs.about(...)` when its path takes `{project}`."""

    def get_route_handler(self) -> Callable[[Request], Coroutine[Any, Any, Response]]:
        handler = super().get_route_handler()
        if "project" not in self.param_convertors:
            return handler

        async def about_its_project(request: Request) -> Response:
            project = str(request.path_params.get("project") or "")
            with logs.about(**await logs.concerning_from_a_loop(project)):
                return await handler(request)

        return about_its_project
