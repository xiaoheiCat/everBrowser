# Core and Utils
import os
import sys
import json
import time
import asyncio
import platform
import threading
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
如果用户的消息让你摸不着头脑，说不定用户说的话与浏览器当前页面有关，查看页面并理解用户的意图后再开始工作。
遇到不确定的时效性问题，请使用 www.bing.com/search?q=URL%20Encoded%20Search%20Query 或者 cn.bing.com/search?q=URL%20Encoded%20Search%20Query 搜索引擎在互联网上查询。
始终使用简体中文思考与回复。
""")

# API Models
class ChatRequest(BaseModel):
    message: str
    session_id: str = "default"

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
    
    # 服务器启动完成后再打开浏览器
    try:
        if os.name == 'nt':  # Windows
            os.system("cmd /c \"start /b npx playwright cr http://127.0.0.1:41465 ^& exit\"")
        else:  # Unix / Linux / macOS
            os.system("npx playwright cr http://127.0.0.1:41465 &")
    except Exception as e:
        print(f"Warning: 无法自动打开浏览器: {e}")

    if image_window and tkinter.Toplevel.winfo_exists(image_window):
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

    image_window, photo_obj = show_image('starting.png')

    try:
        with open('config.json', 'r', encoding='utf-8') as config_file:
            config = json.load(config_file)

        os.system("npx playwright install")

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
            temperature = 0.7
        )

        # 创建持久的MCP会话
        session_manager = client.session("everbrowser")
        session = await session_manager.__aenter__()
        
        try:
            tools = await load_mcp_tools(session)
            agent = create_agent(model, tools=tools)

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

    async def stream_agent_response(message: str, session_id: str = "default") -> AsyncGenerator[str, None]:
        """改进版流式生成 Agent 响应 - 更智能的内容提取"""
        try:
            # 确保会话处于活动状态
            if not global_session:
                raise Exception("MCP会话未初始化")
            
            # 构建消息列表
            chat_messages = [SystemMessage(content=system_msg_content), HumanMessage(content=message)]

            # 发送开始标记
            yield f"data: {json.dumps({'type': 'start', 'session_id': session_id, 'timestamp': time.time()})}\n\n"

            # 使用更智能的流式处理
            last_content = ""  # 避免重复发送相同内容
            tool_call_active = False  # 跟踪是否有活跃的工具调用
            skip_next_token = False   # 标记是否需要跳过下一个token
            
            async for chunk in global_agent.astream(
                {"messages": chat_messages},
                stream_mode=["messages"]
            ):
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
                                # 只发送新增的内容，避免重复
                                if content != last_content:
                                    # 过滤掉代码块标签，但保留 think 标签内的内容
                                    if not content.strip().startswith('```') and not content.strip().startswith('</'):
                                        # 检查是否需要跳过这个token（工具调用后的第一个token）
                                        if skip_next_token:
                                            print(f"[DEBUG] Skipping tool return token: {content[:50]}{'...' if len(content) > 50 else ''}")
                                            skip_next_token = False
                                            last_content = content  # 更新last_content避免重复处理
                                            continue
                                        
                                        # 处理 <think> 标签 - 在每行开始前添加 >，并移除标签本身
                                        if '<think>' in content and '</think>' in content:
                                            # 完整标签的情况
                                            think_start = content.find('<think>')
                                            think_end = content.find('</think>') + 8  # </think> 的长度
                                            
                                            before_think = content[:think_start]
                                            think_content = content[think_start + 7:think_end - 8]  # 移除标签
                                            after_think = content[think_end:]
                                            
                                            # 为 think 内容每行添加 > 前缀，跳过空行
                                            quoted_think = '\n'.join(['> ' + line for line in think_content.split('\n') if line.strip()])
                                            
                                            content = before_think + '\n' + quoted_think + '\n---\n' + after_think
                                        elif '<think>' in content:
                                            # 只有开始标签的情况
                                            before_think = content.split('<think>')[0]
                                            think_content = content.split('<think>')[1]
                                            
                                            # 为 think 内容每行添加 > 前缀，跳过空行
                                            quoted_think = '\n'.join(['> ' + line for line in think_content.split('\n') if line.strip()])
                                            
                                            content = before_think + '\n' + quoted_think
                                        elif '</think>' in content:
                                            # 只有结束标签的情况
                                            think_content = content.split('</think>')[0]
                                            after_think = content.split('</think>')[1]
                                            
                                            # 为 think 内容每行添加 > 前缀，跳过空行
                                            quoted_think = '\n'.join(['> ' + line for line in think_content.split('\n') if line.strip()])
                                            
                                            content = quoted_think + '\n---\n' + after_think
                                        
                                        # 添加调试信息 - 记录每个token
                                        print(f"[DEBUG] Processing token: {content[:50]}{'...' if len(content) > 50 else ''}")
                                        
                                        chunk_data = {
                                            'type': 'token',
                                            'content': content,
                                            'session_id': session_id,
                                            'timestamp': time.time()
                                        }
                                        yield f"data: {json.dumps(chunk_data, ensure_ascii=False)}\n\n"
                                        last_content = content
                            
                            # 处理工具调用 - 静默处理，不发送给客户端
                            if hasattr(ai_message_chunk, 'tool_calls') and ai_message_chunk.tool_calls:
                                # 工具调用信息不发送给客户端，保持静默处理
                                print(f"[DEBUG] Tool call detected but not sent to client: {ai_message_chunk.tool_calls}")
                                # 设置标记，跳过工具调用后的第一个token（通常是工具返回结果）
                                skip_next_token = True
                                pass
                
                # 也可能是直接的 AIMessage 对象（向后兼容）
                elif hasattr(chunk, 'content') and chunk.content:
                    content = str(chunk.content)
                    if content != last_content:
                        if not content.strip().startswith('```') and not content.strip().startswith('</'):
                            # 检查是否需要跳过这个token（工具调用后的第一个token）
                            if skip_next_token:
                                print(f"[DEBUG] Skipping tool return token (direct): {content[:50]}{'...' if len(content) > 50 else ''}")
                                skip_next_token = False
                                last_content = content  # 更新last_content避免重复处理
                                continue
                            
                            # 处理 <think> 标签 - 在每行开始前添加 >，并移除标签本身
                            if '<think>' in content and '</think>' in content:
                                # 完整标签的情况
                                think_start = content.find('<think>')
                                think_end = content.find('</think>') + 8  # </think> 的长度
                                
                                before_think = content[:think_start]
                                think_content = content[think_start + 7:think_end - 8]  # 移除标签
                                after_think = content[think_end:]
                                
                                # 为 think 内容每行添加 > 前缀，跳过空行
                                quoted_think = '\n'.join(['> ' + line for line in think_content.split('\n') if line.strip()])
                                
                                content = before_think + '\n' + quoted_think + '\n---\n' + after_think
                            elif '<think>' in content:
                                # 只有开始标签的情况
                                before_think = content.split('<think>')[0]
                                think_content = content.split('<think>')[1]
                                
                                # 为 think 内容每行添加 > 前缀，跳过空行
                                quoted_think = '\n'.join(['> ' + line for line in think_content.split('\n') if line.strip()])
                                
                                content = before_think + '\n' + quoted_think
                            elif '</think>' in content:
                                # 只有结束标签的情况
                                think_content = content.split('</think>')[0]
                                after_think = content.split('</think>')[1]
                                
                                # 为 think 内容每行添加 > 前缀，跳过空行
                                quoted_think = '\n'.join(['> ' + line for line in think_content.split('\n') if line.strip()])
                                
                                content = quoted_think + '\n---\n' + after_think
                            
                            # 添加调试信息 - 记录每个token
                            print(f"[DEBUG] Processing token (direct): {content[:50]}{'...' if len(content) > 50 else ''}")
                            
                            chunk_data = {
                                'type': 'token',
                                'content': content,
                                'session_id': session_id,
                                'timestamp': time.time()
                            }
                            yield f"data: {json.dumps(chunk_data, ensure_ascii=False)}\n\n"
                            last_content = content

            # 发送结束标记
            yield f"data: {json.dumps({'type': 'end', 'session_id': session_id, 'timestamp': time.time()})}\n\n"

        except Exception as e:
            # 发送错误信息
            error_data = {
                'type': 'error',
                'error': str(e),
                'session_id': session_id,
                'timestamp': time.time()
            }
            yield f"data: {json.dumps(error_data, ensure_ascii=False)}\n\n"

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
        return StreamingResponse(
            stream_agent_response(request.message, request.session_id),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no"  # 禁用 Nginx 缓冲
            }
        )

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
                    "chat_stream": "/chat/stream - 流式聊天接口",
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
                "chat_stream": "/chat/stream - 流式聊天接口",
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