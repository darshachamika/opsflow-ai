from datetime import datetime, timezone
from uuid import uuid4
import pytest
from fastapi import FastAPI, Depends
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool
from app.api import workspace
from app.core.approval_auth import Actor, current_actor
from app.models import Product, Location, Incident

@pytest.fixture
def client(monkeypatch):
    engine=create_engine('sqlite://',poolclass=StaticPool,connect_args={'check_same_thread':False})
    for model in [Product,Location,Incident]:
        model.__table__.create(engine)
    with Session(engine) as s,s.begin():
        p1=Product(id=uuid4(),sku='MOTOR-A',name='Motor Alpha',unit_of_measure='UNIT',is_active=True)
        p2=Product(id=uuid4(),sku='MOTOR-B',name='Motor Beta',unit_of_measure='UNIT',is_active=True)
        p3=Product(id=uuid4(),sku='OLD',name='Old',unit_of_measure='UNIT',is_active=False)
        plant=Location(id=uuid4(),code='LK-PLANT',name='Homagama',type='PLANT')
        wh=Location(id=uuid4(),code='LK-WH',name='Wattala',type='WAREHOUSE')
        s.add_all([p1,p2,p3,plant,wh]);s.flush()
        s.add(Incident(id=uuid4(),source_system='TEST',source_ref='REF-1',title='Motor shortage',
                      product_id=p1.id,plant_id=plant.id,status='OPEN',detected_at=datetime.now(timezone.utc)))
    monkeypatch.setattr(workspace,'engine',engine)
    app=FastAPI();app.include_router(workspace.router,dependencies=[Depends(current_actor)])
    app.dependency_overrides[current_actor]=lambda:Actor('reader','OPERATOR')
    with TestClient(app) as c:yield c
    engine.dispose()

def test_active_products_and_pagination(client):
    data=client.get('/api/v1/workspace/products?limit=1').json()
    assert data['items'][0]['sku']=='MOTOR-A'
    assert data['next_offset']==1
    data=client.get('/api/v1/workspace/products?limit=1&offset=1').json()
    assert data['items'][0]['sku']=='MOTOR-B'
    assert data['next_offset'] is None
    assert client.get('/api/v1/workspace/products?q=beta').json()['items'][0]['sku']=='MOTOR-B'
    assert client.get('/api/v1/workspace/products?q=%25').json()['items']==[]

def test_locations_filtered_and_bad_type(client):
    assert client.get('/api/v1/workspace/locations?type=PLANT').json()['items'][0]['name']=='Homagama'
    assert client.get('/api/v1/workspace/locations?type=WAREHOUSE').json()['items'][0]['name']=='Wattala'
    assert client.get('/api/v1/workspace/locations?type=OTHER').status_code==422

def test_incident_names_and_search(client):
    response=client.get('/api/v1/workspace/incidents?q=Motor')
    assert response.status_code==200
    item=response.json()['items'][0]
    assert item['sku']=='MOTOR-A' and item['plant_name']=='Homagama'
    assert client.get('/api/v1/workspace/incidents?q=missing').json()['items']==[]

def test_list_bounds(client):
    assert client.get('/api/v1/workspace/incidents?limit=10000').status_code==422
    assert client.get('/api/v1/workspace/products?offset=-1').status_code==422
