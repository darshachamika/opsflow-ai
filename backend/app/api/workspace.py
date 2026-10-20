"""Authenticated, bounded lists for the single-organization browser workspace."""
from typing import Annotated, Literal
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, or_
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session
from app.core.database import engine
from app.models import Product, Location, Incident, RecoveryProposal
from app.schemas.proposals import ProposalResponse

router = APIRouter(prefix='/api/v1/workspace', tags=['Workspace'])

def db_session():
    try:
        with Session(engine) as session:
            yield session
    except SQLAlchemyError:
        raise HTTPException(503, 'Workspace data unavailable.') from None

DB = Annotated[Session, Depends(db_session)]

@router.get('/products')
def products(session: DB, q: str = Query('', max_length=128), offset: int = Query(0, ge=0), limit: int = Query(50, ge=1, le=100)):
    query = select(Product).where(Product.is_active.is_(True))
    if q.strip():
        query = query.where(or_(Product.sku.icontains(q.strip(), autoescape=True), Product.name.icontains(q.strip(), autoescape=True)))
    rows = session.scalars(query.order_by(Product.sku, Product.id).offset(offset).limit(limit+1)).all()
    return {'items': [{'id':str(x.id), 'sku':x.sku, 'name':x.name} for x in rows[:limit]],
            'next_offset':offset+limit if len(rows)>limit else None}

@router.get('/locations')
def locations(session: DB, type: Literal['PLANT','WAREHOUSE'], q: str = Query('', max_length=128), offset: int = Query(0, ge=0), limit: int = Query(50, ge=1, le=100)):
    query = select(Location).where(Location.type == type)
    if q.strip():
        query = query.where(or_(Location.code.icontains(q.strip(), autoescape=True), Location.name.icontains(q.strip(), autoescape=True)))
    rows = session.scalars(query.order_by(Location.code, Location.id).offset(offset).limit(limit+1)).all()
    return {'items':[{'id':str(x.id),'code':x.code,'name':x.name,'type':x.type} for x in rows[:limit]],
            'next_offset':offset+limit if len(rows)>limit else None}

@router.get('/incidents')
def incidents(session: DB, q: str = Query('', max_length=128), offset: int = Query(0, ge=0), limit: int = Query(20, ge=1, le=100)):
    query = select(Incident, Product, Location).join(Product, Incident.product_id==Product.id).join(Location, Incident.plant_id==Location.id)
    if q.strip():
        query = query.where(or_(Incident.title.icontains(q.strip(), autoescape=True), Product.sku.icontains(q.strip(), autoescape=True)))
    rows = session.execute(query.order_by(Incident.created_at.desc(), Incident.id.desc()).offset(offset).limit(limit+1)).all()
    return {'items':[{'id':str(i.id),'title':i.title,'description':i.description,'status':i.status,
              'product_id':str(p.id),'sku':p.sku,'plant_id':str(l.id),'plant_code':l.code,'plant_name':l.name,
              'created_at':i.created_at,'detected_at':i.detected_at} for i,p,l in rows[:limit]],
            'next_offset':offset+limit if len(rows)>limit else None}

@router.get('/incidents/{incident_id}/proposals')
def proposals(incident_id: UUID, session: DB, before_version: int | None = Query(None, ge=1), limit: int = Query(20, ge=1, le=100)):
    if session.get(Incident, incident_id) is None:
        raise HTTPException(404, 'Incident not found.')
    query = select(RecoveryProposal).where(RecoveryProposal.incident_id==incident_id)
    if before_version is not None:
        query = query.where(RecoveryProposal.version<before_version)
    rows = session.scalars(query.order_by(RecoveryProposal.version.desc()).limit(limit+1)).all()
    return {'items':[ProposalResponse.model_validate(x).model_dump(mode='json') for x in rows[:limit]],
            'next_before_version': rows[limit-1].version if len(rows)>limit else None}
