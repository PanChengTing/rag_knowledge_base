from mcp.server.fastmcp import FastMCP
from app.mcp_server.tools import register_tools

knowledge_mcp = FastMCP(
    name = "rag-knowledge-base",
    instructions = (
        "知识库工具集，先调用ask_knowledge_base直接回答"
    ),
    stateless_http =True,
    json_response = True,
    stream_http_path = "/"

)

register_tools(knowledge_mcp)
