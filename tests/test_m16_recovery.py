"""M16.1 checkpoint and resume contract tests."""
import pytest

from radich.contracts import NodeInput, NodeOutput
from radich.demo import build_demo_graph, demo_handlers
from radich.recovery import MemoryCheckpointStore, RecoverableScheduler, RunCheckpoint


def test_resume_skips_completed_nodes_after_failure():
    store = MemoryCheckpointStore()
    counts = {"extract": 0, "validate": 0}
    handlers = demo_handlers()
    extract, validate = handlers["extract"], handlers["validate"]

    def counting_extract(inp):
        counts["extract"] += 1
        return extract(inp)

    def flaky_validate(inp):
        counts["validate"] += 1
        if counts["validate"] == 1:
            raise RuntimeError("temporary failure")
        return validate(inp)

    handlers["extract"] = counting_extract
    handlers["validate"] = flaky_validate
    scheduler = RecoverableScheduler(build_demo_graph(), handlers, store)
    first = scheduler.run("r1", {"extract": {"text": "resume works"}})
    assert first.state.value == "FAILED"
    assert list(store.load("r1").completed) == ["extract"]
    second = scheduler.run("r1", {"extract": {"text": "resume works"}})
    assert second.state.value == "COMPLETED"
    assert second.outputs["summarize"].payload["summary"] == "resume works"
    assert counts == {"extract": 1, "validate": 2}


def test_checkpoint_survives_new_scheduler_instance():
    store = MemoryCheckpointStore()
    handlers = demo_handlers()
    scheduler = RecoverableScheduler(build_demo_graph(), handlers, store)
    first = scheduler.run("r2", {"extract": {"text": "saved"}})
    assert first.state.value == "COMPLETED"

    def must_not_execute(inp):
        raise AssertionError("completed node reexecuted")

    restarted = RecoverableScheduler(
        build_demo_graph(), {node: must_not_execute for node in handlers}, store
    )
    assert restarted.run("r2").state.value == "COMPLETED"


def test_invalid_checkpoint_is_rejected():
    store = MemoryCheckpointStore()
    store.save(RunCheckpoint("r3", {"ghost": NodeOutput("r3", "ghost", {}, True)} , ("ghost",)))
    scheduler = RecoverableScheduler(build_demo_graph(), demo_handlers(), store)
    with pytest.raises(ValueError, match="unknown nodes"):
        scheduler.run("r3")
