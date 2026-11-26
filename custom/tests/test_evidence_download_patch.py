import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PATCH = ROOT / 'frontend/evidence-download.patch'
BUILD = ROOT / 'frontend/build.sh'


class EvidenceDownloadPatchTests(unittest.TestCase):
    def test_patch_is_limited_to_evidence_download_and_tests(self):
        text = PATCH.read_text(encoding='utf-8')
        paths = set(re.findall(r'^diff --git a/(.+?) b/', text, re.MULTILINE))
        self.assertEqual(
            {
                'src/lib/utils/evidence-download.ts',
                'src/lib/utils/__tests__/evidence-download.test.ts',
                'src/lib/services/__tests__/case-datastore.service.test.ts',
                'src/routes/(app)/case/[case_id]/evidence/[evidence_id]/EvidenceDetailView.svelte',
                'src/routes/(app)/case/[case_id]/evidence/components/evidence-sidebar.svelte',
            },
            paths,
        )

    def test_download_uses_datastore_hash_match_and_authenticated_blob(self):
        text = PATCH.read_text(encoding='utf-8')
        self.assertIn('findEvidenceDatastoreFile', text)
        self.assertIn('file.file_sha256?.trim().toLowerCase() === expectedHash', text)
        self.assertIn('file.file_is_evidence === true', text)
        self.assertIn('datastore.fetchFileBlobUrl(currentFile.file_id)', text)
        self.assertIn('datastoreDownloadBlobUrl(', text)
        self.assertIn("'Download ZIP'", text)
        self.assertIn("'Download file'", text)
        self.assertIn('Export Evidence list as CSV', text)
        self.assertIn('disabled={isDownloading}', text)

    def test_build_applies_patch_after_existing_frontend_patches(self):
        text = BUILD.read_text(encoding='utf-8')
        previous = 'apply "$ROOT/incident-terminology.patch"'
        current = 'apply "$ROOT/evidence-download.patch"'
        self.assertIn(previous, text)
        self.assertIn(current, text)
        self.assertLess(text.index(previous), text.index(current))


if __name__ == '__main__':
    unittest.main()
