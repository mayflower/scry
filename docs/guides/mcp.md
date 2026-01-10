# MCP Integration

Scry can run as an [MCP (Model Context Protocol)](https://modelcontextprotocol.io/) server, allowing LLM agents to use browser automation as a tool.

## Starting the MCP Server

```bash
# Start MCP server (default port 8085)
python -m scry.mcp_server

# With custom configuration
MCP_PORT=8085 MCP_HOST=0.0.0.0 python -m scry.mcp_server
```

## The `browser` Tool

The MCP server exposes a single powerful tool called `browser`:

```json
{
  "name": "browser",
  "description": "Automate browser tasks using LLM-driven exploration and code generation",
  "parameters": {
    "url": "The starting URL to navigate to",
    "task": "Natural language description of what to accomplish",
    "output_schema": "JSON schema describing expected output data structure",
    "login_username": "Optional username for form-based login",
    "login_password": "Optional password for form-based login",
    "max_steps": "Maximum exploration steps (default 20)"
  }
}
```

## Example Tool Call

**Request:**

```json
{
  "url": "https://news.ycombinator.com",
  "task": "Extract the top 5 story titles from the front page",
  "output_schema": {
    "type": "object",
    "properties": {
      "titles": {
        "type": "array",
        "items": {"type": "string"},
        "description": "List of story titles"
      }
    }
  }
}
```

**Response:**

```json
{
  "job_id": "abc123",
  "data": {
    "titles": ["Story 1", "Story 2", "Story 3", "Story 4", "Story 5"]
  },
  "execution_log": ["received", "exploring", "exploration_complete", "codegen", "executing_script", "done"],
  "status": "success",
  "last_screenshot_b64": "iVBORw0KGgo..."
}
```

## Client Integration

### Python (langchain-mcp-adapters)

```python
from langchain_mcp_adapters.client import MultiServerMCPClient

client = MultiServerMCPClient({
    "scry": {
        "url": "http://localhost:8085/mcp",
        "transport": "streamable_http",
    }
})

tools = await client.get_tools()
# tools now contains the 'browser' tool
```

### Claude Desktop

Add to your MCP configuration:

```json
{
  "mcpServers": {
    "scry": {
      "url": "http://localhost:8085/mcp",
      "transport": "streamable-http"
    }
  }
}
```

### Other MCP Hosts

Any MCP-compatible host can connect using the StreamableHTTP transport:

- URL: `http://localhost:8085/mcp`
- Transport: `streamable-http`

## Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `MCP_PORT` | `8085` | Server port |
| `MCP_HOST` | `0.0.0.0` | Bind address |

## Use Cases

### Web Research Agent

An LLM agent can use the browser tool to:

- Navigate to search engines
- Click through results
- Extract information from pages
- Fill forms and interact with web apps

### Data Collection

Automate data extraction from:

- News sites
- E-commerce platforms
- Social media (public pages)
- Any website with structured data

### Testing and Validation

Use in automated testing workflows to:

- Verify website functionality
- Check content accuracy
- Monitor for changes
