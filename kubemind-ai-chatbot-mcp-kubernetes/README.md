# KubeMind: AI Chatbot + MCP + Kubernetes Project

KubeMind is an AI chatbot that can answer questions about a live Kubernetes cluster. It uses a Flask backend, an LLM (NVIDIA Nemotron via OpenRouter), a custom MCP client, and a custom Kubernetes MCP server. Everything runs on a single AWS EC2 instance.

> Example: "give me the pods list in the namespace called rohith" -> the LLM calls the `list_pods` MCP tool -> real pods from the cluster are shown in the chat.

## Architecture

```
Browser (frontend)  --:5000-->  Flask backend (app.py)
                                   |  import
                                mcp_client.py
                                   |  HTTP :8000/mcp (Streamable HTTP)
                                server.py (MCP Server)
                                   |  kubeconfig
                                Kind Kubernetes Cluster (mcp-demo)
```

## Folder Structure

```
kubemind-ai-chatbot-mcp-kubernetes/
|
|-- chatbot/                  # Built as a Docker image
|   |-- frontend/
|   |   |-- index.html        # UI structure
|   |   |-- style.css         # Dark theme
|   |   `-- script.js         # Sends messages to /chat
|   |-- backend/
|   |   |-- app.py            # Flask + LLM + tool calling
|   |   `-- mcp_client.py     # MCP client (list_tools, call_tool)
|   |-- requirements.txt
|   |-- Dockerfile
|   `-- .dockerignore
|
`-- kubernetes-mcp-server/    # Runs directly on EC2
    |-- server.py             # MCP server with list_pods tool
    `-- requirements.txt
```

## Tech Stack

| Layer | Technology |
|---|---|
| Frontend | HTML, CSS, JavaScript |
| Backend | Python, Flask |
| LLM | `nvidia/nemotron-3-super-120b-a12b:free` via OpenRouter |
| MCP | Python MCP SDK, Streamable HTTP |
| Kubernetes | Kind cluster, Kubernetes Python client |
| Infra | Docker, AWS EC2 |

---

# Level 1: Setup Steps

Order: **EC2** -> **Chatbot** -> **Kubernetes** -> **MCP Server** -> **Run**

## Step 0: Prepare EC2

- Launch an EC2 instance (Ubuntu, t3.medium or larger, since Kubernetes needs memory)
- Security Group: allow **22** (SSH) and **5000** (chatbot) with source = My IP. Do not open port 8000

```bash
ssh -i key.pem ubuntu@EC2_PUBLIC_IP
sudo apt update
sudo apt install -y docker.io python3-venv git
sudo usermod -aG docker $USER      # log out and log back in after this
git clone https://github.com/iam-rohithaerva/ai.git
```

## Step 1: Chatbot setup

1. `chatbot/frontend/` has 3 files: `index.html`, `style.css`, `script.js`
2. `chatbot/backend/` has 2 files: `app.py`, `mcp_client.py`
3. `chatbot/` has `requirements.txt`, `Dockerfile`, `.dockerignore`

```bash
cd ~/ai/kubemind-ai-chatbot-mcp-kubernetes/chatbot
docker build -t mcp-chatbot .
```

## Step 2: Kubernetes setup (Kind)

```bash
# Kind install
curl -Lo ./kind https://kind.sigs.k8s.io/dl/v0.33.0/kind-linux-amd64
chmod +x ./kind
sudo mv ./kind /usr/local/bin/kind

# kubectl install
curl -LO "https://dl.k8s.io/release/$(curl -L -s https://dl.k8s.io/release/stable.txt)/bin/linux/amd64/kubectl"
chmod +x kubectl
sudo mv kubectl /usr/local/bin/kubectl

# Create the cluster
kind create cluster --name mcp-demo

# Verify
kubectl cluster-info
kubectl get nodes        # STATUS = Ready
kubectl get pods -A      # system pods Running

# Optional: create a test pod in the rohith namespace
kubectl create namespace rohith
kubectl run nginx --image=nginx -n rohith
```

## Step 3: MCP Server setup

```bash
cd ~/ai/kubemind-ai-chatbot-mcp-kubernetes/kubernetes-mcp-server
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

## Step 4: Run

```bash
# Terminal 1: MCP Server (port 8000)
cd ~/ai/kubemind-ai-chatbot-mcp-kubernetes/kubernetes-mcp-server
source venv/bin/activate
python server.py

# Terminal 2: Chatbot container (port 5000)
export OPENROUTER_API_KEY="YOUR_KEY"
docker run -d --name mcp-chatbot --network host \
  -e OPENROUTER_API_KEY="$OPENROUTER_API_KEY" mcp-chatbot

# Check
docker ps
docker logs mcp-chatbot
sudo ss -tlnp | grep -E '5000|8000'
```

Open `http://EC2_PUBLIC_IP:5000` in the browser and ask **"give me the pods list in the namespace called rohith"**.

**Remember:**
- Only two things run: **server.py** and the **chatbot container**. `mcp_client.py` is not run separately, `app.py` imports it
- `--network host` lets the container reach the MCP server on `localhost:8000`. In this mode `-p 5000:5000` is not needed
- `server.py` must be running before you send a prompt, otherwise you get "connection refused"
- Never put the API key in code, Git, or the Docker image. Pass it only at runtime with `-e`

---

# Level 2: Which Code Connects to Which File

## Connection Map

```
[0] app.py         --static_folder="../frontend"---------->  frontend files serve
[1] script.js      --fetch("/chat")----------------------->  app.py  chat()
[2] app.py         --from mcp_client import ...------------>  mcp_client.py
[3] app.py         --client.chat.completions.create()----->  OpenRouter LLM
[4] mcp_client.py  --MCP_URL + call_tool()---------------->  server.py  list_pods()
[5] server.py      --load_kube_config() + CoreV1Api------->  Kind cluster
```

## Link 0: Flask -> Frontend (how the UI loads)

| File | Code |
|---|---|
| `backend/app.py` | `Flask(__name__, static_folder="../frontend", static_url_path="")` and `app.send_static_file("index.html")` |

- `static_folder="../frontend"` tells Flask to serve the frontend folder next to backend
- Opening `http://EC2_IP:5000/` returns `index.html`
- `index.html` links to `/style.css` and `/script.js`, which Flask also serves
- There is no separate frontend server

## Link 1: Frontend -> Backend

| From | To |
|---|---|
| `frontend/script.js`: `fetch("/chat", { method: "POST", ... })` | `backend/app.py`: `@app.route("/chat", methods=["POST"])` |

- When the user clicks Send, `script.js` posts the message as JSON to `/chat`
- `app.py` reads it with `request.get_json()`
- The reply comes back as `jsonify({"response": ...})` and `addMessage()` shows it on screen

## Link 2: Backend -> MCP Client

| From | To |
|---|---|
| `backend/app.py`: `from mcp_client import get_tools, run_tool` | `backend/mcp_client.py`: `get_tools()`, `run_tool()` |

- This is not a network connection, just a Python **import**
- Both files are in the same folder (`backend/`), so the import works directly
- That is why the client has no port and is not run separately

## Link 3: Backend -> LLM (decision)

| File | Code |
|---|---|
| `backend/app.py` | `client.chat.completions.create(..., tools=tools)` |

- `mcp_to_openai()` converts the MCP tools list into the LLM's tool format
- The LLM decides whether to call a tool or answer directly
- "Hi" gets a direct answer. "pods in rohith" returns `tool_calls`: `list_pods`, `{"namespace": "rohith"}`
- The **LLM** extracts the namespace from the message, not our code

## Link 4: MCP Client -> MCP Server

| From | To |
|---|---|
| `backend/mcp_client.py`: `MCP_URL = "http://localhost:8000/mcp"`, `session.call_tool(name, args)` | `kubernetes-mcp-server/server.py`: `@server.tool() def list_pods(...)` |

- `streamablehttp_client(MCP_URL)`: opens an HTTP connection to the server
- `session.initialize()`: MCP handshake
- `call_tool("list_pods", ...)`: runs the server function with the same name
- The `@server.tool()` decorator registers the function name as the tool name, which is why the names match

## Link 5: MCP Server -> Kubernetes

| File | Code |
|---|---|
| `server.py` | `config.load_kube_config()`, `client.CoreV1Api()`, `list_namespaced_pod()` |

- `load_kube_config()` reads `~/.kube/config`, which `kind create cluster` created automatically
- It contains the cluster API address and certificates
- `list_namespaced_pod("rohith")` sends `GET /api/v1/namespaces/rohith/pods` to the Kubernetes API
- The result is returned as `namespace/name: status` lines

## Full Example: "give me the pods list in the namespace called rohith"

| # | File | Code | What happens |
|---|---|---|---|
| 1 | `script.js` | `fetch("/chat")` | Message goes to Flask |
| 2 | `app.py` | `chat()` | Message added to history |
| 3 | `mcp_client.py` | `list_tools()` | Gets `list_pods` tool info from the server |
| 4 | `app.py` | `completions.create(tools=)` | LLM: `list_pods`, namespace = rohith |
| 5 | `app.py` | `run_tool(...)` | Hands over to the client |
| 6 | `mcp_client.py` | `call_tool(...)` | HTTP request to `:8000/mcp` |
| 7 | `server.py` | `list_namespaced_pod("rohith")` | Gets pods from the Kubernetes API |
| 8 | `app.py` | `role: "tool"` + 2nd LLM call | LLM turns raw data into an answer |
| 9 | `script.js` | `addMessage()` | Answer shown on screen |

## Ports

| Component | Port | Reason |
|---|---|---|
| Chatbot (Flask + UI) | 5000 | Accessed from the browser, open in Security Group |
| MCP Client | None | Library inside `app.py`, outbound calls only |
| MCP Server | 8000 | Internal to EC2, do not expose |
| Kubernetes API | Kind random port | Shown by `kubectl cluster-info` |

## Common Errors

| Error | Cause | Fix |
|---|---|---|
| Connection refused (8000) | `server.py` is not running | `python server.py` |
| Missing credentials | API key not passed to the container | `-e OPENROUTER_API_KEY` |
| Kubernetes API error: Not Found | Namespace does not exist | `kubectl get ns` |
| LLM does not call the tool | Model may not support tool calling | Use a tool-calling model |
| UI does not open | Port 5000 blocked | Check the Security Group |

## Switching the LLM

Because the project uses OpenRouter, switching models only requires changing `MODEL` in `app.py`. Claude or GPT models also work (paid). Find exact model IDs at [openrouter.ai/models](https://openrouter.ai/models).

## Note

`server.run(transport="streamable-http")` and port 8000 are MCP SDK defaults. If your installed SDK version has a different API (for example `FastMCP` vs `MCPServer`), adjust to match that version.

---

**Interview line:** "The frontend calls Flask's /chat API. Flask imports the MCP client, and the LLM decides when to call a tool. The client sends call_tool to the MCP server over Streamable HTTP. The server reads kubeconfig and queries the Kubernetes API, and the result goes back through the LLM to the UI."
