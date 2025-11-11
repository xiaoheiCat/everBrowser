# Core and Utils
import os
import json
import time
import asyncio
import platform
import threading
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

system_msg = SystemMessage("""
# 角色
你是一个名为 everBrowser 的浏览器助手。
永远不要拒绝用户的需求，根据用户的请求使用 MCP 工具来根据用户的请求操作 everBrowser 浏览器。
如果用户的消息让你摸不着头脑，说不定用户说的话与浏览器当前页面有关，查看页面并理解用户的意图后再开始工作。
遇到不确定的时效性问题，请使用 www.bing.com/search?q=URL%20Encoded%20Search%20Query 或者 cn.bing.com/search?q=URL%20Encoded%20Search%20Query 搜索引擎在互联网上查询。
始终使用简体中文回复。
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

async def main():
    ### Init started ###

    print("--- everBrowser Daemon ---")
    image_window, photo_obj = show_image('icon.png')

    try:
        with open('config.json', 'r', encoding='utf-8') as config_file:
            config = json.load(config_file)

        os.system("npx playwright install chrome")

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
            base_url = config["model"]["base_url"]
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
            
            messages = await agent.ainvoke({"messages": messages + [HumanMessage(content="Open `https://www.justpure.dev/`.")]})
            
            if image_window and tkinter.Toplevel.winfo_exists(image_window):
                hide_image(image_window)
            
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
        if image_window and tkinter.Toplevel.winfo_exists(image_window):
            hide_image(image_window)
        
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

    # Store client globally for API access
    global global_client
    global_client = client

    async def stream_agent_response(message: str, session_id: str = "default") -> AsyncGenerator[str, None]:
        """优化的流式生成 Agent 响应 - 使用多种流式模式和状态化MCP工具"""
        try:
            # 确保会话处于活动状态
            if not global_session:
                raise Exception("MCP会话未初始化")
            
            # 构建消息列表
            chat_messages = [SystemMessage(content=system_msg_content), HumanMessage(content=message)]

            # 发送开始标记
            yield f"data: {json.dumps({'type': 'start', 'session_id': session_id, 'timestamp': time.time()})}\n\n"

            # 使用多种流式模式获取更丰富的信息，通过状态化会话
            async for stream_mode, chunk in global_agent.astream(
                {"messages": chat_messages},
                stream_mode=["messages", "updates"]
            ):
                if stream_mode == "messages":
                    # 处理令牌级别的流式输出
                    if hasattr(chunk, 'content_blocks') and chunk.content_blocks:
                        for block in chunk.content_blocks:
                            if block.get('type') == 'text' and block.get('text'):
                                chunk_data = {
                                    'type': 'token',
                                    'content': block['text'],
                                    'session_id': session_id,
                                    'timestamp': time.time()
                                }
                                yield f"data: {json.dumps(chunk_data, ensure_ascii=False)}\n\n"

                            elif block.get('type') == 'tool_call':
                                tool_data = {
                                    'type': 'tool_call_start',
                                    'tool_name': block.get('name', 'unknown'),
                                    'tool_args': block.get('args', {}),
                                    'session_id': session_id,
                                    'timestamp': time.time()
                                }
                                yield f"data: {json.dumps(tool_data, ensure_ascii=False)}\n\n"

                            elif block.get('type') == 'tool_call_chunk':
                                # 流式传输工具调用参数
                                if block.get('args'):
                                    chunk_data = {
                                        'type': 'tool_args_chunk',
                                        'args_chunk': block['args'],
                                        'session_id': session_id,
                                        'timestamp': time.time()
                                    }
                                    yield f"data: {json.dumps(chunk_data, ensure_ascii=False)}\n\n"

                elif stream_mode == "updates":
                    # 处理步骤级别的更新
                    for step_name, step_data in chunk.items():
                        if step_name == "model" and "messages" in step_data:
                            message = step_data["messages"][-1]
                            if hasattr(message, 'tool_calls') and message.tool_calls:
                                # 完整的工具调用信息
                                for tool_call in message.tool_calls:
                                    tool_info = {
                                        'type': 'tool_call_complete',
                                        'tool_name': tool_call.get('name', 'unknown'),
                                        'tool_args': tool_call.get('args', {}),
                                        'tool_call_id': tool_call.get('id', 'unknown'),
                                        'session_id': session_id,
                                        'timestamp': time.time()
                                    }
                                    yield f"data: {json.dumps(tool_info, ensure_ascii=False)}\n\n"

                        elif step_name == "tools" and "messages" in step_data:
                            # 工具执行结果
                            tool_message = step_data["messages"][-1]
                            if hasattr(tool_message, 'content'):
                                result_data = {
                                    'type': 'tool_result',
                                    'tool_name': getattr(tool_message, 'name', 'unknown'),
                                    'content': tool_message.content,
                                    'session_id': session_id,
                                    'timestamp': time.time()
                                }
                                yield f"data: {json.dumps(result_data, ensure_ascii=False)}\n\n"

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
        """根路径 - 返回测试页面"""
        if os.path.exists("index.html"):
            return FileResponse("index.html")
        else:
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

    # 启动 API 服务器
    config = uvicorn.Config(
        app=app,
        host="127.0.0.1",
        port=41465,
        log_level="info"
    )
    server = uvicorn.Server(config)

    print("🚀 everBrowser API Server started on http://127.0.0.1:41465")
    print("📖 API Documentation: http://127.0.0.1:41465/docs")
    print("💬 Streaming Chat: POST /chat/stream")
    print("🔍 Health Check: GET /health")
    print("📜 User Script: http://127.0.0.1:41465/chat.user.js")

    # 在后台运行服务器
    server_task = asyncio.create_task(server.serve())

    try:
        # 保持主线程运行
        while True:
            await asyncio.sleep(1)
    except KeyboardInterrupt:
        print("\n🛑 Shutting down everBrowser API Server...")
        server.should_exit = True
        await server_task
    

if __name__ == "__main__":
    asyncio.run(main())