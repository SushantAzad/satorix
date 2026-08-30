# Satorix application directory

See the [main project README](../README.md) for the problem statement, supported features, architecture, setup, demonstration workflow, tests, and limitations.

The active application is the **focused four-service configuration**: one React dashboard, two FastAPI services, and PostgreSQL. From this directory, start a prepared local environment with:

```powershell
.\scripts\start-focused.ps1
```

The launcher requires cached images and populated frontend dependency volumes. See the main README before using a fresh clone. Do not launch the historical full-stack `docker-compose.yml` expecting the focused application.

Additional documentation:

- [Focused architecture](FOCUSED_APP.md)
- [CSV import contract](CSV_IMPORT.md)
- [Relationship exposure](RELATIONSHIP_EXPOSURE.md)
- [Gemini setup and alerts](GEMINI_AND_ALERTS.md)

Historical connector, streaming, and ML modules remain in this directory. They are not advertised as supported features of the focused dashboard. Earlier production-grade/full-stack claims in this README are superseded by the main project README.
