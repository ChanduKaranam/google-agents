import os

import uvicorn
from google.adk.a2a.utils.agent_to_a2a import to_a2a

from agent import root_agent

PORT = int(os.environ.get("PORT", 8080))

# pyrefly: ignore [unexpected-keyword]
app = to_a2a(
    agent=root_agent,
    host="0.0.0.0",
    port=PORT,
    protocol="http",
)

if __name__ == "__main__":
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=PORT,
    )