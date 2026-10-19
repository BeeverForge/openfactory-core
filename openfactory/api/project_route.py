"""A panel route whose path names a project logs about that project (#681).

With `OPENFACTORY_LOG_FORMAT=json` a line carries `project` and `product` when the record concerns
one (`observability/logs.py`). A route like `/api/board/{project}` concerns exactly one, and so does
every warning its handler, the libraries below it and the body of the stream it answers with write
— so the route says it once, around the handler and around the stream, rather than each
`log.warning` repeating it.

THE APP'S ROUTE CLASS, NOT A LIST OF ROUTES: `app.py` makes this the class every route is built
with, so a route added tomorrow that takes `{project}` is tagged without anybody remembering it.
A route that names no project is built exactly as FastAPI builds it.

IT COSTS THE REQUEST NOTHING (second review of #818). Naming the project is a context variable. The
product is never read here: the line's formatter takes it from what this process last read of the
registry, and only a request the gate admitted asks for that to be read again — without waiting,
on a thread of the log's own (`logs.freshen_products`). A path the gate opens to anybody, the HTML
shell, asks for nothing, so no stranger can make this process read a file for them. A route measured
before this read the registry on the gate's own executor once per request, the shell's included.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Callable, Coroutine
from typing import Any, ClassVar

from fastapi import Request, Response
from fastapi.responses import StreamingResponse
from fastapi.routing import APIRoute

from openfactory.observability import logs


class AboutItsProject(APIRoute):
    """An `APIRoute` whose handler, and the body of the stream it answers with, run inside
    `logs.about(...)` when its path takes `{project}`."""

    #: Whether the gate admits a request for this path only with a credential: the app's own rule,
    #: handed in by `gated_by` (`api/app.py::_gated`). Unset, no path is, and nothing is asked.
    gated: ClassVar[Callable[[str], bool]] = staticmethod(lambda path: False)

    @classmethod
    def gated_by(cls, rule: Callable[[str], bool]) -> type[AboutItsProject]:
        """This class, for an app whose gate admits the paths `rule` names only with a
        credential."""
        return type(cls.__name__, (cls,), {"gated": staticmethod(rule)})

    def get_route_handler(self) -> Callable[[Request], Coroutine[Any, Any, Response]]:
        handler = super().get_route_handler()
        if "project" not in self.param_convertors:
            return handler
        gated = type(self).gated

        async def about_its_project(request: Request) -> Response:
            project = str(request.path_params.get("project") or "")
            if gated(request.url.path):
                logs.freshen_products()
            with logs.about(project=project):
                response = await handler(request)
            if isinstance(response, StreamingResponse):
                response.body_iterator = _AboutWhileStreaming(response.body_iterator, project)
            return response

        return about_its_project


class _AboutWhileStreaming:
    """A stream's body, each step of it run inside `logs.about(project=…)`.

    The handler has returned by the time its stream is read, so the block around it is closed and a
    record the body logs said nothing (second review of #818: `/api/jobs/{project}/{issue}/stream`).
    PER STEP, NOT ONE BLOCK AROUND THE WHOLE ITERATION: a `with` held open across `yield` would be
    closed by whoever finalises the generator — possibly another task, whose context the variable
    was never set in — while a step sets and resets it inside one call, in one task.

    NO `aclose` OF ITS OWN (fourth review of #818: one stood here, and no test could reach it).
    Nothing in the stack calls it: a `StreamingResponse` only iterates its body
    (`starlette/responses.py::stream_response`). The body it wraps is still closed as any async
    generator is — cancelled inside the step a disconnect interrupts, or finalised by the loop."""

    def __init__(self, body: Any, project: str) -> None:
        self._body: AsyncIterator[Any] = body.__aiter__()
        self._project = project

    def __aiter__(self) -> _AboutWhileStreaming:
        return self

    async def __anext__(self) -> Any:
        with logs.about(project=self._project):
            return await self._body.__anext__()
