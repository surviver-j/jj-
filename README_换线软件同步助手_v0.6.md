# 换线软件同步助手 v0.6

## 功能
- 通过公司 FTP 上传标准测试软件目录为 `package.zip`，同时上传 SHA-256 摘要文件。
- 按“项目 / 工单或版本 / 工站”路径下载并部署。
- 部署前备份已有目录；以合并覆盖方式部署，不主动删除目标目录中其他文件。
- ZIP 完整性检查、SHA-256 摘要存在时强制比对、部署后文件校验；失败时尝试恢复备份。
- 通用 INI/TXT 参数规则：扫描真实文件、选择 Section/Key、按 Windows 主机名保存每台电脑独立的参数值，并在应用前备份相关配置文件。
- 使用 Python 标准库，无需额外 pip 依赖。

## 运行
Windows 安装 Python 3.10 或更高版本后：
```powershell
python onekey_change_line_v0.6.py
```

## 打包为 EXE
在 Windows 命令提示符或 PowerShell 执行：
```powershell
python -m pip install pyinstaller
python -m PyInstaller --noconsole --onefile --clean --name 换线软件同步助手_v0.6 onekey_change_line_v0.6.py
```
生成文件位于 `dist\换线软件同步助手_v0.6.exe`。请在隔离测试电脑验证后再部署到产线。

## 首次配置提醒
1. FTP 地址、端口、账号和密码由操作员输入；程序仅保存服务器、端口和账号，不保存密码。
2. 先在标准电脑上选择并上传正确的软件目录；其他电脑选择相同的项目、工单/版本、工站后下载部署。
3. 在“本机 INI 参数”页扫描实际 INI 文件，人工确认准确的 Section 和 Key，再保存该电脑的本机值。程序不会自动猜测端口号或夹具编号的键名。
4. 请确认被扫描的 INI 文件位于所选部署目录内，避免产生不受支持的相对路径。
5. 请先用测试目录验证 FTP 路径权限、备份/回滚、文件编码和参数写入，再用于产线。

## 已知限制
- 这是源码交付，不是预先编译好的 Windows EXE；需在 Windows 环境自行打包。
- FTP 连接使用传统 FTP；若公司服务器要求 FTPS/SFTP，需要另行适配。
- 若服务器没有 `package.zip.sha256`，程序会提示无法与服务器摘要比对，但仍会检查 ZIP 完整性并计算本地摘要。
- 该工具不会推断 INI 参数含义。错误配置规则可能修改错误参数，使用前必须核对实际配置文件。
