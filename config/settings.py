"""Application configuration using Pydantic settings."""

import os
from typing import Optional
from pydantic_settings import BaseSettings
from pydantic import Field


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    # LLM Settings
    llm_provider: str = Field(default="openai", description="LLM provider: openai or anthropic")
    openai_api_key: Optional[str] = Field(default=None, description="OpenAI API key")
    anthropic_api_key: Optional[str] = Field(default=None, description="Anthropic API key")
    llm_model: str = Field(default="gpt-4-turbo", description="LLM model to use")

    # Nextflow Tower Settings
    tower_api_endpoint: str = Field(default="https://api.tower.nf", description="Tower API endpoint")
    tower_access_token: Optional[str] = Field(default=None, description="Tower access token")
    tower_workspace: Optional[str] = Field(default=None, description="Tower workspace")

    # Data Settings
    cellxgene_census_version: str = Field(default="stable", description="CELLxGENE Census version")
    max_upload_size_mb: int = Field(default=500, description="Max upload size in MB")

    # Probe Design Settings (paths are now relative to the app, set in probe_service.py)
    probe_design_path: Optional[str] = Field(
        default=None,
        description="Path to probe design library (uses bundled version if not set)"
    )
    barcode_csv_path: Optional[str] = Field(
        default=None,
        description="Path to barcode library CSV (uses bundled version if not set)"
    )

    # Multifish Knowledge Base
    multifish_knowledge_dir: Optional[str] = Field(
        default=None,
        description="Path to multifish-mcp knowledge directory"
    )
    multifish_knowledge_repo: Optional[str] = Field(
        default=None,
        description="GitHub repo URL for shared knowledge sync (e.g. git@github.com:org/multifish-knowledge.git)"
    )
    multifish_knowledge_branch: str = Field(
        default="main",
        description="Git branch for knowledge sync"
    )

    # GitHub API-based Knowledge Sync (for Streamlit Cloud / no-git environments)
    github_token: Optional[str] = Field(
        default=None,
        description="GitHub PAT for knowledge sync (repo scope required)"
    )
    github_repo: str = Field(
        default="Y-Wang-Lab/CellDecipher",
        description="GitHub repo for knowledge storage (owner/repo format)"
    )
    github_knowledge_path: str = Field(
        default="knowledge",
        description="Path within repo to knowledge directory"
    )

    # Analysis Defaults
    default_n_neighbors: int = Field(default=15, description="Default neighbors for UMAP")
    default_leiden_resolution: float = Field(default=1.0, description="Default Leiden resolution")
    default_n_pcs: int = Field(default=50, description="Default number of PCs")

    # App Password
    app_password_hash: Optional[str] = Field(
        default=None,
        description="SHA-256 hash of the app password (leave empty to disable)"
    )

    # Logging
    log_level: str = Field(default="INFO", description="Logging level")

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        extra = "ignore"


# Global settings instance
settings = Settings()
