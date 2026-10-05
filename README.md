# 听声辨金

面向《暗区突围：无限》行商场景的 Windows 实时声音识别工具。它监听电脑正在播放的声音，识别本地音库中的物品音效，并用悬浮提示帮助玩家自己判断和购买高价值物品。

本项目只提供声音提示，不会自动购买或操作游戏。它通过 Windows 音频回环采集声音，不读取游戏内存、不注入游戏、不连接游戏服务器，也不模拟键鼠。项目与游戏官方及发行商无隶属关系；游戏名称仅用于说明用途。

## 功能

- 从系统扬声器回环采集音频并实时匹配本地音效模板。
- 支持离线 WAV 匹配、匹配结果列表和悬浮提示。
- 可为每个物品维护多个声音样本、匹配阈值、图标和提示名称。
- 同音组提示可能的大金与非大金物品及其仓库格子尺寸；唯一类直接标注为唯一类大金。
- 仓库附带 10 个默认物品条目及其声音样本和图标，克隆后即可体验识别。

## 环境

- Windows 10/11
- Python 3.12（建议）
- 扬声器或耳机的 WASAPI 回环采集支持

## 新手使用（Windows）

1. 从 GitHub 下载 ZIP 并解压到一个固定目录。
2. 安装 [Python 3.12](https://www.python.org/downloads/windows/)；安装时启用 Python Launcher。
3. 双击 `setup.bat`，等待虚拟环境和依赖安装完成。
4. 双击 `start_live.bat` 即可使用仓库附带的默认音库。将游戏设置为无边框窗口并正常播放声音；命中时悬浮窗会显示候选物品和格子信息。
5. 停止时在启动窗口按 `Ctrl+C`。

想换成自己的整套音库时，把兼容的 SoundRadar `.srz` 文件拖到 `import_library.bat` 上。导入会替换音库索引；建议先备份 `data/library/`。如只想替换某一个样本，可替换 `data/library/_raw/items/<条目ID>/samples/` 中的 WAV 文件，并保持 `items.json` 中的路径不变。

仓库提供 Windows 批处理启动方式，**当前没有打包好的 `.exe`**。启动脚本会检查环境和默认音库，并提示下一步操作。

## 手动安装

```powershell
py -3.12 -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
```

默认音库已随仓库提供，也可以用命令行启动：

```powershell
.venv\Scripts\python.exe main.py items
.venv\Scripts\python.exe main.py live --overlay
.venv\Scripts\python.exe main.py live --overlay --lang en
```

也可以双击 `start_live.bat` 启动悬浮提示。游戏建议使用无边框窗口，以便显示悬浮窗。

## 音库

默认音库随项目提供。你可以直接使用它，也可以备份后替换 `data/library/` 中的声音、图标和索引。公开候选分类与格子提示保存在 `data/catalog_hints.json`。

如果已有兼容的 SoundRadar `.srz` 音库，可以导入：

```powershell
.venv\Scripts\python.exe import_library.py --src "C:\path\to\library.srz"
```

导入器会在 `data/library/` 生成索引和原始素材。条目索引中的声音路径使用相对路径，换目录后仍可加载。

## 命令

```powershell
python main.py items
python main.py items --lang en
python main.py match --wav "C:\path\to\sample.wav"
python main.py live --overlay
python main.py live --overlay --lang en
python main.py live --seconds 30
python main.py calibrate
```

## 隐私与限制

- 实时识别只监听所选扬声器的系统回环音频；队友语音等其他播放声音也可能被采集并影响结果。
- 识别效果取决于音库质量、音量和游戏环境。请自行判断结果，不要把它当作准确性保证。
- 悬浮窗在独占全屏模式下可能不可见；使用无边框窗口。
- 音库素材由使用者自行提供和保管，不应未经授权公开分享。
- `tests/` 中的验证脚本使用仓库附带的默认音库；若替换音库，验证结果会随素材变化。

## 开源许可

项目源码及随仓库提供的默认音库采用 MIT 许可证，详见 [LICENSE](LICENSE)。

英文使用说明见 [README.en.md](README.en.md)。程序默认显示中文；使用 `--lang en` 可切换英文，物品名按游戏英文名称显示。
