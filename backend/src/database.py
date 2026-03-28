import os
from supabase import create_client, Client
from dotenv import load_dotenv

# 加载 .env 文件中的环境变量
load_dotenv()

# 获取 Supabase 配置
SUPABASE_URL: str = os.environ.get("SUPABASE_URL")
SUPABASE_KEY: str = os.environ.get("SUPABASE_KEY")

def get_supabase_client() -> Client:
    """初始化并返回 Supabase 客户端实例"""
    if not SUPABASE_URL or not SUPABASE_KEY:
        raise ValueError("无法初始化 Supabase 客户端：环境变量 SUPABASE_URL 或 SUPABASE_KEY 缺失。请检查 .env 文件。")
    return create_client(SUPABASE_URL, SUPABASE_KEY)

# 全局的 client 实例（如果有需要，也可以每次请求依赖注入）
supabase = None
try:
    if SUPABASE_URL and SUPABASE_KEY:
        supabase = get_supabase_client()
except Exception as e:
    print(f"Supabase 初始化失败: {e}")
