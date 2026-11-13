"""隔离网络会话的桌面后台进程，不会在账号之间共享 main 的全局变量。"""
import argparse
import gzip
import json
from pathlib import Path
import sys


def flatten_history(data):
    if isinstance(data, list):
        return data
    if not isinstance(data, dict):
        raise ValueError('历史列表格式错误')
    if 'rank' in data:
        return [r for month in data['rank'] for r in month.get('rankList', [])]
    return data.get('records', data.get('list', data.get('rows', [])))


def history_request(app, router, body=''):
    ctx = {}
    text = app.default_post(router, body if isinstance(body, str) else json.dumps(body), key_ctx=ctx)
    try:
        result = json.loads(text)
    except ValueError:
        result = None
    if not isinstance(result, dict):
        # 部分版本把密文包成 JSON 字符串；json.loads 成功不代表已解出业务对象。
        cipher = result if isinstance(result, str) else text
        raw = app.decrypt_sm4(cipher, app.b64decode(ctx['key']))
        if raw[:2] == b'\x1f\x8b':
            raw = gzip.decompress(raw)
        result = json.loads(raw)
    if not isinstance(result, dict) or str(result.get('code')) != '200':
        raise ValueError(f"接口未成功：{result.get('code') if isinstance(result, dict) else '格式错误'}")
    return result


def main():
    p = argparse.ArgumentParser()
    p.add_argument('action', choices=['auth', 'terms', 'history', 'download', 'upload', 'replay'])
    p.add_argument('--config', required=True)
    p.add_argument('--table')
    p.add_argument('--record')
    p.add_argument('--fixture')
    p.add_argument('--digest')
    args = p.parse_args()
    import main as app
    app.set_args(str(Path(args.config).resolve()))
    if args.action in ('upload', 'replay'):
        import hashlib
        from upload_test import upload_with_original
        path = Path(args.fixture).resolve()
        if hashlib.sha256(path.read_bytes()).hexdigest() != args.digest:
            raise ValueError('预览后的文件发生变化，请重新生成或预览，未创建记录')
        obj = json.loads(path.read_text(encoding='utf-8'))
        if args.action == 'upload' and obj.get('synthetic') is not True:
            raise ValueError('生成数据入口只接受明确标记的测试副本')
        return upload_with_original(args.config, path)
    if args.action == 'auth':
        result = history_request(app, '/run/getHomeRunInfo')
        data = result.get('data') or {}
        value = {'message': '认证成功', 'tasks': len(data.get('cralist') or [])}
    elif args.action == 'terms':
        value = history_request(app, '/run/listXnYearXqByStudentId').get('data') or []
    elif args.action == 'history':
        data = history_request(app, '/run/crsReocordInfoList', {'tableName': args.table}).get('data') or {}
        value = flatten_history(data)
    else:
        value = history_request(app, '/run/crsReocordInfo', {'id': args.record, 'tableName': args.table})
    print('DESKTOP_RESULT='+json.dumps(value, ensure_ascii=False), flush=True)
    return 0


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except Exception as exc:
        print('任务失败：'+str(exc), file=sys.stderr, flush=True)
        raise SystemExit(1)
