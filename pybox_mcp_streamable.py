"""
PyBox MCP Server - 使用 FastMCP (支持 Streamable HTTP)
会话隔离版本 - 使用相对路径 + chdir（不修改挂载点）
"""
import os
import json
import asyncio
import uuid
from pathlib import Path
from datetime import datetime
from typing import Annotated
from urllib.parse import quote

import httpx
import websockets
from fastmcp import FastMCP
from starlette.responses import JSONResponse

# 配置
KERNEL_GATEWAY_URL = os.getenv("KERNEL_GATEWAY_URL", "http://kernel:8888")
DATA_DIR = Path(os.getenv("DATA_DIR", "/mnt/data"))
TIMEOUT = int(os.getenv("EXEC_TIMEOUT", "60"))
# API Key for HTTP route auth
API_KEY = os.getenv("API_KEY", "")
WS_MAX_SIZE_RAW = os.getenv("WS_MAX_SIZE", "1048576")
WS_MAX_SIZE = None if WS_MAX_SIZE_RAW.lower() in {"0", "none", "null"} else int(WS_MAX_SIZE_RAW)

# nginx 文件下载服务器地址
FILE_DOWNLOAD_BASE_URL = os.getenv("FILE_DOWNLOAD_URL", "http://localhost:8080/data")

# 创建 FastMCP Server (支持 streamable-http)
mcp = FastMCP("pybox")

async def execute_python_code(code: str, timeout: int = TIMEOUT) -> dict:
    """在 Kernel Gateway 中执行 Python 代码（会话隔离）"""
    start_time = datetime.now()
    stdout_lines = []
    stderr_lines = []
    images = []

    # 创建会话隔离目录
    session_id = str(uuid.uuid4())
    session_data_dir = DATA_DIR / f"session_{session_id}"
    session_data_dir.mkdir(parents=True, exist_ok=True)
    
    # 设置目录权限
    try:
        session_data_dir.chmod(0o777)
    except:
        pass

# 创建会话初始化代码（仅切换工作目录，不修改 /mnt/data 挂载点）
    setup_code = f'''
import os
import sys
from pathlib import Path

# 会话配置
_SESSION_ID = "{session_id}"
_SESSION_DATA_DIR = "{session_data_dir.as_posix()}"

# 设置工作目录到会话目录
os.chdir(_SESSION_DATA_DIR)
'''

    # 组合完整代码
    full_code = setup_code + "\n\n" + code

    async with httpx.AsyncClient(timeout=timeout + 10) as client:
        try:
            # 创建内核时传递会话环境变量
            kernel_request = {
                "name": "python3",
                "env": {
                    "SESSION_DATA_DIR": str(session_data_dir),
                    "SESSION_ID": session_id
                }
            }
            r = await client.post(f"{KERNEL_GATEWAY_URL}/api/kernels", json=kernel_request)
            r.raise_for_status()
            kernel_id = r.json()["id"]
        except Exception as e:
            return {
                "success": False,
                "error": f"无法创建 Kernel: {e}",
                "stdout": "",
                "images": [],
                "files": [],
                "session_id": session_id,
                "execution_time": 0
            }

        try:
            ws_url = f"{KERNEL_GATEWAY_URL.replace('http', 'ws')}/api/kernels/{kernel_id}/channels"

            async with asyncio.timeout(timeout):
                async with websockets.connect(ws_url, ping_interval=None, max_size=WS_MAX_SIZE) as ws:
                    execute_request = {
                        "header": {
                            "msg_id": f"exec-{kernel_id}",
                            "msg_type": "execute_request",
                            "username": "pybox",
                            "session": kernel_id,
                            "version": "5.3"
                        },
                        "parent_header": {},
                        "metadata": {},
                        "content": {
                            "code": full_code,
                            "silent": False,
                            "store_history": False,
                            "user_expressions": {},
                            "allow_stdin": False
                        }
                    }

                    await ws.send(json.dumps(execute_request))

                    async for msg_str in ws:
                        msg = json.loads(msg_str)
                        msg_type = msg.get("msg_type", "")
                        content = msg.get("content", {})

                        if msg_type == "stream":
                            if content.get("name") == "stdout":
                                stdout_lines.append(content.get("text", ""))
                            elif content.get("name") == "stderr":
                                stderr_lines.append(content.get("text", ""))
                        elif msg_type == "error":
                            stderr_lines.extend(content.get("traceback", []))
                        elif msg_type in ("display_data", "execute_result"):
                            if "image/png" in content.get("data", {}):
                                images.append(content["data"]["image/png"])
                        elif msg_type == "execute_reply":
                            break

        except asyncio.TimeoutError:
            return {
                "success": False,
                "error": f"代码执行超时 (>{timeout}s)",
                "stdout": "".join(stdout_lines),
                "images": images,
                "files": [],
                "session_id": session_id,
                "execution_time": timeout
            }
        finally:
            try:
                await client.delete(f"{KERNEL_GATEWAY_URL}/api/kernels/{kernel_id}")
            except:
                pass

    # 简化文件检测：直接返回会话目录中的所有文件
    all_files = []
    if session_data_dir.exists():
        for f in session_data_dir.rglob("*"):
            if f.is_file():
                rel_path = f.relative_to(session_data_dir).as_posix()
                all_files.append(rel_path)

    execution_time = (datetime.now() - start_time).total_seconds()

    return {
        "success": len(stderr_lines) == 0,
        "error": "".join(stderr_lines) if stderr_lines else "",
        "stdout": "".join(stdout_lines),
        "images": images,
        "files": all_files,
        "session_id": session_id,
        "execution_time": execution_time
    }


# ============= HTTP Endpoint =============
@mcp.custom_route("/http/run", methods=["POST"])
async def http_run(request):
    """
    HTTP 执行端点：POST /http/run
    - Header: X-Api-Key: <API_KEY>
    - Body: { "code": "...", "timeout": 60 }
    返回 JSON，复用 execute_python_code 与下载链接拼接逻辑。
    """
    # Auth
    provided = request.headers.get("X-Api-Key", "")
    if API_KEY and provided != API_KEY:
        return JSONResponse({"error": "Unauthorized"}, status_code=401)

    try:
        payload = await request.json()
    except Exception:
        return JSONResponse({"error": "Invalid JSON"}, status_code=400)

    code = (payload or {}).get("code", "")
    timeout = (payload or {}).get("timeout", TIMEOUT)

    if not code:
        return JSONResponse({"error": "Missing 'code'"}, status_code=400)

    result = await execute_python_code(code, timeout)

    # Build message text (same guidance as MCP tool)
    if result["success"]:
        message = "✅ 执行成功\n\n"
        if result["stdout"]:
            message += f"**输出:**\n```\n{result['stdout']}\n```\n\n"
        files_urls = []
        if result["files"]:
            message += "**生成的文件:**\n"
            session_id = result["session_id"]
            for file in result["files"]:
                parts = file.split('/')
                encoded_parts = [quote(part) for part in parts]
                url = f"{FILE_DOWNLOAD_BASE_URL}/session_{session_id}/{'/'.join(encoded_parts)}"
                files_urls.append(url)
                message += f"- [{file}]({url})\n"
            message += "\n"
        else:
            message += (
                "提示：如果你在本次代码中创建了文件但没有返回，请改为使用相对路径（例如：'report.csv' 或 'reports/chart.png'）再次运行；若本次未创建新文件请忽略。\n\n"
            )

        if result["images"]:
            message += f"**生成图片:** {len(result['images'])} 张\n\n"

        message += f"**执行时间:** {result['execution_time']:.3f}s"

        return JSONResponse({
            **result,
            "files_urls": files_urls,
            "message": message
        })

    # Failure case
    message = (
        f"❌ 执行失败\n\n**错误:**\n```\n{result['error']}\n```\n\n"
        f"**执行时间:** {result['execution_time']:.3f}s\n\n"
        "请使用相对路径保存文件（例如：'report.csv' 或 'reports/chart.png'）。绝对禁止使用绝对路径（如 '/mnt/data/...'）；必须使用相对路径。若本次未创建新文件请忽略。"
    )
    return JSONResponse({**result, "message": message}, status_code=500)

@mcp.tool()
async def run_python(
    code: Annotated[str, "要执行的 Python 代码。⚠️ 绝对禁止使用绝对路径（如 '/mnt/data/...'），必须使用相对路径（例如 'result.csv'、'reports/chart.png'）。当前工作目录已切换到本次会话目录，所有相对路径会保存到会话隔离空间。"],
    timeout: Annotated[int, "超时时间(秒),默认 60"] = 60
) -> str:
    """
    在安全沙盒中执行 Python 代码（会话隔离）

    **已安装的库:**
    - 数据处理: pandas, numpy, scipy, openpyxl, xlrd, xlsxwriter
    - 可视化: matplotlib, seaborn, plotly
    - 机器学习: scikit-learn, xgboost, lightgbm
    - 图像处理: pillow (PIL), pytesseract (OCR 支持中英文)
    - 文件处理: PyPDF2, python-docx, python-pptx
    - 办公自动化: reportlab
    - 数据生成: faker, mimesis
    - 网络请求: requests, beautifulsoup4, lxml
    - 其他: tqdm, python-dateutil, pytz

    **文件保存规范（强约束）:**
    - ✅ 相对路径: 'report.csv'（保存到当前会话目录）
    - ✅ 子目录: 'reports/chart.png'
    - ❌ 绝对路径禁止: '/mnt/data/...'

    **重要特性:**
    - 每次执行都有独立的文件空间，确保数据安全
    - 所有生成的文件会自动返回下载链接（支持子目录）
    - 每次执行都是独立的内核，不保留状态

    **示例（仅使用相对路径）:**
    - 数据分析:
      df = pd.DataFrame({'name': ['Alice'], 'age': [25]})
      print(df.describe())
      df.to_csv('report.csv', index=False)

    - 图表可视化:
      import matplotlib.pyplot as plt
      plt.plot([1,2,3], [4,5,6])
      plt.savefig('chart.png')

    - 创建子目录:
      import os
      os.makedirs('reports', exist_ok=True)
      df.to_csv('reports/analysis.csv', index=False)
    """
    result = await execute_python_code(code, timeout)

    if result["success"]:
        output = f"✅ 执行成功!\n\n"

        if result["stdout"]:
            output += f"**输出:**\n```\n{result['stdout']}\n```\n\n"

        if result["files"]:
            output += f"**生成的文件:**\n"
            session_id = result["session_id"]
            
            for file in result['files']:
                # URL 编码：处理中文和特殊字符，支持子目录和会话隔离
                parts = file.split('/')
                encoded_parts = [quote(part) for part in parts]
                download_url = f"{FILE_DOWNLOAD_BASE_URL}/session_{session_id}/{'/'.join(encoded_parts)}"
                output += f"- [{file}]({download_url})\n"
            
            output += f"\n"
        else:
            output += (
                "提示：如果你在本次代码中创建了文件但没有返回，请改为使用相对路径（例如：'report.csv' 或 'reports/chart.png'）再次运行；若本次未创建新文件请忽略。\n\n"
            )

        if result["images"]:
            output += f"**生成图片:** {len(result['images'])} 张\n\n"

        output += f"**执行时间:** {result['execution_time']:.3f}s"
        return output
    else:
        output = f"❌ 执行失败!\n\n**错误:**\n```\n{result['error']}\n```\n\n"

        if result["stdout"]:
            output += f"**部分输出:**\n```\n{result['stdout']}\n```\n\n"

        output += f"**执行时间:** {result['execution_time']:.3f}s\n\n"
        output += (
            "请使用相对路径保存文件（例如：'report.csv' 或 'reports/chart.png'）。绝对禁止使用绝对路径（如 '/mnt/data/...'）；必须使用相对路径。若本次未创建新文件请忽略。"
        )
        return output


# 主函数: 启动 MCP Server (Streamable HTTP)
if __name__ == "__main__":
    # 使用 streamable-http transport (新标准,取代 SSE)
    mcp.run(transport="streamable-http", port=8001, host="0.0.0.0")
