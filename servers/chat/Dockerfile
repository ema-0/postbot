FROM python:3.11-slim

WORKDIR /app

RUN pip install fastapi "uvicorn[standard]" openai websockets "mcp[cli]"

COPY main.py chat.py ./

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--timeout-keep-alive", "0"]
