"""Vertex custom prediction protocol, using the training image's exact dependencies."""
import os
import tempfile
from pathlib import Path

import joblib
import pandas as pd
import uvicorn
from fastapi import FastAPI, HTTPException

from cloudlayer.gcp import GcpAdapter
from src import config, data

app = FastAPI()
model = None


@app.on_event('startup')
def startup():
    global model
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / 'model.joblib'
        GcpAdapter(config.load(strict=False)).download(os.environ['AIP_STORAGE_URI'] + '/model.joblib', str(path))
        model = joblib.load(path)


@app.get(os.environ.get('AIP_HEALTH_ROUTE', '/health'))
def health():
    return {'ready': model is not None}


@app.post(os.environ.get('AIP_PREDICT_ROUTE', '/predict'))
def predict(payload: dict):
    try:
        frame = pd.DataFrame(payload['instances'], columns=data.FEATURES)
        return {'predictions': model.predict_proba(frame).tolist()}
    except (ValueError, KeyError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


if __name__ == '__main__':
    uvicorn.run(app, host='0.0.0.0', port=int(os.environ.get('AIP_HTTP_PORT', '8080')))
