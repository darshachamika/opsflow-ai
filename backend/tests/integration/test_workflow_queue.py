"""Queue concurrency and fencing tests against migrated opsflow_test."""
from datetime import datetime,timedelta,timezone
from uuid import uuid4
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import Mock
import pytest
from sqlalchemy import create_engine,select,delete,func
from sqlalchemy.orm import Session
from app.core.database import database_url
from app.models import Incident,Product,Location
from app.models.workflow import WorkflowRun,WorkflowStep
from app.models.workflow_job import WorkflowJob,WorkflowAttempt
from app.schemas.orchestration import OrchestrationRequest
from app.services import workflow_queue as queue,workflows


@pytest.fixture
def scenario(monkeypatch):
    engine=create_engine(database_url.set(database="opsflow_test"),isolation_level="READ COMMITTED",connect_args={"connect_timeout":5})
    monkeypatch.setattr(queue,"engine",engine);monkeypatch.setattr(workflows,"engine",engine)
    ids={k:uuid4() for k in ("product","plant","incident")};suffix=uuid4().hex
    with Session(engine) as s,s.begin():
        s.add_all([Product(id=ids["product"],sku=f"Q-{suffix}",name="Queue test",unit_of_measure="UNIT"),Location(id=ids["plant"],code=f"Q-{suffix}",name="Queue plant",type="PLANT")]);s.flush()
        s.add(Incident(id=ids["incident"],source_system="QUEUE_TEST",source_ref=suffix,title="Queue test",product_id=ids["product"],plant_id=ids["plant"],status="OPEN",detected_at=datetime.now(timezone.utc)))
    body=OrchestrationRequest(warehouse_code="WH",transfer_lead_time_hours=6,transport_cost="18000",purchase_freight_cost="12000",currency="LKR")
    try:yield engine,ids["incident"],body,f"actor.{suffix}"
    finally:
        with Session(engine) as s,s.begin():
            runs=select(WorkflowRun.id).where(WorkflowRun.incident_id==ids["incident"])
            jobs=select(WorkflowJob.id).where(WorkflowJob.run_id.in_(runs))
            s.execute(delete(WorkflowAttempt).where(WorkflowAttempt.job_id.in_(jobs)))
            s.execute(delete(WorkflowJob).where(WorkflowJob.run_id.in_(runs)))
            s.execute(delete(WorkflowStep).where(WorkflowStep.run_id.in_(runs)))
            s.execute(delete(WorkflowRun).where(WorkflowRun.incident_id==ids["incident"]))
            s.execute(delete(Incident).where(Incident.id==ids["incident"]))
            s.execute(delete(Product).where(Product.id==ids["product"]))
            s.execute(delete(Location).where(Location.id==ids["plant"]))
        engine.dispose()


def result():return {"status":"NEEDS_EVIDENCE","steps":["ASSESS_IMPACT"],"persisted":False,"llm_used":False}


def expire(engine,claim):
    with Session(engine) as s,s.begin():
        job=s.get(WorkflowJob,claim.job_id)
        job.lease_until=s.scalar(select(func.clock_timestamp()))-timedelta(seconds=1)


def test_enqueue_replay_and_one_claim(scenario):
    engine,incident,body,actor=scenario
    with ThreadPoolExecutor(max_workers=2) as pool:
        ids=list(pool.map(lambda _:queue.enqueue(incident,body,actor,"one"),range(2)))
    assert ids[0]==ids[1]
    with ThreadPoolExecutor(max_workers=2) as pool:
        claims=list(pool.map(queue.claim_one,["w1","w2"]))
    assert sum(c is not None for c in claims)==1
    claim=next(c for c in claims if c is not None)
    assert queue.finish(claim,result=result())
    assert not queue.finish(claim,result=result())
    assert workflows.get_run(ids[0])["status"]=="SUCCEEDED"
    assert queue.job_history(ids[0])["job"]["status"]=="COMPLETED"


def test_expired_worker_cannot_overwrite_reclaimed_result(scenario):
    engine,incident,body,actor=scenario
    run=queue.enqueue(incident,body,actor,"expiry")
    old=queue.claim_one("old");expire(engine,old)
    assert queue.finish(old,result=result()) is False
    new=queue.claim_one("new")
    assert new.token!=old.token
    assert queue.finish(new,result=result())
    assert queue.finish(old,result={**result(),"status":"WRONG"}) is False
    assert workflows.get_run(run)["result"]["status"]=="NEEDS_EVIDENCE"
    assert [a["status"] for a in queue.job_history(run)["attempts"]]==["LEASE_EXPIRED","SUCCEEDED"]


def test_crash_attempt_limit(scenario):
    engine,incident,body,actor=scenario
    run=queue.enqueue(incident,body,actor,"crashes")
    for _ in range(3):
        claim=queue.claim_one("crashing");assert claim is not None;expire(engine,claim)
    assert queue.claim_one("fourth") is None
    assert workflows.get_run(run)["error_code"]=="RETRY_EXHAUSTED"
    assert queue.job_history(run)["job"]["attempt_count"]==3


def test_retry_delay_and_final_failure(scenario):
    engine,incident,body,actor=scenario
    run=queue.enqueue(incident,body,actor,"retry")
    for number in range(3):
        claim=queue.claim_one("worker")
        assert queue.finish(claim,error_code="PLANNING_FAILED",retryable=True)
        if number<2:
            assert queue.claim_one("early") is None
            with Session(engine) as s,s.begin():
                job=s.get(WorkflowJob,claim.job_id)
                job.available_at=s.scalar(select(func.clock_timestamp()))-timedelta(seconds=1)
    assert workflows.get_run(run)["status"]=="FAILED"


def test_worker_calls_planner_and_explainer(scenario,monkeypatch):
    _,incident,body,actor=scenario
    run=queue.enqueue(incident,body,actor,"process")
    planner=Mock(return_value=result());llm=Mock(side_effect=lambda r:dict(r))
    monkeypatch.setattr(queue,"plan_incident",planner);monkeypatch.setattr(queue,"add_explanation",llm)
    assert queue.process_one("test")
    assert planner.call_count==llm.call_count==1
    assert workflows.get_run(run)["result"]["persisted"] is True


def test_changed_inputs_conflict(scenario):
    _,incident,body,actor=scenario
    queue.enqueue(incident,body,actor,"same")
    with pytest.raises(workflows.WorkflowConflict):
        queue.enqueue(incident,body.model_copy(update={"currency":"USD"}),actor,"same")
