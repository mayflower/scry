from fastapi import FastAPI

from .api.routes import router as api_router


def create_app() -> FastAPI:
    app = FastAPI(title="Scry API", version="0.1.0")
    app.include_router(api_router)

    @app.get("/healthz")
    def healthz():
        return {"status": "ok"}

    return app


app = create_app()
