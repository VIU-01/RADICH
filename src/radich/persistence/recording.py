"""Run M08 and record its completed snapshot in PostgreSQL."""

from collections.abc import Mapping

from ..scheduler import Scheduler, SchedulerResult
from .postgres import PostgresRunRepository


class RecordingScheduler:
    def __init__(self, scheduler: Scheduler, repository: PostgresRunRepository) -> None:
        if not isinstance(scheduler, Scheduler):
            raise TypeError("scheduler must be Scheduler")
        if not isinstance(repository, PostgresRunRepository):
            raise TypeError("repository must be PostgresRunRepository")
        self._scheduler = scheduler
        self._repository = repository

    def run(self, run_id: str, initial_payloads: Mapping[str, dict] | None = None) -> SchedulerResult:
        result = self._scheduler.run(run_id, initial_payloads)
        self._repository.save_result(result)
        return result
