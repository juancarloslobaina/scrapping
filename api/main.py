from fastapi import FastAPI
from vercel_kv import VercelKV
import json
import os

app = FastAPI()
kv = VercelKV()

@app.get("/api/data")
def get_data():
    """
    Retrieves data from Vercel KV.
    """
    try:
        data_str = kv.get("cron_data")
        if data_str is None:
            return {"message": "No data found. The cron job may not have run yet."}
        return json.loads(data_str)
    except Exception as e:
        return {"error": str(e)}

@app.get("/api/cron")
def job_execution():
    """
    This function is executed by the Vercel cron job.
    It generates data and stores it in Vercel KV.
    """
    # 1. Generate your data JSON
    data = {"status": "actualizado", "valor": 12345}

    # 2. SAVE in Vercel KV (external database)
    try:
        kv.set("cron_data", json.dumps(data))
        return {"message": "Cron executed successfully"}
    except Exception as e:
        return {"error": str(e)}
