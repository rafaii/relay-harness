"""
FastAPI Main Application
========================

Web UI server for Relay Framework.
"""

import os
from pathlib import Path
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

# Import route modules
from .routes import projects, tasks, agents, status

# Create FastAPI app
app = FastAPI(
    title="Relay Framework API",
    description="Multi-Agent Development Framework Web UI",
    version="2.0.0"
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(projects.router, prefix="/api", tags=["projects"])
app.include_router(tasks.router, prefix="/api", tags=["tasks"])
app.include_router(agents.router, prefix="/api", tags=["agents"])
app.include_router(status.router, prefix="/api", tags=["status"])


@app.get("/")
async def root():
    """Root endpoint."""
    return {
        "message": "Relay Framework API",
        "version": "2.0.0",
        "docs": "/docs"
    }


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "healthy"}
