# 云运动 GUI｜区间随机数据 · 多账号管理 · 跑步/走路双模式

基于 [Zirconium233/yunForNewVersion](https://github.com/Zirconium233/yunForNewVersion) 合工大云运动跑步脚本扩展的本地 GUI 工具，面向新版 2 km 强制结束场景设计。适用于合工大及接口兼容的其他学校，具体兼容性以目标服务器为准。

通过可交互窗口完成多账号配置、History 历史路线下载与导入、路线预览，以及跑步和走路模式切换。支持设置里程（默认 2 km）、配速范围、步频与节奏变化，无需每次手工修改 JSON。

路线可从已有历史文件中随机选择并截取连续路段；跑步模式根据目标里程和配速区间生成随机总时长，并同步调整逐点配速、累计时间和里程。分段速度保留原路线的快慢特征，并可加入平滑变化，不再把每个点都写成同一个速度值。走路模式采用更缓和的节奏曲线，步频可独立设置。另保留原 JSON 回放、旧脚本高级菜单、执行日志与异常停止功能。

App 的轨迹颜色取决于其着色规则，即使速度有变化也可能显示为相近颜色；本项目不承诺“永不全红/全橙”或“完全模拟真人”。生成副本会保留合成测试标记，不能仅凭颜色或接口返回成功认定记录有效。

本工具在本机运行，不提供公开网页服务。默认生成离线副本；联网查询和提交是独立操作。请仅连接你有权使用的接口与测试账号。服务器接受请求与最终判定有效是两回事，窗口不会自动修改服务器任务类型或绕过认证要求。

## 图文上手教程

第一次使用建议打开 **[七步图文教程](docs/QUICKSTART.md)**：PCAPdroid 选择云运动 → 开始捕获 → 复制请求头 → GUI 保存账号 → History 下载 → 路线预览与执行。

也可以双击 [离线 HTML 教程](docs/QUICKSTART.html)，或查看 [演示路线与导入说明](demo_routes/README.md)。插图不含真实登录凭据；无需公开自己的抓包或 history 文件。

## Windows 安装与启动

安装 Python 3.10～3.13（包含 Tkinter），下载仓库后在项目目录执行：

```powershell
powershell -ExecutionPolicy Bypass -File .\setup.ps1
.\.venv\Scripts\python.exe .\desktop.py
```

也可以双击 `start_gui.bat`。Python 需要包含 Tcl/Tk；其他平台可以用 `python -m venv .venv`、安装 `requirements-desktop.txt` 后启动 `desktop.py`，但防休眠保护仅在 Windows 生效。

## 第一次使用

1. 在“账号管理”新增账号，填写自己的服务器基础地址及登录信息。可以粘贴请求头自动填写 token、设备信息、UUID 和版本，再保存。模板地址是本机占位地址，不是可用服务器。
2. 每个账号保存为独立的本机 INI；切换账号不会登录、退出或刷新 token。密码字段仅供原 CLI 登录流程使用，窗口不自动登录。token 失效时需要正常登录并更新。
3. 导入自己的 history/tasklist JSON，或先选 `demo_routes` 检查本地预览。演示路线是 (0,0) 附近的人工坐标，不是校园路线，也不包含有效踩点。
4. 在“History 记录”依次获取学期、历史列表、下载所选记录。请求仅针对当前所选账号；不同任务在独立进程运行，防止账号全局变量串用。
5. 设置运动模式、距离（默认 2 km）、配速、步频、节奏变化和随机种子。跑步默认平均 5～7 分/km、170 步/分钟；走路默认平均 9 分/km、120 步/分钟。走路模式不等于更换服务器上的业务任务类型。
6. 点击“生成本地副本与预览”。随机模式从目录中选择足够长的路线并截取连续路段，不拼接不相连的路径；随机种子留空时每次重新生成，填写数字可复现。
7. 核对路线、配速曲线和摘要。修改参数后必须重新生成，提交时会检查文件哈希，避免上传旧预览。平均配速限制不代表所有瞬时点都在同一区间，App 的颜色阈值也不由本窗口决定。
8. 如需提交，点击提交按钮并核对账号、地址、里程和时长。只有确认后才会创建服务器记录。“原 JSON 回放”沿用源文件参数，不进行合成；“高级菜单”可继续使用原 CLI 的导航、漂移和其他旧选项。

原路线文件不会被覆盖。生成器保留原 JSON 的踩点元数据，不虚构新增点，也不把保留视为已重新验证经过。点不足或路线过短时，需要使用正确的源文件。

旧导航模式的 `map.json` 在公开包中也是人工示例；如使用原脚本高级菜单中的导航，需要先配置自己的地图 Key 和实际导航控制点。高级旧接口是否可用取决于目标服务器，不属于离线测试验证范围。

## 执行与中断

窗口最多启动一个后台任务。日志会隐藏已保存的 token、密码、UUID、设备 ID 和地图 Key。手动停止、网络中断、认证失败会停止流程，不盲目重复提交。失败后先核对服务器上的未完成记录，再决定是否重新开始。

Windows 运行期间使用临时线程级电源请求阻止空闲睡眠，退出时恢复；它不覆盖合盖策略，也不能阻止手动睡眠。执行期间请保持开盖并保持网络稳定。

## 本机文件与公开发布

以下内容都是私密本机数据，不要上传 GitHub：

- `config.ini`、`accounts/`：账号和凭据，INI 为本机明文文件，应自行保护。
- `tasks_else/`：导入及下载的个人路线。
- `test_fixtures/`、`logs/`、`desktop_state.json`：生成记录、日志及使用状态。
- 抓包文件、虚拟环境和旧仓库的 `.git` 历史。

仓库仅分发 `config.example.ini` 空白模板与人工演示路线。发布时运行：

```powershell
.\.venv\Scripts\python.exe .\build_public_release.py
```

它按白名单生成全新的 `release/campus-motion-studio_.../` 和同名 ZIP，检查当前本机凭据及服务器 IP 是否混入。不要把整个开发目录或旧 Git 历史直接推送。

在 GitHub 新建空仓库后，可以直接将发布目录中的内容上传（不是 ZIP 文件本身），或者在该目录初始化全新的 Git 仓库：

```powershell
git init
git add .
git commit -m "Add desktop motion studio"
git branch -M main
git remote add origin https://github.com/YOUR_NAME/YOUR_REPOSITORY.git
git push -u origin main
```

不要将这里的占位地址原样用于上传。该操作由仓库所有者在自己的 GitHub 账号完成。

## 命令行兼容

```powershell
# 只生成，不联网
.\.venv\Scripts\python.exe .\upload_test.py -f .\accounts\YOUR_ACCOUNT.ini --mode run
.\.venv\Scripts\python.exe .\walk_test.py -f .\accounts\YOUR_ACCOUNT.ini

# 显式提交，使用原 CLI 上传流程
.\.venv\Scripts\python.exe .\upload_test.py -f .\accounts\YOUR_ACCOUNT.ini --mode run --upload
```

高级自定义参数在桌面窗口设置，默认命令行用法保留。运行离线测试：

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

测试覆盖参数及距离/时间一致性、账号隔离、路线随机截取、历史响应解析、上传中断停止、电源状态恢复及公开发布审计。测试通过不代表具体服务器已经接受或判定有效。

## 来源

底层命令行基于 [Zirconium233/yunForNewVersion](https://github.com/Zirconium233/yunForNewVersion)，桌面窗口、配置隔离和发布流程为扩展。原脚本及登录协议有学校和版本差异；保留原作者说明，不替上游代码重新声明许可证。
