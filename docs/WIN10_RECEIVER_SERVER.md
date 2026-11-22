# Win10 局域网接收端：iPhone 只用 Safari

推荐拓扑：

```text
断网发送电脑 ── 屏幕动态二维码 ──> iPhone Safari
                                     ↑ 只加载接收网页
                              Wi-Fi / 局域网 HTTPS
                                     ↑
                              另一台 Win10 服务器
```

发送电脑可以断网。iPhone 和服务器接入同一局域网，路由器可以断开外网。iPhone 用 Safari 打开局域网接收页，直接在手机上完成扫码、还原、SHA-256 校验和保存。服务器提供静态接收页以及首次配置时的公开证书下载。

## 1. 在 Win10 服务器准备

安装 Python 3.10 或更新版本。接收服务只用 Python 标准库，不需要安装发送端的 Pillow、qrcode、pytest，也不需要 Node.js。

在服务器上使用项目目录。若要单独部署接收服务，拷贝以下文件并保持相对位置。

```text
receiver-standalone.html
receiver_server.py
receiver_terminal_qr.py
receiver-qr.zip
start_receiver_server.cmd
prepare_receiver_https.ps1
LICENSE
docs/THIRD_PARTY_NOTICES.md
docs/WIN10_RECEIVER_SERVER.md
tools/mkcert.exe                 # 自行准备
```

从 [mkcert 官方发布页](https://github.com/FiloSottile/mkcert/releases) 准备适合 Windows 架构的可执行文件，重命名为 `mkcert.exe` 放入 `tools` 目录，或直接与 `prepare_receiver_https.ps1` 放在同一目录。脚本依次查找这两个位置及 PATH 中的 `mkcert.exe`，也可通过 `-MkcertPath` 指定文件。Python 安装包和 mkcert 可以提前下载后拷入；运行接收服务不需要互联网。

在 Win10 用 `ipconfig` 查看用于连接手机的 IPv4 地址，例如 `192.168.1.50`。建议在路由器设置 DHCP 地址保留，避免重启后 IP 改变。以下地址仅为示例，均须换成你的真实地址。

## 2. 生成 HTTPS 证书

在服务器的项目目录打开 PowerShell：

```powershell
.\prepare_receiver_https.ps1 -ServerAddress 192.168.1.50
```

脚本不联网下载，不导入系统信任库，不修改防火墙。mkcert 在该 Windows 用户下生成本地 CA，签发含服务器 IP 的证书，输出：

```text
certs/receiver.pem           # 服务器证书
certs/receiver-key.pem       # 服务器私钥
certs/rootCA.cer             # 提供给 iPhone 安装的公开根证书
certs/server-address.txt     # 启动时显示的地址
```

`rootCA-key.pem` 保留在 mkcert 的 CA 目录，不要发给手机或放到网站。脚本显示 `rootCA.cer` 的 SHA-256，手机安装前确认下载来源是你自己的 Win10 服务器。若执行策略阻止 `.ps1`，可由管理员按本机策略允许脚本，或手动运行以下等价步骤；无需绕过执行策略：

```powershell
New-Item -ItemType Directory -Path certs -Force
.\tools\mkcert.exe -cert-file certs\receiver.pem -key-file certs\receiver-key.pem 192.168.1.50 localhost 127.0.0.1
$receiverCaRoot = .\tools\mkcert.exe -CAROOT
certutil -decode "$receiverCaRoot\rootCA.pem" certs\rootCA.cer
```

脚本不覆盖现有证书。IP 改变后，先保留旧文件备份，再移走 `receiver.pem`、`receiver-key.pem` 并用新 IP 生成；在同一用户、同一个 mkcert CA 下重签通常无需在手机重新安装根证书。

## 3. 首次启动和 iPhone 信任

在 Win10 启动：

```powershell
.\start_receiver_server.cmd --bootstrap-ca
```

初次配置使用 TCP 8443（HTTPS 接收端）和 8000（只下载公开根证书）。如果 Windows 防火墙弹窗，请只放行需要的网络。必要时，在管理员 PowerShell 明确添加仅限专用网络、本地子网的规则：

```powershell
New-NetFirewallRule -DisplayName "QFS Receiver HTTPS" -Direction Inbound -Action Allow -Protocol TCP -LocalPort 8443 -Profile Private -RemoteAddress LocalSubnet
New-NetFirewallRule -DisplayName "QFS Receiver CA Setup" -Direction Inbound -Action Allow -Protocol TCP -LocalPort 8000 -Profile Private -RemoteAddress LocalSubnet
```

若当前网络为 Public，应先由你确认是否将这个可信局域网设为 Private；上述规则不对 Public 网络生效。

iPhone 连接该局域网 Wi-Fi，用 Safari 打开 `http://192.168.1.50:8000/rootCA.cer`，允许下载描述文件。根据系统提示进入设置安装，通常位于“设置 → 通用 → VPN 与设备管理”。再到“设置 → 通用 → 关于本机 → 证书信任设置”，为该根证书启用完全信任。这是系统证书设置，不需要安装 App。

然后用 Safari 打开：

```text
https://192.168.1.50:8443/
```

必须使用证书包含的同一个 IP，手机系统日期时间应正确。应在无证书警告的情况下打开；仅点击“继续访问”不能代替正确的证书信任。普通 `http://服务器IP` 不满足摄像头安全上下文要求。

安装完成后，按 Ctrl+C 停止服务，正常启动：

```powershell
.\start_receiver_server.cmd
```

此时不监听 8000，只保留 HTTPS。初次设置的防火墙规则也可以删除：

```powershell
Remove-NetFirewallRule -DisplayName "QFS Receiver CA Setup"
```

## 4. 传输与验收

1. 路由器断开外网，iPhone 关闭蜂窝数据但保留局域网 Wi-Fi。
2. 确认发送电脑无网络连接，在发送电脑运行 `run_sender.cmd "待传文件夹" --fps 8`。
3. Safari 访问 Win10 的 HTTPS 地址，点击“开始接收”，允许使用摄像头。
4. 对准发送电脑二维码，等待还原和 SHA-256 校验通过，直接下载 ZIP 或通过系统分享存储到“文件”。

网页完整加载后，扫码、还原、校验和下载可在手机本地完成。刷新页面会重新向服务器加载网页，并清空接收进度。

服务默认监听 `0.0.0.0:8443`。如果仅允许某个接口，可传 `--bind 192.168.1.50`；改 HTTPS 端口使用 `--port 9443`。证书只绑定主机/IP，不绑定端口。

## 启动时扫码打开接收页

运行 `start_receiver_server.cmd` 后，CMD 或 PowerShell 中会显示接收页地址二维码。使用 iPhone 系统相机扫描，点击识别出的链接即可在 Safari 打开。二维码使用当前 `certs/server-address.txt` 中的地址及实际服务端口，手机仍需已信任该服务器证书。手机与服务器连接同一可互通的局域网即可，无需互联网。

二维码生成代码已经随部署包附带，不需要 pip 安装依赖。请将 `receiver_terminal_qr.py` 与 `receiver-qr.zip` 保留在启动脚本同目录。使用等宽字体，避免窗口窄到折行。传入 `--no-terminal-qr` 可只输出文字地址。

