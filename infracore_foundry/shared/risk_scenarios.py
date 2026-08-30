"""Deterministic synthetic UI/integration scenarios, not calibrated risk models."""
VERSION = "synthetic-risk-scenarios/v1"
COMPONENTS = ("financialStress", "regulatoryExposure", "governanceIssues", "deliveryDelays")
# Independent scenario inputs. Caps: 35 + 30 + 20 + 15 = 100.
SCENARIOS = (
    ("Clearwater Stable", (0, 0, 0, 0)),
    ("Sunmeadow Minor Delay", (0, 0, 0, 15)),
    ("Pineharbor Review", (0, 30, 0, 0)),
    ("Ambervale Threshold", (25, 0, 0, 15)),
    ("Coppercloud Governance", (35, 0, 20, 0)),
    ("Redwillow Elevated", (35, 20, 0, 15)),
    ("Stormglass Multi Signal", (35, 30, 20, 0)),
    ("Crimsonpeak Maximum", (35, 30, 20, 15)),
    ("Mistfield Missing Metrics", (None, None, None, None)),
    ("Limebrook Below Medium", (24, 0, 0, 15)),
    ("Goldreef Below High", (34, 20, 0, 15)),
    ("Rubyshore High Boundary", (35, 0, 20, 15)),
)


def assessment(values):
    components = dict(zip(COMPONENTS, values))
    score = None if any(value is None for value in values) else min(100, sum(values))
    flags = [key for key, value in components.items() if value is not None and value > 0]
    return {
        "riskScore": score, "riskFlags": flags,
        "riskComponents": components, "riskMethod": VERSION,
        "riskAssessmentStatus": "UNASSESSED" if score is None else "ASSESSED",
        "riskExplanation": ("Unassessed: required scenario metrics are missing." if score is None else
            f"Synthetic rule score {score}/100: " + ", ".join(f"{key}={value}" for key, value in components.items()) + ".")
            + " Test data only; not a probability, production assessment, or allegation.",
    }


def build_risk_scenarios():
    objects, links = [], []
    for i in range(4):
        address = f"synthetic risk lab campus {i + 1}"
        objects.append(("address", {"normalizedAddress": address, "fullAddress": address,
            "synthetic": True, "scenarioDataset": VERSION, "riskScore": None, "riskFlags": []}))
    for i, (name, values) in enumerate(SCENARIOS, 1):
        company, director, project = f"TEST-RISK-C-{i:03}", f"TEST-RISK-D-{i:03}", f"TEST-RISK-P-{i:03}"
        common = {"synthetic": True, "scenarioDataset": VERSION}
        objects.append(("company", {**common, "cin": company, "name": f"SYNTHETIC RISK LAB {name}",
            "status": "active", **assessment(values)}))
        objects.append(("director", {**common, "din": director, "name": f"SYNTHETIC RISK LAB Person {i:02}",
            **assessment((0, 0, values[2], 0) if values[2] is not None else (None,) * 4)}))
        objects.append(("project", {**common, "projectId": project, "name": f"SYNTHETIC RISK LAB Project {i:02}",
            **assessment(values)}))
        for link_type, st, sid, tt, tid in (
            ("DIRECTED", "director", director, "company", company),
            ("OWNS_PROJECT", "company", company, "project", project),
            ("REGISTERED_AT", "company", company, "address", f"synthetic risk lab campus {(i - 1) % 4 + 1}"),
        ):
            links.append(dict(link_type=link_type, source_type=st, source_id=sid, target_type=tt,
                target_id=tid, properties={**common, "scenarioReference": f"{VERSION}:{i:03}"}))
    return objects, links
