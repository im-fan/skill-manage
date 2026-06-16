# Skill Manager 源码安装、npm 打包发布与使用教程

这份教程从一份源码目录开始，带你完成本地启动、npm 打包、本地安装、全局安装、发布前检查，以及通过 `skill-manager` 管理本地服务的完整流程。

## 适用范围

本文适用于当前项目结构：

- npm 包名：`@im-fan/skill-manage`
- 全局命令：`skill-manager`
- Python 服务入口：`python -m skill_manage`
- npm CLI 入口：`bin/skill-manager.js`
- 默认配置文件：`~/.skill-manager/config.json`
- 默认运行目录：`~/.skill-manager`

`skill-manager` 是 Node CLI。它负责读取配置、管理 pid、检查端口、启动和停止后台 Python 服务。Python 后端继续提供实际的本地 Web 服务。

## 你需要准备什么

- Python 3.10 或更高版本
- Node.js 18 或更高版本
- npm
- macOS 或 Linux 环境
- 当前项目源码目录，例如：

```bash
cd /Users/mac/project/my/skill-manage
```

检查版本：

```bash
python3 --version
node --version
npm --version
```

## 1. 从源码启动服务

源码开发时可以直接运行 Python 服务。推荐先使用 package 模块入口，因为它和 npm CLI 启动后端时使用的是同一个 Python 入口。

```bash
cd /Users/mac/project/my/skill-manage
PYTHONPATH=src python3 -m skill_manage --host 127.0.0.1 --port 8765
```

看到服务启动后，在浏览器打开：

```text
http://127.0.0.1:8765/
```

如果希望启动后自动打开浏览器：

```bash
PYTHONPATH=src python3 -m skill_manage --host 127.0.0.1 --port 8765 --open
```

也可以使用兼容入口：

```bash
python3 src/skill-manage-server.py --host 127.0.0.1 --port 8765 --open
```

或使用源码启动脚本：

```bash
./scripts/start.sh
```

源码启动脚本会检查 Python，读取 `requirements.txt`，并把日志写入源码目录下的 `logs/skill-manage.log`。

## 2. 配置源码运行目录

源码模式默认把数据写到项目目录：

```text
data/skill-manage.sqlite3
logs/skill-manage.log
```

如果你希望源码启动也使用独立运行目录，可以设置 `SKILL_MANAGE_HOME`：

```bash
mkdir -p /tmp/skill-manager-dev-home
SKILL_MANAGE_HOME=/tmp/skill-manager-dev-home \
PYTHONPATH=src python3 -m skill_manage --host 127.0.0.1 --port 8765
```

此时数据和日志会写到：

```text
/tmp/skill-manager-dev-home/data/skill-manage.sqlite3
/tmp/skill-manager-dev-home/logs/skill-manage.log
```

## 3. 在源码目录测试 npm CLI

不用安装也可以直接运行 CLI：

```bash
node bin/skill-manager.js h
node bin/skill-manager.js version
```

为了不污染默认的 `~/.skill-manager`，本地测试建议使用临时 home：

```bash
export SKILL_MANAGER_HOME=/tmp/skill-manager-cli-home
node bin/skill-manager.js status
```

再执行启动、状态和停止。`start` 会在服务已运行时先重启旧进程；如果配置端口被占用，会先释放端口再继续启动：

```bash
node bin/skill-manager.js start
node bin/skill-manager.js status
node bin/skill-manager.js stop
```

`status`、`start` 或 `web` 首次执行时会创建配置文件：

```text
$SKILL_MANAGER_HOME/config.json
```

配置文件默认内容类似：

```json
{
  "server": {
    "host": "127.0.0.1",
    "port": 8765
  },
  "runtimeHome": "/tmp/skill-manager-cli-home"
}
```

CLI 会把 `runtimeHome` 传给 Python 服务作为 `SKILL_MANAGE_HOME`，所以数据库和日志会写入运行目录，而不是 npm 包安装目录。

## 4. 运行项目自检

提交或打包前，先运行 CLI 测试：

```bash
npm run test:cli
```

运行 Python 路径测试：

```bash
python3 -m unittest test.test_skill_manage_paths
```

检查 Markdown 和代码改动是否有尾随空白：

```bash
git diff --check
```

## 5. npm pack 打包检查

先做 dry-run，确认即将进入 npm 包的文件：

```bash
npm pack --dry-run
```

你应该能在输出中看到这些关键文件或目录：

```text
package/bin/skill-manager.js
package/src/skill_manage/
package/web/skill-manage.html
package/docs/npm-install-publish-use-zh.md
package/README.md
package/README-zh.md
package/LICENSE
```

如果 dry-run 通过，再生成本地 tarball：

```bash
npm pack
```

命令会生成类似文件：

```text
im-fan-skill-manage-0.1.0.tgz
```

这个 tarball 就是本地 npm 安装和发布时使用的包文件。

## 6. 从 tarball 做本地安装验证

发布前建议先安装本地 tarball。为了避免影响真实全局 npm 环境，可以用临时 npm prefix 模拟全局安装：

```bash
mkdir -p /tmp/skill-manager-npm-prefix
npm install -g ./im-fan-skill-manage-0.1.0.tgz --prefix /tmp/skill-manager-npm-prefix
```

执行临时安装出来的命令：

```bash
/tmp/skill-manager-npm-prefix/bin/skill-manager h
/tmp/skill-manager-npm-prefix/bin/skill-manager version
```

用隔离运行目录完成一次启动和停止：

```bash
export SKILL_MANAGER_HOME=/tmp/skill-manager-installed-home
/tmp/skill-manager-npm-prefix/bin/skill-manager start
/tmp/skill-manager-npm-prefix/bin/skill-manager status
/tmp/skill-manager-npm-prefix/bin/skill-manager stop
```

确认运行目录中生成了数据、日志和 run 文件：

```bash
find /tmp/skill-manager-installed-home -maxdepth 3 -type f | sort
```

## 7. 安装到真实全局 npm 环境

如果只是本机使用，并且已经通过 tarball 验证，可以从本地包安装：

```bash
npm install -g ./im-fan-skill-manage-0.1.0.tgz
```

如果包已经发布到 npm registry，可以直接安装：

```bash
npm install -g @im-fan/skill-manage
```

安装后检查：

```bash
skill-manager h
skill-manager version
```

## 8. 使用 skill-manager 管理服务

启动后台服务：

```bash
skill-manager start
```

查看状态：

```bash
skill-manager status
```

打开 Web 管理界面：

```bash
skill-manager web
```

重启服务：

```bash
skill-manager restart
```

停止服务：

```bash
skill-manager stop
```

查看帮助和版本：

```bash
skill-manager h
skill-manager help
skill-manager version
skill-manager --version
```

## 9. 修改端口和运行目录

默认配置文件路径：

```text
~/.skill-manager/config.json
```

默认配置：

```json
{
  "server": {
    "host": "127.0.0.1",
    "port": 8765
  },
  "runtimeHome": "~/.skill-manager"
}
```

修改端口时，编辑 `server.port`，然后重启：

```bash
skill-manager restart
```

修改运行目录时，编辑 `runtimeHome`，然后重启。新的 SQLite、日志和 pid 状态会写入新目录：

```text
<runtimeHome>/data/skill-manage.sqlite3
<runtimeHome>/logs/skill-manage.log
<runtimeHome>/run/skill-manager.pid
<runtimeHome>/run/skill-manager.json
```

也可以通过环境变量指定配置和运行目录：

```bash
SKILL_MANAGER_CONFIG=/path/to/config.json skill-manager status
SKILL_MANAGER_HOME=/path/to/home skill-manager start
SKILL_MANAGER_PYTHON=/usr/bin/python3 skill-manager start
```

## 10. 发布到 npm registry

发布前确认包名、版本和文件列表：

```bash
npm pkg get name version files bin
npm pack --dry-run
```

确认登录状态：

```bash
npm whoami
```

如果没有登录：

```bash
npm login
```

发布 scoped package 时，如果要公开发布，需要带 `--access public`：

```bash
npm publish --access public
```

发布后可以用干净环境验证安装：

```bash
npm install -g @im-fan/skill-manage
skill-manager version
skill-manager h
```

如果只是验证发布流程但不真正发布，可以先运行：

```bash
npm publish --dry-run
```

## 11. 常见问题

### 端口被占用

如果 `skill-manager start` 发现配置端口被占用，会杀掉占用该端口的进程，然后继续启动服务。服务已运行时，再次执行 `start` 等同于先停止旧的托管进程再启动。

查看当前状态：

```bash
skill-manager status
```

如果你确实想换端口，再编辑配置文件，例如：

```text
~/.skill-manager/config.json
```

把：

```json
"port": 8765
```

改成目标端口，例如：

```json
"port": 8766
```

再启动：

```bash
skill-manager start
```

### Python 不可用

如果 CLI 提示需要 Python 3.10+，先检查：

```bash
python3 --version
```

如果系统里有多个 Python，可以指定：

```bash
SKILL_MANAGER_PYTHON=/path/to/python3 skill-manager start
```

### web 命令提示服务未运行

`skill-manager web` 只负责打开当前运行中的服务。如果服务未运行，先执行：

```bash
skill-manager start
skill-manager web
```

### stale pid

如果 `status` 显示 `stale pid`，说明 pid 文件存在，但对应进程已经不存在，或不是当前服务进程。通常执行一次 `stop` 清理 run 文件即可：

```bash
skill-manager stop
skill-manager start
```

## 12. 推荐发布前检查清单

发布前至少跑完：

```bash
npm run test:cli
python3 -m unittest test.test_skill_manage_paths
npm pack --dry-run
npm publish --dry-run
git diff --check
```

如果改动过运行目录、配置或 CLI 启停逻辑，再做一次隔离目录 smoke test：

```bash
export SKILL_MANAGER_HOME=/tmp/skill-manager-release-check
mkdir -p "$SKILL_MANAGER_HOME"
node -e 'const fs=require("fs"); const home=process.env.SKILL_MANAGER_HOME; fs.writeFileSync(`${home}/config.json`, JSON.stringify({server:{host:"127.0.0.1",port:18765}, runtimeHome:home}, null, 2)+"\n");'
node bin/skill-manager.js start
node bin/skill-manager.js status
node bin/skill-manager.js stop
```

到这里，你已经完成了从源码启动、npm 打包、本地安装、全局安装、发布检查和 `skill-manager` 日常使用的完整流程。
