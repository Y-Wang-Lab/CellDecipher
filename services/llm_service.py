"""LLM service for natural language query parsing."""

import os
from typing import Optional, Dict, Any, List
from dataclasses import dataclass


@dataclass
class ParsedQuery:
    """Parsed search query parameters."""
    tissue: Optional[List[str]] = None
    cell_type: Optional[List[str]] = None
    disease: Optional[List[str]] = None
    organism: str = "Homo sapiens"
    assay: Optional[List[str]] = None
    development_stage: Optional[str] = None
    sex: Optional[str] = None
    raw_query: str = ""


class LLMService:
    """Service for parsing natural language queries using LLMs."""

    SYSTEM_PROMPT = """You are a bioinformatics assistant that parses natural language queries
about single-cell RNA-seq data into structured search parameters.

Extract the following information from user queries:
- tissue: body tissue or organ (e.g., "lung", "heart", "brain")
- cell_type: cell types (e.g., "T cell", "B cell", "neuron")
- disease: disease or condition (e.g., "cancer", "COVID-19", "healthy")
- organism: species (default "Homo sapiens", or "Mus musculus")
- assay: sequencing technology (e.g., "10x 3' v3", "Smart-seq2")
- development_stage: developmental stage (e.g., "adult", "fetal")
- sex: biological sex (e.g., "male", "female")

Return the parameters as a JSON object."""

    def __init__(self, provider: str = "openai", api_key: Optional[str] = None):
        """Initialize LLM service.

        Args:
            provider: 'openai' or 'anthropic'
            api_key: API key (uses env var if not provided)
        """
        self.provider = provider
        self.api_key = api_key or os.environ.get(
            "OPENAI_API_KEY" if provider == "openai" else "ANTHROPIC_API_KEY"
        )
        self._client = None

    def _get_client(self):
        """Lazy load the LLM client."""
        if self._client is None:
            if self.provider == "openai":
                from openai import OpenAI
                self._client = OpenAI(api_key=self.api_key)
            else:
                from anthropic import Anthropic
                self._client = Anthropic(api_key=self.api_key)
        return self._client

    def parse_query(self, query: str) -> ParsedQuery:
        """Parse natural language query into structured parameters.

        Args:
            query: Natural language search query

        Returns:
            ParsedQuery with extracted parameters
        """
        if not self.api_key:
            # Fallback to simple keyword extraction
            return self._simple_parse(query)

        try:
            client = self._get_client()

            if self.provider == "openai":
                response = client.chat.completions.create(
                    model="gpt-4-turbo",
                    messages=[
                        {"role": "system", "content": self.SYSTEM_PROMPT},
                        {"role": "user", "content": query}
                    ],
                    response_format={"type": "json_object"},
                    max_tokens=500,
                )
                result = response.choices[0].message.content
            else:
                response = client.messages.create(
                    model="claude-sonnet-4-20250514",
                    max_tokens=500,
                    system=self.SYSTEM_PROMPT,
                    messages=[{"role": "user", "content": query}]
                )
                result = response.content[0].text

            # Parse JSON response
            import json
            params = json.loads(result)

            return ParsedQuery(
                tissue=params.get("tissue"),
                cell_type=params.get("cell_type"),
                disease=params.get("disease"),
                organism=params.get("organism", "Homo sapiens"),
                assay=params.get("assay"),
                development_stage=params.get("development_stage"),
                sex=params.get("sex"),
                raw_query=query,
            )

        except Exception as e:
            print(f"LLM parsing failed: {e}")
            return self._simple_parse(query)

    def _simple_parse(self, query: str) -> ParsedQuery:
        """Simple keyword-based parsing fallback.

        Args:
            query: Search query

        Returns:
            ParsedQuery with basic extraction
        """
        query_lower = query.lower()

        # Simple keyword detection
        tissues = ["lung", "heart", "brain", "liver", "kidney", "skin", "blood", "bone marrow"]
        cell_types = ["t cell", "b cell", "macrophage", "neuron", "fibroblast", "epithelial"]
        diseases = ["cancer", "tumor", "covid", "healthy", "normal", "disease"]

        found_tissues = [t for t in tissues if t in query_lower]
        found_cells = [c for c in cell_types if c in query_lower]
        found_diseases = [d for d in diseases if d in query_lower]

        organism = "Mus musculus" if "mouse" in query_lower else "Homo sapiens"

        return ParsedQuery(
            tissue=found_tissues if found_tissues else None,
            cell_type=found_cells if found_cells else None,
            disease=found_diseases if found_diseases else None,
            organism=organism,
            raw_query=query,
        )
