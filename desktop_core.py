"""桌面窗口的本地服务层：不在导入时联网或读取账号凭据。"""
import configparser
import hashlib
import json
import math
from pathlib import Path
import random
import re
from datetime import datetime

from tools.generate_test_fixture import build_fixture, distance

ROOT = Path(__file__).resolve().parent
USER_FIELDS = ('token', 'device_id', 'device_name', 'sys_edition', 'uuid', 'map_key')
HEADER_FIELDS = {'token': 'token', 'deviceid': 'device_id', 'devicename': 'device_name',
                 'sysversion': 'sys_edition', 'uuid': 'uuid'}


def read_conf(path):
    c = configparser.ConfigParser(interpolation=None)
    with Path(path).open(encoding='utf-8-sig') as f:
        c.read_file(f)
    return c


def write_conf(c, path):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix('.ini.tmp')
    with temporary.open('w', encoding='utf-8') as f:
        c.write(f)
    temporary.replace(path)


def parse_headers(text):
    result = {}
    for line in text.splitlines():
        if ':' not in line:
            continue
        key, value = line.split(':', 1)
        key, value = key.strip().lower(), value.strip()
        if key in HEADER_FIELDS:
            result[HEADER_FIELDS[key]] = value
        elif key == 'version':
            result['app_edition'] = value
        elif key == 'host':
            result['school_host'] = 'http://' + value.rstrip('/') + '/m-api'
    if not result:
        raise ValueError('没有识别到 token、deviceId 等请求头字段')
    return result


def redact(text, secrets=()):
    value = str(text)
    for secret in sorted((s for s in secrets if s), key=len, reverse=True):
        value = value.replace(secret, '***')
    value = re.sub(r'(?i)\b(token|password|sign|map_key|deviceId|uuid)\s*[:=]\s*[^\s,}]+', r'\1: ***', value)
    return value


def load_route(path):
    with Path(path).open(encoding='utf-8-sig') as f:
        obj = json.load(f)
    data = obj.get('data', obj)
    if not isinstance(data, dict) or not isinstance(data.get('pointsList'), list):
        raise ValueError('需要包含 data.pointsList 的 history/tasklist JSON')
    coords = []
    for p in data['pointsList']:
        pair = tuple(map(float, p['point'].split(',')))
        if len(pair) != 2 or not all(math.isfinite(x) for x in pair) or not -180 <= pair[0] <= 180 or not -90 <= pair[1] <= 90:
            raise ValueError('经纬度格式错误')
        coords.append(pair)
    if len(coords) < 2:
        raise ValueError('路线至少需要两个坐标点')
    if 'data' not in obj:
        obj = {'code': 200, 'data': obj}
    return obj, coords


def route_summary(path):
    obj, coords = load_route(path)
    d = obj['data']
    length = sum(distance(a, b) for a, b in zip(coords, coords[1:]))
    return {'name': Path(path).name, 'path': str(Path(path).resolve()), 'points': len(coords),
            'geometry_km': length/1000, 'reported_km': d.get('recordMileage'),
            'duration': d.get('duration'), 'pace': d.get('recodePace'),
            'cadence': d.get('recodeCadence'), 'coords': coords, 'data': obj}


class Library:
    def __init__(self, root=ROOT):
        self.root = Path(root)
        self.state_path = self.root/'desktop_state.json'
        self.state = {'imports': [], 'records': [], 'preferences': {}}
        if self.state_path.exists():
            try:
                saved = json.loads(self.state_path.read_text(encoding='utf-8'))
                self.state.update(saved)
            except (ValueError, OSError):
                pass

    def save_state(self):
        self.state_path.write_text(json.dumps(self.state, ensure_ascii=False, indent=2), encoding='utf-8')

    def profiles(self):
        paths = [self.root/'config.ini', *sorted((self.root/'accounts').glob('*.ini'))]
        return [(c.get('Login', 'username', fallback=p.stem) or p.stem, p)
                for p in paths if p.exists() for c in [read_conf(p)]]

    def profile_values(self, path):
        c = read_conf(path)
        return {**{k: c.get('User', k, fallback='') for k in USER_FIELDS},
                'username': c.get('Login', 'username', fallback=''),
                'password': c.get('Login', 'password', fallback=''),
                'school_host': c.get('Yun', 'school_host', fallback=''),
                'app_edition': c.get('Yun', 'app_edition', fallback='3.6.7')}

    def save_profile(self, values, path=None):
        name = values['username'].strip()
        if not re.fullmatch(r'[A-Za-z0-9_-]{1,64}', name):
            raise ValueError('账号名称仅支持数字、字母、下划线和横线')
        target = Path(path) if path else self.root/'accounts'/f'{name}.ini'
        if path is None and (target.exists() or any(label == name for label, _ in self.profiles())):
            raise ValueError('该账号已存在，请从列表选择后编辑')
        template = self.root/'config.example.ini'
        c = read_conf(target if path else template)
        if path and c.get('Login', 'username', fallback='') not in ('', name):
            raise ValueError('不能直接修改已有配置所属账号；请新增账号')
        for section in ('Login', 'User', 'Yun'):
            if not c.has_section(section):
                c.add_section(section)
        for key in USER_FIELDS:
            c.set('User', key, values.get(key, '').strip())
        for key in ('utc', 'sign'):
            c.set('User', key, '')
        if c.has_option('User', 'sys_version'):
            c.set('User', 'sys_version', values.get('sys_edition', ''))
        for key in ('username', 'password'):
            c.set('Login', key, values.get(key, '').strip())
        host = values.get('school_host', '').strip().rstrip('/')
        if not host.startswith(('http://', 'https://')):
            raise ValueError('服务器地址必须以 http:// 或 https:// 开头')
        c.set('Yun', 'school_host', host)
        c.set('Yun', 'app_edition', values.get('app_edition', '3.6.7').strip())
        write_conf(c, target)
        return target

    def routes(self):
        paths = set()
        for name in ('tasks_else', 'tasks_fch', 'tasks_txl', 'tasks_xc', 'demo_routes'):
            paths.update((self.root/name).glob('*.json'))
        return sorted(paths, key=lambda p: (p.parent.name, p.name))

    def import_route(self, source, account=''):
        obj, _ = load_route(source)
        stamp = datetime.now().strftime('%Y%m%d_%H%M%S_%f')
        target = self.root/'tasks_else'/f'tasklist_import_{stamp}.json'
        target.parent.mkdir(exist_ok=True)
        target.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding='utf-8')
        self.state['imports'].append({'file': str(target), 'source': Path(source).name,
                                      'account': account, 'imported_at': stamp})
        self.save_state()
        return target

    def generate(self, parameters, source=None, source_dir=None, account=''):
        seed_text = str(parameters.get('seed', '')).strip()
        seed = int(seed_text) if seed_text else None
        rng = random.Random(seed)
        paths = [Path(source)] if source else list(Path(source_dir or self.root/'tasks_else').glob('*.json'))
        if not source:
            rng.shuffle(paths)
        options = {k: float(parameters[k]) for k in ('distance_km', 'pace_min', 'pace_max', 'walk_pace', 'cadence')}
        options['variation'] = float(parameters['variation'])/100
        errors = []
        for p in paths:
            try:
                obj, _ = load_route(p)
                fixture = build_fixture(obj, rng, randomize=True, mode=parameters['mode'], **options)
                break
            except (ValueError, KeyError, TypeError, OSError) as exc:
                if source:
                    raise
                errors.append(f'{p.name}: {exc}')
        else:
            raise ValueError('没有满足长度和格式要求的路线。\n'+'\n'.join(errors[:8]))
        fixture.update(test_account=account, source_file=str(p.resolve()), generation_seed=seed)
        folder = self.root/'test_fixtures'
        folder.mkdir(exist_ok=True)
        target = folder/f'desktop_{datetime.now():%Y%m%d_%H%M%S_%f}.json'
        target.write_text(json.dumps(fixture, ensure_ascii=False, indent=2), encoding='utf-8')
        digest = hashlib.sha256(target.read_bytes()).hexdigest()
        item = {'file': str(target), 'sha256': digest, 'account': account,
                'mode': parameters['mode'], 'distance': fixture['data']['recordMileage'],
                'duration': fixture['data']['duration'], 'status': '仅生成',
                'time': datetime.now().isoformat(timespec='seconds')}
        self.state['records'].append(item)
        self.state['preferences'] = parameters.copy()
        self.save_state()
        return target

    def record_status(self, path, status):
        for r in reversed(self.state['records']):
            if r['file'] == str(path):
                r['status'] = status
                break
        self.save_state()
