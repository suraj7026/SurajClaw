# AGENTS.md

This file contains crucial instructions and guidelines for any AI agents (like OpenCode, Cursor, or Copilot) operating in the Personal AI Assistant repository. Read this completely before generating or modifying code.

## 1. Project Overview & Architecture
- **Project Purpose:** A personal, local-first AI assistant with Git automation, web search, notes generation, and Gmail reading capabilities.
- **Backend Stack:** Python, FastAPI, LangGraph, LangChain, ChromaDB, SQLite.
- **Frontend Stack:** React 18, Vite, TailwindCSS.
- **Environment:** Ubuntu Linux, Intel i5 9th Gen, 8GB RAM, GTX 1650 (4GB VRAM).
- **LLM Routing:** 
  - Primary (Local): Gemma 4 E2B (via Ollama) for fast, private, low-resource tasks.
  - Secondary (Cloud): Gemini API for complex tasks.

## 2. Build, Lint, and Test Commands

### Backend (Python)
- **Install Dependencies:** `pip install -r requirements.txt`
- **Run Gateway (Dev):** `uvicorn main:app --reload --host 127.0.0.1 --port 8000`
- **Run Gateway (Prod):** Executed via systemd user service.
- **Linting & Formatting:** 
  - Lint: `ruff check .`
  - Format: `ruff format .`
  - Type Check: `mypy .`
- **Testing (pytest):**
  - Run all tests: `pytest`
  - Run tests in a directory: `pytest tests/`
  - Run a specific test file: `pytest tests/test_agents.py`
  - **Run a single test function:** `pytest tests/test_agents.py::test_git_agent_routing`
  - Run tests with print output: `pytest -s -v`

### Frontend (React/Vite in `ui/` folder)
- **Install Dependencies:** `cd ui && npm install`
- **Run Dev Server:** `cd ui && npm run dev`
- **Build for Production:** `cd ui && npm run build`
- **Linting:** `cd ui && npm run lint`
- **Testing (Vitest/Jest):**
  - Run all frontend tests: `cd ui && npm run test`
  - **Run a single test file:** `cd ui && npx vitest run path/to/test.file.ts`

## 3. Code Style & Implementation Guidelines

### Python (Backend)
1. **Formatting & Style:** 
   - Strictly follow `ruff` default configurations (PEP 8 compliant).
   - Use double quotes for strings.
   - Keep maximum line length to 88-100 characters.
2. **Type Hinting:** 
   - Mandatory for all function arguments and return types.
   - LangGraph states must use `TypedDict` with `Annotated` reducers.
3. **Imports:**
   - Grouping: Standard library, third-party packages, local application modules.
   - Use absolute imports (e.g., `from agents.supervisor import SupervisorNode`) over relative imports.
4. **Error Handling & Resilience:** 
   - **Never** use bare `except:` clauses. Catch specific exceptions.
   - Tools must catch exceptions and return string error messages rather than crashing the LangGraph execution thread.
   - Example: `except subprocess.TimeoutExpired as e: return f"Command timed out: {e}"`
5. **Naming Conventions:**
   - `snake_case` for variables, functions, filenames.
   - `PascalCase` for classes (e.g., `AgentState`).
   - `UPPER_SNAKE_CASE` for global constants.
6. **LangGraph & Tool Design:**
   - Tools (`@tool`) must have comprehensive docstrings; the LLM routing depends on them.
   - Validate paths to prevent directory traversal (e.g., verify path starts with `WORKSPACE_DIR`).

### React (Frontend)
1. **Component Style:** 
   - Exclusively use Functional Components with React Hooks.
   - Keep components modular and single-responsibility.
2. **Styling (TailwindCSS):** 
   - Use Tailwind utility classes directly in `className`. Avoid custom CSS unless necessary.
3. **Naming Conventions:**
   - `PascalCase` for component files (`ChatInterface.jsx`) and component functions.
   - `camelCase` for variables, state variables, and helper functions.
4. **State Management:** 
   - Use React Context for global state (e.g., UI themes, WebSocket connection state).
   - Avoid heavy state libraries like Redux unless the UI complexity grows significantly.

## 4. System Constraints & Safety Rules
1. **Resource Limits:** The target hardware is RAM-constrained (8GB total, ~4GB available). Do not run more than 2 concurrent agent threads. Do not introduce large in-memory datasets.
2. **Security & Sandboxing:**
   - **Bash Tool:** Must enforce a denylist (e.g., no `rm -rf /`). Provide timeouts.
   - **File Tools:** Must strictly constrain operations to the `~/assistant/workspace` directory.
   - **Gmail Tool:** Must remain read-only (`gmail.readonly` scope). Do not implement send capabilities.
3. **Git Operations:**
   - Agents should not push directly to the `main` branch.
   - Create feature branches: `feature/short-description` or `fix/issue-description`.
   - Ask for user confirmation before executing `git push` to a remote origin.

## 5. Development Workflow for Agents
1. **Understand First:** Before modifying the LangGraph architecture, trace the current routing logic in `main.py` and `agents/`.
2. **Self-Verification:** Write unit tests for new tools. Use debug statements and test outputs to verify behavior before finalizing.
3. **Minimal Modifications:** Only modify files necessary for the requested feature. Do not refactor unrelated code.
4. **No Chitchat Comments:** Add code comments to explain *why* complex orchestration logic exists, not *what* basic Python syntax does.

---
*Note to Agent: Always prioritize the `PersonalAI_SoftwareDoc.md` for architectural context when making systemic changes.*