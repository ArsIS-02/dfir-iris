#!/usr/bin/env python3
"""Guard exact-time rendering in both IRIS case-table implementations."""
from pathlib import Path


def main():
    patch = (Path(__file__).resolve().parents[1] / "frontend" / "case-opened-at.patch").read_text()
    required = (
        "diff --git a/src/lib/components/common/cases-data-table.svelte",
        "accessorFn: (row) => row.initial_date ?? row.open_date",
        "diff --git a/src/routes/(app)/manage/cases/+page.svelte",
        "{formatDate(c.initial_date ?? c.open_date)}",
        "diff --git a/src/lib/types/resources/case.ts",
        "initial_date?: string | null;",
    )
    for fragment in required:
        assert fragment in patch, f"missing patch fragment: {fragment}"
    print("case-opened-at patch: common table and Cases management use initial_date")


if __name__ == "__main__":
    main()
