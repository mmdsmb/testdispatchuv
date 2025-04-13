from typing import Any
from fastapi import APIRouter, Query
from pydantic import BaseModel

router = APIRouter()

class EchoRequest(BaseModel):
    message: str

@router.get("/sum", tags=["math"])
async def sum_numbers(a: int = Query(..., description="First number"), b: int = Query(..., description="Second number")):
    """
    Add two numbers together.
    """
    return {"result": a + b}

@router.post("/echo", tags=["utils"])
async def echo(request: EchoRequest):
    """
    Echo back the received JSON payload.
    """
    return request

@router.get("/version", tags=["info"])
async def get_version():
    """
    Get the current API version.
    """
    return {"version": "v1.0.0"}

# Example of how to add a new route
@router.get("/multiply", tags=["math"])
async def multiply_numbers(a: int = Query(..., description="First number"), b: int = Query(..., description="Second number")):
    """
    Multiply two numbers together.
    """
    return {"result": a * b} 