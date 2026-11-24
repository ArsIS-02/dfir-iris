#!/usr/bin/env python3
"""Guard presentation-only Case → Incident terminology in IRIS."""
from pathlib import Path


def main():
    custom = Path(__file__).resolve().parents[1]
    patch = (custom / "frontend" / "incident-terminology.patch").read_text()
    required = (
        "diff --git a/src/lib/actions/incident-terminology.ts",
        "export function incidentDisplayText(value: string): string",
        "const observer = new MutationObserver",
        "<svelte:body use:incidentTerminology />",
        "diff --git a/src/lib/actions/__tests__/incident-terminology.test.ts",
        "'/api/v2/cases /case/42 case_id CaseService",
        "expect(button.textContent).toBe('Open Incidents')",
    )
    for fragment in required:
        assert fragment in patch, f"missing patch fragment: {fragment}"

    build = (custom / "frontend" / "build.sh").read_text()
    apply_order = (
        'git -C "$WORK/source" apply "$ROOT/case-opened-at.patch"',
        'git -C "$WORK/source" apply "$ROOT/incident-terminology.patch"',
    )
    positions = [build.index(fragment) for fragment in apply_order]
    assert positions == sorted(positions), "incident terminology must apply after opened-at"
    print("incident-terminology patch: display-only renaming and regression tests present")


if __name__ == "__main__":
    main()
