#!/usr/bin/env python3
"""Регрессионная проверка custom CaseSchemaForAPIV2 в backend-контейнере."""
import datetime
import importlib.util
import os
import sys

os.environ.setdefault("POSTGRES_SERVER", "localhost")

from app import app  # noqa: E402


def main():
    if len(sys.argv) != 2:
        raise SystemExit("usage: test_case_initial_date_schema.py /path/to/marshables.py")
    spec = importlib.util.spec_from_file_location("iris_custom_marshables", sys.argv[1])
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    with app.app_context():
        schema = module.CaseSchemaForAPIV2()
        field = schema.fields.get("initial_date")
        assert field is not None, "initial_date is absent from the API schema"
        assert field.dump_only, "initial_date must remain server-owned"
        dumped = schema.dump({
            "initial_date": datetime.datetime(2026, 11, 23, 4, 4, 31, 123456),
        })
        assert dumped["initial_date"] == "2026-11-23T04:04:31.123456", dumped
        print("initial_date: present, dump_only, exact timestamp serialised")


if __name__ == "__main__":
    main()
