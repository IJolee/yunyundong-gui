"""按文件白名单生成无私密配置、无旧 Git 历史的公开发布目录和 ZIP。"""
import configparser
from datetime import datetime
import hashlib
import json
import math
from pathlib import Path
import shutil
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parent
FILES = ['desktop.py', 'desktop_core.py', 'desktop_worker.py', 'main.py', 'history.py',
         'upload_test.py', 'walk_test.py', 'genSM4Key.py', 'start_gui.bat', 'start.bat',
         'setup.ps1', 'requirements.txt', 'requirements-desktop.txt', 'config.example.ini',
         'build_public_release.py', 'README_DESKTOP.md',
         'tools/__init__.py', 'tools/Login.py', 'tools/getUrl_Id.py', 'tools/drift.py',
         'tools/pace_changer.py', 'tools/account_profiles.py', 'tools/generate_test_fixture.py',
         'tools/runtime_guard.py', 'docs/make_guide.py', 'docs/QUICKSTART.md', 'docs/QUICKSTART.html',
         'demo_routes/README.md', 'docs/images/SCREENSHOT_MANIFEST.json',
         *[f'docs/images/{name}.png' for name in ('01-target-photo', '02-start-photo', '03-connections-photo',
                                                '04-http-photo', '05-account-photo', '06-history-photo')]]


def demo_route(radius, loops):
    # 完全人工构造的示例，坐标位于 (0,0) 附近，不来自任何个人记录。
    points = []
    total = 0.0
    from tools.generate_test_fixture import distance
    previous = None
    count = 600
    for i in range(count+1):
        angle = i/count*2*math.pi*loops
        coord = (math.cos(angle)*radius/111195, math.sin(angle)*radius/111195)
        if previous:
            total += distance(previous, coord)
        previous = coord
        points.append({'point': f'{coord[0]:.12f},{coord[1]:.12f}', 'runTime': str(i*3),
                       'speed': 5+0.6*math.sin(angle/2), 'runMileage': str(total),
                       'runStep': str(round(i*3*170/60)), 'runStatus': 1, 'isFence': 'Y'})
    return {'code': 200, 'synthetic': True, 'purpose': 'demo_only', 'data': {
        'recordMileage': total/1000, 'duration': count*3, 'recodePace': count*3/60/(total/1000),
        'recodeCadence': 170, 'recodeDislikes': 0, 'manageList': [], 'managePoints': '',
        'pointsList': points, 'recordStartTime': '2000-01-01 00:00:00',
        'recordEndTime': '2000-01-01 00:30:00'}}


def forbidden_values(root):
    values = set()
    for path in [root/'config.ini', *sorted((root/'accounts').glob('*.ini'))]:
        if not path.exists():
            continue
        c = configparser.ConfigParser(interpolation=None)
        c.read(path, encoding='utf-8')
        hostname = urlsplit(c.get('Yun', 'school_host', fallback='')).hostname
        if hostname and hostname not in ('localhost', '127.0.0.1', '::1'):
            values.add(hostname)
        for section in ('User', 'Login'):
            if c.has_section(section):
                for key in ('token', 'password', 'username', 'device_id', 'uuid', 'map_key'):
                    value = c.get(section, key, fallback='').strip()
                    if len(value) >= 6:
                        values.add(value)
    return values


def build(root=ROOT, output=None):
    root = Path(root)
    output = Path(output) if output else root/'release'/f'campus-motion-studio_{datetime.now():%Y%m%d_%H%M%S_%f}'
    output.mkdir(parents=True, exist_ok=False)
    for name in FILES:
        source = root/name
        if source.exists():
            target = output/name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, target)
        else:
            raise FileNotFoundError(f'发布文件缺失：{name}')
    shutil.copyfile(root/'README_DESKTOP.md', output/'README.md')
    ignored = '''.venv/
__pycache__/
*.pyc
config.ini
accounts/
desktop_state.json
logs/
tasks_else/
test_fixtures/
release/
dist/
*.pcap
*.pcapng
'''
    (output/'.gitignore').write_text(ignored, encoding='utf-8')
    (output/'ATTRIBUTION.md').write_text(
        '# 来源\n\n底层 CLI 基于 Zirconium233/yunForNewVersion：\n'
        'https://github.com/Zirconium233/yunForNewVersion\n\n'
        '桌面界面、配置隔离、离线测试生成和发布打包为本地扩展。\n'
        '保留上游代码中的作者说明；本包不替上游代码重新声明许可证。\n', encoding='utf-8')
    for name, radius, loops in [('tasklist_9.json', 150, 4), ('tasklist_6.json', 165, 4)]:
        folder = output/'demo_routes'
        folder.mkdir(exist_ok=True)
        (folder/name).write_text(json.dumps(demo_route(radius, loops), ensure_ascii=False, indent=2), encoding='utf-8')
    (output/'map.json').write_text(json.dumps({
        'origin_point': '0.001,0', 'mypoints': ['0,0.001', '-0.001,0', '0,-0.001']
    }, indent=2), encoding='utf-8')
    tests = output/'tests'
    tests.mkdir()
    for source in sorted((root/'tests').glob('test_*.py')):
        shutil.copyfile(source, tests/source.name)
    # 发布包初次启动没有真实配置；测试使用空白模板和人工演示路线。
    workflows = output/'.github/workflows'
    workflows.mkdir(parents=True)
    (workflows/'offline-tests.yml').write_text('''name: Offline tests
on: [push, pull_request]
jobs:
  test:
    runs-on: windows-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: '3.12'
      - run: python -m pip install -r requirements-desktop.txt
      - run: python -m unittest discover -s tests -v
''', encoding='utf-8')
    blocked = forbidden_values(root)
    for p in output.rglob('*'):
        if p.is_file():
            content = p.read_bytes()
            if any(secret.encode('utf-8') in content for secret in blocked):
                raise ValueError(f'发布审计未通过，文件包含本地账号或地址信息：{p.relative_to(output)}')
    manifest = {str(p.relative_to(output)): hashlib.sha256(p.read_bytes()).hexdigest()
                for p in sorted(output.rglob('*')) if p.is_file()}
    (output/'PUBLIC_MANIFEST.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding='utf-8')
    archive = shutil.make_archive(str(output), 'zip', root_dir=output)
    return output, Path(archive)


if __name__ == '__main__':
    directory, archive = build()
    print(f'发布目录：{directory}\nZIP：{archive}\n不包含账号、token、个人路线和原 .git 历史。')
