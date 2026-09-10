import io
import json
import os

from fastapi import FastAPI, HTTPException, UploadFile, WebSocket, WebSocketDisconnect
from langgraph.checkpoint.memory import MemorySaver
from langgraph.checkpoint.mongodb import MongoDBSaver
from langgraph.types import Command
from pypdf import PdfReader

from backend.db import (
    get_checkpoint_client,
    get_manuals_collection,
    get_work_orders_collection,
)
from backend.graph.build import build_graph as default_build_graph
from backend.llm.claude_client import ClaudeClient
from backend.llm.ollama_client import OllamaClient


def default_llm_factory(backend_choice: str):
    if backend_choice == "cloud":
        return ClaudeClient()
    return OllamaClient()


def make_checkpointer(checkpoint_client):
    """Checkpoint into the same database as `manuals`/`work_orders`.

    `MongoDBSaver` accepts `db_name` (defaulting to `checkpointing_db`), so the
    checkpoint collections are kept alongside the application's own data.
    Its async methods offload the blocking pymongo calls to a thread pool, so
    it is safe to drive under `astream` from the event loop.
    """
    if checkpoint_client is None:
        return MemorySaver()
    return MongoDBSaver(
        checkpoint_client,
        db_name=os.environ.get("MONGODB_DB", "machine_repair"),
    )


def create_app(
    build_graph_fn=default_build_graph,
    llm_factory=default_llm_factory,
    manuals_collection_factory=get_manuals_collection,
    work_orders_collection_factory=get_work_orders_collection,
    checkpoint_client_factory=get_checkpoint_client,
):
    app = FastAPI(title="Machine Repair AI")

    @app.post("/upload")
    async def upload_pdf(file: UploadFile):
        contents = await file.read()
        try:
            reader = PdfReader(io.BytesIO(contents))
            text = "\n".join(page.extract_text() or "" for page in reader.pages)
        except Exception as exc:
            raise HTTPException(
                status_code=400,
                detail=(
                    "Could not read this PDF — please paste the error description "
                    f"as text instead. ({exc})"
                ),
            )
        return {"extracted_text": text}

    @app.websocket("/ws/{thread_id}")
    async def websocket_chat(websocket: WebSocket, thread_id: str, backend: str = "local"):
        await websocket.accept()

        llm = llm_factory(backend)
        graph = build_graph_fn(
            llm,
            manuals_collection_factory(),
            work_orders_collection_factory(),
            make_checkpointer(checkpoint_client_factory()),
        )
        config = {"configurable": {"thread_id": thread_id}}

        try:
            while True:
                message = json.loads(await websocket.receive_text())

                if message["type"] == "chat":
                    graph_input = {
                        "user_input": message["content"],
                        "pdf_text": message.get("pdf_text"),
                    }
                elif message["type"] == "approval":
                    graph_input = Command(resume=message["decision"])
                else:
                    continue

                try:
                    async for chunk in graph.astream(graph_input, config, stream_mode="updates"):
                        if "__interrupt__" in chunk:
                            await websocket.send_json(
                                {
                                    "type": "approval_request",
                                    "payload": chunk["__interrupt__"][0].value,
                                }
                            )
                            continue
                        for node_name, update in chunk.items():
                            await websocket.send_json(
                                {"type": "node_update", "node": node_name, "data": update}
                            )
                except Exception as exc:
                    # The graph run failed (e.g. the MCP subprocess is
                    # unreachable). Surface it and keep the socket open so the
                    # technician can retry rather than stalling silently.
                    await websocket.send_json({"type": "error", "message": str(exc)})
        except WebSocketDisconnect:
            pass

    return app


app = create_app()
