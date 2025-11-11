# Core and Utils
import json
import time
import asyncio
import platform
import threading

# Artificiall Intelligence
from langchain_mcp_adapters.client import MultiServerMCPClient
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

    with open('config.json', 'r', encoding='utf-8') as config_file:
        config = json.load(config_file)

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

    tools = await client.get_tools()
    agent = create_agent(model, tools=tools)

    messages = [system_msg]
    try:
        for i in range(10):
            if image_window and tkinter.Toplevel.winfo_exists(image_window):
                image_window.update()
                image_window.update_idletasks()
            await asyncio.sleep(0.5)
        
        messages = await agent.ainvoke({"messages": messages + [HumanMessage(content="Open `https://www.justpure.dev/`.")]})
        
        if image_window and tkinter.Toplevel.winfo_exists(image_window):
            hide_image(image_window)
            
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
    # 这里开始将 Agent 中的能力监听 127.0.0.1 作为 API 开放给其他服务
    

if __name__ == "__main__":
    asyncio.run(main())