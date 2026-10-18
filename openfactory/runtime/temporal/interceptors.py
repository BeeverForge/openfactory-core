"""An activity whose input names a project logs about that project (#681).

With `OPENFACTORY_LOG_FORMAT=json` a line carries `project` and `product` when the record concerns
one (`observability/logs.py`). On the worker, nearly all of the work about one project is an
activity — a job, a merge check, a sweep, a turn of the product role — and its input already names
the project: a field of its input model (`RunJobInput.project`), a field one model down
(`PreviewPlanInput.step.project`), or a parameter (`product_sweep(project_name)`). So the worker
says it once, around each activity, and every record the activity and the libraries below it write
carries it.

A WORKER INTERCEPTOR, NOT A LINE IN EACH ACTIVITY: the worker registers it (`worker.py`), so an
activity added tomorrow is tagged without anybody remembering it. An activity whose input names no
project runs exactly as it did.
"""

from __future__ import annotations

import inspect
from collections.abc import Callable, Sequence
from typing import Any

from temporalio.worker import ActivityInboundInterceptor, ExecuteActivityInput, Interceptor

from openfactory.observability import logs

#: The parameter names that ARE a project's name when an activity takes one bare.
PROJECT_PARAMETERS = ("project", "project_name")


def _carried(value: object, depth: int = 2) -> tuple[str, str]:
    """`(project, product)` an input carries: its own `project` / `product` fields, or the first
    model field `depth - 1` levels down that names a project."""
    project = getattr(value, "project", None)
    product = getattr(value, "product", None)
    project = project if isinstance(project, str) else ""
    product = product if isinstance(product, str) else ""
    fields = getattr(type(value), "model_fields", None)
    if not project and depth > 1 and isinstance(fields, dict):
        for name in fields:
            inner, inner_product = _carried(getattr(value, name, None), depth - 1)
            if inner:
                return inner, product or inner_product
    return project, product


def named(fn: Callable[..., Any], args: Sequence[Any]) -> tuple[str, str]:
    """`(project, product)` an activity's arguments name — `("", "")` when they name none."""
    try:
        bound = inspect.signature(fn).bind_partial(*args).arguments
    except (TypeError, ValueError):
        bound = {str(n): value for n, value in enumerate(args)}
    for parameter, value in bound.items():
        if parameter in PROJECT_PARAMETERS and isinstance(value, str) and value:
            return value, ""
        project, product = _carried(value)
        if project:
            return project, product
    return "", ""


class AboutItsProject(Interceptor):
    """Every activity whose input names a project runs inside `logs.about(...)`."""

    def intercept_activity(self, next: ActivityInboundInterceptor) -> ActivityInboundInterceptor:
        return _ActivityAboutItsProject(next)


class _ActivityAboutItsProject(ActivityInboundInterceptor):
    async def execute_activity(self, input: ExecuteActivityInput) -> Any:
        project, product = named(input.fn, input.args)
        if not project:
            return await super().execute_activity(input)
        with logs.about(**await logs.concerning_from_a_loop(project, product)):
            return await super().execute_activity(input)
