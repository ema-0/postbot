from fastapi import FastAPI

from chat import router

app = FastAPI()

app.include_router(router)
