#!/usr/bin/env python3
"""Regression check for exact close timestamps in CaseSchemaForAPIV2."""
import datetime
import importlib.util
import os
import sys

os.environ.setdefault("POSTGRES_SERVER", "localhost")

from app import app  # noqa: E402


def main():
    if len(sys.argv) != 2:
        raise SystemExit("usage: test_case_closed_at_schema.py /path/to/marshables.py")
    spec = importlib.util.spec_from_file_location("iris_custom_marshables_closed_at", sys.argv[1])
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    with app.app_context():
        schema = module.CaseSchemaForAPIV2()
        field = schema.fields.get("closed_at")
        assert field is not None, "closed_at is absent from the API schema"
        assert field.dump_only, "closed_at must remain server-owned"

        day_start = datetime.datetime(2026, 11, 23, tzinfo=datetime.timezone.utc).timestamp()
        case = {
            "close_date": datetime.date(2026, 11, 23),
            "modification_history": {
                "invalid": {"action": "case closed"},
                str(day_start + 1.25): {"action": "case closed"},
                str(day_start + 2.5): {"action": "case closed"},
                str(day_start + 3.0): {"action": "case reopened"},
            },
        }
        dumped = schema.dump(case)
        assert dumped["closed_at"] == "2026-11-23T00:00:02.500000", dumped

        case["close_date"] = None
        assert schema.dump(case)["closed_at"] is None, "reopened case exposes stale closed_at"
        case["close_date"] = datetime.date(2026, 11, 23)
        case["modification_history"] = {}
        assert schema.dump(case)["closed_at"] is None, "missing history must allow frontend fallback"

        original_activity_lookup = module.CaseSchemaForAPIV2._get_activity_closed_at
        try:
            module.CaseSchemaForAPIV2._get_activity_closed_at = staticmethod(
                lambda case_id, close_date: datetime.datetime(2026, 11, 22, 17, 8, 33, 455108)
            )
            legacy_case = {
                "case_id": 60,
                "close_date": datetime.date(2026, 11, 22),
                "modification_history": {
                    str(day_start): {"action": "case closed"},
                },
            }
            dumped = schema.dump(legacy_case)
            assert dumped["closed_at"] == "2026-11-22T17:08:33.455108", dumped
        finally:
            module.CaseSchemaForAPIV2._get_activity_closed_at = original_activity_lookup
        print("closed_at: dump_only, consistent history, legacy activity and reopened states correct")


if __name__ == "__main__":
    main()
