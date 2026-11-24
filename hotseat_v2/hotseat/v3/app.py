from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import os

app = FastAPI()
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

@app.get("/list/{dir_name}")
def list_dir(dir_name: str):
    if os.path.exists(dir_name):
        return {"folder": dir_name, "content": os.listdir(dir_name)}
    return {"error": "Directory not found"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
