# QR File Sender Free

**这是一个基于屏幕和摄像头的单向光学文件传输系统**

文件夹 → 打包成 ZIP → 计算整包 SHA-256 → 切分并封装数据包
      → 编码成二维码并循环播放 → 手机摄像头采集并解码
      → 逐包校验、去重、按编号重组 → 校验整包 SHA-256 → 下载或分享 ZIP

## 发送端

Windows 发送端需要 Python 3.10+（含 pip 和 Tkinter）。首次使用时按以下步骤准备：

1. 在联网电脑上解压项目，运行 `setup_sender.cmd`。脚本会把依赖下载到项目内的 `wheelhouse`。
2. 把项目连同 `wheelhouse` 复制到离线电脑。如果项目里已有 `.venv`，复制时跳过它。
3. 离线电脑使用与联网电脑相同主次版本和架构的 Python，例如两台都用 Python 3.12 x64。已有兼容的 Python 可以直接使用。
4. 双击离线电脑上的 `run_sender.cmd`，按提示输入待传文件夹路径。首次运行会在本机创建 `.venv` 并从 `wheelhouse` 安装依赖，后续运行直接使用本机已安装的依赖。

也可以直接传入文件夹路径和播放参数：

```powershell
.\run_sender.cmd "F:\qr_file_sender_free\testFile" --fps 15 --symbol-size 2899 --qr-ecc L
```

## 传输速度

和屏幕刷新率和手机性能相关，可使用手机支架提升稳定性

**参数说明**

fps：二维码播放速度

ecc L：纠错等级，L/M/Q/H四个等级，级别越高漏扫几率越小，但每张二维码可承载最大数据量也越小

symbol-size：每张二维码承载的信息量（ecc L支持上限2899）

iPhone 17 实测传输 6.6 MB 文件，使用 `--fps 15 --symbol-size 2899 --qr-ecc L`，漏扫率小于 1%，含手动补发的总用时小于 3 分钟。

macOS 可运行 `zsh setup_sender.command` 安装，再运行 `zsh run_sender.command "/路径/待传文件夹" --fps 8`。也可在装好 `requirements.txt` 后直接运行 `python -m sender`。

发送窗口每轮按编号从 `1` 播放到 `N`，期间定期显示文件信息帧 `0`。漏扫时，可在发送窗口按手机显示的缺失编号补发。

对比传输速度时，可以用 `--fps 12 --symbol-size 1600 --qr-ecc L` 测试更大的分片，再用 `--fps 12 --symbol-size 900 --qr-ecc M` 测试更强的单帧纠错。默认分片为 1200 字节，二维码纠错为 L。对比时保持二维码显示面积和机位一致，记录首轮到达率和校验通过的总用时。

分片上限取决于二维码编码器和纠错级别。超过上限时，发送端会提示并使用该上限。使用 ZXing-C++ 和 L 级纠错时，每个分片最多为 2899 字节。

打包后的 ZIP 最大可为 128 MiB，超过 20 MiB 时发送端会提示传输可能耗时较长。二维码内容未加密，能拍到屏幕的人也能尝试接收。

## 手机接收（GitHub Pages）

iPhone 可用 Safari（已实测）。Android 可用 Chrome（根据浏览器 API 支持情况判断，尚未进行 Android 真机测试）。

1. 在手机浏览器打开 [GitHub Pages 接收页](https://hnshdp-ui.github.io/qr_file_sender_free/)，点击“开始接收”并允许访问摄像头。
2. 将手机镜头对准电脑上的二维码并固定位置，再点击电脑发送窗口中的“播放”。
3. 需要补片时，将手机显示的编号填入电脑发送窗口，点击“仅补发列表”。详见 [播放控制与手动补发](docs/MANUAL_REPAIR.md)。
4. 接收完成并通过 SHA-256 校验后，点击“下载 ZIP”保存文件。

手机打开或刷新接收页时需要访问 GitHub Pages。页面加载后，扫码、还原与校验都在手机上完成。文件经过屏幕二维码传输，发送电脑运行时无需联网。

## 构建和测试

- `python scripts/build_standalone_receiver.py` 从 `web/` 生成 GitHub Pages 的 `dist/pages/index.html`。接收页已内置 ZXing-C++ WASM 和 jsQR，构建无需 npm。
- 使用安装了 `requirements.txt` 和 `pytest>=8,<9` 的 Python 运行 `python -m pytest -q`。二维码集成测试需要 Node.js。
- 使用 Node.js 22 或更新版本运行 `node --test tests/test_*.mjs`。接收测试默认调用项目的 `.venv`，也可用 `QFS_TEST_PYTHON` 指定已安装发送端依赖的 Python。

项目沿用 QFS1 v1 协议。参见 [协议参数](protocol/contract.json)、[MIT 许可](LICENSE)和[第三方组件声明](docs/THIRD_PARTY_NOTICES.md)。
