# Satorix mode controller

The supported local modes are mutually exclusive and use different Docker project
names and fresh data volumes. Historical `infracore_foundry` volumes remain
quarantined and are never mounted by any controller mode.

## Modes

- **Safe** is read-only except for login and the approved fixture-import operation.
- **Development** permits local API mutations against separate development data.
  It deliberately retains `LOCAL_SAFE_MODE=true`, the Python destination allowlist,
  the no-masquerade bridge, synthetic credentials, offline dependency settings and
  the self-only frontend CSP. External connectors, LLM/model loading, Airflow,
  streaming workers, background Kafka consumers and webhooks remain disabled.
- **Unrestricted** runs the original application entrypoints and normal network,
  with `LOCAL_SAFE_MODE=false`. It enables mutations, external connectors,
  webhooks, Airflow, streaming/background consumers, LLM providers, Ollama model
  initialization and dependency builds/installations. It can contact external
  systems, modify data and incur API or download charges.

Development v1 is therefore an offline application-development environment, not
the historical unrestricted Compose stack.

Unrestricted uses separate `satorix-unrestricted_*` volumes. It does not make
unsafe operations reversible and does not certify configured destinations or
credentials. Starting it requires an explicit acknowledgement switch.

## Commands

Run from `infracore_foundry` in PowerShell:

```powershell
.\scripts\status-satorix.ps1
.\scripts\start-satorix.ps1 -Mode Safe -CheckOnly
.\scripts\start-satorix.ps1 -Mode Safe
.\scripts\stop-satorix.ps1 -Mode Safe
.\scripts\start-satorix.ps1 -Mode Development -CheckOnly
.\scripts\start-satorix.ps1 -Mode Development
.\scripts\stop-satorix.ps1 -Mode Development
.\scripts\start-satorix.ps1 -Mode Unrestricted -CheckOnly
.\scripts\start-satorix.ps1 -Mode Unrestricted -AcknowledgeUnrestrictedRisk
.\scripts\stop-satorix.ps1 -Mode Unrestricted
```

To switch modes, stop the running mode first. Stop preserves its data volumes.
The controller refuses simultaneous modes because they intentionally share the
same loopback ports.

Use the synthetic credentials documented in `LOCAL_SAFETY_AUDIT.md`. Do not place
real credentials in the source tree or attempt to enable an integration by setting
an environment flag. External capabilities require a future reviewed allowlist.

Unrestricted is the explicit exception: create an uncommitted `.env` from
`.env.example`, replace every required placeholder, inspect all configured sources
and destinations, stop the other modes, then pass
`-AcknowledgeUnrestrictedRisk`. `-SkipBuild` is available only when current images
already contain the desired code. The controller never starts Unrestricted during
`-CheckOnly`.
