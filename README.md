# PyBox - Python Sandbox Execution Environment

一个基于 Docker 的 Python 代码沙盒执行环境,通过 **MCP Streamable HTTP** 协议让 LLM / Agent 远程安全执行 Python 代码,支持数据分析、可视化等任务,并自动返回生成的文件下载链接。

## 特性

- 🔒 **安全沙盒** - 代码在内核容器中执行,与宿主机网络隔离
- 🚀 **Streamable HTTP** - 使用http连接,远程可用
- 📊 **数据科学全家桶** - pandas / numpy / matplotlib / scikit-learn / OCR 等 20+ 库
- 📁 **文件下载链接** - 执行后自动生成可点击的下载链接(支持子目录)
- 🛡️ **会话隔离** - 每次执行独立的文件空间,避免冲突
- ⏱️ **超时控制** - 可配置的执行超时,防止资源耗尽
- 🌐 **跨域支持** - 内置 CORS 配置,前端可直接调用

## 架构

```
┌─────────────────────────────────────────────┐
│  对外端口: 6811 (MCP) / 6812 (文件下载)      │
├─────────────────────────────────────────────┤
│                                             │
│  ┌─────────────┐       ┌─────────────┐      │
│  │     MCP     │       │    Nginx    │      │
│  │   Server    │       │  文件下载    │      │
│  │ Streamable  │       │  (只读)     │      │
│  │    HTTP     │       │             │      │
│  └──────┬──────┘       └──────┬──────┘      │
│         │                     │             │
│         │ WebSocket          │             │
│         ▼                     ▼             │
│  ┌──────────────────────────────────┐      │
│  │  Kernel Gateway (Jupyter)         │      │
│  │  代码执行引擎                      │      │
│  └──────────────────────────────────┘      │
│         │                                   │
│         ▼                                   │
│      ./data  (共享存储)                     │
└─────────────────────────────────────────────┘
```

**三容器协作**:

| 容器 | 作用 | 对外暴露 |
|---|---|---|
| `pybox-kernel` | Jupyter Kernel Gateway,执行 Python 代码 | ❌ 内部 |
| `pybox-mcp` | MCP Server (FastMCP + Streamable HTTP) | ✅ 6811 |
| `pybox-nginx` | Nginx 静态文件下载服务 | ✅ 6812 |

## 快速开始

### 前置条件

- Docker ≥ 20.10
- Docker Compose ≥ v2
- 可用端口: 6811 (MCP) 和 6812 (文件下载)

### 启动服务

```bash
# 克隆仓库
git clone https://github.com/Parabellum97/PyBox.git pybox
cd pybox

# 构建并启动
docker-compose up -d --build

# 查看启动日志
docker-compose logs -f
```

首次启动会拉取基础镜像并安装依赖,大约需要 3-5 分钟。

### 验证服务

```bash
# 健康检查 (返回 200 表示成功)
curl http://localhost:6812/health

# 查看 MCP 端点
curl http://localhost:6811/

# 列出所有工具
curl http://localhost:6811/tools
```

## MCP 接入

### Streamable HTTP (推荐)

连接地址: `http://localhost:6811`

```json
{
  "mcpServers": {
    "pybox": {
      "url": "http://localhost:6811",
      "transport": "streamable-http"
    }
  }
}
```

### stdio (本地 Claude Desktop)

```json
{
  "mcpServers": {
    "pybox": {
      "command": "docker",
      "args": ["exec", "-i", "pybox-mcp", "python", "pybox_mcp_streamable.py"]
    }
  }
}
```

## 可用工具

### `run_python` - 执行 Python 代码

| 参数 | 类型 | 必需 | 说明 |
|---|---|---|---|
| `code` | string | ✅ | 要执行的 Python 代码 |
| `timeout` | number | ❌ | 超时时间(秒),默认 60,最大 300 |

**返回值**: 包含 `stdout`、`stderr`、`images`、`files`、`execution_time`、`session_id` 的 JSON 对象。

**已安装的库**:

| 类别 | 库 |
|---|---|
| 数据处理 | pandas, numpy, scipy, openpyxl, xlrd, xlsxwriter |
| 可视化 | matplotlib, seaborn, plotly |
| 机器学习 | scikit-learn, xgboost, lightgbm |
| 图像处理 | pillow (PIL), pytesseract (OCR 中英文) |
| 文件处理 | PyPDF2, python-docx, python-pptx |
| 办公自动化 | reportlab |
| 数据生成 | faker, mimesis |
| 网络请求 | requests, beautifulsoup4, lxml |
| 其他 | tqdm, python-dateutil, pytz |

**使用示例**:

```python
# 数据分析
import pandas as pd
df = pd.DataFrame({'name': ['Alice', 'Bob'], 'age': [25, 30]})
print(df.describe())
df.to_csv('report.csv', index=False)
```

```python
# 可视化
import matplotlib.pyplot as plt
plt.plot([1, 2, 3], [4, 5, 6])
plt.title('Sample Plot')
plt.savefig('chart.png', dpi=150)
```

```python
# OCR 识别 (中文)
import pytesseract
from PIL import Image
img = Image.open('screenshot.png')
text = pytesseract.image_to_string(img, lang='chi_sim')
print(text)
```

## 文件保存规范(强约束)

> ⚠️ **必须使用相对路径,绝对路径会被沙盒自动转换到会话目录**

| 写法 | 结果 |
|---|---|
| ✅ `'report.csv'` | 保存到当前会话目录 |
| ✅ `'reports/chart.png'` | 保存到子目录(自动创建) |
| ❌ `'/mnt/data/...'` | 仍然能工作,但不规范 |

**为什么用相对路径?**: 每次执行都有独立的 `session_<uuid>/` 子目录,避免多用户/多会话之间的文件冲突。

## 客户端示例

### Python

```python
import requests

# 执行代码
response = requests.post(
    "http://localhost:6811/tools/call",
    json={
        "name": "run_python",
        "arguments": {
            "code": """
import pandas as pd
import matplotlib.pyplot as plt

df = pd.DataFrame({'x': [1, 2, 3, 4], 'y': [10, 20, 15, 25]})
df.to_csv('analysis.csv', index=False)

plt.plot(df['x'], df['y'], marker='o')
plt.savefig('chart.png')
print(f"平均: {df['y'].mean()}")
""",
            "timeout": 60
        }
    }
)
result = response.json()
print("输出:", result["content"][0]["text"])
```

### HTTP 直接调用 (绕过 MCP 协议)

MCP Streamable HTTP 服务同时也提供了 `POST /http/run` 直连端点,适合不想走 MCP 协议的客户端:

```bash
curl -X POST http://localhost:6811/http/run \
  -H "X-Api-Key: <your-api-key>" \
  -H "Content-Type: application/json" \
  -d '{"code": "print(\"hello\")", "timeout": 60}'
```

**配置 API Key**: 在项目根目录创建 `.env` 文件,设置 `API_KEY=your-secret-key`。如果未设置则跳过鉴权。

## 配置

通过环境变量配置,推荐方式:

1. 复制 `.env.example` 为 `.env`
2. 按需修改后启动

```bash
cp .env.example .env
```

| 变量 | 默认值 | 说明 |
|---|---|---|
| `EXEC_TIMEOUT` | 60 | 代码执行超时(秒) |
| `FILE_DOWNLOAD_URL` | `http://localhost:6812/data` | 文件下载链接前缀,公网部署需改为外网域名 |
| `API_KEY` | (空) | `/http/run` 端点的鉴权密钥,留空则关闭鉴权 |
| `WS_MAX_SIZE` | 5242880 | WebSocket 最大消息字节数(5MB) |

## 部署到生产服务器

### Linux 服务器

```bash
# 1. 上传代码 (rsync/scp)
rsync -avz --exclude='data/' --exclude='.env' ./ user@server:/opt/pybox/

# 2. SSH 登录并配置环境
ssh user@server
cd /opt/pybox
cp .env.example .env
vim .env  # 设置 FILE_DOWNLOAD_URL 和 API_KEY

# 3. 启动
docker-compose up -d --build

# 4. 配置防火墙
sudo ufw allow 6811/tcp  # MCP
sudo ufw allow 6812/tcp  # 文件下载
```

### 反向代理 (Nginx)

如果需要在 80/443 端口对外提供服务,推荐用 Nginx 反向代理:

```nginx
server {
    listen 443 ssl;
    server_name pybox.example.com;

    # MCP Streamable HTTP
    location / {
        proxy_pass http://localhost:6811;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_read_timeout 300s;
    }

    # 文件下载
    location /data/ {
        proxy_pass http://localhost:6812/data/;
    }
}
```

## 安全建议

⚠️ **本项目执行任意 Python 代码,仅适合可信环境或加鉴权后使用**

1. **必须配置 API_KEY**: 在 `.env` 中设置强随机密钥
2. **使用 HTTPS**: 不要直接暴露 6811 端口到公网,通过反向代理 + TLS
3. **网络隔离**: 默认仅暴露 6811/6812,kernel 容器无外网
4. **资源限制**: 在 `docker-compose.yml` 中添加资源约束:

   ```yaml
   services:
     kernel:
       deploy:
         resources:
           limits:
             cpus: '2.0'
             memory: 4G
   ```

5. **定期清理**: 定时清理 `data/` 目录中的过期文件,避免磁盘占满

## 常用命令

```bash
# 查看所有容器状态
docker-compose ps

# 查看日志
docker-compose logs -f              # 所有容器
docker-compose logs -f mcp          # 仅 MCP 服务
docker-compose logs -f kernel       # 仅 Kernel

# 进入 Kernel 容器调试
docker-compose exec kernel bash

# 重启服务
docker-compose restart

# 停止并清理
docker-compose down                 # 停止
docker-compose down -v              # 停止并删除卷(会清空 ./data)

# 完全重建 (镜像级)
docker-compose down
docker-compose build --no-cache
docker-compose up -d
```

## 故障排查

### Q: MCP 容器启动失败

检查 fastmcp 版本兼容性,以及 `pybox_mcp_streamable.py` 是否能独立运行:

```bash
docker-compose logs mcp
docker-compose exec mcp python pybox_mcp_streamable.py
```

### Q: 文件下载返回 404

确认 `./data/` 目录存在且文件实际生成:

```bash
ls -la ./data/session_*/
curl http://localhost:6812/health
```

### Q: 代码执行超时

1. 检查 `EXEC_TIMEOUT` 配置
2. 在 `docker-compose.yml` 的 `kernel` 服务中添加资源限制
3. 复杂任务可分批执行

## TODO - 未来计划

当前已实现 MCP **Streamable HTTP** 协议。以下功能计划在未来版本中加入:

### MCP 协议增强

- [ ] **list_files MCP 工具** - 将"列出持久化文件"封装为 MCP 标准工具(目前通过 `run_python` 间接实现)

### 安全与权限

- [ ] **用户隔离** - 每个调用方使用独立的 `session_<user_id>/` 目录,基于 token 识别
- [ ] **白名单库** - 默认只允许预安装的库,可选开启 `pip install` 沙盒
- [ ] **执行审计日志** - 记录所有代码执行历史到数据库,便于事后审计
- [ ] **资源配额** - 按用户/按 IP 限制 CPU、内存、磁盘使用

### 用户体验

- [ ] **流式输出** - 长任务支持 SSE 流式回传 stdout/stderr
- [ ] **Notebook 格式输出** - 支持 Jupyter `.ipynb` 格式导出
- [ ] **异步任务** - 提交后立即返回 task_id,客户端轮询或 WebSocket 订阅结果
- [ ] **Web UI** - 提供浏览器交互界面,方便手动调试

### 运维

- [ ] **Prometheus metrics** - 暴露执行次数、耗时、错误率等指标
- [ ] **健康检查增强** - `/health` 返回 kernel pool 状态

## License

本项目基于 MIT 协议开源 - 详见 [LICENSE](LICENSE) 文件。

GitHub: [https://github.com/Parabellum97/PyBox](https://github.com/Parabellum97/PyBox)
