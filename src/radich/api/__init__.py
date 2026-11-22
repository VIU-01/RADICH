"""M12: synchronous, dependency-injected HTTP API for RADICH.

No global database connection, no built-in workflows, no public execution endpoint.
"""
from __future__ import annotations

import hmac
from typing import Any, Literal
from uuid import uuid4

from fastapi import Depends, FastAPI, Header, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from ..persistence.postgres import DuplicateRunError
from ..scheduler import SchedulerResult


class RunRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    initial_payloads: dict[str, dict[str, Any]] = Field(default_factory=dict)


class OutputResponse(BaseModel):
    run_id: str
    node_id: str
    payload: dict[str, Any]
    success: bool
    error: str | None


class RunResponse(BaseModel):
    run_id: str
    state: str
    node_states: dict[str, str]
    outputs: dict[str, OutputResponse]
    execution_order: list[str]


class RunProgressResponse(BaseModel):
    """Metadata-only progress; never expose request or checkpoint payloads."""

    run_id: str
    phase: Literal["REGISTERED", "CHECKPOINTED", "FINALIZED"]
    terminal_state: str | None
    completed_nodes: list[str]
    execution_order: list[str]


def _serialize(result: SchedulerResult) -> RunResponse:
    if not isinstance(result, SchedulerResult):
        raise TypeError("runner/repository must return SchedulerResult")
    return RunResponse(
        run_id=result.run_id,
        state=result.state.value,
        node_states={node: state.value for node, state in result.node_states.items()},
        outputs={
            node: OutputResponse(
                run_id=out.run_id, node_id=out.node_id,
                payload=out.payload, success=out.success, error=out.error
            )
            for node, out in result.outputs.items()
        },
        execution_order=list(result.execution_order),
    )


def create_app(*, runner: Any, repository: Any, api_key: str,
               resume_runner: Any | None = None,
               progress_reader: Any | None = None) -> FastAPI:
    """Create an API with injected synchronous runner and persistent repository.

    Pass RecordingScheduler for durable POST results. Never expose without HTTPS.
    """
    if not isinstance(api_key, str) or not api_key.strip():
        raise ValueError("api_key must be configured")
    if runner is None or not callable(getattr(runner, "run", None)):
        raise TypeError("runner must expose run(run_id, initial_payloads)")
    if repository is None or not callable(getattr(repository, "get_run", None)):
        raise TypeError("repository must expose get_run(run_id)")

    if resume_runner is not None and not callable(getattr(resume_runner, "resume", None)):
        raise TypeError("resume_runner must expose resume(run_id)")
    if progress_reader is not None and not callable(getattr(progress_reader, "get_progress", None)):
        raise TypeError("progress_reader must expose get_progress(run_id)")

    app = FastAPI(title="RADICH Core API", version="0.1.0")

    def authorize(x_api_key: str | None = Header(default=None)) -> None:
        if x_api_key is None or not hmac.compare_digest(
            x_api_key.encode("utf-8"), api_key.encode("utf-8")
        ):
            raise HTTPException(status_code=401, detail="Unauthorized")

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.post("/v1/runs", response_model=RunResponse, dependencies=[Depends(authorize)])
    def create_run(body: RunRequest) -> RunResponse:
        run_id = str(uuid4())
        try:
            result = runner.run(run_id, body.initial_payloads)
            return _serialize(result)
        except DuplicateRunError:
            raise HTTPException(status_code=409, detail="Run already exists") from None
        except (ValueError, TypeError) as exc:
            # Input validation may originate from the graph/scheduler.
            raise HTTPException(status_code=422, detail="Invalid execution request") from exc
        except Exception as exc:
            raise HTTPException(status_code=500, detail="Execution failed") from exc

    @app.get("/v1/runs/{run_id}", response_model=RunResponse, dependencies=[Depends(authorize)])
    def get_run(run_id: str) -> RunResponse:
        try:
            result = repository.get_run(run_id)
            if result is None:
                raise HTTPException(status_code=404, detail="Run not found")
            return _serialize(result)
        except HTTPException:
            raise
        except Exception as exc:
            raise HTTPException(status_code=500, detail="Unable to read run") from exc

    if progress_reader is not None:
        @app.get("/v1/runs/{run_id}/progress", response_model=RunProgressResponse,
                 dependencies=[Depends(authorize)])
        def get_run_progress(run_id: str) -> RunProgressResponse:
            """Read a consistent metadata-only view without starting any handler."""
            try:
                progress = progress_reader.get_progress(run_id)
                if progress is None:
                    raise HTTPException(status_code=404, detail="Run not found")
                return RunProgressResponse.model_validate(progress)
            except HTTPException:
                raise
            except Exception as exc:
                raise HTTPException(status_code=500, detail="Unable to read run progress") from exc

    if resume_runner is not None:
        @app.post("/v1/runs/{run_id}/resume", response_model=RunResponse,
                  dependencies=[Depends(authorize)])
        def resume_run(run_id: str) -> RunResponse:
            """Explicitly resume an interrupted, pre-registered execution."""
            try:
                return _serialize(resume_runner.resume(run_id))
            except KeyError:
                raise HTTPException(status_code=404, detail="Run not found") from None
            except DuplicateRunError:
                raise HTTPException(status_code=409, detail="Run is busy or already exists") from None
            except (ValueError, TypeError) as exc:
                raise HTTPException(status_code=422, detail="Invalid execution request") from exc
            except Exception as exc:
                raise HTTPException(status_code=500, detail="Execution failed") from exc

    return app
