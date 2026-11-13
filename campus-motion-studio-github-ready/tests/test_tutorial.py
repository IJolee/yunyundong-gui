from html.parser import HTMLParser
import re
import unittest
from unittest.mock import patch
from types import SimpleNamespace
import hashlib
import json
import struct
from pathlib import Path

from desktop_core import ROOT


class References(HTMLParser):
    def __init__(self):
        super().__init__()
        self.local = []
        self.scripts = []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == 'script':
            self.scripts.append(attrs)
        value = attrs.get('src') if tag == 'img' else attrs.get('href')
        if value and not value.startswith(('http://', 'https://', '#', 'data:')):
            self.local.append(value.split('#', 1)[0])


class TutorialTests(unittest.TestCase):
    def test_gui_guide_opens_local_file_only(self):
        from desktop import Desktop
        fake = SimpleNamespace(root_dir=ROOT, safe=lambda action: action())
        with patch('webbrowser.open') as browser:
            Desktop.open_guide(fake)
        browser.assert_called_once_with((ROOT/'docs/QUICKSTART.html').resolve().as_uri())

    def test_html_links_images_and_no_scripts(self):
        path = ROOT/'docs/QUICKSTART.html'
        parser = References()
        parser.feed(path.read_text(encoding='utf-8'))
        self.assertFalse(parser.scripts)
        for link in parser.local:
            with self.subTest(link=link):
                # 开发目录可能没有名为 README.md 的本包说明，但项目自有 README 仍存在。
                self.assertTrue((path.parent/link).is_file())

    def test_six_supplied_screenshots_match_manifest(self):
        images = ROOT/'docs/images'
        manifest = json.loads((images/'SCREENSHOT_MANIFEST.json').read_text(encoding='utf-8'))
        self.assertEqual(len(manifest['images']), 6)
        for item in manifest['images']:
            with self.subTest(name=item['file']):
                blob = (images/item['file']).read_bytes()
                self.assertEqual(hashlib.sha256(blob).hexdigest(), item['output_sha256'])
                self.assertNotEqual(item['source_sha256'], item['output_sha256'])
                self.assertEqual(blob[:8], b'\x89PNG\r\n\x1a\n')
                # 确认公开图片未携带 EXIF 或文本元数据。
                offset = 8
                while offset < len(blob):
                    size = struct.unpack('>I', blob[offset:offset+4])[0]
                    kind = blob[offset+4:offset+8]
                    self.assertNotIn(kind, (b'eXIf', b'tEXt', b'iTXt', b'zTXt'))
                    offset += size+12
        content = (ROOT/'docs/QUICKSTART.html').read_text(encoding='utf-8')
        self.assertNotIn('.svg', content)

    def test_markdown_image_links_and_required_steps(self):
        path = ROOT/'docs/QUICKSTART.md'
        text = path.read_text(encoding='utf-8')
        for image in re.findall(r'!\[[^]]*\]\(([^)]+)\)', text):
            self.assertTrue((path.parent/image).is_file())
        for term in ('复制两者', '#2', '保存本机配置', '下载所选记录到路线库', '完整载荷', '非空', '人工演示路线'):
            self.assertIn(term if term != '非空' else 'token:', text)


if __name__ == '__main__':
    unittest.main()
