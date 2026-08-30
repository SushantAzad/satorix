"""Bounded, allowlisted evidence projection. Never send entire imported records."""
import hashlib
import json


def project_evidence(report):
    sections = report.get('sections', {})
    entity = sections.get('entity_record', {})
    props = entity.get('properties', entity)
    def keep(record, fields):
        return {k: (v[:500] if isinstance(v, str) else v) for k in fields
                if isinstance((v := record.get(k)), (str, int, float, bool)) or k in record and v is None}
    graph = sections.get('relationship_snapshot', {})
    payload = {
        'entity_type': report['entity_type'], 'entity_id': report['entity_id'],
        'synthetic': report.get('synthetic', False), 'snapshot_at': report.get('generated_at'),
        'entity': keep(props, ('name', 'companyName', 'status', 'synthetic', 'riskScore')),
        'recorded_risk': keep(sections.get('executive_summary', {}), ('risk_score', 'risk_band')),
        'nodes': [keep(n.get('properties', n), ('name', 'entityId', 'object_type', 'cin', 'din', 'riskScore', 'synthetic')) for n in graph.get('nodes', [])[:20]],
        'relationships': [keep(e, ('sourceLabel', 'sourcePK', 'targetLabel', 'targetPK', 'type', 'isInferred')) for e in graph.get('edges', [])[:40]],
        'coverage': {'partial': True, 'total_nodes': len(graph.get('nodes', [])), 'total_edges': len(graph.get('edges', [])),
                     'network_unavailable': graph.get('status') == 'unavailable'},
    }
    encoded = json.dumps(payload, sort_keys=True, ensure_ascii=True)
    if len(encoded.encode()) > 32000:
        raise ValueError('Evidence exceeds 32 KB limit')
    return payload, hashlib.sha256(encoded.encode()).hexdigest()
