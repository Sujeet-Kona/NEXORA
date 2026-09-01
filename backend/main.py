from fastapi import FastAPI

app = FastAPI(
    title="Nexora API",
    description="Secure Enterprise AI Knowledge Platform",
    version="0.1.0",
)


@app.get("/health")
def health_check():
    return {"status": "ok"}