"""本地账号配置选择；各账号的登录信息保存在独立 INI 文件中。"""
import configparser
from pathlib import Path


def list_profiles(root):
    root = Path(root)
    paths = [root / 'config.ini']
    paths.extend(sorted((root / 'accounts').glob('*.ini')))
    profiles = []
    for path in paths:
        if not path.is_file():
            continue
        conf = configparser.ConfigParser()
        with path.open(encoding='utf-8-sig') as source:
            conf.read_file(source)
        username = conf.get('Login', 'username', fallback='').strip()
        label = '原账号' if path == root / 'config.ini' else '账号'
        label += ' ' + (username or path.stem)
        profiles.append((label, str(path)))
    return profiles


def choose_profile(root, input_fn=input, output_fn=print):
    profiles = list_profiles(root)
    if not profiles:
        raise FileNotFoundError('没有找到账号配置，请检查 config.ini 或 accounts 目录')
    if len(profiles) == 1:
        return profiles[0][1]
    output_fn('请选择本次使用的账号：')
    for index, (label, _) in enumerate(profiles, 1):
        output_fn(f'  {index}. {label}')
    output_fn('  q. 退出')
    while True:
        choice = input_fn('账号序号（回车使用原账号）：').strip()
        if choice.lower() == 'q':
            return None
        if not choice:
            choice = '1'
        if choice.isdigit() and 1 <= int(choice) <= len(profiles):
            label, path = profiles[int(choice) - 1]
            output_fn(f'本次使用：{label}')
            return path
        output_fn('请输入有效序号，或输入 q 退出。')
