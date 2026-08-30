"""On-demand tenant-scoped signals, persisted in the existing PostgreSQL DB."""
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, text
from core.auth import get_current_user, RoleChecker
from core.database import get_db, L6SignalState
from shared.alert_signals import signals, reconcile

router = APIRouter()
writer = RoleChecker(['platform_administrator', 'analyst', 'compliance_head', 'data_steward'])


def tenant(user):
    value = user.get('client_id')
    if not value or value == 'PLATFORM_GLOBAL':
        raise HTTPException(403, 'A private tenant is required for alert scans')
    return value


async def state(db, user, lock=False):
    key = tenant(user)
    if lock:
        await db.execute(text('SELECT pg_advisory_xact_lock(hashtext(:key))'), {'key': 'signals:' + key})
    row = (await db.execute(select(L6SignalState).where(L6SignalState.client_id == key))).scalar_one_or_none()
    if row is None and lock:
        row = L6SignalState(client_id=key, payload={})
        db.add(row)
    return row


def summary(row):
    alerts = list(row.payload.values()) if row else []
    return dict(total=len(alerts), unacknowledged=sum(not a['isAcknowledged'] for a in alerts),
                critical_count=0, high_count=len(alerts), last_scan=row.scanned_at if row else None)


@router.get('/summary')
async def counts(user=Depends(get_current_user), db=Depends(get_db)):
    return summary(await state(db, user))


@router.get('')
@router.get('/')
async def listing(severity: str = None, acknowledged: bool = None,
                  limit: int = Query(100, ge=1, le=200), offset: int = Query(0, ge=0),
                  user=Depends(get_current_user), db=Depends(get_db)):
    row = await state(db, user)
    items = [a for a in (row.payload.values() if row else [])
             if (not severity or a['severity'] == severity)
             and (acknowledged is None or a['isAcknowledged'] == acknowledged)]
    items.sort(key=lambda a: (a['createdAt'], a['alertId']), reverse=True)
    return {**summary(row), 'matching': len(items), 'alerts': items[offset:offset + limit]}


@router.post('/scan')
async def scan(user=Depends(writer), db=Depends(get_db)):
    row = await state(db, user, True)
    params = {'tenant': tenant(user)}
    objects = (await db.execute(text('SELECT object_type, primary_key, properties FROM ontology_objects WHERE client_id=:tenant AND NOT is_deleted ORDER BY object_type, primary_key LIMIT 5001'), params)).fetchall()
    links = (await db.execute(text('SELECT * FROM ontology_links WHERE client_id=:tenant LIMIT 10001'), params)).fetchall()
    if len(objects) > 5000 or len(links) > 10000:
        raise HTTPException(422, 'Scan limit exceeded: 5000 entities / 10000 links. Previous alerts retained.')
    graph = {'nodes': [{**o.properties, 'object_type': o.object_type, 'entityId': o.primary_key} for o in objects],
             'edges': [dict(sourceLabel=e.source_type, sourcePK=e.source_id, targetLabel=e.target_type,
                            targetPK=e.target_id, type=e.link_type, isInferred=e.is_inferred, properties=e.properties) for e in links]}
    now = datetime.now(timezone.utc)
    row.payload = reconcile(row.payload, signals(graph), now.isoformat())
    row.scanned_at = now
    await db.commit()
    return summary(row)


@router.patch('/{alert_id}/acknowledge')
async def acknowledge(alert_id: str, user=Depends(writer), db=Depends(get_db)):
    row = await state(db, user, True)
    if alert_id not in row.payload:
        raise HTTPException(404, 'Alert not found')
    payload = dict(row.payload)
    payload[alert_id] = {**payload[alert_id], 'isAcknowledged': True,
                         'acknowledgedBy': user['sub'], 'acknowledgedAt': datetime.now(timezone.utc).isoformat()}
    row.payload = payload
    await db.commit()
    return payload[alert_id]


@router.get('/{alert_id}')
async def detail(alert_id: str, user=Depends(get_current_user), db=Depends(get_db)):
    row = await state(db, user)
    if not row or alert_id not in row.payload:
        raise HTTPException(404, 'Alert not found')
    return row.payload[alert_id]
