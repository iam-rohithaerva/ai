import os
import json
import asyncio
from flask import Flask, request, jsonify
from openai import OpenAI
from mcp_client import get_tools, run_tool

# Flask serves the frontend files
app = Flask(__name__, static_folder="../frontend", static_url_path="")

MODEL = "nvidia/nemotron-3-super-120b-a12b:free"
client = OpenAI(
    base_url="https://openrouter.ai/api/v1",
    api_key=os.getenv("OPENROUTER_API_KEY"),
)

conversation_history = []


def mcp_to_openai(tools):
    """Convert MCP tools into the LLM tool format."""
    return [
        {
            "type": "function",
            "function": {
                "name": t.name,
                "description": t.description,
                "parameters": t.inputSchema,
            },
        }
        for t in tools
    ]


@app.route("/")
def home():
    return app.send_static_file("index.html")


@app.route("/chat", methods=["POST"])
def chat():
    data = request.get_json() or {}
    message = (data.get("message") or "").strip()
    if not message:
        return jsonify({"error": "Empty message"}), 400

    conversation_history.append({"role": "user", "content": message})

    try:
        # 1. Get the tools list from the MCP server
        tools = mcp_to_openai(asyncio.run(get_tools()))

        # 2. Send the message and tools to the LLM
        response = client.chat.completions.create(
            model=MODEL, messages=conversation_history, tools=tools
        )
        msg = response.choices[0].message

        # 3. If the LLM asks for a tool, run it through MCP
        if msg.tool_calls:
            conversation_history.append(msg.model_dump(exclude_none=True))
            for tc in msg.tool_calls:
                result = asyncio.run(
                    run_tool(tc.function.name, json.loads(tc.function.arguments))
                )
                conversation_history.append(
                    {"role": "tool", "tool_call_id": tc.id, "content": result}
                )

            # 4. Get the final answer using the tool result
            response = client.chat.completions.create(
                model=MODEL, messages=conversation_history
            )
            msg = response.choices[0].message

        conversation_history.append({"role": "assistant", "content": msg.content})
        return jsonify({"response": msg.content})

    except Exception as e:
        return jsonify({"error": str(e)}), 500


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
