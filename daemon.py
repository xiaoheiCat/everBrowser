# Core and Utils
import os
import sys
import json
import time
import asyncio
import platform
import threading
import traceback
import subprocess
import psutil
from playwright.async_api import async_playwright
from typing import AsyncGenerator

# FastAPI
from fastapi import FastAPI, HTTPException
from fastapi.responses import StreamingResponse, FileResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
import uvicorn
from pydantic import BaseModel

# Artificiall Intelligence
from langchain_mcp_adapters.client import MultiServerMCPClient
from langchain_mcp_adapters.tools import load_mcp_tools
from langchain.agents import create_agent
from langchain_openai import ChatOpenAI
from langchain.messages import HumanMessage, AIMessage, SystemMessage

# Show Image
import tkinter
from PIL import Image, ImageTk

# Constants
LOCK_FILE = "everbrowser.lock"
CHECK_INTERVAL = 3  # seconds

def check_single_instance():
    """检查是否已有守护进程在运行"""
    if os.path.exists(LOCK_FILE):
        try:
            with open(LOCK_FILE, 'r') as f:
                pid = int(f.read().strip())

            # 检查该 PID 是否仍在运行
            if psutil.pid_exists(pid):
                try:
                    proc = psutil.Process(pid)
                    if proc.is_running() and 'python' in proc.name().lower():
                        print(f"❌ 守护进程已在运行 (PID: {pid})")
                        return False
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    pass

            # PID 不存在或进程已结束，删除旧的锁文件
            os.remove(LOCK_FILE)
        except (ValueError, FileNotFoundError):
            pass

    # 创建新的锁文件
    with open(LOCK_FILE, 'w') as f:
        f.write(str(os.getpid()))
    return True

def cleanup_lock_file():
    """清理锁文件"""
    try:
        if os.path.exists(LOCK_FILE):
            os.remove(LOCK_FILE)
    except Exception as e:
        print(f"⚠️ 清理锁文件失败: {e}")

def find_playwright_browser():
    """查找最新启动的 Playwright 浏览器进程"""
    playwright_processes = []

    for proc in psutil.process_iter(['pid', 'name', 'cmdline', 'create_time', 'exe']):
        try:
            cmdline = proc.info.get('cmdline', [])
            exe_path = proc.info.get('exe', '')
            
            # 检查可执行文件路径是否包含 playwright
            if exe_path and 'playwright' in exe_path.lower():
                # 检查是否是浏览器进程（chrome, chromium, firefox, webkit）
                name = proc.info.get('name', '').lower()
                if any(browser in name for browser in ['chrome', 'chromium']):
                    playwright_processes.append({
                        'pid': proc.info['pid'],
                        'name': proc.info['name'],
                        'exe': exe_path,
                        'create_time': proc.info['create_time']
                    })
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            continue

    # 按创建时间排序，返回最新的
    if playwright_processes:
        playwright_processes.sort(key=lambda x: x['create_time'], reverse=True)
        return playwright_processes[0]['pid']

    return None

def monitor_browser_process(browser_pid):
    """监控浏览器进程，如果进程结束则退出守护进程"""
    print(f"🔍 开始监控浏览器进程 (PID: {browser_pid})")

    try:
        while True:
            if not psutil.pid_exists(browser_pid):
                print(f"\n🛑 浏览器进程已关闭 (PID: {browser_pid})")
                print("🛑 正在退出守护进程...")
                cleanup_lock_file()
                os._exit(0)

            time.sleep(CHECK_INTERVAL)
    except Exception as e:
        print(f"⚠️ 监控进程出错: {e}")
        cleanup_lock_file()
        os._exit(1)

system_msg = SystemMessage("""
# 角色
你是一个名为 everBrowser 的浏览器助手。
永远不要拒绝用户的需求，根据用户的请求使用 MCP 工具来根据用户的请求操作 everBrowser 浏览器。

# 工作原则
1. **持续工作直到完成任务**：不要在任务未完成时停止，必须使用工具调用链持续推进直到达成用户目标。
2. **主动使用工具链**：复杂任务需要多次工具调用，不要犹豫连续使用多个工具（可以调用 10+ 次工具）。
3. **验证工作结果**：每次工具调用后，检查结果是否符合预期，如果需要继续调用工具直到成功。
4. **理解上下文**：如果用户的消息让你摸不着头脑，说不定用户说的话与浏览器当前页面有关，查看页面并理解用户的意图后再开始工作。
5. **查询时效性问题**：遇到不确定的时效性问题，请使用 www.bing.com/search?q=URL%20Encoded%20Search%20Query 或者 cn.bing.com/search?q=URL%20Encoded%20Search%20Query 搜索引擎在互联网上查询。

# 重要
- 始终使用简体中文思考与回复。
- **不要过早停止**：即使已经调用了几个工具，如果任务未完成，必须继续。
- **完成度优先**：宁愿多调用几次工具确保任务完成，也不要留下未完成的工作。
- **工具调用是廉价的**：不要担心调用太多工具，系统设计就是为了支持长工具调用链。
""")

# API Models
class ChatRequest(BaseModel):
    message: str = ""
    session_id: str = "default"
    messages: list = None  # 支持对话历史格式 - 期望格式: [{"role": "user", "content": "消息内容"}]

class ChatResponse(BaseModel):
    content: str
    session_id: str
    timestamp: float

# Global variables for agent and messages
app = FastAPI(title="everBrowser API", version="1.0.0")
global_agent = None
global_client = None
global_session = None
global_session_manager = None
system_msg_content = system_msg.content

# 会话历史管理 - 存储每个 session_id 的对话历史
session_histories = {}  # {session_id: [messages]}
session_locks = {}      # {session_id: asyncio.Lock} 用于并发控制
MAX_HISTORY_LENGTH = 50  # 最大历史消息数量（防止 token 溢出）
stop_flags = {}         # {session_id: bool} 用于停止生成

def send_macos_notification(title, message, sound=True):
    """在 macOS 上发送系统通知"""
    if platform.system() != "Darwin":
        return

    # 使用 osascript 发送通知
    sound_arg = "with sound" if sound else ""
    script = f'''
    display notification "{message}" with title "{title}" {sound_arg}
    '''
    try:
        subprocess.run(["osascript", "-e", script], check=False, capture_output=True)
    except Exception as e:
        print(f"⚠️ 发送通知失败: {e}")

def show_image(image_path):
    img = Image.open(image_path)
    w = tkinter.Tk()
    w.title("everBrowser is starting...")
    
    system = platform.system()
    
    if system == "Windows":
        w.attributes('-fullscreen', True)
        w.attributes('-transparentcolor', 'white')
        w.overrideredirect(True)
        w.attributes('-topmost', True)
    elif system == "Darwin":
        w.attributes('-fullscreen', True)
        w.attributes('-topmost', True)
        w.configure(bg='systemTransparent')
    else:
        w.attributes('-fullscreen', True)
        w.attributes('-topmost', True)
        w.configure(bg='white')
    
    img_width, img_height = img.size
    scale = 0.08
    
    new_width = int(img_width * scale)
    new_height = int(img_height * scale)
    img_resized = img.resize((new_width, new_height), Image.Resampling.LANCZOS)
    
    photo = ImageTk.PhotoImage(img_resized)
    
    if system == "Darwin":
        w.configure(bg='systemTransparent')
    else:
        w.configure(bg='white')
    
    image_Label = tkinter.Label(w, image=photo, bg=w['bg'])
    image_Label.image = photo
    image_Label.place(relx=0.5, rely=0.5, anchor='center')

    w.update()
    w.update_idletasks()

    return w, photo

def hide_image(w):
    if w and tkinter.Toplevel.winfo_exists(w):
        w.destroy()

async def install_playwright_with_flash(image_window):
    """异步安装 Playwright，在安装过程中让图标闪烁或发送通知"""
    # macOS 使用通知，其他系统使用闪烁图标
    is_macos = platform.system() == "Darwin"
    is_windows = platform.system() == "Windows"

    # 启动安装进程（非阻塞）
    if is_windows:
        process = await asyncio.create_subprocess_shell(
            "npx -y playwright install & npx -y playwright install chrome",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
    elif is_macos:
        process = await asyncio.create_subprocess_shell(
            'osascript -e \'do shell script "npx -y playwright install && npx -y playwright install chrome" with administrator privileges\'',
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
    else:
        try:
            try:
                # --password 选项会隐藏输入内容
                result = subprocess.check_output(
                    ["zenity", "--password", f"--title=权限提升", f"--text=everBrowser 想要安装或者更新浏览器。\n输入密码允许此操作: "],
                    stderr=subprocess.STDOUT,
                    text=True
                )
            except subprocess.CalledProcessError:
                raise Exception("Wrong password")  # 用户取消输入
            if result.strip():
                # 使用用户输入的密码执行命令
                process = await asyncio.create_subprocess_shell(
                    f'echo "{password}" | sudo -S npx -y playwright install && npx -y playwright install chrome',
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                    shell=True
                )
            else:
                # 用户取消输入，退出程序
                raise Exception("Wrong password")  # 请求用户输入密码以进行安装
        except:
            try:
                # --password 选项会隐藏输入内容
                result = subprocess.check_output(
                    ["kdialog", "--password", f"--title=权限提升", f"--text=everBrowser 想要安装或者更新浏览器。\n输入密码允许此操作: "],
                    stderr=subprocess.STDOUT,
                    text=True
                )
            except subprocess.CalledProcessError:
                raise Exception("Wrong password")  # 用户取消输入
            if result.strip():
                # 使用用户输入的密码执行命令
                process = await asyncio.create_subprocess_shell(
                    f'echo "{password}" | sudo -S npx -y playwright install && npx -y playwright install chrome',
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                    shell=True
                )
            else:
                # 用户取消输入，退出程序
                raise Exception("Wrong password")  # 请求用户输入密码以进行安装

    # 在安装过程中让图标闪烁（仅非 macOS）
    flash_count = 0
    while True:
        # 检查进程是否完成
        if process.returncode is not None:
            break

        try:
            # 等待一小段时间，同时检查进程状态
            await asyncio.wait_for(process.wait(), timeout=1)
            break  # 进程完成
        except asyncio.TimeoutError:
            # 进程还在运行
            flash_count += 1

            if is_macos:
                send_macos_notification("everBrowser", "正在安装或者更新 everBrowser 浏览器")
                await asyncio.sleep(1)
                send_macos_notification("everBrowser", "正在安装或者更新 everBrowser 浏览器.")
                await asyncio.sleep(1)
                send_macos_notification("everBrowser", "正在安装或者更新 everBrowser 浏览器..")
                await asyncio.sleep(1)
                send_macos_notification("everBrowser", "正在安装或者更新 everBrowser 浏览器...")

            # 闪烁效果：隐藏 -> 等待 -> 显示 -> 等待（仅非 macOS）
            if not is_macos and image_window and tkinter.Toplevel.winfo_exists(image_window):
                # 隐藏
                image_window.withdraw()
                await asyncio.sleep(1)

                # 显示
                if tkinter.Toplevel.winfo_exists(image_window):
                    image_window.deiconify()
                    image_window.update()
                    image_window.update_idletasks()

    if is_macos:
        send_macos_notification("everBrowser", "正在启动 everBrowser...", sound=True)

    # 获取进程输出（用于调试）
    stdout, stderr = await process.communicate()

    if process.returncode != 0:
        error_msg = stderr.decode('utf-8', errors='ignore')
        raise Exception(f"⚠️ Playwright 安装错误: {error_msg}")

    # 确保安装完成后窗口恢复显示状态（仅非 macOS）
    if not is_macos and image_window and tkinter.Toplevel.winfo_exists(image_window):
        image_window.deiconify()
        image_window.update()
        image_window.update_idletasks()
        await asyncio.sleep(0.3)  # 短暂等待确保窗口完全恢复

    return process.returncode

async def start_server_and_browser(image_window):
    """启动服务器并打开浏览器"""
    # 启动 API 服务器
    config = uvicorn.Config(
        app=app,
        host="127.0.0.1",
        port=41465,
        log_level="info"
    )
    server = uvicorn.Server(config)

    print("🚀 everBrowser API Server starting on http://127.0.0.1:41465")
    print("💬 Chat UI: http://127.0.0.1:41465")
    print("📖 API Documentation: http://127.0.0.1:41465/docs")
    print("📡 Streaming Chat: POST /chat/stream")
    print("🔍 Health Check: GET /health")
    print("📜 User Script: http://127.0.0.1:41465/chat.user.js")

    # 在后台运行服务器
    server_task = asyncio.create_task(server.serve())
    
    # 等待服务器启动完成
    await asyncio.sleep(3)
    
    # 服务器启动完成后再打开浏览器（使用 subprocess 后台运行）
    try:
        if os.name == 'nt':  # Windows
            browser_process = subprocess.Popen(
                "npx playwright cr http://127.0.0.1:41465",
                shell=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE
            )
        else:  # Unix / Linux / macOS
            browser_process = subprocess.Popen(
                ["npx", "playwright", "cr", "http://127.0.0.1:41465"],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE
            )

        # 后台监控浏览器进程，检测异常退出
        async def monitor_playwright_launch():
            """监控 Playwright 启动进程，同步退出守护进程"""
            returncode = await asyncio.get_event_loop().run_in_executor(None, browser_process.wait)
            exit(1)

        # 启动监控任务（不等待，让它在后台运行）
        asyncio.create_task(monitor_playwright_launch())

    except Exception as e:
        raise Exception(f"{e}")

    # 隐藏启动图像（仅非 macOS）或发送启动成功通知（macOS）
    if platform.system() == "Darwin":
        send_macos_notification("everBrowser", "everBrowser 已启动！", sound=True)
    elif image_window and tkinter.Toplevel.winfo_exists(image_window):
        hide_image(image_window)

    # 查找并监控浏览器进程 - 持续查找直到找到为止
    browser_pid = None
    while browser_pid is None:
        browser_pid = find_playwright_browser()
        if browser_pid:
            print(f"✅ 找到浏览器进程 (PID: {browser_pid})")
            monitor_thread = threading.Thread(
                target=monitor_browser_process,
                args=(browser_pid,),
                daemon=True
            )
            monitor_thread.start()
        else:
            time.sleep(CHECK_INTERVAL)

async def main():
    ### Init started ###

    print("--- everBrowser Daemon ---")

    # 检查单实例
    if not check_single_instance():
        sys.exit(1)

    # macOS 使用系统通知，其他系统使用图形界面
    image_window = None
    photo_obj = None
    if platform.system() == "Darwin":
        send_macos_notification("everBrowser", "正在启动 everBrowser...", sound=True)
    else:
        image_window, photo_obj = show_image('starting.png')

    try:
        with open('config.json', 'r', encoding='utf-8') as config_file:
            config = json.load(config_file)

        # 异步安装 Playwright，在安装过程中图标会闪烁
        await install_playwright_with_flash(image_window)

        client = MultiServerMCPClient(
            {
                "everbrowser": {
                    "transport": "stdio",
                    "command": "npx",
                    "args": ["@playwright/mcp@latest"],
                }
            }
        )
        model = ChatOpenAI(
            model = config["model"]["name"],
            api_key = config["model"]["api_key"],
            base_url = config["model"]["base_url"],
            streaming = True,
            temperature = 0.7,
            max_tokens = None,  # 不限制最大 token 数 - 作为显式参数
            request_timeout = None  # 不限制请求超时时间
        )

        # 创建持久的MCP会话
        session_manager = client.session("everbrowser")
        session = await session_manager.__aenter__()
        
        try:
            tools = await load_mcp_tools(session)
            # 配置 Agent 支持长工具调用链
            agent = create_agent(
                model,
                tools=tools,
            )

            messages = [system_msg]

            for i in range(10):
                if image_window and tkinter.Toplevel.winfo_exists(image_window):
                    image_window.update()
                    image_window.update_idletasks()
                await asyncio.sleep(0.5)
            
            # 保存会话和agent到全局变量
            global global_agent, global_session, global_session_manager
            global_agent = agent
            global_session = session
            global_session_manager = session_manager

            
        except Exception as e:
            # 确保在出错时也能正确关闭会话
            await session_manager.__aexit__(type(e), e, e.__traceback__)
            raise e
            
    except Exception as e:
        try:
            if image_window and tkinter.Toplevel.winfo_exists(image_window):
                hide_image(image_window)
        except:
            pass

        print(f"Error: {e}")
        traceback.print_exc()

        # macOS 使用通知，其他系统使用失败图标闪烁
        if platform.system() == "Darwin":
            # 发送失败通知
            send_macos_notification("everBrowser", f"⚠️ 启动失败！", sound=True)
        else:
            # 失败图标闪烁 3 次
            fail_window, fail_photo = show_image('fail.png')
            await asyncio.sleep(1)
            if fail_window and tkinter.Toplevel.winfo_exists(fail_window):
                hide_image(fail_window)
            await asyncio.sleep(1)

            fail_window, fail_photo = show_image('fail.png')
            await asyncio.sleep(1)
            if fail_window and tkinter.Toplevel.winfo_exists(fail_window):
                hide_image(fail_window)
            await asyncio.sleep(1)

            fail_window, fail_photo = show_image('fail.png')
            await asyncio.sleep(1)
            if fail_window and tkinter.Toplevel.winfo_exists(fail_window):
                hide_image(fail_window)

        cleanup_lock_file()
        exit(1)

    ### Init Finished ###
    messages = [system_msg]

    # Set up CORS middleware
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Mount static files from client directory
    if os.path.exists("client"):
        app.mount("/static", StaticFiles(directory="client"), name="static")

    # Store client globally for API access
    global global_client
    global_client = client

    # 启动服务器后再打开浏览器
    await start_server_and_browser(image_window)

    # ===== 会话历史管理辅助函数 =====

    def get_session_lock(session_id: str) -> asyncio.Lock:
        """获取或创建会话锁"""
        if session_id not in session_locks:
            session_locks[session_id] = asyncio.Lock()
        return session_locks[session_id]

    def get_session_history(session_id: str) -> list:
        """获取会话历史"""
        if session_id not in session_histories:
            session_histories[session_id] = []
        return session_histories[session_id]

    def add_to_history(session_id: str, message):
        """添加消息到历史，自动管理长度"""
        history = get_session_history(session_id)
        history.append(message)

        # 保持历史长度在限制内（保留系统消息）
        if len(history) > MAX_HISTORY_LENGTH:
            # 保留第一条系统消息，删除最旧的对话
            system_msg = history[0] if isinstance(history[0], SystemMessage) else None
            history = history[-(MAX_HISTORY_LENGTH-1):]
            if system_msg:
                history.insert(0, system_msg)
            session_histories[session_id] = history

    def clear_session_history(session_id: str):
        """清除会话历史"""
        if session_id in session_histories:
            session_histories[session_id] = []
        if session_id in stop_flags:
            del stop_flags[session_id]

    def set_stop_flag(session_id: str, value: bool = True):
        """设置停止标志"""
        stop_flags[session_id] = value

    def should_stop(session_id: str) -> bool:
        """检查是否应该停止"""
        return stop_flags.get(session_id, False)

    async def check_task_completion(session_id: str) -> str:
        """
        后台检查任务是否完成
        返回值:
        - "completed": 任务完成
        - "continue": 任务未完成，需要继续
        - "userActionRequired": 需要用户操作，停止自动继续
        """
        try:
            # 获取会话历史
            history = get_session_history(session_id)

            # 构建检查消息 - 不添加到历史，只用于检查
            check_messages = history.copy()
            check_messages.append(HumanMessage(content="""当前任务是否完成？只通过上下文判断，不要调用工具；只回答以下三个选项之一，不要回答其他内容：
- `True` - 任务已完成
- `False` - 任务未完成，我应该继续执行
- `userActionRequired` - 需要用户提供更多信息或进行操作 (例如需要用户登录)"""))

            # 使用非流式调用检查
            response = await global_agent.ainvoke({"messages": check_messages})

            if response and 'messages' in response:
                ai_message = response['messages'][-1]
                content = ai_message.content.strip()

                # 过滤 <think> 标签
                import re
                # 移除所有 <think>...</think> 标签及其内容
                content = re.sub(r'<think>.*?</think>', '', content, flags=re.DOTALL)
                content = content.strip().lower()

                print(f"[DEBUG] Task completion check response (filtered): {content}")

                # 解析回答 - 优先检查 userActionRequired
                if 'useractionrequired' in content.replace(' ', '') or '需要用户' in content or '用户操作' in content or '用户提供' in content:
                    return "userActionRequired"
                elif 'true' in content or '是' == content or '完成' in content or '已完成' in content:
                    return "completed"
                elif 'false' in content or '否' == content or '未完成' in content or '没有' in content:
                    return "continue"

            # 默认认为任务完成（保守策略，避免过度继续）
            return "completed"
        except Exception as e:
            print(f"[ERROR] Task completion check failed: {e}")
            return "completed"  # 出错时假设任务完成，避免无限循环

    async def stream_agent_response(message: str, session_id: str = "default") -> AsyncGenerator[str, None]:
        """改进版流式生成 Agent 响应 - 支持连贯上下文和自动任务完成检查"""
        MAX_AUTO_CONTINUE = 80  # 最多自动继续 80 次
        MAX_ERROR_RETRY = 80  # 最多连续错误 80 次

        # 获取会话锁，确保同一会话的请求串行处理
        lock = get_session_lock(session_id)

        async with lock:
            error_count = 0  # 错误计数器

            # 确保会话处于活动状态
            if not global_session:
                error_data = {
                    'type': 'error',
                    'error': 'MCP会话未初始化',
                    'session_id': session_id,
                    'timestamp': time.time()
                }
                yield f"data: {json.dumps(error_data, ensure_ascii=False)}\n\n"
                return

            # 重置停止标志
            set_stop_flag(session_id, False)

            # 获取会话历史
            history = get_session_history(session_id)

            # 如果历史为空，添加系统消息
            if not history:
                history.append(SystemMessage(content=system_msg_content))
                session_histories[session_id] = history

            # 添加当前用户消息到历史
            user_message = HumanMessage(content=message)
            add_to_history(session_id, user_message)

            # 发送开始标记（只发送一次）
            yield f"data: {json.dumps({'type': 'start', 'session_id': session_id, 'timestamp': time.time()})}\n\n"

            # 主循环：处理任务和错误重试
            continue_count = 0
            connection_alive = True

            while continue_count <= MAX_AUTO_CONTINUE and error_count < MAX_ERROR_RETRY:
                try:
                    # 如果用户请求停止，退出循环
                    if should_stop(session_id):
                        print(f"[INFO] Stop requested for session {session_id}")
                        connection_alive = False
                        break

                    # 构建完整的消息列表（包含历史上下文）
                    chat_messages = get_session_history(session_id).copy()

                    # 使用更智能的流式处理
                    last_content = ""  # 避免重复发送相同内容
                    tool_call_active = False  # 跟踪是否有活跃的工具调用
                    skip_next_content_token = False   # 跳过工具调用后的第一个有内容的token
                    in_think_block = False    # 标记是否在think块中（处理跨chunk的情况）
                    ai_response_content = ""  # 累积 AI 的完整回复

                    async for chunk in global_agent.astream(
                        {"messages": chat_messages},
                        stream_mode=["messages"]
                    ):
                        # 检查停止标志
                        if should_stop(session_id):
                            print(f"[INFO] Stop requested for session {session_id}")
                            connection_alive = False
                            break

                        # 检查连接是否仍然活跃
                        try:
                            # 尝试发送一个心跳包来检查连接
                            yield f"data: {json.dumps({'type': 'ping', 'timestamp': time.time()})}\n\n"
                        except (ConnectionError, BrokenPipeError, GeneratorExit):
                            print(f"[INFO] Client disconnected, stopping stream for session {session_id}")
                            connection_alive = False
                            break

                        # LangChain 的流式响应格式：('messages', (AIMessageChunk(...), metadata_dict))
                        if isinstance(chunk, tuple) and len(chunk) >= 2:
                            # 检查是否是 messages 类型
                            if chunk[0] == 'messages':
                                # 获取 AIMessageChunk 对象（元组的第一个元素）
                                message_data = chunk[1]
                                if isinstance(message_data, tuple) and len(message_data) >= 1:
                                    ai_message_chunk = message_data[0]

                                    # 提取内容
                                    if hasattr(ai_message_chunk, 'content') and ai_message_chunk.content:
                                        content = str(ai_message_chunk.content)

                                        # 累积 AI 回复内容（用于添加到历史）
                                        ai_response_content += content

                                        # 只发送新增的内容，避免重复
                                        if content != last_content:
                                            # 过滤掉代码块标签
                                            if not content.strip().startswith('```') and not content.strip().startswith('</'):
                                                # 检查是否需要跳过这个token（工具调用后的第一个有内容的token）
                                                if skip_next_content_token:
                                                    print(f"[DEBUG] Skipping tool return token: {content[:50]}{'...' if len(content) > 50 else ''}")
                                                    skip_next_content_token = False
                                                    last_content = content
                                                    continue

                                                # 过滤 think 标签对中的内容
                                                original_content = content

                                                if in_think_block:
                                                    if '</think>' in content:
                                                        think_end = content.find('</think>') + 8
                                                        content = content[think_end:]
                                                        in_think_block = False
                                                    else:
                                                        content = ""
                                                else:
                                                    if '<think>' in content and '</think>' in content:
                                                        think_start = content.find('<think>')
                                                        think_end = content.find('</think>') + 8
                                                        content = content[:think_start] + content[think_end:]
                                                    elif '<think>' in content:
                                                        think_start = content.find('<think>')
                                                        content = content[:think_start]
                                                        in_think_block = True
                                                    elif '</think>' in content:
                                                        think_end = content.find('</think>') + 8
                                                        content = content[think_end:]

                                                # 如果过滤后内容为空，跳过这个token
                                                if not content.strip():
                                                    last_content = original_content
                                                    continue

                                                # 去除内容的首尾换行
                                                content = content.strip()

                                                chunk_data = {
                                                    'type': 'token',
                                                    'content': content,
                                                    'session_id': session_id,
                                                    'timestamp': time.time()
                                                }
                                                try:
                                                    yield f"data: {json.dumps(chunk_data, ensure_ascii=False)}\n\n"
                                                except (ConnectionError, BrokenPipeError, GeneratorExit):
                                                    print(f"[INFO] Client disconnected while sending token")
                                                    connection_alive = False
                                                    break
                                                last_content = content

                                    # 处理工具调用 - 静默处理
                                    if hasattr(ai_message_chunk, 'tool_calls') and ai_message_chunk.tool_calls:
                                        print(f"[DEBUG] Tool call detected: {ai_message_chunk.tool_calls}")
                                        skip_next_content_token = True

                    # 如果连接断开，退出循环
                    if not connection_alive:
                        break

                    # 流式响应结束后，将 AI 回复添加到历史
                    if ai_response_content.strip():
                        ai_message = AIMessage(content=ai_response_content)
                        add_to_history(session_id, ai_message)
                        print(f"[INFO] Added AI response to history for session {session_id}")

                        # 重置错误计数（成功响应后）
                        error_count = 0

                        # 后台检查任务是否完成
                        task_status = await check_task_completion(session_id)

                        if task_status == "completed":
                            # 任务完成，退出循环
                            print(f"[INFO] Task completed (count: {continue_count})")
                            break
                        elif task_status == "userActionRequired":
                            # 需要用户操作，停止自动继续
                            print(f"[INFO] User action required, stopping auto-continue (count: {continue_count})")
                            break
                        elif task_status == "continue":
                            # 检查是否达到最大次数
                            if continue_count >= MAX_AUTO_CONTINUE:
                                print(f"[INFO] Max auto-continue reached ({MAX_AUTO_CONTINUE})")
                                break

                            # 任务未完成，自动继续
                            print(f"[INFO] Task not completed, auto-continuing... ({continue_count + 1}/{MAX_AUTO_CONTINUE})")
                            continue_count += 1

                            # 添加"继续"到历史
                            continue_message = HumanMessage(content="继续")
                            add_to_history(session_id, continue_message)

                            # 继续下一轮循环
                            continue
                        else:
                            # 未知状态，默认完成
                            print(f"[WARNING] Unknown task status: {task_status}, treating as completed")
                            break
                    else:
                        # 没有内容，退出循环
                        break

                except Exception as e:
                    # 增加错误计数
                    error_count += 1
                    print(f"[ERROR] Stream error for session {session_id} (attempt {error_count}/{MAX_ERROR_RETRY}): {str(e)}")
                    traceback.print_exc()

                    # 🔧 修复：先保存已经生成的内容到历史记录（如果有的话）
                    if ai_response_content.strip():
                        try:
                            ai_message = AIMessage(content=ai_response_content)
                            add_to_history(session_id, ai_message)
                            print(f"[INFO] Saved partial AI response to history before retry ({len(ai_response_content)} chars)")
                        except Exception as save_error:
                            print(f"[WARNING] Failed to save partial response: {save_error}")

                    if error_count >= MAX_ERROR_RETRY:
                        # 达到最大错误次数，报错
                        print(f"[FATAL] Max error retries reached ({MAX_ERROR_RETRY}), giving up")
                        error_data = {
                            'type': 'error',
                            'error': f"连续错误 {error_count} 次: {str(e)}",
                            'session_id': session_id,
                            'timestamp': time.time()
                        }
                        try:
                            yield f"data: {json.dumps(error_data, ensure_ascii=False)}\n\n"
                        except (ConnectionError, BrokenPipeError, GeneratorExit):
                            pass
                        break
                    else:
                        # 未达到最大次数，添加"继续"并重试
                        print(f"[INFO] Error occurred, adding '继续' to retry... ({error_count}/{MAX_ERROR_RETRY})")
                        try:
                            # 尝试添加"继续"到历史
                            continue_message = HumanMessage(content="继续")
                            add_to_history(session_id, continue_message)
                            # 继续循环
                            continue
                        except Exception as retry_error:
                            # 如果添加"继续"也失败了，直接报错
                            print(f"[FATAL] Failed to add continue message: {retry_error}")
                            error_data = {
                                'type': 'error',
                                'error': f"重试失败: {str(retry_error)}",
                                'session_id': session_id,
                                'timestamp': time.time()
                            }
                            try:
                                yield f"data: {json.dumps(error_data, ensure_ascii=False)}\n\n"
                            except (ConnectionError, BrokenPipeError, GeneratorExit):
                                pass
                            break

            # 发送结束标记（只在连接正常时发送一次）
            if connection_alive:
                try:
                    yield f"data: {json.dumps({'type': 'end', 'session_id': session_id, 'timestamp': time.time()})}\n\n"
                except (ConnectionError, BrokenPipeError, GeneratorExit):
                    print(f"[INFO] Client disconnected while sending end marker")

    @app.post("/chat", response_model=ChatResponse)
    async def chat(request: ChatRequest):
        """普通聊天接口（非流式）- 使用状态化MCP工具"""
        try:
            # 确保会话处于活动状态
            if not global_session:
                raise Exception("MCP会话未初始化")
            
            chat_messages = [SystemMessage(content=system_msg_content), HumanMessage(content=request.message)]
            response = await global_agent.ainvoke({"messages": chat_messages})

            if response and 'messages' in response:
                ai_message = response['messages'][-1]
                content = ai_message.content if hasattr(ai_message, 'content') else "抱歉，我现在无法处理您的请求。"
            else:
                content = "抱歉，我现在无法处理您的请求。"

            return ChatResponse(
                content=content,
                session_id=request.session_id,
                timestamp=time.time()
            )
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    @app.post("/chat/stream")
    async def chat_stream(request: ChatRequest):
        """流式聊天接口"""
        # 支持对话历史格式
        if hasattr(request, 'messages') and request.messages:
            # 如果收到的是对话历史，使用最后一条用户消息
            last_user_message = None
            for msg in reversed(request.messages):
                if msg.get('role') == 'user':
                    last_user_message = msg.get('content', '')
                    break
            message = last_user_message or request.message
        else:
            # 兼容旧格式
            message = request.message
            
        return StreamingResponse(
            stream_agent_response(message, request.session_id),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no"  # 禁用 Nginx 缓冲
            }
        )

    @app.post("/chat/stop")
    async def stop_generation(request: ChatRequest):
        """停止当前会话的生成"""
        try:
            session_id = request.session_id
            set_stop_flag(session_id, True)
            print(f"[INFO] Stop flag set for session {session_id}")

            return {
                "success": True,
                "message": f"已请求停止会话 {session_id} 的生成",
                "session_id": session_id,
                "timestamp": time.time()
            }
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    @app.post("/chat/clear")
    async def clear_history(request: ChatRequest):
        """清除会话历史"""
        try:
            session_id = request.session_id
            clear_session_history(session_id)
            print(f"[INFO] Cleared history for session {session_id}")

            return {
                "success": True,
                "message": f"已清除会话 {session_id} 的历史",
                "session_id": session_id,
                "timestamp": time.time()
            }
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    @app.get("/chat/history/{session_id}")
    async def get_history(session_id: str):
        """获取会话历史（调试用）"""
        try:
            history = get_session_history(session_id)
            # 转换为可序列化的格式
            history_data = []
            for msg in history:
                if isinstance(msg, SystemMessage):
                    history_data.append({"role": "system", "content": msg.content})
                elif isinstance(msg, HumanMessage):
                    history_data.append({"role": "user", "content": msg.content})
                elif isinstance(msg, AIMessage):
                    history_data.append({"role": "assistant", "content": msg.content})

            return {
                "session_id": session_id,
                "message_count": len(history_data),
                "messages": history_data,
                "timestamp": time.time()
            }
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    @app.get("/health")
    async def health_check():
        """健康检查接口"""
        return {
            "status": "healthy",
            "service": "everBrowser API",
            "timestamp": time.time(),
            "agent_ready": global_agent is not None,
            "session_active": global_session is not None,
            "mcp_tools_ready": global_session is not None and global_agent is not None
        }

    @app.get("/")
    async def root():
        """根路径 - 返回聊天页面"""
        if os.path.exists("client/index.html"):
            return FileResponse("client/index.html")
        elif os.path.exists("index.html"):
            return FileResponse("index.html")
        else:
            return {
                "message": "everBrowser API Server",
                "version": "1.0.0",
                "endpoints": {
                    "chat": "/chat - 普通聊天接口",
                    "chat_stream": "/chat/stream - 流式聊天接口（支持上下文）",
                    "chat_stop": "/chat/stop - 停止当前生成",
                    "chat_clear": "/chat/clear - 清除会话历史",
                    "chat_history": "/chat/history/{session_id} - 查看会话历史",
                    "health": "/health - 健康检查接口",
                    "chat_ui": "/ - 聊天界面",
                    "userscript": "/chat.user.js - Tampermonkey 用户脚本",
                    "docs": "/docs - Swagger API 文档"
                }
            }

    @app.get("/icon.png")
    async def get_icon():
        """提供 icon.png"""
        if os.path.exists("icon.png"):
            return FileResponse("icon.png", media_type="image/png")
        else:
            raise HTTPException(status_code=404, detail="Icon not found")

    @app.get("/api")
    async def api_info():
        """API 信息接口"""
        return {
            "message": "everBrowser API Server",
            "version": "1.0.0",
            "endpoints": {
                "chat": "/chat - 普通聊天接口",
                "chat_stream": "/chat/stream - 流式聊天接口（支持上下文）",
                "chat_stop": "/chat/stop - 停止当前生成",
                "chat_clear": "/chat/clear - 清除会话历史",
                "chat_history": "/chat/history/{session_id} - 查看会话历史",
                "health": "/health - 健康检查接口",
                "userscript": "/chat.user.js - Tampermonkey 用户脚本",
                "docs": "/docs - Swagger API 文档"
            }
        }

    @app.get("/chat.user.js")
    async def get_userscript():
        """提供 Tampermonkey 用户脚本"""
        script_path = "chat.user.js"
        if os.path.exists(script_path):
            return FileResponse(
                script_path,
                media_type="application/javascript",
                headers={
                    "Content-Disposition": "inline; filename=chat.user.js",
                    "Cache-Control": "no-cache, no-store, must-revalidate",
                    "Pragma": "no-cache",
                    "Expires": "0"
                }
            )
        else:
            raise HTTPException(status_code=404, detail="User script not found")

    try:
        # 保持主线程运行
        while True:
            await asyncio.sleep(1)
    except KeyboardInterrupt:
        print("\n🛑 Shutting down everBrowser API Server...")
        cleanup_lock_file()
        server.should_exit = True
        await server_task
    finally:
        cleanup_lock_file()
    

if __name__ == "__main__":
    asyncio.run(main())