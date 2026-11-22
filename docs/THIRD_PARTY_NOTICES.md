# 第三方组件声明

- Safari 接收页使用 jsQR 1.4.0（Apache-2.0）和 ZXing-C++ WASM reader（Apache-2.0）。接收页的 JavaScript 封装来自 zxing-wasm 3.1.2（MIT）。完整许可证随生成的 HTML 内嵌，也保存在源码的 `web/vendor/` 目录。来源见 [jsQR](https://github.com/cozmo/jsQR)、[ZXing-C++](https://github.com/zxing-cpp/zxing-cpp) 和 [zxing-wasm](https://github.com/Sec-ant/zxing-wasm)。
- 局域网接收服务器的地址二维码由内置的 Python `qrcode` 8.2 生成，Copyright (c) 2011 Lincoln Loop。`receiver-qr.zip` 附带原始 BSD 许可和未修改的 Python 源码。来源见 [python-qrcode](https://github.com/lincolnloop/python-qrcode)。
- Python 发送端通过 pip 安装 Pillow、ZXing-C++ 和 qrcode。安装包随附各自的许可证。
