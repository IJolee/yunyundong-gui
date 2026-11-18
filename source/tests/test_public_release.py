import configparser
import hashlib
import json
from pathlib import Path
import shutil
import tempfile
import unittest
import zipfile

import build_public_release as release


class PublicReleaseTests(unittest.TestCase):
    def test_archive_is_clean_and_manifest_matches(self):
        with tempfile.TemporaryDirectory() as folder:
            directory, archive = release.build(output=Path(folder)/'public')
            with zipfile.ZipFile(archive) as z:
                names = set(z.namelist())
                self.assertFalse(any(name.startswith(('.git/', 'accounts/', 'tasks_else/', 'logs/', 'test_fixtures/', '.venv/')) for name in names))
                self.assertNotIn('config.ini', names)
                self.assertIn('desktop.py', names)
                self.assertIn('config.example.ini', names)
                self.assertIn('demo_routes/tasklist_9.json', names)
                self.assertIn('docs/QUICKSTART.md', names)
                self.assertIn('docs/QUICKSTART.html', names)
                self.assertIn('docs/images/04-http-photo.png', names)
                self.assertIn('docs/images/05-account-photo.png', names)
                self.assertFalse(any(name.endswith('.svg') for name in names))
            manifest = json.loads((directory/'PUBLIC_MANIFEST.json').read_text(encoding='utf-8'))
            for name, digest in manifest.items():
                self.assertEqual(hashlib.sha256((directory/name).read_bytes()).hexdigest(), digest)
            c = configparser.ConfigParser()
            c.read(directory/'config.example.ini', encoding='utf-8')
            self.assertFalse(c.get('User', 'token'))
            self.assertFalse(c.get('Login', 'password'))

    def test_secret_in_source_prevents_archive_creation(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)/'source'
            root.mkdir()
            for name in release.FILES:
                target = root/name
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(release.ROOT/name, target)
            (root/'config.ini').write_text('[User]\ntoken=do-not-publish-this-token\n[Login]\nusername=demo_secret_account\n', encoding='utf-8')
            with (root/'desktop.py').open('a', encoding='utf-8') as f:
                f.write('\n# do-not-publish-this-token\n')
            output = Path(folder)/'blocked'
            with self.assertRaisesRegex(ValueError, '发布审计'):
                release.build(root=root, output=output)
            self.assertFalse(output.with_suffix('.zip').exists())


if __name__ == '__main__':
    unittest.main()
