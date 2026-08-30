"""Bounded CSV mapping and validation; never interprets formulas or file paths."""
import csv
import hashlib
import io
import re
from datetime import date

FIELDS = {
    "company": {"id": True, "name": True, "status": False, "registeredAddress": False},
    "director": {"id": True, "name": True},
    "directorship": {"director_id": True, "company_id": True, "appointed_date": False},
}
ID = re.compile(r"^[A-Za-z0-9_.-]{1,100}$")


def parse_csv(kind, content, mapping):
    if kind not in FIELDS:
        raise ValueError("Unsupported record type")
    if len(content.encode("utf-8")) > 256_000:
        raise ValueError("CSV must be at most 256 KB")
    if "\x00" in content:
        raise ValueError("CSV contains null bytes")
    reader = csv.reader(io.StringIO(content.lstrip("\ufeff")), strict=True)
    try:
        headers = next(reader)
        if not headers or any(not h.strip() for h in headers) or len(set(headers)) != len(headers):
            raise ValueError("CSV requires unique, nonempty column headers")
        if len(headers) > 40:
            raise ValueError("Maximum 40 columns")
        if not mapping:
            return {"headers": headers, "fields": FIELDS[kind], "rows": [], "errors": []}
        if set(mapping) - set(FIELDS[kind]):
            raise ValueError("Unknown mapped field")
        for field, required in FIELDS[kind].items():
            if required and not mapping.get(field):
                raise ValueError(f"Map required field: {field}")
        selected = [v for v in mapping.values() if v]
        if len(set(selected)) != len(selected) or any(v not in headers for v in selected):
            raise ValueError("Each mapping must use a distinct existing CSV column")
        rows, errors, seen = [], [], set()
        for number, values in enumerate(reader, 2):
            if number > 201:
                raise ValueError("Maximum 200 data rows per import")
            if not values or not any(v.strip() for v in values):
                continue
            if len(values) != len(headers):
                errors.append({"row": number, "message": "Column count does not match header"})
                continue
            raw = dict(zip(headers, values))
            data = {k: raw[v].strip() for k, v in mapping.items() if v}
            messages = []
            for field, required in FIELDS[kind].items():
                value = data.get(field, "")
                if required and not value:
                    messages.append(f"{field} is required")
                if len(value) > 1000:
                    messages.append(f"{field} exceeds 1000 characters")
                if (field == "id" or field.endswith("_id")) and not ID.fullmatch(value):
                    messages.append(f"{field} must be a stable ID using letters, numbers, dot, underscore or hyphen")
            if data.get("appointed_date"):
                try:
                    date.fromisoformat(data["appointed_date"])
                except ValueError:
                    messages.append("appointed_date must be YYYY-MM-DD")
            key = data.get("id") or (data.get("director_id"), data.get("company_id"))
            if key in seen:
                messages.append("Duplicate identifier or relationship within file")
            seen.add(key)
            errors.extend({"row": number, "message": m} for m in messages)
            rows.append({"row": number, "data": data})
        if not rows and not errors:
            raise ValueError("CSV has no data rows")
        return {"headers": headers, "fields": FIELDS[kind], "rows": rows, "errors": errors,
                "sha256": hashlib.sha256(content.encode("utf-8")).hexdigest()}
    except (csv.Error, StopIteration) as exc:
        raise ValueError("Invalid or empty CSV") from exc
