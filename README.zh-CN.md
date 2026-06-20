# Kindle Renderer

[English README](README.md)

这是一个给 Kindle 风格屏幕使用的黑白仪表盘渲染项目。它分成两部分：

- 本地 Python 脚本：生成 `db_1.png`、`db_2.png` 这类页面图片
- Kindle 端 Go 程序：在设备上轮播图片，并通过 KUAL 菜单启动/停止

## 功能

- 将仪表盘内容渲染为 `db_1.png`、`db_2.png` 等图片
- 通过 `https://api.csapi.de` 获取关注的 CS 战队最新比赛信息
- 从本地 `matches/cs/teams/` 目录读取战队 logo
- 通过 SSH 采集服务器状态：
  - `CPU`
  - `RAM`
  - `Uptime`
- 将本地生成的 `db_*.png` 自动同步到远端 Kindle 目录
- 自动删除远端多余的旧图片，并执行远端刷屏命令
- 支持打 tag 后自动构建 Kindle 扩展包并发布到 GitHub Releases

## 目录说明

- `main.py`：把 `data.json` 渲染成页面图片
- `update_data.py`：生成 `data.json`
- `prepare_team_logos.py`：下载或准备本地队伍 logo
- `sync_kindle_images.py`：把 `db_*.png` 上传到远端并执行刷新命令
- `kindle/`：Kindle 端 Go 程序、KUAL 扩展文件和打包脚本
- `config.json`：本地私有配置，不会提交到 git
- `config.json.template`：本地配置模板
- `connection.json`：远端同步配置，不会提交到 git
- `connection.json.template`：远端同步配置模板

## 本地生成图片

1. 创建本地配置：

```bash
cp config.json.template config.json
```

2. 修改 `config.json`：

- 配置你关注的 `teams`
- 配置 `servers` 中真实的 SSH 服务器信息
- 根据需要调整标题、时区、logo 路径等

3. 准备 logo：

```bash
python3 prepare_team_logos.py
```

4. 生成数据并渲染图片：

```bash
python3 update_data.py
python3 main.py data.json dashboard.png
```

渲染完成后会得到：

- `db_1.png`
- `db_2.png`
- ...

## 同步到远端 Kindle

1. 创建同步配置：

```bash
cp connection.json.template connection.json
```

2. 修改 `connection.json`：

```json
{
  "host": "203.0.113.10",
  "port": 22,
  "user": "root",
  "key_path": "~/.ssh/id_ed25519",
  "remote_dir": "/path/to/remote/dashboard",
  "refresh_command": "cd /path/to/remote/dashboard && ./refresh.sh",
  "local_glob": "db_*.png"
}
```

字段说明：

- `host`：远端主机地址
- `port`：SSH 端口
- `user`：SSH 用户名
- `key_path`：本地私钥路径
- `remote_dir`：远端图片目录
- `refresh_command`：上传完成后在远端执行的刷屏命令
- `local_glob`：本地要上传的图片匹配规则，默认是 `db_*.png`

3. 执行同步：

```bash
python3 sync_kindle_images.py
```

这个脚本会：

- 上传所有本地匹配 `local_glob` 的图片到 `remote_dir`
- 用本地同名文件覆盖远端已有文件
- 删除远端这次本地不存在的旧 `db_*.png`
- 上传结束后执行 `refresh_command`

## Kindle 端扩展

`kindle/` 目录包含 Kindle 上运行的 Go 程序和 KUAL 扩展包装文件。

本地打包命令：

```bash
cd kindle
./build_kual_package.sh
```

打包后会生成：

- `kindle/dist/kindle-dashboard.zip`

解压并拷贝到 Kindle 后，目录结构应为：

```text
/mnt/us/extensions/kindle-dashboard/config.xml
/mnt/us/extensions/kindle-dashboard/menu.json
/mnt/us/extensions/kindle-dashboard/bin/start.sh
/mnt/us/extensions/kindle-dashboard/bin/stop.sh
/mnt/us/extensions/kindle-dashboard/bin/dashboard-kindle
/mnt/us/extensions/kindle-dashboard/config
```

然后在 KUAL 中就可以看到启动和停止仪表盘的菜单。

## 队伍 Logo

队伍 logo 只从本地文件读取。

路径格式：

```text
matches/cs/teams/<team-slug>.png
```

例如：

- `matches/cs/teams/falcons.png`
- `matches/cs/teams/vitality.png`
- `matches/cs/teams/spirit.png`

如果缺少 logo，渲染器会打印警告，并使用占位图。

## 服务器状态采集

`config.json` 中每个服务器配置大致如下：

```json
{
  "title": "My Server",
  "host": "your-host.example.com",
  "port": 22,
  "user": "root",
  "key_path": "~/.ssh/id_ed25519"
}
```

采集逻辑会调用本机 `ssh` 命令，并使用你配置的私钥。

如果 SSH 连接失败，状态卡片仍然会渲染，但会显示降级内容。

## 自动发布

项目已经配置 GitHub Actions：

- 每次 push 一个 tag
- 自动执行 `kindle/build_kual_package.sh`
- 创建与 tag 同名的 GitHub Release
- 把 `kindle/dist/kindle-dashboard.zip` 上传到 Release 附件中
