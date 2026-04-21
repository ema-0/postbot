FROM python:3.11-slim

WORKDIR /app

RUN pip install "mcp[cli]" voyageai numpy

COPY main.py embedder.py ./

CMD ["python", "main.py"]
