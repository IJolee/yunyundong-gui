"""Campus Motion Studio：本地 Tkinter 窗口，无浏览器服务和远程遥测。"""
import hashlib
import json
import os
from pathlib import Path
import queue
import subprocess
import sys
import threading
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

from desktop_core import ROOT, Library, USER_FIELDS, parse_headers, redact, read_conf, route_summary


class Desktop(tk.Tk):
    def __init__(self, root_dir=ROOT):
        super().__init__()
        self.root_dir = Path(root_dir)
        self.library = Library(root_dir)
        self.title('Campus Motion Studio · 校园运动工具箱')
        self.geometry('1180x830')
        self.minsize(1000, 720)
        self.configure(bg='#edf2f7')
        style = ttk.Style(self)
        style.theme_use('clam')
        style.configure('.', font=('Microsoft YaHei UI', 10))
        style.configure('TFrame', background='#edf2f7')
        style.configure('TLabel', background='#edf2f7')
        style.configure('TButton', padding=(12, 7))
        style.configure('Accent.TButton', background='#1d4ed8', foreground='white')
        style.configure('Treeview', rowheight=29)
        self.events = queue.Queue()
        self.process = None
        self.secrets = []
        self.profile_paths = {}
        self.profile_path = None
        self.current_fixture = None
        self.fixture_config = None
        self.fixture_hash = None
        self.preview = None
        self.term_items = []
        self.history_items = []
        self.busy_callback = None
        self.job_fixture = None
        self.status = tk.StringVar(value='就绪 · 所有账号和文件保存在本机')
        self.account_var = tk.StringVar()
        self.params = {}
        self.protocol('WM_DELETE_WINDOW', self.close_window)
        self.build_window()
        self.refresh_profiles()
        self.refresh_routes()
        self.refresh_records()
        self._poll_id = self.after(100, self.poll_events)

    def build_window(self):
        header = tk.Frame(self, bg='#102b4c', height=94)
        header.pack(fill='x')
        tk.Label(header, text='Campus Motion Studio', font=('Segoe UI', 23, 'bold'), fg='white', bg='#102b4c').pack(anchor='w', padx=24, pady=(14, 0))
        tk.Label(header, text='账号 · 路线 · 参数 · 预览 · 执行记录', fg='#c5d9f3', bg='#102b4c', font=('Microsoft YaHei UI', 10)).pack(anchor='w', padx=26, pady=(0, 12))
        top = ttk.Frame(self, padding=(18, 12))
        top.pack(fill='x')
        ttk.Label(top, text='当前账号').pack(side='left')
        self.account_combo = ttk.Combobox(top, textvariable=self.account_var, state='readonly', width=27)
        self.account_combo.pack(side='left', padx=10)
        self.account_combo.bind('<<ComboboxSelected>>', self.select_profile)
        ttk.Button(top, text='认证检查（只读）', command=self.auth).pack(side='left')
        ttk.Button(top, text='停止当前任务', command=self.stop_job).pack(side='right')
        ttk.Button(top, text='图文教程', command=self.open_guide).pack(side='right', padx=8)
        self.tabs = ttk.Notebook(self)
        self.tabs.pack(fill='both', expand=True, padx=18)
        for name in ('路线与预览', '账号管理', 'History 记录', '执行日志', '本地生成记录'):
            frame = ttk.Frame(self.tabs, padding=14)
            self.tabs.add(frame, text=name)
        self.build_route_tab(self.tabs.nametowidget(self.tabs.tabs()[0]))
        self.build_account_tab(self.tabs.nametowidget(self.tabs.tabs()[1]))
        self.build_history_tab(self.tabs.nametowidget(self.tabs.tabs()[2]))
        self.log = tk.Text(self.tabs.nametowidget(self.tabs.tabs()[3]), wrap='word', bg='#132238', fg='#d4e2f4', font=('Consolas', 10), state='disabled')
        self.log.pack(fill='both', expand=True)
        self.records = ttk.Treeview(self.tabs.nametowidget(self.tabs.tabs()[4]), columns=('time', 'account', 'mode', 'distance', 'duration', 'status'), show='headings')
        for key, title, width in [('time', '时间', 180), ('account', '账号', 130), ('mode', '模式', 80), ('distance', '公里', 65), ('duration', '秒', 70), ('status', '状态', 180)]:
            self.records.heading(key, text=title)
            self.records.column(key, width=width)
        self.records.pack(fill='both', expand=True)
        self.records.bind('<Double-1>', self.preview_saved_record)
        ttk.Label(self, textvariable=self.status, padding=(20, 10)).pack(fill='x')

    def build_route_tab(self, tab):
        controls = ttk.Frame(tab, width=365)
        controls.pack(side='left', fill='y', padx=(0, 16))
        controls_body = ttk.Frame(controls)
        controls_body.pack(side='top', fill='both', expand=True)
        scroll = tk.Canvas(controls_body, width=350, bg='#edf2f7', highlightthickness=0)
        bar = ttk.Scrollbar(controls_body, orient='vertical', command=scroll.yview)
        scroll.configure(yscrollcommand=bar.set)
        bar.pack(side='right', fill='y')
        scroll.pack(side='left', fill='both', expand=True)
        left = ttk.Frame(scroll)
        window = scroll.create_window(0, 0, window=left, anchor='nw')
        left.bind('<Configure>', lambda _: scroll.configure(scrollregion=scroll.bbox('all')))
        scroll.bind('<Configure>', lambda event: scroll.itemconfigure(window, width=event.width))
        ttk.Label(left, text='01  选择路线与运动参数', font=('Microsoft YaHei UI', 12, 'bold')).pack(anchor='w', pady=(0, 10))
        self.source_mode = tk.StringVar(value='random')
        ttk.Radiobutton(left, text='从目录随机选路线并截取连续路段', variable=self.source_mode, value='random', command=self.invalidate).pack(anchor='w')
        ttk.Radiobutton(left, text='使用下方选中的已有路线', variable=self.source_mode, value='selected', command=self.invalidate).pack(anchor='w')
        default_dir = self.root_dir/'tasks_else'
        if not list(default_dir.glob('*.json')) and (self.root_dir/'demo_routes').exists():
            default_dir = self.root_dir/'demo_routes'
        self.route_dir = tk.StringVar(value=str(default_dir))
        ttk.Entry(left, textvariable=self.route_dir, width=38).pack(fill='x', pady=5)
        ttk.Button(left, text='选择目录', command=self.choose_directory).pack(anchor='w')
        self.routes = ttk.Treeview(left, columns=('folder', 'file'), show='headings', height=7, selectmode='browse')
        self.routes.heading('folder', text='目录')
        self.routes.heading('file', text='文件')
        self.routes.column('folder', width=95)
        self.routes.column('file', width=215)
        self.routes.pack(fill='x', pady=8)
        self.routes.bind('<<TreeviewSelect>>', self.select_route)
        row = ttk.Frame(left)
        row.pack(fill='x')
        ttk.Button(row, text='导入 history JSON', command=self.import_file).pack(side='left')
        ttk.Button(row, text='刷新', command=self.refresh_routes).pack(side='left', padx=5)
        form = ttk.Frame(left)
        form.pack(fill='x', pady=10)
        defaults = {'mode': 'run', 'distance_km': '2.0', 'pace_min': '5', 'pace_max': '7', 'walk_pace': '9', 'cadence': '170', 'variation': '15', 'seed': ''}
        defaults.update(self.library.state.get('preferences', {}))
        labels = [('mode', '运动数据模式'), ('distance_km', '总长度（km）'), ('pace_min', '跑步配速下限（分/km）'), ('pace_max', '跑步配速上限（分/km）'), ('walk_pace', '走路平均配速（分/km）'), ('cadence', '步频（步/分钟）'), ('variation', '平滑节奏变化（%）'), ('seed', '随机种子（可留空）')]
        for i, (key, label) in enumerate(labels):
            ttk.Label(form, text=label).grid(row=i, column=0, sticky='w', pady=3)
            self.params[key] = tk.StringVar(value=defaults[key])
            if key == 'mode':
                entry = ttk.Combobox(form, textvariable=self.params[key], values=['run', 'walk'], state='readonly', width=16)
                entry.bind('<<ComboboxSelected>>', self.change_mode)
            else:
                entry = ttk.Entry(form, textvariable=self.params[key], width=19)
            entry.grid(row=i, column=1, padx=(12, 0), sticky='e')
            self.params[key].trace_add('write', lambda *_: self.invalidate())
        self.route_dir.trace_add('write', lambda *_: self.invalidate())
        actions = ttk.Frame(controls, padding=(0, 8, 16, 0))
        actions.pack(side='bottom', fill='x')
        ttk.Button(actions, text='02  生成本地副本与预览', style='Accent.TButton', command=self.generate).pack(fill='x', pady=3)
        ttk.Button(actions, text='03  提交当前预览的数据', command=self.upload_preview).pack(fill='x', pady=3)
        ttk.Button(left, text='原 JSON 回放（不改变数据）', command=self.replay_source).pack(fill='x', pady=5)
        ttk.Button(left, text='打开原脚本高级菜单', command=self.legacy_menu).pack(fill='x', pady=5)
        right = ttk.Frame(tab)
        right.pack(side='left', fill='both', expand=True)
        ttk.Label(right, text='路线与配速预览 · 本地绘制，无需地图密钥', font=('Microsoft YaHei UI', 12, 'bold')).pack(anchor='w', pady=(0, 10))
        self.summary = tk.StringVar(value='先导入路线或生成副本。默认只生成，不联网。')
        ttk.Label(right, textvariable=self.summary, wraplength=610).pack(anchor='w', pady=(0, 8))
        self.canvas = tk.Canvas(right, bg='white', height=350, highlightthickness=1, highlightbackground='#d6dee9')
        self.canvas.pack(fill='both', expand=True)
        self.canvas.bind('<Configure>', lambda _: self.draw_preview())
        self.chart = tk.Canvas(right, bg='white', height=125, highlightthickness=0)
        self.chart.pack(fill='x', pady=(8, 0))
        self.chart.bind('<Configure>', lambda _: self.draw_preview())
        ttk.Label(right, text='run / walk 控制生成数据，不会改变服务器的任务类型。\n保留源文件踩点字段；窗口不虚构额外踩点或重新核验经过情况。', foreground='#52637a', wraplength=610).pack(anchor='w', pady=8)

    def build_account_tab(self, tab):
        ttk.Label(tab, text='本机账号配置 · 密码和 token 不进入公开发布包', font=('Microsoft YaHei UI', 12, 'bold')).pack(anchor='w', pady=(0, 14))
        grid = ttk.Frame(tab)
        grid.pack(anchor='w')
        self.account_fields = {}
        fields = [('username', '账号 / 本地标识'), ('password', '密码（可选，本窗口不自动登录）'), ('token', 'Token'), ('device_id', 'Device ID'), ('device_name', '设备名称'), ('sys_edition', '系统版本'), ('uuid', 'UUID'), ('app_edition', 'App 版本'), ('school_host', '服务器基础地址（包含路径前缀）'), ('map_key', '高德 Key（旧导航模式可选）')]
        for i, (key, label) in enumerate(fields):
            ttk.Label(grid, text=label).grid(row=i, column=0, sticky='w', pady=6)
            v = tk.StringVar()
            self.account_fields[key] = v
            ttk.Entry(grid, textvariable=v, width=75, show='•' if key in ('password', 'token', 'map_key') else '').grid(row=i, column=1, padx=14, sticky='w')
        buttons = ttk.Frame(tab)
        buttons.pack(anchor='w', pady=16)
        ttk.Button(buttons, text='新增账号', command=self.new_profile).pack(side='left', padx=(0, 8))
        ttk.Button(buttons, text='从请求头填写', command=self.paste_headers).pack(side='left', padx=8)
        ttk.Button(buttons, text='保存本机配置', style='Accent.TButton', command=self.save_profile).pack(side='left', padx=8)
        ttk.Button(buttons, text='检查所选已保存账号', command=self.auth).pack(side='left', padx=8)
        ttk.Label(tab, text='新增账号需要填写自己的服务器地址及登录凭据。修改表单后请先保存。\n切换账号只切换本机配置；不会替你登录、退出或刷新服务器会话。', foreground='#52637a').pack(anchor='w', pady=12)

    def build_history_tab(self, tab):
        row = ttk.Frame(tab)
        row.pack(fill='x', pady=(0, 12))
        ttk.Button(row, text='1  获取学期（联网只读）', command=self.fetch_terms).pack(side='left')
        self.term_var = tk.StringVar()
        self.term_combo = ttk.Combobox(row, textvariable=self.term_var, state='readonly', width=35)
        self.term_combo.pack(side='left', padx=10)
        ttk.Button(row, text='2  获取历史列表', command=self.fetch_history).pack(side='left')
        ttk.Button(row, text='3  下载所选记录到路线库', command=self.download_history).pack(side='left', padx=10)
        self.history_tree = ttk.Treeview(tab, columns=('time', 'km', 'pace', 'duration'), show='headings', selectmode='browse')
        for key, title in [('time', '开始时间'), ('km', '里程 km'), ('pace', '配速'), ('duration', '时长 秒')]:
            self.history_tree.heading(key, text=title)
            self.history_tree.column(key, width=170)
        self.history_tree.pack(fill='both', expand=True)
        ttk.Label(tab, text='仅读取当前账号的历史记录；下载后可在“路线与预览”中使用。无需手工运行 history.py。').pack(anchor='w', pady=12)

    def safe(self, action):
        try:
            return action()
        except Exception as exc:
            messagebox.showerror('操作未完成', redact(exc, self.secrets), parent=self)

    def open_guide(self):
        def action():
            import webbrowser
            guide = self.root_dir/'docs/QUICKSTART.html'
            if not guide.is_file():
                raise FileNotFoundError('未找到 docs/QUICKSTART.html，请使用完整发布包')
            webbrowser.open(guide.resolve().as_uri())
        self.safe(action)

    def refresh_profiles(self, selected=None):
        profiles = self.library.profiles()
        self.profile_paths = {name: path for name, path in profiles}
        self.account_combo['values'] = list(self.profile_paths)
        chosen = next((name for name, p in profiles if selected and p == Path(selected)), None)
        self.account_var.set(chosen or (profiles[0][0] if profiles else ''))
        self.select_profile()

    def select_profile(self, _=None):
        self.profile_path = self.profile_paths.get(self.account_var.get())
        self.invalidate()
        self.term_items = []
        self.term_combo['values'] = []
        self.term_var.set('')
        self.history_tree.delete(*self.history_tree.get_children())
        values = self.library.profile_values(self.profile_path) if self.profile_path else {}
        for key, var in self.account_fields.items():
            var.set(values.get(key, ''))
        self.load_secrets()

    def load_secrets(self):
        self.secrets = []
        for _, path in self.library.profiles():
            c = read_conf(path)
            for section, key in [('User', 'token'), ('Login', 'password'), ('User', 'map_key'), ('User', 'uuid'), ('User', 'device_id')]:
                self.secrets.append(c.get(section, key, fallback=''))

    def require_profile(self):
        if not self.profile_path:
            raise ValueError('请先新增并保存账号')
        return self.profile_path

    def new_profile(self):
        if self.process:
            messagebox.showinfo('任务运行中', '请等待当前任务结束后再新增账号', parent=self)
            return
        self.profile_path = None
        self.account_var.set('')
        c = read_conf(self.root_dir/'config.example.ini')
        for key, var in self.account_fields.items():
            var.set(c.get('Yun', key, fallback='') if key in ('app_edition', 'school_host') else '')
        self.invalidate()
        self.status.set('正在新增账号；填写完毕后点击保存')

    def save_profile(self):
        def save():
            if self.process:
                raise ValueError('当前有任务运行，请结束后再修改配置')
            values = {k: v.get() for k, v in self.account_fields.items()}
            path = self.library.save_profile(values, self.profile_path)
            self.refresh_profiles(path)
            self.status.set('已保存本机账号配置，未联网')
        self.safe(save)

    def paste_headers(self):
        dialog = tk.Toplevel(self)
        dialog.title('粘贴请求头（不会上传到其他服务）')
        text = tk.Text(dialog, width=90, height=20)
        text.pack(padx=12, pady=12)
        def apply():
            try:
                values = parse_headers(text.get('1.0', 'end'))
                for k, v in values.items():
                    if k in self.account_fields:
                        self.account_fields[k].set(v)
                dialog.destroy()
                self.status.set('已填写请求头信息，请确认所属账号后保存')
            except Exception as exc:
                messagebox.showerror('解析失败', str(exc), parent=dialog)
        ttk.Button(dialog, text='填写到表单（尚未保存）', command=apply).pack(pady=(0, 12))

    def refresh_routes(self):
        self.routes.delete(*self.routes.get_children())
        self.route_paths = {}
        for i, path in enumerate(self.library.routes()):
            self.route_paths[str(i)] = path
            self.routes.insert('', 'end', iid=str(i), values=(path.parent.name, path.name))

    def choose_directory(self):
        folder = filedialog.askdirectory(parent=self, initialdir=self.root_dir)
        if folder:
            self.route_dir.set(folder)

    def selected_route(self):
        selected = self.routes.selection()
        if not selected:
            raise ValueError('请先选中一个路线文件')
        return self.route_paths[selected[0]]

    def select_route(self, _=None):
        self.invalidate()
        self.safe(lambda: self.show_preview(self.selected_route(), source=True))

    def import_file(self):
        paths = filedialog.askopenfilenames(parent=self, title='导入 history / tasklist JSON', filetypes=[('JSON 文件', '*.json')])
        if not paths:
            return
        def action():
            for path in paths:
                target = self.library.import_route(path, self.account_var.get())
            self.refresh_routes()
            self.show_preview(target, source=True)
            self.status.set(f'已导入 {len(paths)} 份路线；原文件未修改')
        self.safe(action)

    def change_mode(self, _=None):
        walking = self.params['mode'].get() == 'walk'
        self.params['cadence'].set('120' if walking else '170')
        self.params['variation'].set('5' if walking else '15')

    def invalidate(self):
        self.current_fixture = None
        self.fixture_config = None
        self.fixture_hash = None
        if hasattr(self, 'status'):
            self.status.set('参数或选择已变化：请重新生成，再提交')

    def generate(self):
        def action():
            if self.process:
                raise ValueError('当前有任务运行，请结束后再生成')
            source = self.selected_route() if self.source_mode.get() == 'selected' else None
            parameters = {k: v.get() for k, v in self.params.items()}
            config = self.require_profile()
            path = self.library.generate(parameters, source, self.route_dir.get(), self.account_var.get())
            self.show_preview(path)
            self.current_fixture = path
            self.fixture_config = config
            self.fixture_hash = hashlib.sha256(path.read_bytes()).hexdigest()
            self.refresh_records()
            self.status.set('本地副本已生成；尚未联网或提交。可以检查路线与配速曲线。')
        self.safe(action)

    def show_preview(self, path, source=False):
        self.preview = route_summary(path)
        d = self.preview
        points = d['data']['data']['pointsList']
        speeds = [float(p['speed']) for p in points if 'speed' in p]
        pace = d['pace']
        pace_text = f'{float(pace):.2f}' if pace is not None else '—'
        self.summary.set(f"{'源文件' if source else '当前副本'}：{d['name']}\n坐标长度 {d['geometry_km']:.3f} km · 汇总 {d['reported_km']} km · 时长 {d['duration']} 秒\n平均配速 {pace_text} 分/km · 步频 {d['cadence']} · {len(points)} 个点" + (f' · 逐点配速 {min(speeds):.2f}～{max(speeds):.2f}' if speeds else ''))
        self.draw_preview()

    def draw_preview(self):
        if not self.preview:
            return
        self.canvas.delete('all')
        self.chart.delete('all')
        coords = self.preview['coords']
        import math
        lat = sum(p[1] for p in coords)/len(coords)
        planar = [(p[0]*math.cos(math.radians(lat)), -p[1]) for p in coords]
        xmin, xmax = min(x for x, y in planar), max(x for x, y in planar)
        ymin, ymax = min(y for x, y in planar), max(y for x, y in planar)
        w, h = max(100, self.canvas.winfo_width()), max(100, self.canvas.winfo_height())
        scale = min((w-70)/max(xmax-xmin, 1e-10), (h-60)/max(ymax-ymin, 1e-10))
        screen = [((x-(xmin+xmax)/2)*scale+w/2, (y-(ymin+ymax)/2)*scale+h/2) for x, y in planar]
        self.canvas.create_line(*[v for p in screen for v in p], fill='#2373dd', width=3, smooth=False)
        for p, color, title in [(screen[0], '#16a085', '起'), (screen[-1], '#e05a4f', '终')]:
            self.canvas.create_oval(p[0]-8, p[1]-8, p[0]+8, p[1]+8, fill=color, outline='white', width=2)
            self.canvas.create_text(p[0]+16, p[1]-10, text=title, fill=color)
        self.canvas.create_text(12, 16, text='路线几何示意 · 无地图底图 · 非 App 着色规则', anchor='w', fill='#64748b')
        points = self.preview['data']['data']['pointsList']
        paces = [float(p['speed']) for p in points if 'speed' in p]
        if len(paces) > 1:
            cw = max(100, self.chart.winfo_width())
            low, high = min(paces), max(paces)
            xy = [(35+i*(cw-60)/(len(paces)-1), 97-(v-low)/max(high-low, 0.01)*62) for i, v in enumerate(paces)]
            self.chart.create_text(12, 12, text=f'逐点配速（分/km）  {low:.2f}～{high:.2f}', anchor='w', fill='#52637a')
            self.chart.create_line(*[v for p in xy for v in p], fill='#bd7c1a', width=2)

    def upload_preview(self):
        def action():
            config = self.require_profile()
            if not self.current_fixture or self.fixture_config != config:
                raise ValueError('请先为当前账号生成预览；参数变化后必须重新生成')
            if hashlib.sha256(self.current_fixture.read_bytes()).hexdigest() != self.fixture_hash:
                self.invalidate()
                raise ValueError('文件已发生变化，请重新生成')
            self.confirm_upload('upload', self.current_fixture, self.fixture_hash)
        self.safe(action)

    def confirm_upload(self, action, path, digest):
        config = self.require_profile()
        c = read_conf(config)
        if not c.get('User', 'token', fallback='').strip():
            raise ValueError('所选账号缺少 token；请在账号管理中填写并保存')
        d = route_summary(path)
        host = c.get('Yun', 'school_host')
        text = f"账号：{self.account_var.get()}\n地址：{host}\n文件：{Path(path).name}\n里程：{d['reported_km']} km；时长：{d['duration']} 秒\n\n此操作会创建并提交服务器记录。确认执行？"
        if not messagebox.askyesno('确认提交当前数据', text, parent=self):
            return
        self.job_fixture = path
        self.start_job(action, ['--fixture', str(path), '--digest', digest], self.upload_finished)

    def replay_source(self):
        def action():
            source = self.selected_route()
            obj, _ = __import__('desktop_core').load_route(source)
            for key in ('duration', 'recordMileage', 'recodePace', 'recodeCadence', 'manageList', 'recodeDislikes'):
                if key not in obj['data']:
                    raise ValueError(f'原始 JSON 缺少 {key}，不能回放')
            self.confirm_upload('replay', source, hashlib.sha256(source.read_bytes()).hexdigest())
        self.safe(action)

    def upload_finished(self, code, result):
        if self.job_fixture:
            self.library.record_status(self.job_fixture, '结束请求已接受' if code == 0 else '已中断/失败，需核对服务器记录')
            self.job_fixture = None
        self.refresh_records()
        self.status.set('任务结束：服务器是否判定有效请在官方客户端核对' if code == 0 else '任务失败或中断，请查看日志及服务器未完成记录')

    def legacy_menu(self):
        def action():
            if self.process:
                raise ValueError('当前已有运行任务，请先结束')
            config = self.require_profile()
            flags = subprocess.CREATE_NEW_CONSOLE if os.name == 'nt' else 0
            process = subprocess.Popen([sys.executable, str(self.root_dir/'main.py'), '-f', str(config)], cwd=self.root_dir, creationflags=flags)
            self.process = process
            self.busy_callback = None
            self.account_combo.configure(state='disabled')
            threading.Thread(target=lambda: self.events.put(('done', (process.wait(), None))), daemon=True).start()
            self.status.set('原脚本高级菜单已打开；关闭独立控制台后窗口才允许启动其他任务')
        self.safe(action)

    def auth(self):
        self.safe(lambda: self.start_job('auth', [], lambda code, result: self.status.set('认证成功，任务数：'+str(result.get('tasks', 0)) if code == 0 and isinstance(result, dict) else '认证未成功，请查看日志')))

    def fetch_terms(self):
        def done(code, result):
            if code == 0 and isinstance(result, list):
                self.term_items = result
                values = [str(t.get('key', t.get('value', '学期'))) for t in result]
                self.term_combo['values'] = values
                self.term_var.set(values[0] if values else '')
                self.status.set(f'读取到 {len(values)} 个学期')
        self.safe(lambda: self.start_job('terms', [], done))

    def table(self):
        i = self.term_combo.current()
        if i < 0 or i >= len(self.term_items):
            raise ValueError('请先获取并选择学期')
        return str(self.term_items[i]['value'])

    def fetch_history(self):
        def done(code, result):
            if code == 0 and isinstance(result, list):
                self.history_items = result
                self.history_tree.delete(*self.history_tree.get_children())
                for i, r in enumerate(result):
                    self.history_tree.insert('', 'end', iid=str(i), values=(r.get('recordStartTime', r.get('endTime', '')), r.get('recordMileage', ''), r.get('recodePace', ''), r.get('duration', '')))
                self.status.set(f'读取到 {len(result)} 条历史记录')
        self.safe(lambda: self.start_job('history', ['--table', self.table()], done))

    def download_history(self):
        def action():
            selected = self.history_tree.selection()
            if not selected:
                raise ValueError('请先选中一条历史记录')
            record = self.history_items[int(selected[0])]
            account = self.account_var.get()
            def done(code, result):
                if code == 0 and isinstance(result, dict):
                    folder = self.root_dir/'tasks_else'
                    folder.mkdir(exist_ok=True)
                    from datetime import datetime
                    target = folder/f'tasklist_history_{datetime.now():%Y%m%d_%H%M%S_%f}.json'
                    target.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
                    self.library.state['imports'].append({'file': str(target), 'account': account, 'source': 'history'})
                    self.library.save_state()
                    self.refresh_routes()
                    self.show_preview(target, source=True)
                    self.status.set('历史记录已保存到本机路线库')
            self.start_job('download', ['--table', self.table(), '--record', str(record['id'])], done)
        self.safe(action)

    def start_job(self, action, args, callback):
        if self.process:
            raise ValueError('已有任务正在执行，请勿重复启动')
        config = self.require_profile()
        self.load_secrets()
        env = os.environ.copy()
        env['PYTHONIOENCODING'] = 'utf-8'
        env['PYTHONUNBUFFERED'] = '1'
        flags = (subprocess.CREATE_NO_WINDOW | subprocess.CREATE_NEW_PROCESS_GROUP) if os.name == 'nt' else 0
        command = [sys.executable, '-u', str(self.root_dir/'desktop_worker.py'), action, '--config', str(config), *args]
        process = subprocess.Popen(command, cwd=self.root_dir, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, encoding='utf-8', errors='replace', creationflags=flags)
        self.process = process
        self.busy_callback = callback
        self.account_combo.configure(state='disabled')
        self.status.set(f'正在执行 {action} · {self.account_var.get()}')
        self.append_log(f'开始 {action}，账号 {self.account_var.get()}')
        def reader():
            result = None
            for line in process.stdout:
                line = line.rstrip('\r\n')
                if line.startswith('DESKTOP_RESULT='):
                    try:
                        result = json.loads(line.split('=', 1)[1])
                    except ValueError:
                        pass
                elif line:
                    self.events.put(('log', line))
            self.events.put(('done', (process.wait(), result)))
        threading.Thread(target=reader, daemon=True).start()

    def poll_events(self):
        try:
            while True:
                kind, data = self.events.get_nowait()
                if kind == 'log':
                    self.append_log(data)
                else:
                    self.process = None
                    self.account_combo.configure(state='readonly')
                    code, result = data
                    self.append_log(f'后台进程退出码：{code}')
                    callback, self.busy_callback = self.busy_callback, None
                    if code != 0:
                        self.status.set('任务未成功，请查看执行日志')
                    if callback:
                        self.safe(lambda: callback(code, result))
        except queue.Empty:
            pass
        self._poll_id = self.after(100, self.poll_events)

    def append_log(self, message):
        from datetime import datetime
        text = f'[{datetime.now():%H:%M:%S}] {redact(message, self.secrets)}\n'
        self.log.configure(state='normal')
        self.log.insert('end', text)
        self.log.see('end')
        self.log.configure(state='disabled')
        folder = self.root_dir/'logs'
        folder.mkdir(exist_ok=True)
        with (folder/f'desktop_{datetime.now():%Y%m%d}.log').open('a', encoding='utf-8') as f:
            f.write(text)

    def stop_job(self):
        if not self.process:
            return
        if not messagebox.askyesno('停止当前任务', '停止后服务器可能留有未完成记录，程序不会自动重试或补发结束请求。确认停止？', parent=self):
            return
        if os.name == 'nt':
            subprocess.run(['taskkill', '/PID', str(self.process.pid), '/T', '/F'], capture_output=True, creationflags=subprocess.CREATE_NO_WINDOW)
        else:
            self.process.terminate()
        self.status.set('已请求停止；请核对服务器未完成记录')

    def refresh_records(self):
        self.records.delete(*self.records.get_children())
        self.record_paths = {}
        for i, r in enumerate(reversed(self.library.state['records'])):
            key = str(i)
            self.record_paths[key] = Path(r['file'])
            self.records.insert('', 'end', iid=key, values=(r.get('time'), r.get('account'), r.get('mode'), r.get('distance'), r.get('duration'), r.get('status')))

    def preview_saved_record(self, _=None):
        def action():
            selected = self.records.selection()
            if selected:
                self.invalidate()
                self.show_preview(self.record_paths[selected[0]])
                self.tabs.select(0)
        self.safe(action)

    def close_window(self):
        if self.process:
            self.stop_job()
            if self.process and self.process.poll() is None:
                return
        self.destroy()

    def destroy(self):
        if getattr(self, '_poll_id', None):
            self.after_cancel(self._poll_id)
            self._poll_id = None
        super().destroy()


if __name__ == '__main__':
    Desktop().mainloop()
