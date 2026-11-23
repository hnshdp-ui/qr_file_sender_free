# QR File Sender Free

电脑把文件夹打包成 ZIP，再通过屏幕循环播放二维码。iPhone 用 Safari 扫描，在手机上还原 ZIP，完成 SHA-256 校验后即可下载或分享。接收页无广告，支持 GitHub Pages 和本地离线部署。

## 发送端

Windows 安装 Python 3.10+（含 Tkinter），在项目目录运行：

```powershell
.\setup_sender.cmd
.\run_sender.cmd "D:\待传文件夹" --fps 8
```

macOS 可运行 `zsh setup_sender.command` 安装，再运行 `zsh run_sender.command "/路径/待传文件夹" --fps 8`。也可在装好 `requirements.txt` 后直接运行 `python -m sender`。

发送窗口每轮按编号从 `1` 播放到 `N`，期间定期显示文件信息帧 `0`。漏扫时，可在发送窗口按手机显示的缺失编号补发。

对比传输速度时，可以用 `--fps 12 --symbol-size 1600 --qr-ecc L` 测试更大的分片，再用 `--fps 12 --symbol-size 900 --qr-ecc M` 测试更强的单帧纠错。默认分片为 1200 字节，二维码纠错为 L。对比时保持二维码显示面积和机位一致，记录首轮到达率和校验通过的总用时。

分片上限取决于二维码编码器和纠错级别。超过上限时，发送端会提示并使用该上限。使用 ZXing-C++ 和 L 级纠错时，每个分片最多为 2899 字节。

打包后的 ZIP 最大可为 128 MiB，超过 20 MiB 时发送端会提示传输可能耗时较长。二维码内容未加密，能拍到屏幕的人也能尝试接收。

## iPhone 接收（GitHub Pages）

1. 将项目推送到自己的 GitHub 仓库，在 **Settings → Pages → Build and deployment → Source** 选择 **GitHub Actions**。
2. 在仓库的 **Actions** 页面选择 **Deploy receiver to GitHub Pages**，从默认分支运行 **Run workflow**。部署成功后，从 **Settings → Pages** 复制接收页链接。若仓库名是 `qr_file_sender_free`，默认地址为 `https://你的用户名.github.io/qr_file_sender_free/`。默认分支上的接收页源码更新会自动部署。参见 [GitHub Pages 发布设置](https://docs.github.com/en/pages/getting-started-with-github-pages/configuring-a-publishing-source-for-your-github-pages-site)。
3. 在 iPhone 的 Safari 打开接收页，点击“开始接收”并授权摄像头。固定镜头后，在电脑的发送窗口点击“播放”。校验通过后即可保存 ZIP。需要补片时，将手机显示的编号填入电脑窗口，点击“仅补发列表”。详见 [播放控制与手动补发](docs/MANUAL_REPAIR.md)。

手机首次打开或刷新页面时需要能访问 GitHub Pages。页面加载后，扫码、还原与校验都在手机上完成，文件经过屏幕二维码传输，接收页不会把文件上传到 GitHub。此方式无需启动 `start_receiver_server.cmd`，发送电脑可以断网，手机也无需和电脑连接同一局域网。

### 离线接收

现场无法访问 GitHub Pages 时，可按 [Windows 局域网 HTTPS 接收端](docs/WIN10_RECEIVER_SERVER.md) 使用 `start_receiver_server.cmd`。

手机本机也可运行单文件接收页。提前在 iPhone 安装 a-Shell 等带 Python 的工具，把 `receiver-standalone.html` 复制到本机，在该文件的目录执行 `python3 -m http.server 8000 --bind 127.0.0.1`，再用 Safari 打开 `http://127.0.0.1:8000/receiver-standalone.html`。相机权限需在目标 iPhone 上验证。

## 离线安装和部署包

在与目标 Windows 电脑使用相同 Python 版本和架构的联网机器上，运行 `python -m pip download --only-binary=:all: -r requirements.txt -d wheelhouse`。将项目、`wheelhouse` 和 Python 安装包拷入隔离电脑。安装 Python 后运行 `setup_sender_offline.cmd`，然后正常启动发送端。

- `python scripts/package_sender_offline.py` 将发送端及已准备的 wheel 打包。使用与目标匹配的 Windows Python 运行。
- `python scripts/package_receiver_server.py` 生成独立接收部署包。打包环境需要 `qrcode==8.2` 以生成内置终端二维码依赖。

## 构建和测试

- `python scripts/build_standalone_receiver.py` 从 `web/` 重新生成 `receiver-standalone.html`。接收页已内置 ZXing-C++ WASM 和 jsQR，构建无需 npm。
- 使用安装了 `requirements.txt` 和 `pytest>=8,<9` 的 Python 运行 `python -m pytest -q`。二维码集成测试需要 Node.js，HTTPS 测试通过 PowerShell 7 生成临时证书。
- 使用 Node.js 22 或更新版本运行 `node --test tests/test_*.mjs`。接收测试默认调用项目的 `.venv`，也可用 `QFS_TEST_PYTHON` 指定已安装发送端依赖的 Python。

项目沿用 QFS1 v1 协议。参见 [协议参数](protocol/contract.json)、[MIT 许可](LICENSE)和[第三方组件声明](docs/THIRD_PARTY_NOTICES.md)。
