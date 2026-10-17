"""Requires migrated opsflow_test PostgreSQL database; never calls Gemini."""
from datetime import datetime, timezone
from uuid import uuid4
from unittest.mock import Mock
from concurrent.futures import ThreadPoolExecutor

import pytest
from sqlalchemy import create_engine, select, delete, func
from sqlalchemy.orm import Session
from app.core.database import database_url
from app.models import Incident,Product,Location
from app.models.workflow import WorkflowRun,WorkflowStep
from app.services import workflows as service
from app.schemas.orchestration import OrchestrationRequest


@pytest.fixture
def scenario(monkeypatch):
    engine=create_engine(database_url.set(database="opsflow_test"),isolation_level="READ COMMITTED",connect_args={"connect_timeout":5})
    monkeypatch.setattr(service,"engine",engine)
    suffix=uuid4().hex
    product_id,plant_id,incident_id=uuid4(),uuid4(),uuid4()
    with Session(engine) as session,session.begin():
        session.add_all([Product(id=product_id,sku=f"WF-{suffix}",name="Workflow test",unit_of_measure="UNIT"),Location(id=plant_id,code=f"WF-{suffix}",name="Workflow test plant",type="PLANT")])
        session.flush()
        session.add(Incident(id=incident_id,source_system="TEST",source_ref=suffix,title="Test incident",product_id=product_id,plant_id=plant_id,status="OPEN",detected_at=datetime.now(timezone.utc)))
    planner=Mock(return_value={"status":"NEEDS_EVIDENCE","next_action":"REFRESH_EVIDENCE","steps":["ASSESS_IMPACT"],"persisted":False,"llm_used":False})
    explainer=Mock(side_effect=lambda result:dict(result))
    monkeypatch.setattr(service,"plan_incident",planner)
    monkeypatch.setattr(service,"add_explanation",explainer)
    request=OrchestrationRequest(warehouse_code="WH",transfer_lead_time_hours=6,transport_cost="18000",purchase_freight_cost="12000",currency="LKR")
    try:
        yield engine,incident_id,request,f"actor.{suffix}",planner,explainer
    finally:
        with Session(engine) as session,session.begin():
            ids=select(WorkflowRun.id).where(WorkflowRun.incident_id==incident_id)
            session.execute(delete(WorkflowStep).where(WorkflowStep.run_id.in_(ids)))
            session.execute(delete(WorkflowRun).where(WorkflowRun.incident_id==incident_id))
            session.execute(delete(Incident).where(Incident.id==incident_id))
            session.execute(delete(Product).where(Product.id==product_id))
            session.execute(delete(Location).where(Location.id==plant_id))
        engine.dispose()


def test_saved_result_and_idempotent_replay(scenario):
    engine,incident,body,actor,planner,llm=scenario
    first,created=service.create_run(incident,body,actor,"one")
    second,recreated=service.create_run(incident,body,actor,"one")
    assert created and not recreated and first==second
    assert first["status"]=="SUCCEEDED"
    assert first["result"]["status"]=="NEEDS_EVIDENCE"
    assert first["result"]["persisted"] is True
    assert [s["name"] for s in first["steps"]]==["PLAN_INCIDENT","ASSESS_IMPACT","EXPLAIN_RESULT"]
    assert planner.call_count==llm.call_count==1
    assert service.list_runs(incident,20,0)["items"][0]["id"]==first["id"]


def test_changed_inputs_conflict(scenario):
    _,incident,body,actor,*_=scenario
    service.create_run(incident,body,actor,"one")
    with pytest.raises(service.WorkflowConflict):
        service.create_run(incident,body.model_copy(update={"currency":"USD"}),actor,"one")


def test_concurrent_requests_claim_one_run(scenario):
    engine,incident,body,actor,planner,llm=scenario
    with ThreadPoolExecutor(max_workers=2) as pool:
        results=list(pool.map(lambda _:service.create_run(incident,body,actor,"race"),range(2)))
    assert results[0][0]["id"]==results[1][0]["id"]
    assert sum(created for _,created in results)==1
    assert planner.call_count==llm.call_count==1
    with Session(engine) as session:
        assert session.scalar(select(func.count()).select_from(WorkflowRun).where(WorkflowRun.incident_id==incident))==1


def test_failed_run_is_recorded_without_sensitive_text(scenario):
    _,incident,body,actor,planner,llm=scenario
    planner.side_effect=RuntimeError("secret text must never persist")
    result,_=service.create_run(incident,body,actor,"fail")
    assert result["status"]=="FAILED"
    assert result["error_code"]=="PLANNING_FAILED"
    assert "secret text" not in str(result)
    llm.assert_not_called()
