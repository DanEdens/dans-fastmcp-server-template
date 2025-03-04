from fastmcp import FastMCP, Context
from pymongo import MongoClient
from datetime import datetime, UTC
import uuid
import os
from dotenv import load_dotenv
import json
# import logging
import asyncio
from aiohttp import web
import paho.mqtt.client as mqtt
from typing import Union
import subprocess

# Import the tool functions from the tools module
from fastmcp_todo_server.tools import (
    add_todo,
    query_todos,
    update_todo,
    mqtt_publish,
    delete_todo,
    get_todo,
    mark_todo_complete,
    list_todos_by_status,
    add_lesson,
    get_lesson,
    update_lesson,
    delete_lesson,
    list_lessons,
    search_todos,
    search_lessons,
)

# Comment out all logging configuration
# logging.basicConfig(
#     level=logging.DEBUG,
#     format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
# )
# logger = logging.getLogger(__name__)

# Also enable debug logging for FastMCP
# logging.getLogger('fastmcp').setLevel(logging.DEBUG)
# logging.getLogger('mcp').setLevel(logging.DEBUG)

# Load environment variables
load_dotenv()

# MongoDB configuration
MONGODB_URI = os.getenv("MONGODB_URI", "mongodb://localhost:27017")
MONGODB_DB = os.getenv("MONGODB_DB", "swarmonomicon")
MONGODB_COLLECTION = os.getenv("MONGODB_COLLECTION", "todos")

# MQTT configuration
MQTT_HOST = "3.134.3.199"
MQTT_PORT = 3003
MQTT_KEEPALIVE = 60

# Cursor MCP configuration
# CURSOR_MCP_URL = os.getenv("CURSOR_MCP_URL", "http://localhost:8000")
# CURSOR_MCP_SSE_ENDPOINT = os.getenv("CURSOR_MCP_SSE_ENDPOINT", "/sse")

# Import the server instance from our server module
from fastmcp_todo_server.server import server

# Create MongoDB connection at module level
mongo_client = MongoClient(MONGODB_URI)
db = mongo_client[MONGODB_DB]
collection = db[MONGODB_COLLECTION]
lessons_collection = db["lessons_learned"]

# Register tools using the FastMCP decorator syntax
@server.tool()
async def add_todo_tool(description: str, priority: str = "initial", target_agent: str = "user", ctx: Context = None) -> dict:
    return await add_todo(description, priority, target_agent, ctx)

@server.tool()
async def query_todos_tool(filter: dict = None, projection: dict = None, limit: int = 100) -> dict:
    return await query_todos(filter, projection, limit)

@server.tool()
async def update_todo_tool(todo_id: str, updates: dict, ctx: Context = None) -> str:
    return await update_todo(todo_id, updates, ctx)

@server.tool()
async def mqtt_publish_tool(topic: str, message: str, ctx: Context = None) -> str:
    await server.publish(topic, message)
    return {"topic": topic, "message": message}

@server.tool()
async def update_device_status_tool(agent_name: str, status: bool = True, ctx: Context = None) -> str:
    """
    Updates the status of a device in the MQTT Status Dashboard.
    
    Args:
        agent_name: Name of the device to update
        status: True for online (green), False for offline (red)
        
    Returns:
        Result of the operation
    """
    topic = f"status/{agent_name}/alive"
    message = "1" if status else "0"
    await server.publish(topic, message)
    status_text = "online" if status else "offline"
    return {"device": agent_name, "status": status_text, "topic": topic}

@server.tool()
async def deploy_nodered_flow_tool(flow_json_name: str, ctx: Context = None) -> str:
    """
    Deploys a Node-RED flow to a Node-RED instance.
    
    Args:
        flow_json_name: The name of the flow JSON file in the dashboard directory
        
    Returns:
        Result of the deployment operation
    """
    import aiohttp
    import base64
    import json
    import logging

    # Set up logging
    logging.basicConfig(level=logging.DEBUG)
    logger = logging.getLogger(__name__)

    # Set default Node-RED URL if not provided
    node_red_url = os.getenv("NR_URL", "http://localhost:9191")
    username = os.getenv("NR_USER", None)
    password = os.getenv("NR_PASS", None)

    logger.debug(f"Node-RED URL: {node_red_url}")
    logger.debug(f"Username: {username}")
    logger.debug(f"Password: {'*' * len(password) if password else 'None'}")

    # Add local git pull
    dashboard_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../dashboard"))
    result = ""
    try:
        result = subprocess.run(['git', 'pull'], cwd=dashboard_dir, check=True)
    except subprocess.CalledProcessError as e:
        return {"success": False, "error": f"Git pull failed: {str(e)} {result}"}

    flow_json_path = f"../../dashboard/{flow_json_name}"
    flow_path = os.path.abspath(os.path.join(os.path.dirname(__file__), flow_json_path))
    
    if not os.path.exists(flow_path):
        return {"success": False, "error": f"Flow file not found: {flow_json_name}, {result}"}

    # Read the JSON content from the file
    try:
        with open(flow_path, 'r') as file:
            flow_data = json.load(file)
    except json.JSONDecodeError as e:
        return {"success": False, "error": f"Invalid JSON in file {flow_json_name}: {str(e)}"}
    except Exception as e:
        return {"success": False, "error": f"Error reading file {flow_json_name}: {str(e)}"}

    # Validate flow_data is either a list or a dict
    if not isinstance(flow_data, (list, dict)):
        return {"success": False, "error": f"Flow JSON must be a list or dict, got {type(flow_data).__name__}"}

    # If it's a single flow object, wrap it in a list
    if isinstance(flow_data, dict):
        flow_data = [flow_data]

    headers = {
        "Content-Type": "application/json"
    }

    # Add authentication if provided
    if username and password:
        auth_string = f"{username}:{password}"
        encoded_auth = base64.b64encode(auth_string.encode()).decode()
        headers["Authorization"] = f"Basic {encoded_auth}"
        logger.debug(f"Authorization header: {headers['Authorization']}")

    try:
        # Determine if this is a new flow or an update to an existing one
        flow_id = None
        flow_label = None

        # Find the tab/flow ID and label if available in the flow JSON
        if isinstance(flow_data, list):
            for node in flow_data:
                if node.get("type") == "tab":
                    flow_id = node.get("id")
                    flow_label = node.get("label")
                    break

        async with aiohttp.ClientSession() as session:
            # If we have an ID, check if the flow exists
            if flow_id and flow_label:
                async with session.get(f"{node_red_url}/flows", headers=headers) as response:
                    logger.debug(f"Flows check response status: {response.status}")
                    logger.debug(f"Flows check response headers: {response.headers}")
                    if response.status == 200:
                        existing_flows = await response.json()
                        # Check if flow with this ID exists
                        flow_exists = any(f.get("id") == flow_id and f.get("type") == "tab" for f in existing_flows)

                        # If flow already exists, update it
                        if flow_exists:
                            operation = "update"
                            endpoint = f"{node_red_url}/flow/{flow_id}"
                            method = session.put
                        else:
                            operation = "create"
                            endpoint = f"{node_red_url}/flows"
                            method = session.post
                    else:
                        # If can't fetch flows, just try to create
                        operation = "create"
                        endpoint = f"{node_red_url}/flows"
                        method = session.post
            else:
                # No ID found, just create as new flow
                operation = "create"
                endpoint = f"{node_red_url}/flows"
                method = session.post

            # Deploy the flow
            async with method(endpoint, headers=headers, json=flow_data) as response:
                logger.debug(f"Deploy response status: {response.status}")
                logger.debug(f"Deploy response headers: {response.headers}")
                result = await response.text()
                logger.debug(f"Deploy response body: {result}")
                
                if response.status not in (200, 201):
                    return {"success": False, "error": f"HTTP {response.status}: {result}", "operation": operation}

                return {
                    "success": True,
                    "operation": operation,
                    "flow_id": flow_id,
                    "flow_label": flow_label,
                    "dashboard_url": f"{node_red_url}/ui"
                }

    except Exception as e:
        logger.exception("Deployment error")
        return {"success": False, "error": str(e)}

@server.tool()
async def delete_todo_tool(todo_id: str, ctx: Context = None) -> str:
    return await delete_todo(todo_id, ctx)

@server.tool()
async def get_todo_tool(todo_id: str) -> str:
    return await get_todo(todo_id)

@server.tool()
async def mark_todo_complete_tool(todo_id: str, ctx: Context = None) -> str:
    return await mark_todo_complete(todo_id, ctx)

@server.tool()
async def list_todos_by_status_tool(status: str, limit: int = 100) -> str:
    return await list_todos_by_status(status, limit)

@server.tool()
async def add_lesson_tool(language: str, topic: str, lesson_learned: str, tags: list = None, ctx: Context = None) -> str:
    return await add_lesson(language, topic, lesson_learned, tags, ctx)

@server.tool()
async def get_lesson_tool(lesson_id: str) -> str:
    return await get_lesson(lesson_id)

@server.tool()
async def update_lesson_tool(lesson_id: str, updates: dict, ctx: Context = None) -> str:
    return await update_lesson(lesson_id, updates, ctx)

@server.tool()
async def delete_lesson_tool(lesson_id: str, ctx: Context = None) -> str:
    return await delete_lesson(lesson_id, ctx)

@server.tool()
async def list_lessons_tool(limit: int = 100) -> str:
    return await list_lessons(limit)

@server.tool()
async def search_todos_tool(query: str, fields: list = None, limit: int = 100) -> str:
    """Search todos with text search capabilities"""
    return await search_todos(query, fields, limit)

@server.tool()
async def search_lessons_tool(query: str, fields: list = None, limit: int = 100) -> str:
    """Search lessons with text search capabilities"""
    return await search_lessons(query, fields, limit)

async def run_server():
    """Run the FastMCP server"""
    print("Starting FastMCP server")
    try:
        import sys
        import uvicorn

        # Custom exception handler to silence specific SSE-related errors
        original_excepthook = sys.excepthook

        def custom_excepthook(exctype, value, traceback):
            # Only silence the specific 'NoneType' object is not callable errors from Starlette
            if exctype is TypeError and "'NoneType' object is not callable" in str(value) and "starlette/routing.py" in str(traceback.tb_frame):
                # Log minimally instead of full stack trace
                print(f"Suppressed known error in SSE endpoint: {str(value)}")
                return
            # For all other errors, use the original exception handler
            original_excepthook(exctype, value, traceback)

        # Replace the default exception handler
        sys.excepthook = custom_excepthook

        # Configure uvicorn to suppress specific access logs for /messages endpoint
        log_config = uvicorn.config.LOGGING_CONFIG
        if "formatters" in log_config:
            log_config["formatters"]["access"]["fmt"] = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'

        await server.run_sse_async()  # Use run_sse_async directly
    except Exception as e:
        print(f"Error in server: {str(e)}")
        raise
