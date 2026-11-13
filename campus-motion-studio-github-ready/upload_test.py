"""生成测试副本；显式 --upload 时复用原 main.py 上传流程。"""
import argparse
import configparser
import json
import random
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime
from pathlib import Path

from tools.account_profiles import choose_profile
from tools.runtime_guard import prevent_idle_sleep
from tools.generate_test_fixture import ROOT, build_fixture


def generate_local(config_path, source=None, seed=None, source_dir=ROOT/'tasks_else', mode='run'):
    conf = configparser.ConfigParser()
    with Path(config_path).open(encoding='utf-8-sig') as f:
        conf.read_file(f)
    account = conf.get('Login', 'username', fallback='未设置')
    rng = random.Random(seed)
    if source is None:
        candidates = sorted(Path(source_dir).glob('tasklist_*.json'))
        rng.shuffle(candidates)
    else:
        candidates = [Path(source)]
    fixture = None
    rejected = []
    for candidate in candidates:
        try:
            with candidate.open(encoding='utf-8-sig') as f:
                original = json.load(f)
            fixture = build_fixture(original, rng, randomize=True, mode=mode)
        except (ValueError, KeyError, TypeError, OSError) as exc:
            if source is not None:
                raise
            rejected.append(f'{candidate.name}: {exc}')
            continue
        source = candidate
        break
    if fixture is None:
        raise ValueError('没有足够长且格式有效的路线。'+'；'.join(rejected))
    fixture['source_file'] = str(Path(source).resolve())
    fixture['generation_seed'] = seed
    fixture['test_account'] = account
    folder = ROOT/'test_fixtures'
    folder.mkdir(exist_ok=True)
    path = folder/f'local_test_{account}_{datetime.now():%Y%m%d_%H%M%S_%f}.json'
    with path.open('x', encoding='utf-8') as f:
        json.dump(fixture, f, ensure_ascii=False, indent=2)
    d = fixture['data']
    seconds = d['duration']/2
    print(f'本地测试账号：{account}')
    print('模式：' + ('走路（平均9分钟/km，小幅平缓变化）' if mode == 'walk' else '跑步'))
    window = fixture['source_window_m']
    print(f"源路线：{Path(source).name}；随机截取 {window['start']:.1f}～{window['end']:.1f} 米")
    print(f"2.00 km；配速 {int(seconds//60)}分{seconds%60:04.1f}秒/km；总时长 {d['duration']}秒")
    print(f"保留原踩点字段：manageList={len(d.get('manageList') or [])}项，recodeDislikes={d.get('recodeDislikes', '未提供')}")
    print('踩点信息沿用源文件，未重新验证截取后的路线是否经过全部点。')
    print(f'本地副本：{path}')
    print('未联网、未创建记录、未提交。原文件保留。')
    return path


def run_interactive(config_path, source_dir):
    sources = sorted(Path(source_dir).glob('*.json'))
    if not sources:
        raise ValueError('没有可用 JSON 路线')
    for index, source in enumerate(sources):
        print(f'{index}. {source.name}')
    choice = int(input('选择路线（-1 随机）：'))
    if choice == -1:
        return generate_local(config_path, source_dir=source_dir)
    elif 0 <= choice < len(sources):
        source = sources[choice]
    else:
        raise ValueError('无效路线序号')
    return generate_local(config_path, source)


def upload_with_original(config_path, fixture_path):
    """隔离出本次生成的一份 JSON，避免随机选中旧副本或结果文件。"""
    config_path = Path(config_path).resolve()
    fixture_path = Path(fixture_path).resolve()
    with tempfile.TemporaryDirectory(prefix='selected_', dir=ROOT/'test_fixtures') as folder:
        shutil.copyfile(fixture_path, Path(folder)/'tasklist_test.json')
        print('运行期间已启用空闲睡眠保护；请保持开盖，勿手动睡眠。', flush=True)
        with prevent_idle_sleep():
            return subprocess.run([
                sys.executable, str(ROOT/'main.py'), '-f', str(config_path),
                '-a', '-t', folder,
            ], cwd=str(ROOT)).returncode


def main(default_mode='run'):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('-f', '--config', type=Path)
    parser.add_argument('--source', type=Path, help='指定源文件；不指定时从路线目录随机选择')
    parser.add_argument('--source-dir', type=Path, default=ROOT/'tasks_else')
    parser.add_argument('--seed', type=int)
    parser.add_argument('--mode', choices=['run', 'walk'], default=default_mode, help='run 跑步；walk 走路（9分钟/km）')
    parser.add_argument('--upload', action='store_true', help='使用原脚本流程上传本次生成的测试副本')
    parser.add_argument('--check', action='store_true', help='仅检查本地配置与 JSON')
    args = parser.parse_args()
    if args.upload and args.check:
        parser.error('--check 和 --upload 不能同时使用')
    config = args.config or choose_profile(ROOT)
    if config:
        config = Path(config).resolve()
        target = generate_local(config, args.source, args.seed, args.source_dir, args.mode)
        if args.upload:
            print('现在调用原 main.py 上传上述测试副本；会创建并提交服务器记录。', flush=True)
            return upload_with_original(config, target)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
