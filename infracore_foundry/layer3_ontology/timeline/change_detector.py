from typing import Any
from deepdiff import DeepDiff


class ChangeDetector:
    def compute_diff(self, old: dict[str, Any], new: dict[str, Any]) -> list[dict]:
        diff = DeepDiff(old, new, ignore_order=True)
        changes = []

        for key, value in diff.get("values_changed", {}).items():
            field = key.replace("root['", "").replace("']", "")
            changes.append({
                "field": field,
                "old_value": value.get("old_value"),
                "new_value": value.get("new_value"),
            })

        for key in diff.get("dictionary_item_added", set()):
            field = str(key).replace("root['", "").replace("']", "")
            changes.append({"field": field, "old_value": None, "new_value": new.get(field)})

        for key in diff.get("dictionary_item_removed", set()):
            field = str(key).replace("root['", "").replace("']", "")
            changes.append({"field": field, "old_value": old.get(field), "new_value": None})

        return changes


change_detector = ChangeDetector()
