"""走路测试入口：默认 2 km，平均配速 9 分钟/km；--upload 才上传。"""
from upload_test import main


if __name__ == '__main__':
    raise SystemExit(main(default_mode='walk'))
