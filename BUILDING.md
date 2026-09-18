# Build v0.17.11

当前唯一支持的构建方式是手动运行 `build.sh`。此前实验性的 Finder 双击构建 App 已暂时移除，因为在下载目录中会受到 macOS Finder 权限与 bundle 路径解析影响。

```bash
chmod +x build.sh
./build.sh
```

构建脚本会先执行完整 Swift semantic `-typecheck`，再进入优化编译；因此跨文件作用域、缺失 helper、错误类型名等问题会在链接前直接报出。

如果 LLDB Python 检查失败，确认已安装完整 Xcode 并执行：

```bash
sudo xcode-select -s /Applications/Xcode.app/Contents/Developer
xcrun lldb -P
```

输出 App 位于项目构建目录；具体路径会由 `build.sh` 在成功时打印。
