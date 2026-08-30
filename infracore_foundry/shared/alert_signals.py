"""Deterministic review signals from recorded data, not AI findings."""
import hashlib
import json
import math
from shared.relationship_exposure import relationship_exposure


def signals(graph):
    result = {}
    for node in graph['nodes']:
        kind, key = node['object_type'], node['entityId']
        score = node.get('riskScore')
        valid = type(score) in (int, float) and math.isfinite(score) and 0 <= score <= 100
        findings = []
        if kind == 'company' and valid and score >= 70:
            findings.append(('RECORDED_HIGH_RISK', f'Recorded company risk is {score}/100.', {'score': score}))
        if kind in ('director', 'company'):
            exposure = relationship_exposure(kind, key, graph)
            companies = [dict(entity_id=c['entity_id'], score=c['score']) for c in exposure['companies'] if c['band'] == 'HIGH']
            if companies:
                findings.append(('RELATIONSHIP_EXPOSURE', f'Direct recorded links to {len(companies)} high-risk companies. Association is not evidence of wrongdoing.', {'companies': companies}))
        for rule, message, evidence in findings:
            identity = hashlib.sha256(json.dumps([kind, key, rule]).encode()).hexdigest()
            payload = dict(alertId=identity, severity='HIGH', alertType=rule,
                           title=('Synthetic · ' if node.get('synthetic') else '') + rule.replace('_', ' ').title(),
                           message=message, affectedEntityType=kind, affectedEntityId=key,
                           affectedEntityName=node.get('name', key), source='RULE_ENGINE', evidence=evidence,
                           isActive=True, isAcknowledged=False)
            payload['fingerprint'] = hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()
            result[identity] = payload
    return result


def reconcile(previous, fresh, now):
    for key, alert in fresh.items():
        old = previous.get(key, {})
        alert['createdAt'] = old.get('createdAt', now)
        if old.get('fingerprint') == alert['fingerprint'] and old.get('isActive'):
            for field in ('isAcknowledged', 'acknowledgedBy', 'acknowledgedAt'):
                if field in old:
                    alert[field] = old[field]
    return fresh
