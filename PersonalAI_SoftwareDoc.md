# Personal AI Assistant — Software Design Document
### Inspired by OpenClaw · Built with LangGraph · Optimized for Home Server

> **Version:** 1.0  
> **Date:** April 2026  
> **Target Hardware:** Intel i5 9th Gen · 8 GB RAM · GTX 1650 · 512 GB Storage · Ubuntu Linux  
> **Model:** Gemini API (`gemini-3.1-flash-lite-preview`)  

---

## Table of Contents

1. [Project Overview](#1-project-overview)
2. [Hardware & Environment Constraints](#2-hardware--environment-constraints)
3. [System Architecture](#3-system-architecture)
4. [Tech Stack & Dependencies](#4-tech-stack--dependencies)
5. [Core Features & Requirements](#5-core-features--requirements)
6. [LangGraph Agent Design](#6-langgraph-agent-design)
7. [Tool Implementations](#7-tool-implementations)
8. [Git & OpenCode Workflow Agent](#8-git--opencode-workflow-agent)
9. [Notes & Research Documents Feature](#9-notes--research-documents-feature)
10. [Gmail Integration](#10-gmail-integration)
11. [Web Search Integration](#11-web-search-integration)
12. [Model Runtime](#12-model-runtime)
13. [API & WebChat Interface](#13-api--webchat-interface)
14. [Data Storage & Persistence](#14-data-storage--persistence)
15. [Configuration Reference](#15-configuration-reference)
16. [Implementation Roadmap](#16-implementation-roadmap)
17. [Notes App Recommendations](#17-notes-app-recommendations)

---

## 1. Project Overview

This document describes a **personal AI assistant** — a self-hosted, single-user system modelled on the architecture of [OpenClaw](https://github.com/openclaw/openclaw) but rebuilt from scratch using **LangGraph** as the agent orchestration layer. The system runs entirely on a home server (laptop) and integrates with external services via APIs only when required.

### Core Goals

- A persistent, always-on AI assistant accessible via a local web UI
- Uses **Gemini API** for planning, orchestration, response generation, and embeddings
- Full **Git workflow automation**: clone → branch → edit → hand off to OpenCode CLI → push
- **Notes/research docs** creation with a recommended local app for reading
- **Gmail read access** to process emails and convert them to tasks (integrating your `mailtotasks` project)
- **Web search** via Google Search API
- Built in **Python** with LangGraph, FastAPI, and a minimal React web UI

---

## 2. Hardware & Environment Constraints

| Resource | Spec | Implication |
|---|---|---|
| CPU | Intel i5 9th Gen (6-core) | Good for I/O-heavy orchestration; limit CPU-bound inference |
| RAM | 8 GB | Keep concurrent agents limited to 2–3 |
| GPU | GTX 1650 (4 GB VRAM) | Not required for the Gemini API runtime |
| Storage | 512 GB | Ample for models, notes, conversation history, repos |
| OS | Ubuntu Linux | Full support for Docker and systemd services |

### RAM Budget (Operating)

| Component | Est. RAM |
|---|---|
| Ubuntu + system | ~1.5 GB |
| FastAPI gateway | ~150 MB |
| LangGraph agent process | ~300 MB |
| ChromaDB (vector store) | ~200 MB |
| React UI dev server or static | ~100 MB |
| **Total** | **~4.25 GB** |

This leaves ~3.75 GB headroom — comfortable for stable operation.

### Key Constraints

- **No more than 2 LangGraph agent threads concurrently** to avoid OOM pressure
- **Gemini API** is the only LLM runtime; monitor API usage and quotas
- **GTX 1650 VRAM cap:** Do NOT attempt to run models larger than 3B parameters on-device

---

## 3. System Architecture

```
┌────────────────────────────────────────────────────────────┐
│                     User Interface                          │
│        React WebChat (localhost:3000)                       │
│        REST + WebSocket                                     │
└────────────────────┬───────────────────────────────────────┘
                     │
┌────────────────────▼───────────────────────────────────────┐
│                  FastAPI Gateway                             │
│               (localhost:8000)                              │
│   - Session management                                      │
│   - Auth (local token)                                      │
│   - REST endpoints + WS relay                               │
└────────────────────┬───────────────────────────────────────┘
                     │
┌────────────────────▼───────────────────────────────────────┐
│              LangGraph Agent Orchestrator                    │
│                                                             │
│   ┌─────────────┐  ┌──────────────┐  ┌─────────────────┐  │
│   │  Supervisor  │  │  Git Agent   │  │  Research Agent  │  │
│   │    Node     │  │    Node      │  │     Node         │  │
│   └──────┬──────┘  └──────┬───────┘  └────────┬────────┘  │
│          │                │                    │            │
│   ┌──────▼────────────────▼────────────────────▼────────┐  │
│   │                  Tool Registry                        │  │
│   │  web_search │ git_ops │ gmail_read │ opencode_cli   │  │
│   │  notes_write │ bash_exec │ file_ops                  │  │
│   └──────────────────────────────────────────────────────┘  │
└─────────────────────────────┬──────────────────────────────┘
                              │
          ┌───────────────────┼─────────────────────┐
          │                   │                      │
   ┌──────▼──────┐   ┌────────▼───────┐   ┌─────────▼──────┐
   │  Gemini API    │   │   ChromaDB      │
   │  (cloud)       │   │  (vector DB)    │
   │ gemini-3.1...  │   │  notes + mem    │
   └────────────────┘   └────────────────┘
```

---

## 4. Tech Stack & Dependencies

### Backend

| Package | Version | Purpose |
|---|---|---|
| `langgraph` | ≥0.2 | Agent graph orchestration |
| `langchain` | ≥0.2 | LLM abstractions, tool wrappers |
| `langchain-google-genai` | latest | Gemini API integration |
| `fastapi` | ≥0.110 | HTTP + WebSocket gateway |
| `uvicorn` | latest | ASGI server |
| `chromadb` | latest | Vector store for notes/memory |
| `google-api-python-client` | latest | Gmail API |
| `google-auth-oauthlib` | latest | Gmail OAuth2 |
| `gitpython` | latest | Git operations |
| `httpx` | latest | Async HTTP client (search API) |
| `pydantic` | v2 | Data validation/schemas |
| `python-dotenv` | latest | Config/secrets from .env |
| `sqlitedict` | latest | Lightweight persistent K-V store |

### Frontend

| Package | Purpose |
|---|---|
| React 18 + Vite | WebChat UI |
| TailwindCSS | Styling |
| `react-markdown` | Render agent markdown responses |
| `socket.io-client` | WebSocket for streaming responses |

### Infrastructure

| Tool | Purpose |
|---|---|
| systemd | Run gateway as a user service (always-on) |
| Docker (optional) | Sandboxed bash execution |
| OpenCode CLI | AI coding assistant (external) |

---

## 5. Core Features & Requirements

### F1 — Conversational Chat Interface
- Web-based chat UI served at `localhost:3000`
- Streaming responses via WebSocket
- Supports markdown rendering (code blocks, tables, lists)
- Maintains per-session conversation history
- Session commands: `/new`, `/reset`, `/compact`, `/model <name>`

### F2 — Gemini Runtime
- **Model**: Gemini API with `gemini-3.1-flash-lite-preview`
- The same model is used for routine chat, planning, and complex tasks
- Runtime directives can clear or reaffirm the Gemini model selection

### F3 — Git Workflow Automation
- Clone a repository to a working directory
- Create a feature branch
- Read/write files in the repo
- Hand off to **OpenCode CLI** for AI-assisted code changes
- Monitor OpenCode completion
- Stage, commit, push changes back to remote
- Full workflow orchestrated as a LangGraph subgraph

### F4 — Notes & Research Documents
- Agent can create structured Markdown notes in a designated folder (`~/assistant/notes/`)
- Notes are indexed in ChromaDB for semantic search
- User can ask "summarize my research on X" — agent retrieves and synthesizes
- Notes are viewable in an external app (see Section 17)

### F5 — Gmail Integration
- Read-only access via Gmail API with OAuth2
- Lists unread emails from inbox
- Extracts tasks from emails (mirrors your `mailtotasks` project logic)
- Stores extracted tasks in a local SQLite tasks table
- Agent can answer "what tasks came in from email today?"

### F6 — Web Search
- Google Custom Search API integration
- Agent automatically searches when it needs current information
- Returns top-5 results with snippets; agent summarizes
- Can be invoked directly: "search for X"

### F7 — Bash / Shell Execution
- Agent can run shell commands in a sandboxed subprocess
- Configurable working directory and timeout
- stdout/stderr captured and returned to agent
- Dangerous commands blocked by denylist

### F8 — File Operations
- Read, write, list, delete files within permitted directories
- Permitted root: `~/assistant/workspace/`
- Agents cannot escape this sandbox via path traversal

---

## 6. LangGraph Agent Design

The system uses a **supervisor pattern** with LangGraph. One `SupervisorNode` routes each user message to the appropriate specialist agent node.

### Graph Structure

```python
from langgraph.graph import StateGraph, END
from typing import TypedDict, Annotated, List
import operator

class AgentState(TypedDict):
    messages: Annotated[List, operator.add]
    next_node: str
    session_id: str
    use_cloud_model: bool

# Node definitions
builder = StateGraph(AgentState)
builder.add_node("supervisor", supervisor_node)
builder.add_node("general_agent", general_agent_node)
builder.add_node("git_agent", git_agent_node)
builder.add_node("research_agent", research_agent_node)
builder.add_node("email_agent", email_agent_node)

# Entry point
builder.set_entry_point("supervisor")

# Conditional routing from supervisor
builder.add_conditional_edges(
    "supervisor",
    route_by_intent,
    {
        "general": "general_agent",
        "git": "git_agent",
        "research": "research_agent",
        "email": "email_agent",
    }
)

# All agents return to supervisor or END
for node in ["general_agent", "git_agent", "research_agent", "email_agent"]:
    builder.add_edge(node, END)

graph = builder.compile()
```

### SupervisorNode

The supervisor uses a lightweight Gemini prompt to classify intent:

```python
SUPERVISOR_PROMPT = """
You are a routing supervisor. Classify the user's request into one of:
- "general": Conversation, questions, explanations, writing
- "git": Anything about cloning repos, branches, committing, pushing, OpenCode
- "research": Creating notes, research documents, web searches for research
- "email": Reading Gmail, extracting tasks from emails

User message: {message}

Respond with ONLY one word from the list above.
"""
```

### GeneralAgentNode

Uses Gemini for everyday conversation with access to: `web_search`, `bash_exec`, `file_read`, `notes_write`.

### GitAgentNode

Uses Gemini for code and Git workflow tasks. Has access to: `git_clone`, `git_branch`, `git_status`, `git_add_commit_push`, `opencode_invoke`, `file_read`, `file_write`, `bash_exec`.

### ResearchAgentNode

Uses Gemini + ChromaDB retrieval. Has access to: `web_search`, `notes_write`, `notes_search`, `file_write`.

### EmailAgentNode

Uses Gemini. Has access to: `gmail_list_unread`, `gmail_get_message`, `tasks_create`, `tasks_list`.

---

## 7. Tool Implementations

All tools are implemented as LangChain `@tool`-decorated functions and registered in the LangGraph node's tool list.

### 7.1 Web Search Tool

```python
from langchain_core.tools import tool
import httpx, os

@tool
def web_search(query: str) -> str:
    """Search the web using Google Custom Search API. Returns top results."""
    api_key = os.environ["GOOGLE_SEARCH_API_KEY"]
    cx = os.environ["GOOGLE_SEARCH_CX"]
    resp = httpx.get(
        "https://www.googleapis.com/customsearch/v1",
        params={"key": api_key, "cx": cx, "q": query, "num": 5}
    )
    items = resp.json().get("items", [])
    return "\n\n".join(
        f"**{r['title']}**\n{r['snippet']}\n{r['link']}" for r in items
    )
```

**Setup:** Create a Custom Search Engine at [cse.google.com](https://cse.google.com), enable the Custom Search JSON API, obtain an API key.

### 7.2 File Operations Tools

```python
WORKSPACE = os.path.expanduser("~/assistant/workspace")

@tool
def file_read(path: str) -> str:
    """Read a file. Path is relative to workspace."""
    safe = os.path.realpath(os.path.join(WORKSPACE, path))
    assert safe.startswith(WORKSPACE), "Path traversal denied"
    return open(safe).read()

@tool
def file_write(path: str, content: str) -> str:
    """Write content to a file. Path is relative to workspace."""
    safe = os.path.realpath(os.path.join(WORKSPACE, path))
    assert safe.startswith(WORKSPACE), "Path traversal denied"
    os.makedirs(os.path.dirname(safe), exist_ok=True)
    open(safe, "w").write(content)
    return f"Written: {path}"
```

### 7.3 Bash Execution Tool

```python
import subprocess, shlex

BASH_DENYLIST = ["rm -rf /", "mkfs", "dd if=", ":(){:|:&};:"]

@tool
def bash_exec(command: str, cwd: str = None) -> str:
    """Execute a shell command. Returns stdout + stderr."""
    for banned in BASH_DENYLIST:
        if banned in command:
            return f"ERROR: Blocked command pattern: {banned}"
    work_dir = cwd or WORKSPACE
    result = subprocess.run(
        command, shell=True, cwd=work_dir,
        capture_output=True, text=True, timeout=60
    )
    return result.stdout + result.stderr
```

### 7.4 Notes Write Tool

```python
import chromadb
from datetime import datetime

chroma = chromadb.PersistentClient(path=os.path.expanduser("~/assistant/chroma"))
notes_col = chroma.get_or_create_collection("notes")
NOTES_DIR = os.path.expanduser("~/assistant/notes")

@tool
def notes_write(title: str, content: str) -> str:
    """Create or update a research note as a Markdown file."""
    os.makedirs(NOTES_DIR, exist_ok=True)
    filename = title.lower().replace(" ", "_") + ".md"
    filepath = os.path.join(NOTES_DIR, filename)
    full_content = f"# {title}\n\n*Created: {datetime.now().strftime('%Y-%m-%d %H:%M')}*\n\n{content}"
    with open(filepath, "w") as f:
        f.write(full_content)
    # Index in ChromaDB
    notes_col.upsert(
        documents=[content],
        metadatas=[{"title": title, "file": filename, "date": datetime.now().isoformat()}],
        ids=[filename]
    )
    return f"Note saved: {filepath}"

@tool
def notes_search(query: str) -> str:
    """Search notes semantically. Returns relevant note excerpts."""
    results = notes_col.query(query_texts=[query], n_results=3)
    out = []
    for doc, meta in zip(results["documents"][0], results["metadatas"][0]):
        out.append(f"**{meta['title']}** ({meta['date'][:10]})\n{doc[:500]}...")
    return "\n\n---\n\n".join(out) if out else "No notes found."
```

---

## 8. Git & OpenCode Workflow Agent

This is the most complex feature — a full multi-step workflow managed as a LangGraph subgraph.

### Workflow Steps

```
1. git_clone(repo_url, local_path)
       ↓
2. git_branch(branch_name)
       ↓
3. [Agent reads relevant files, understands codebase]
       ↓
4. opencode_invoke(instruction, working_dir)
   [Hands off to OpenCode CLI; waits for completion]
       ↓
5. git_add_commit_push(message, branch)
       ↓
6. [Report PR-ready branch to user]
```

### Tool Implementations

```python
import git  # GitPython

@tool
def git_clone(repo_url: str, local_name: str = None) -> str:
    """Clone a git repository into the workspace."""
    name = local_name or repo_url.split("/")[-1].replace(".git", "")
    dest = os.path.join(WORKSPACE, "repos", name)
    if os.path.exists(dest):
        return f"Already cloned at: {dest}"
    git.Repo.clone_from(repo_url, dest)
    return f"Cloned to: {dest}"

@tool
def git_branch(repo_name: str, branch_name: str) -> str:
    """Create and checkout a new branch in a cloned repo."""
    repo_path = os.path.join(WORKSPACE, "repos", repo_name)
    repo = git.Repo(repo_path)
    new_branch = repo.create_head(branch_name)
    new_branch.checkout()
    return f"Checked out branch: {branch_name}"

@tool
def opencode_invoke(instruction: str, repo_name: str) -> str:
    """
    Hand off a coding task to the OpenCode CLI.
    OpenCode will apply AI-assisted code changes in the repo.
    Waits for OpenCode to complete before returning.
    """
    repo_path = os.path.join(WORKSPACE, "repos", repo_name)
    # OpenCode CLI invocation — adjust to actual opencode command syntax
    cmd = f'opencode "{instruction}"'
    result = subprocess.run(
        cmd, shell=True, cwd=repo_path,
        capture_output=True, text=True, timeout=300  # 5 min timeout
    )
    if result.returncode != 0:
        return f"OpenCode error:\n{result.stderr}"
    return f"OpenCode completed:\n{result.stdout[-2000:]}"  # last 2000 chars

@tool
def git_add_commit_push(repo_name: str, commit_message: str, branch: str) -> str:
    """Stage all changes, commit, and push the branch to remote."""
    repo_path = os.path.join(WORKSPACE, "repos", repo_name)
    repo = git.Repo(repo_path)
    repo.git.add(A=True)
    repo.index.commit(commit_message)
    origin = repo.remotes.origin
    origin.push(branch)
    return f"Pushed branch '{branch}' to remote with message: '{commit_message}'"
```

### Git Agent System Prompt

```
You are a Git workflow agent. When given a task involving code:
1. Clone the repo if not already available
2. Create a descriptively-named feature branch (e.g. "feature/add-dark-mode")
3. Examine relevant files to understand structure
4. Invoke OpenCode with a clear instruction string
5. Once OpenCode finishes, commit and push
6. Report the branch name so a PR can be opened

Always confirm with the user before pushing to remote.
```

---

## 9. Notes & Research Documents Feature

### How It Works

When the user says something like *"do some research on LangGraph memory management and write me a doc"*, the Research Agent:

1. Performs 2–4 web searches on the topic
2. Synthesizes findings into a well-structured Markdown document
3. Saves it to `~/assistant/notes/<topic>.md` via `notes_write`
4. Indexes the content in ChromaDB for future semantic retrieval
5. Tells the user where the file is saved

### Notes Folder Structure

```
~/assistant/
├── notes/
│   ├── langgraph_memory_management.md
│   ├── gemini_runtime_notes.md
│   └── ...
├── workspace/
│   └── repos/
└── chroma/         ← ChromaDB storage
```

### Recommended Notes Apps (Section 17)

See Section 17 for app recommendations that let you read these Markdown files beautifully on your laptop.

---

## 10. Gmail Integration

### Setup

1. Go to [Google Cloud Console](https://console.cloud.google.com)
2. Create a project, enable the **Gmail API**
3. Create OAuth2 credentials → Desktop App
4. Download `credentials.json` → place in `~/assistant/config/gmail_credentials.json`
5. First run: opens browser for auth, stores `token.json`

### Tool Implementations

```python
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
import base64, json

SCOPES = ["https://www.googleapis.com/auth/gmail.readonly"]
CREDS_PATH = os.path.expanduser("~/assistant/config/gmail_credentials.json")
TOKEN_PATH = os.path.expanduser("~/assistant/config/gmail_token.json")

def get_gmail_service():
    creds = None
    if os.path.exists(TOKEN_PATH):
        creds = Credentials.from_authorized_user_file(TOKEN_PATH, SCOPES)
    if not creds or not creds.valid:
        flow = InstalledAppFlow.from_client_secrets_file(CREDS_PATH, SCOPES)
        creds = flow.run_local_server(port=0)
        with open(TOKEN_PATH, "w") as f:
            f.write(creds.to_json())
    return build("gmail", "v1", credentials=creds)

@tool
def gmail_list_unread(max_results: int = 10) -> str:
    """List unread emails from Gmail inbox."""
    service = get_gmail_service()
    results = service.users().messages().list(
        userId="me", labelIds=["UNREAD"], maxResults=max_results
    ).execute()
    messages = results.get("messages", [])
    if not messages:
        return "No unread emails."
    summaries = []
    for msg in messages[:5]:
        m = service.users().messages().get(userId="me", id=msg["id"], format="metadata",
            metadataHeaders=["From", "Subject", "Date"]).execute()
        headers = {h["name"]: h["value"] for h in m["payload"]["headers"]}
        summaries.append(
            f"From: {headers.get('From','?')}\n"
            f"Subject: {headers.get('Subject','?')}\n"
            f"Date: {headers.get('Date','?')}\n"
            f"ID: {msg['id']}"
        )
    return "\n\n---\n\n".join(summaries)

@tool
def gmail_get_message(message_id: str) -> str:
    """Get the full body of an email by message ID."""
    service = get_gmail_service()
    msg = service.users().messages().get(userId="me", id=message_id, format="full").execute()
    # Extract plain text body
    parts = msg["payload"].get("parts", [msg["payload"]])
    for part in parts:
        if part.get("mimeType") == "text/plain":
            data = part["body"].get("data", "")
            return base64.urlsafe_b64decode(data).decode("utf-8")
    return "Could not extract plain text body."
```

### Task Extraction (mailtotasks Integration)

The Email Agent uses a prompt to extract tasks from an email body:

```python
TASK_EXTRACTION_PROMPT = """
Read this email and extract any action items or tasks.
Return a JSON list: [{"task": "...", "due": "...", "from": "..."}]
If no tasks, return [].

Email:
{email_body}
"""
```

Tasks are stored in a local SQLite table and can be listed, marked done, etc.

---

## 11. Web Search Integration

### Google Custom Search API Setup

1. Visit [programmablesearchengine.google.com](https://programmablesearchengine.google.com)
2. Create a search engine → set it to search the entire web
3. Copy your **Search Engine ID (cx)**
4. Visit [console.developers.google.com](https://console.developers.google.com) → enable **Custom Search JSON API**
5. Create an API key
6. Add to your `.env`:
   ```
   GOOGLE_SEARCH_API_KEY=your_key_here
   GOOGLE_SEARCH_CX=your_cx_here
   ```

### Free Tier Limits

The free tier allows 100 queries/day. For personal use this is typically sufficient. Paid tier is $5 per 1,000 queries beyond that.

### Alternative: SerpAPI

If you prefer, [SerpAPI](https://serpapi.com) offers 100 free searches/month and is arguably easier to set up:

```python
@tool
def web_search(query: str) -> str:
    """Search the web via SerpAPI."""
    resp = httpx.get("https://serpapi.com/search", params={
        "api_key": os.environ["SERPAPI_KEY"],
        "q": query, "num": 5
    })
    results = resp.json().get("organic_results", [])
    return "\n\n".join(f"**{r['title']}**\n{r['snippet']}\n{r['link']}" for r in results)
```

---

## 12. Model Runtime

The model runtime uses Gemini for every request.

```python
from langchain_google_genai import ChatGoogleGenerativeAI

MODEL = ChatGoogleGenerativeAI(model="gemini-3.1-flash-lite-preview", temperature=0.3)

COMPLEX_TASK_KEYWORDS = [
    "debug", "complex", "architecture", "explain in depth",
    "refactor", "optimize", "security audit", "compare in detail"
]

def get_model(state: AgentState):
    """Route to cloud model for complex tasks, local otherwise."""
    if state.get("use_cloud_model"):
        return CLOUD_MODEL
    last_msg = state["messages"][-1].content.lower()
    if any(kw in last_msg for kw in COMPLEX_TASK_KEYWORDS):
        return CLOUD_MODEL
    return LOCAL_MODEL
```

Users can also explicitly force cloud: `/think hard` → sets `use_cloud_model: True` for the session.

---

## 13. API & WebChat Interface

### FastAPI Gateway

```python
# main.py
from fastapi import FastAPI, WebSocket
from fastapi.staticfiles import StaticFiles
import uvicorn

app = FastAPI()

@app.websocket("/ws/{session_id}")
async def chat_ws(websocket: WebSocket, session_id: str):
    await websocket.accept()
    while True:
        data = await websocket.receive_json()
        user_msg = data["message"]
        # Stream tokens back
        async for chunk in run_agent_stream(session_id, user_msg):
            await websocket.send_json({"type": "token", "content": chunk})
        await websocket.send_json({"type": "done"})

@app.get("/api/sessions")
def list_sessions(): ...

@app.post("/api/sessions/{session_id}/reset")
def reset_session(session_id: str): ...

@app.get("/api/notes")
def list_notes(): ...

@app.get("/api/tasks")
def list_tasks(): ...

# Serve React frontend
app.mount("/", StaticFiles(directory="ui/dist", html=True), name="ui")

if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=8000)
```

### systemd Service

Create `~/.config/systemd/user/assistant.service`:

```ini
[Unit]
Description=Personal AI Assistant Gateway
After=network.target

[Service]
WorkingDirectory=%h/assistant
ExecStart=/usr/bin/python3 -m uvicorn main:app --host 127.0.0.1 --port 8000
Restart=always
Environment="PYTHONPATH=%h/assistant"
EnvironmentFile=%h/assistant/.env

[Install]
WantedBy=default.target
```

Enable: `systemctl --user enable assistant && systemctl --user start assistant`

---

## 14. Data Storage & Persistence

| Data | Storage | Location |
|---|---|---|
| Conversation history | SQLite | `~/assistant/data/conversations.db` |
| Tasks (from email) | SQLite | `~/assistant/data/tasks.db` |
| Notes (Markdown) | Filesystem | `~/assistant/notes/` |
| Notes index (semantic) | ChromaDB | `~/assistant/chroma/` |
| Session config | SQLite | `~/assistant/data/sessions.db` |
| Gmail token | JSON file | `~/assistant/config/gmail_token.json` |
| Agent memory (short-term) | In-memory (LangGraph state) | — |

### SQLite Schema (conversations)

```sql
CREATE TABLE messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL,
    role TEXT NOT NULL,        -- 'user' | 'assistant' | 'tool'
    content TEXT NOT NULL,
    model TEXT,                -- which model was used
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE tasks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    task TEXT NOT NULL,
    source TEXT,               -- email ID or 'manual'
    from_email TEXT,
    due_date TEXT,
    done INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

---

## 15. Configuration Reference

### `.env` File

```env
# Models
GEMINI_API_KEY=your_gemini_api_key
GEMINI_MODEL=gemini-3.1-flash-lite-preview

# Search
GOOGLE_SEARCH_API_KEY=your_google_search_key
GOOGLE_SEARCH_CX=your_custom_search_id
# OR
SERPAPI_KEY=your_serpapi_key

# Gateway
GATEWAY_PORT=8000
GATEWAY_HOST=127.0.0.1
SECRET_TOKEN=your_local_auth_token  # for WebUI auth

# Paths
WORKSPACE_DIR=/home/youruser/assistant/workspace
NOTES_DIR=/home/youruser/assistant/notes
```

### `config.json` (Runtime Config)

```json
{
  "models": {
    "default": "gemini/gemini-3.1-flash-lite-preview"
  },
  "complexity_threshold": "auto",
  "max_concurrent_agents": 2,
  "bash_timeout_seconds": 60,
  "opencode_timeout_seconds": 300,
  "git": {
    "workspace": "~/assistant/workspace/repos",
    "default_remote": "origin"
  },
  "gmail": {
    "enabled": true,
    "poll_interval_minutes": 15
  },
  "search": {
    "provider": "google",
    "max_results": 5
  }
}
```

---

## 16. Implementation Roadmap

### Phase 1 — Core Foundation (Week 1–2)

- [ ] Configure Gemini API key
- [ ] Create FastAPI gateway skeleton
- [ ] Build basic LangGraph graph with supervisor + general agent
- [ ] Implement `web_search`, `file_read`, `file_write`, `bash_exec` tools
- [ ] Build minimal React WebChat UI with WebSocket streaming
- [ ] Set up systemd service

### Phase 2 — Git & OpenCode Workflow (Week 3)

- [ ] Implement `git_clone`, `git_branch` tools
- [ ] Implement `opencode_invoke` wrapper
- [ ] Implement `git_add_commit_push`
- [ ] Build `git_agent` LangGraph node + subgraph
- [ ] Test full: clone → branch → opencode → push flow

### Phase 3 — Notes & Research (Week 4)

- [ ] Set up ChromaDB persistent store
- [ ] Implement `notes_write`, `notes_search` tools
- [ ] Build `research_agent` node
- [ ] Integrate semantic search into general agent
- [ ] Install and configure recommended notes app

### Phase 4 — Gmail Integration (Week 5)

- [ ] Complete Gmail OAuth2 setup
- [ ] Implement `gmail_list_unread`, `gmail_get_message` tools
- [ ] Port `mailtotasks` task extraction logic into `email_agent`
- [ ] Build `tasks_create`, `tasks_list` tools with SQLite
- [ ] Test full email → task flow

### Phase 5 — Polish & Hardening (Week 6)

- [ ] Add model router (auto-detect complexity → Gemini)
- [ ] Add `/think`, `/model`, `/reset` session commands
- [ ] Conversation history persistence + `/compact` (summarization)
- [ ] Rate limiting + error recovery
- [ ] Monitor RAM/GPU usage; tune concurrent agent limits

---

## 17. Notes App Recommendations

Your agent saves notes as plain **Markdown files** in `~/assistant/notes/`. You want an app on your Linux laptop to read them beautifully. Here are the best options:

### 1. Obsidian ⭐ (Top Recommendation)

**Why:** Industry-leading Markdown editor/viewer. Supports a vault pointing at any folder — just point it at `~/assistant/notes/`. Has a graph view, backlinks, search, and beautiful rendering. Free for personal use.

**Install:** Download AppImage from [obsidian.md](https://obsidian.md) → `chmod +x Obsidian.AppImage && ./Obsidian.AppImage`

**Setup:** Open Obsidian → "Open folder as vault" → select `~/assistant/notes/`

### 2. Logseq

**Why:** Outliner-style Markdown viewer with great search and tagging. Also works as a vault over a local folder. Open source.

**Install:** AppImage from [logseq.com](https://logseq.com)

### 3. Zettlr

**Why:** Academic-flavored Markdown editor. Excellent for research notes with citations. Open source, native Linux app.

**Install:** `sudo apt install zettlr` or download from [zettlr.com](https://zettlr.com)

### 4. Marktext

**Why:** Clean, minimal real-time Markdown renderer. If you want a simple reading experience without Obsidian's complexity.

**Install:** AppImage from [github.com/marktext/marktext](https://github.com/marktext/marktext)

### 5. VS Code (with Markdown Preview)

**Why:** You likely already have it. Press `Ctrl+Shift+V` in any `.md` file for a rendered preview. Install the "Markdown Preview Enhanced" extension for nicer output.

**Verdict:** Use **Obsidian** — it's purpose-built for exactly this use case (a folder of Markdown research notes), has phenomenal search, and is free. The vault setup takes under 2 minutes.

---

## Appendix A — Directory Layout

```
~/assistant/
├── main.py                  ← FastAPI + LangGraph entry point
├── agents/
│   ├── supervisor.py
│   ├── general_agent.py
│   ├── git_agent.py
│   ├── research_agent.py
│   └── email_agent.py
├── tools/
│   ├── search.py
│   ├── file_ops.py
│   ├── bash_exec.py
│   ├── git_ops.py
│   ├── notes.py
│   └── gmail.py
├── ui/                      ← React frontend (built → ui/dist/)
├── config/
│   ├── gmail_credentials.json
│   ├── gmail_token.json
│   └── config.json
├── data/
│   ├── conversations.db
│   └── tasks.db
├── notes/                   ← All Markdown research notes
├── workspace/
│   └── repos/               ← Cloned git repos
├── chroma/                  ← ChromaDB vector store
├── .env
└── requirements.txt
```

## Appendix B — Gemini Setup

```bash
export GEMINI_API_KEY=your_gemini_api_key
export GEMINI_MODEL=gemini-3.1-flash-lite-preview
```

## Appendix C — Key Limitations & Known Trade-offs

| Limitation | Impact | Mitigation |
|---|---|---|
| 4 GB VRAM cap | Cannot run 7B+ models locally | Use Gemini API for complex tasks |
| 8 GB RAM | Limit to 2 concurrent agent threads | Queue incoming requests |
| No GPU for OpenCode | OpenCode uses its own model (cloud) | Already handled — OpenCode is a separate process |
| Gmail read-only | Cannot send replies from agent | Intentional — safety first |
| Google Search free tier | 100 queries/day | Cache results; use judiciously |
| LangGraph in-memory state | Restarts clear active agent state | SQLite-backed conversation history survives restarts |

---

*End of Document*
