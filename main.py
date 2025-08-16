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
# This is a pre-defined list of services the LLM can call.
# This list must be kept in sync with the actual services you want to expose.
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
    },
    {
        "type": "function",
        "function": {
            "name": "set_light_brightness",
            "description": "Sets the brightness of a light. The brightness value is a number between 0 and 100.",
            "parameters": {
                "type": "object",
                "properties": {
                    "entity_id": {
                        "type": "string",
                        "description": "The entity ID of the light to adjust."
                    },
                    "brightness": {
                        "type": "integer",
                        "description": "The brightness level as a percentage (0-100)."
                    }
                },
                "required": ["entity_id", "brightness"]
            }
        }
    }
]

# --- Flask Endpoint ---
@app.route("/v1/chat/completions", methods=["POST"])
async def process_chat_completion():
    """Handles an OpenAI-compatible chat completion request from Home Assistant."""
    try:
        data = request.json
        user_messages = [msg for msg in data.get("messages", []) if msg["role"] == "user"]
        
        # We only care about the most recent user message for now.
        user_input = user_messages[-1]["content"] if user_messages else ""
        if not user_input:
            return jsonify({"error": "No user message found"}), 400

        # --- Forward to AnythingLLM ---
        # Build the payload for the AnythingLLM workspace chat endpoint.
        # This includes our custom system prompt and the Home Assistant tools.
        anythingllm_payload = {
            "model": "deepseek/deepseek-v3-0324:free", # Replace with your chosen OpenRouter model
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
        
        # Check if the LLM has called a tool
        if message.get("tool_calls"):
            tool_call = message["tool_calls"][0]["function"]
            function_name = tool_call["name"]
            arguments = json.loads(tool_call["arguments"])

            # Call the Home Assistant REST API directly
            # This logic must be robust to handle different service calls
            ha_service_url = f"{HA_API_URL}/services/light/turn_on" # Default URL, will be overridden
            
            # Here's where the logic gets more complex for different services.
            # We'll use a simple if/elif structure for this example.
            if "turn_on" in function_name or "turn_off" in function_name:
                domain, service_name = function_name.split('_', 1)
                ha_service_url = f"{HA_API_URL}/services/{domain}/{service_name}"
            elif "set_light_brightness" == function_name:
                ha_service_url = f"{HA_API_URL}/services/light/turn_on"
            
            ha_headers = {
                "Authorization": f"Bearer {HA_ACCESS_TOKEN}",
                "Content-Type": "application/json"
            }

            async with httpx.AsyncClient() as client:
                ha_response = await client.post(
                    ha_service_url,
                    headers=ha_headers,
                    json=arguments
                )
                ha_response.raise_for_status()
            
            # Return a simple confirmation to Home Assistant
            return jsonify({
                "id": "replit-proxy-completion",
                "choices": [{"finish_reason": "stop", "index": 0, "message": {"role": "assistant", "content": "Done."}}],
            })
        
        # If no tool call, return the LLM's conversational response
        text_response = message.get("content", "I am not sure how to respond to that.")
        return jsonify({
            "id": "replit-proxy-completion",
            "choices": [{"finish_reason": "stop", "index": 0, "message": {"role": "assistant", "content": text_response}}],
        })

    except Exception as e:
        print(f"An error occurred: {e}")
        return jsonify({"error": "An internal server error occurred."}), 500

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080)
