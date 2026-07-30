# macOS 常驻后端（LaunchAgent）

面向 **Mac Mini / 本机常开生产**：高频使用 **本机 MLX ASR**（`uv` + `--extra asr-mlx`），不希望为了后端一直开着 Ghostty / 终端窗口。

## 谁适合用

| 场景 | 建议 |
| --- | --- |
| 家用 Mac Mini 当生产、经常无字幕视频要 ASR | **本 runbook**：LaunchAgent + 宿主机 `uv` |
| 日常改代码、热重载 | `scripts/dev.sh`（先 **stop** 服务，避免占 17821） |
| 云端 / Linux / 不依赖 MLX | Docker Compose 或其它部署见 `DEPLOY.md` |

## 为什么这个场景不用 Docker

- 默认 `docker-compose` **server 镜像不装 ASR extras**（无 funasr / 无 MLX）。
- MLX ASR 绑定 **Apple Silicon 宿主机** 与本机 Python/uv 环境；塞进容器收益小、路径与 GPU/ANE 更麻烦。
- 高频 ASR 时，宿主机 `uv run` + LaunchAgent 更直接：开机自启、崩溃重启、日志落盘。

若几乎不需要本地 ASR，Docker 仍可用；需要频繁 MLX 时优先本方案。

## 前置

1. 已安装 [uv](https://docs.astral.sh/uv/)，且 PATH 中可执行（或安装时 `UV=/绝对路径/uv`）。
2. `server/.env` 已从 `.env.example` 拷贝并填好 `LLM_API_KEY` 等。
3. 依赖已装（生产建议带 MLX ASR）：

```bash
cd server
uv sync --extra asr-mlx   # Apple Silicon；跨平台 CPU ASR 用 --extra asr
```

4. 端口 **17821** 空闲（若 `dev.sh` 或旧进程占用，先停掉）。
5. **ffmpeg / ffprobe**（无字幕下音频、yt-dlp 后处理需要）。终端里：

```bash
brew install ffmpeg
which ffmpeg ffprobe   # 常见路径：/opt/homebrew/bin/ffmpeg
```

LaunchAgent **默认 PATH 不含 Homebrew**。`mac-service.sh install` 会把 `/opt/homebrew/bin` 等写进 plist；装完 ffmpeg 后请再跑一次 `install` 或 `restart`（改过模板后需 `install` 重写 plist）。

## 安装 / 卸载

脚本与模板：

- [`scripts/mac-service.sh`](../../scripts/mac-service.sh)
- [`scripts/macos/com.biri-youyaku.api.plist.template`](../../scripts/macos/com.biri-youyaku.api.plist.template)

```bash
# 仓库根目录
bash scripts/mac-service.sh install
```

效果：

- 生成 `~/Library/LaunchAgents/com.biri-youyaku.api.plist`
- `WorkingDirectory` = 仓库 `server/`
- 启动：`uv run --no-dev uvicorn biri_youyaku.app:app --host 127.0.0.1 --port 17821`（**无** `--reload`）
- `RunAtLoad` + `KeepAlive`：登录后启动，崩溃自动拉起
- 日志目录：`~/Library/Logs/biri-youyaku/`（`api.out.log` / `api.err.log`）

```bash
bash scripts/mac-service.sh uninstall   # bootout 并删除 plist；日志文件保留
```

仓库路径搬迁或 `uv` 安装位置变了：再跑一次 `install`（会重写 plist 里的绝对路径）。

## 日常操作

```bash
bash scripts/mac-service.sh status    # launchd + curl /healthz
bash scripts/mac-service.sh restart   # 改代码 / 改 .env / uv sync 后
bash scripts/mac-service.sh stop      # 开发前释放 17821
bash scripts/mac-service.sh start
bash scripts/mac-service.sh logs      # tail -f 双日志
```

| 动作 | 命令 |
| --- | --- |
| 代码或依赖更新后 | `bash scripts/mac-service.sh restart` |
| 看是否在跑 | `bash scripts/mac-service.sh status` |
| 查错 | `bash scripts/mac-service.sh logs` 或直接看 `~/Library/Logs/biri-youyaku/` |

前端：生产可用已构建的静态站 / 反向代理；本机调试仍用 Vite（`web`），API 指 `http://127.0.0.1:17821`。

## 与 `dev.sh` 的切换

1. **生产（不写代码）**：LaunchAgent 常驻；不必开终端。
2. **要开发热重载时**：

```bash
bash scripts/mac-service.sh stop
bash scripts/dev.sh          # 后端 --reload + 前端 Vite
# 开发结束 Ctrl+C 后，若要恢复生产常驻：
bash scripts/mac-service.sh start
```

两边都监听 **17821**，不可同时开。脚本在 install/start 时若发现端口被其它进程占用会告警。

## 故障：`ffprobe and ffmpeg not found`

任务卡在 `DOWNLOADING_AUDIO`，报错类似：

```text
ERROR: Postprocessing: ffprobe and ffmpeg not found. Please install or provide the path using --ffmpeg-location
```

1. 终端确认已安装：`which ffmpeg && ffmpeg -version`
2. 未安装：`brew install ffmpeg`
3. 已装但仍失败（常见于 launchd）：重新写入服务 PATH 并重启：

```bash
bash scripts/mac-service.sh install
# 或至少
bash scripts/mac-service.sh restart
```

4. 页面上对失败任务 **重试**（或重新提交该视频）。

## 备份（仍然推荐）

相对路径存储 + backup/restore **继续使用**（换机、盘损坏、误删恢复）：

```bash
cd server
uv run python scripts/knowledge_backup.py
# 恢复前请先 stop 服务，见 CONFIG.md
# uv run python scripts/knowledge_restore.py --from data/backups/<timestamp>
```

详见 [`CONFIG.md`](../../CONFIG.md) 知识库备份小节。路径尽量保持 `data/*` 相对路径，便于备份与迁移。

## 故障排查

| 现象 | 排查 |
| --- | --- |
| `status` healthz 非 200 | `logs` 看 traceback；检查 `server/.env`、`uv sync` |
| install 报找不到 uv | 装 uv 或 `UV=$(command -v uv) bash scripts/mac-service.sh install`（须绝对路径写入 plist） |
| 端口占用 | `lsof -nP -iTCP:17821 -sTCP:LISTEN`；停掉 `dev.sh` 或其它 uvicorn |
| ASR 不可用 | 确认宿主机 `uv sync --extra asr-mlx`，且 `ASR_MODEL` 为 mlx 相关；服务用的是写进 plist 的那份 `uv` |
| 改代码不生效 | 无 reload；执行 `restart` |

## 相关链接

- 开发一键：[`scripts/dev.sh`](../../scripts/dev.sh)
- 配置全集：[`CONFIG.md`](../../CONFIG.md)
- 部署总览：[`DEPLOY.md`](../../DEPLOY.md)
