import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PATCH = ROOT / 'frontend/case-velociraptor.patch'
BUILD = ROOT / 'frontend/build.sh'


class CaseVelociraptorPatchTests(unittest.TestCase):
    def test_patch_contains_dialog_history_card_and_shared_utilities(self):
        text = PATCH.read_text(encoding='utf-8')
        paths = set(re.findall(r'^diff --git a/(.+?) b/', text, re.MULTILINE))
        required = {
            'src/lib/utils/velociraptor.ts',
            'src/lib/utils/__tests__/velociraptor.test.ts',
            'src/lib/utils/velociraptor-jobs.ts',
            'src/lib/utils/__tests__/velociraptor-jobs.test.ts',
            'src/routes/(app)/case/[case_id]/+layout.svelte',
            'src/routes/(app)/case/[case_id]/+page.svelte',
            'src/routes/(app)/case/[case_id]/components/VelociraptorCollectDialog.svelte',
            'src/routes/(app)/case/[case_id]/components/VelociraptorJobsCard.svelte',
        }
        self.assertEqual(set(), required - paths)
        self.assertIn('<VelociraptorJobsCard caseId={case_id} />', text)
        self.assertIn('incident_id=${positiveInteger(caseId)}', text)
        self.assertIn('velociraptorEvidenceHref', text)
        self.assertIn('velociraptorEvidenceRetryUrl', text)
        self.assertIn('/retry-evidence', text)
        self.assertIn("body: 'confirm=yes'", text)
        self.assertIn('result?.recovery_available === true', text)

    def test_build_substitutes_both_components_without_committing_secrets(self):
        text = BUILD.read_text(encoding='utf-8')
        self.assertIn('VelociraptorCollectDialog.svelte', text)
        self.assertIn('VelociraptorJobsCard.svelte', text)
        patch = PATCH.read_text(encoding='utf-8')
        self.assertIn('__TB_KEY__', patch)
        self.assertIn('__TB_URL__', patch)
        self.assertIn(
            "const jobsEndpoint = '__TB_URL__/velociraptor/jobs?key=__TB_KEY__';",
            patch,
        )


if __name__ == '__main__':
    unittest.main()
