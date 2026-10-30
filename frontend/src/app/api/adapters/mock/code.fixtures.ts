import { FileContent } from '../../models/code.model';

export const MOCK_FILE_CONTENTS: Record<string, FileContent> = {
  'repo-1:src/agent/tools.py': {
    path: 'src/agent/tools.py',
    language: 'python',
    lines: 156,
    size: 5600,
    isMock: true,
    content: `"""Agent tool definitions and invocation layer."""

from typing import Any
from dataclasses import dataclass

@dataclass
class ToolResult:
    success: bool
    output: str
    error: str | None = None

class ToolRegistry:
    def __init__(self, sandbox):
        self._sandbox = sandbox
        self._tools: dict[str, callable] = {}

    def register(self, name: str, handler: callable) -> None:
        self._tools[name] = handler

    def invoke(self, name: str, params: dict[str, Any]) -> ToolResult:
        handler = self._tools.get(name)
        if not handler:
            return ToolResult(False, "", f"Unknown tool: {name}")
        try:
            output = handler(**params)
            return ToolResult(True, output)
        except Exception as e:
            return ToolResult(False, "", str(e))

def read_file(path: str) -> str:
    """Read file contents from sandbox."""
    ...

def search_code(query: str, limit: int = 10) -> list[dict]:
    """Search indexed code chunks via Milvus."""
    ...
`,
  },
  'repo-1:src/agent/graph.py': {
    path: 'src/agent/graph.py',
    language: 'python',
    lines: 89,
    size: 8900,
    isMock: true,
    content: `"""LangGraph agent orchestration graph."""

from langgraph.graph import StateGraph
from typing import TypedDict

class AgentState(TypedDict):
    messages: list
    context: list
    tools_used: list

def build_agent_graph(tools, llm):
    graph = StateGraph(AgentState)
    graph.add_node("plan", plan_step)
    graph.add_node("execute", execute_step)
    graph.add_node("verify", verify_step)
    graph.set_entry_point("plan")
    return graph.compile()
`,
  },
  'repo-2:src/app/app.routes.ts': {
    path: 'src/app/app.routes.ts',
    language: 'typescript',
    lines: 45,
    size: 1200,
    isMock: true,
    content: `import { Routes } from '@angular/router';
import { authGuard } from '@core/auth/auth.guard';

export const routes: Routes = [
  { path: '', redirectTo: 'app/dashboard', pathMatch: 'full' },
  { path: 'login', loadChildren: () => import('./features/auth/auth.routes') },
  {
    path: 'app',
    canActivate: [authGuard],
    loadComponent: () => import('./core/layout/app-shell/app-shell.component'),
    children: [ /* feature routes */ ],
  },
];`,
  },
};

export function getMockFileContent(repositoryId: string, path: string): FileContent {
  const key = `${repositoryId}:${path}`;
  return MOCK_FILE_CONTENTS[key] ?? {
    path,
    language: 'text',
    lines: 1,
    size: 0,
    isMock: true,
    content: `# File content unavailable\n# Path: ${path}\n# Mock preview — backend file retrieval not available.`,
  };
}
