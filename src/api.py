from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from src.tenon import rotate_identify, notch_identify

app = FastAPI()

class RotateIdentifyRequest(BaseModel):
    small_circle: str  # 图片路径
    big_circle: str    # 图片路径
    image_type: int

class NotchIdentifyRequest(BaseModel):
    slider: str        # 图片路径
    background: str    # 图片路径
    image_type: int

@app.post("/api/rotate-identify")
async def api_rotate_identify(request: RotateIdentifyRequest):
    try:
        result = rotate_identify(
            request.small_circle,
            request.big_circle,
            request.image_type
        )
        return {"total_rotate_angle": result.total_rotate_angle}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.post("/api/notch-identify")
async def api_notch_identify(request: NotchIdentifyRequest):
    try:
        result = notch_identify(
            request.slider,
            request.background,
            request.image_type
        )
        return {"offset": result}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e)) 