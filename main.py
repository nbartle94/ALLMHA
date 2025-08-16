# main.py

import os
import json
import httpx
from flask import Flask, request, jsonify

app = Flask(__name__)

# --- Environment Variables ---
# Store your sensitive information in Replit Secrets.
ANYTHINGLLM_API_KEY = os.environ.get("ANYTHINGLLM_API_KEY")
ANYTHINGLLM_URL = os.environ.get("ANYTHINGLLM_URL")
HA_API_URL = os.environ.get("HA_API_URL")
HA_ACCESS_TOKEN = os.environ.get("HA_ACCESS_TOKEN")

# --- Define Home Assistant Tools (Functions) ---
HA_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "turn_on_light",
            "description": "Turns on a specific light in Home Assistant.",
            "parameters": {
                "type": "object",
                "properties": {
                    "entity_id": {
                        "type": "string",
                        "description": "The entity ID of the light to turn on (e.g., light.kitchen_lights)."
                    }
                },
                "required": ["entity_id"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "turn_off_light",
            "description": "Turns off a specific light in Home Assistant.",
            "parameters": {
                "type": "object",
                "properties": {
                    "entity_id": {
                        "type": "string",
                        "description": "The entity ID of the light to turn off (e.g., light.kitchen_lights)."
                    }
                },
                "required": ["entity_id"]
            }
        }
    }
]

# --- Flask Endpoint ---
@app.route("/v1/chat/completions", methods=["POST"])
async def process_chat_completion():
    """Handles an OpenAI-compatible chat completion request from Home Assistant."""
    try:
        # --- DEBUG: Print environment variable values to the log ---
        print(f"ANYTHINGLLM_API_KEY: {ANYTHINGLLM_API_KEY}")
        print(f"ANYTHINGLLM_URL: {ANYTHINGLLM_URL}")
        print(f"HA_API_URL: {HA_API_URL}")
        print(f"HA_ACCESS_TOKEN: {HA_ACCESS_TOKEN}")
        
        # Safely get JSON data from the request
        try:
            data = request.json
        except Exception as e:
            print(f"Error parsing JSON from request: {e}")
            return jsonify({"error": "Invalid JSON in request"}), 400

        user_messages = [msg for msg in data.get("messages", []) if msg["role"] == "user"]
        
        user_input = user_messages[-1]["content"] if user_messages else ""
        if not user_input:
            print("Error: No user message found in request.")
            return jsonify({"error": "No user message found"}), 400

        # --- Forward to AnythingLLM ---
        anythingllm_payload = {
            "model": "deepseek/deepseek-v3-0324:free",
            "messages": [
                {
                    "role": "system",
                    "content": "You are a helpful and efficient Home Assistant conversation agent. Your primary purpose is to assist the user by controlling their smart home devices. You have access to tools that can control devices in the user's home. These tools are provided to you as `function_call` objects. If the user's request can be fulfilled by a tool, you must use that tool and only that tool. Do not provide any conversational response in addition to the tool call. Your response for a tool call must be a valid `function_call` object as defined in your provided tools. If the user's request is not related to controlling the home, provide a helpful and brief conversational response."
                },
                {"role": "user", "content": user_input},
            ],
            "tools": HA_TOOLS,
        }
        
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {ANYTHINGLLM_API_KEY}"
        }

        print(f"Sending payload to AnythingLLM: {anythingllm_payload}")
        print(f"AnythingLLM URL: {ANYTHINGLLM_URL}/v1/workspace/dnu/chat")

        async with httpx.AsyncClient() as client:
            anythingllm_response = await client.post(
                f"{ANYTHINGLLM_URL}/v1/workspace/dnu/chat",
                headers=headers,
                json=anythingllm_payload
            )
            anythingllm_response.raise_for_status()
            llm_response_data = anythingllm_response.json()

        # --- Process AnythingLLM's Response ---
        message = llm_response_data["choices"][0]["message"]
        
        if message.get("tool_calls"):
            tool_call = message["tool_calls"][0]["function"]
            function_name = tool_call["name"]
            arguments = json.loads(tool_call["arguments"])

            domain, service_name = function_name.split('_', 1)
            ha_service_url = f"{HA_API_URL}/services/{domain}/{service_name}"
            
            ha_headers = {
                "Authorization": f"Bearer {HA_ACCESS_TOKEN}",
                "Content-Type": "application/json"
            }

            print(f"Calling HA service: {ha_service_url} with data: {arguments}")

            async with httpx.AsyncClient() as client:
                ha_response = await client.post(
                    ha_service_url,
                    headers=ha_headers,
                    json=arguments
                )
                ha_response.raise_for_status()
            
            return jsonify({
                "id": "replit-proxy-completion",
                "choices": [{"finish_reason": "stop", "index": 0, "message": {"role": "assistant", "content": "Done."}}],
            })
        
        text_response = message.get("content", "I am not sure how to respond to that.")
        return jsonify({
            "id": "replit-proxy-completion",
            "choices": [{"finish_reason": "stop", "index": 0, "message": {"role": "assistant", "content": text_response}}],
        })

    except Exception as e:
        print(f"An error occurred: {e}")
        # Return a simple, safe JSON error response
        return jsonify({"error": f"An internal server error occurred: {e}"}), 500

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)
```
# requirements.txt

Flask[async]==3.0.3
httpx==0.27.0
gunicorn==22.0.0
