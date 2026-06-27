from fastapi import FastAPI, BackgroundTasks, HTTPException
from pydantic import BaseModel
from typing import List
import tasks
from shared.utils.logging import setup_logging

# Setup structured logging
setup_logging()

app = FastAPI(
    title="Stock & Crypto Ingestion Service",
    description="Crawling data using ccxt & vnstock via Celery beat schedulers",
    version="1.0.0",
)


class TriggerRequest(BaseModel):
    symbols: List[str]
    asset_type: str  # stock | crypto
    resolution: str = "1d"


@app.get("/health")
def health_check():
    """Health check endpoint for Docker Compose / Kubernetes."""
    return {"status": "healthy", "service": "ingestion"}


@app.post("/trigger")
def trigger_ingestion(payload: TriggerRequest, background_tasks: BackgroundTasks):
    """
    Manually triggers an ingestion job as a background process.
    Useful for local testing and seeding initial historical data.
    """
    if payload.asset_type == "crypto":
        # Run Celery task in background (async)
        tasks.ingest_crypto_task.delay(payload.symbols, payload.resolution)
        return {
            "status": "triggered",
            "details": f"Crypto task sent for {payload.symbols}",
        }
    elif payload.asset_type == "stock":
        tasks.ingest_stocks_task.delay(payload.symbols, payload.resolution)
        return {
            "status": "triggered",
            "details": f"Stock task sent for {payload.symbols}",
        }
    else:
        raise HTTPException(
            status_code=400, detail="Invalid asset_type. Must be 'stock' or 'crypto'."
        )
