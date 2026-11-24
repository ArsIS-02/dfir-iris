#!/usr/bin/env python3
"""Guard exact close-time rendering in both IRIS case-table implementations."""
from pathlib import Path


def main():
    custom = Path(__file__).resolve().parents[1]
    patch = (custom / "frontend" / "case-closed-at.patch").read_text()
    required = (
        "diff --git a/src/lib/components/common/cases-data-table.svelte",
        "accessorFn: (row) => row.closed_at ?? row.close_date",
        "diff --git a/src/routes/(app)/manage/cases/+page.svelte",
        "{formatDate(c.closed_at ?? c.close_date)}",
        "diff --git a/src/lib/types/resources/case.ts",
        "closed_at?: string | null;",
    )
    for fragment in required:
        assert fragment in patch, f"missing patch fragment: {fragment}"

    build = (custom / "frontend" / "build.sh").read_text()
    opened = build.index('apply "$ROOT/case-opened-at.patch"')
    closed = build.index('apply "$ROOT/case-closed-at.patch"')
    incidents = build.index('apply "$ROOT/incident-terminology.patch"')
    assert opened < closed < incidents, "case-closed-at patch is in the wrong build order"
    print("case-closed-at patch: both tables use exact closed_at with close_date fallback")


if __name__ == "__main__":
    main()
