import json
import os

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from mcp import ClientSession
from mcp.client.sse import sse_client
from openai import AsyncOpenAI

router = APIRouter()

MODEL = "openai/gpt-4o-mini"
RAG_URL = os.environ.get("RAG_URL", "http://localhost:8001/sse")
ALLOWED_ORIGINS = [o.strip() for o in os.environ.get("ALLOWED_ORIGINS", "").split(",") if o.strip()]
MAX_TOOL_ITERATIONS = 5

SYSTEM_PROMPT = """Sei un assistente che risponde a domande su politica, economia e attualità italiana.
Hai accesso a uno strumento di ricerca per trovare articoli de Il Post rilevanti.
Usa lo strumento ogni volta che la domanda riguarda fatti, notizie o eventi specifici.
Rispondi ESCLUSIVAMENTE sulla base degli articoli trovati tramite lo strumento.
Se le informazioni non sono sufficienti, dillo esplicitamente.
Non inventare mai informazioni che non siano presenti negli articoli recuperati.
Al termine di ogni risposta includi una sezione "Fonti:" con titolo e URL di ogni articolo utilizzato.
Tono: chiaro, laico, preciso."""

llm = AsyncOpenAI(
    base_url="https://openrouter.ai/api/v1",
    api_key=os.environ["OPENROUTER_API_KEY"],
)


async def build_tools(session: ClientSession) -> list[dict]:
    """Discover tools from the MCP server and convert to OpenAI format."""
    result = await session.list_tools()
    return [
        {
            "type": "function",
            "function": {
                "name": t.name,
                "description": t.description,
                "parameters": t.inputSchema,
            },
        }
        for t in result.tools
    ]


async def run_agentic_loop(
    history: list[dict],
    tools: list[dict],
    session: ClientSession,
    websocket: WebSocket,
) -> None:
    """Run the LLM+tool loop until the LLM produces a final text answer."""

    for _ in range(MAX_TOOL_ITERATIONS):
        stream = await llm.chat.completions.create(
            model=MODEL,
            messages=history,
            tools=tools,
            stream=True,
        )

        # Accumulate the streamed response
        tool_calls_acc: list[dict] = []
        full_content = ""
        finish_reason = None

        async for chunk in stream:
            choice = chunk.choices[0]
            if choice.finish_reason:
                finish_reason = choice.finish_reason
            delta = choice.delta

            if delta.tool_calls:
                # Accumulate tool call fragments across chunks
                for tc_delta in delta.tool_calls:
                    idx = tc_delta.index
                    while len(tool_calls_acc) <= idx:
                        tool_calls_acc.append({
                            "id": "",
                            "type": "function",
                            "function": {"name": "", "arguments": ""},
                        })
                    if tc_delta.id:
                        tool_calls_acc[idx]["id"] = tc_delta.id
                    if tc_delta.function and tc_delta.function.name:
                        tool_calls_acc[idx]["function"]["name"] += tc_delta.function.name
                    if tc_delta.function and tc_delta.function.arguments:
                        tool_calls_acc[idx]["function"]["arguments"] += tc_delta.function.arguments
                        

            elif delta.content:
                # Stream final answer live to the user
                full_content += delta.content
                await websocket.send_text(delta.content)

        if finish_reason == "tool_calls":
            # Add assistant tool call message to history
            history.append({
                "role": "assistant",
                "content": None,
                "tool_calls": tool_calls_acc,
            })

            # Execute each tool call via MCP and add results to history
            for tc in tool_calls_acc:
                args = json.loads(tc["function"]["arguments"])
                print(f"[CHAT] calling tool '{tc['function']['name']}' with query: '{args.get('query', '')}'", flush=True)
                result = await session.call_tool(
                    tc["function"]["name"],
                    json.loads(tc["function"]["arguments"]),
                )
                chunks = [json.loads(item.text) for item in result.content]
                history.append({
                    "role": "tool",
                    "tool_call_id": tc["id"],
                    "content": json.dumps(chunks, ensure_ascii=False),
                })

        else:
            # LLM produced a final answer — add to history and end loop
            history.append({"role": "assistant", "content": full_content})
            await websocket.send_text("[END]")
            return

    # Safety: max iterations reached without a final answer
    await websocket.send_text("\n[max tool iterations reached]")
    await websocket.send_text("[END]")


@router.websocket("/chat")
async def websocket_endpoint(websocket: WebSocket):
    origin = websocket.headers.get("origin", "")
    if ALLOWED_ORIGINS and origin not in ALLOWED_ORIGINS:
        await websocket.close(code=1008)
        print(f"[CHAT] rejected connection from origin: {origin}", flush=True)
        return

    await websocket.accept()
    history = [{"role": "system", "content": SYSTEM_PROMPT}]

    async with sse_client(RAG_URL) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            tools = await build_tools(session)

            try:
                while True:
                    user_message = await websocket.receive_text()
                    history.append({"role": "user", "content": user_message})
                    await run_agentic_loop(history, tools, session, websocket)

            except WebSocketDisconnect:
                pass
