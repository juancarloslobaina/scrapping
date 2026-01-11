from fastapi import FastAPI
from upstash_redis import Redis
import json

app = FastAPI()
redis = Redis.from_env()

@app.get("/api/data")
def get_data():
    """
    Retrieves data from Upstash Redis.
    """
    try:
        data_str = redis.get("cron_data")
        if data_str is None:
            return {"message": "No data found. The cron job may not have run yet."}
        # upstash-redis can return bytes, so we decode it before parsing JSON
        if isinstance(data_str, bytes):
            data_str = data_str.decode('utf-8')
        return json.loads(data_str)
    except Exception as e:
        return {"error": str(e)}

@app.get("/api/cron")
def job_execution():
    """
    This function is executed by the Vercel cron job.
    It generates data and stores it in Upstash Redis.
    """
    # 1. Generate your data JSON
    data = {"status": "actualizado", "valor": 12345}

    # 2. SAVE in Upstash Redis (external database)
    try:
        redis.set("cron_data", json.dumps(data))
        return {"message": "Cron executed successfully"}
    except Exception as e:
        return {"error": str(e)}
