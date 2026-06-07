"""In-memory semantic property search backed by Gemini embeddings.

Replaces the previous ChromaDB + sentence-transformers (Torch) stack so the app stays
lightweight enough to deploy on a free tier. The catalog is tiny (a handful of demo
listings), so embeddings are computed once at startup and searched with cosine
similarity in NumPy.
"""
import json
import os
from typing import List, Dict, Optional

import numpy as np

import llm


class PropertyManager:
    """Load demo listings and search them semantically via Gemini embeddings."""

    def __init__(self, data_path: str = "properties.json"):
        self.properties: List[Dict] = []
        self._embeddings: Optional[np.ndarray] = None

        self._load(data_path)
        self._build_index()

    def _load(self, data_path: str):
        if not os.path.exists(data_path):
            print(f"⚠️  Property data file not found: {data_path}")
            return
        with open(data_path) as f:
            self.properties = json.load(f)
        print(f"✅ Loaded {len(self.properties)} properties from {data_path}")

    def _searchable_text(self, p: Dict) -> str:
        features = p.get("features", [])
        if isinstance(features, list):
            features = ", ".join(features)
        return (
            f"Property at {p.get('address')}. {p.get('property_type')} with "
            f"{p.get('bedrooms')} bedrooms and {p.get('bathrooms')} bathrooms, "
            f"priced at ${p.get('price', 0):,}, {p.get('square_feet')} square feet, "
            f"in {p.get('neighborhood')} {p.get('city')}. "
            f"Features: {features}. {p.get('description', '')}"
        )

    def _build_index(self):
        """Embed every listing once. Degrades gracefully if Gemini isn't configured."""
        if not self.properties or not llm.is_configured():
            if not llm.is_configured():
                print("⚠️  Gemini not configured — property search will use keyword fallback")
            return
        try:
            texts = [self._searchable_text(p) for p in self.properties]
            self._embeddings = np.array(llm.embed(texts), dtype=np.float32)
            print(f"✅ Embedded {len(texts)} properties for semantic search")
        except Exception as e:
            print(f"⚠️  Could not build embedding index ({e}) — using keyword fallback")
            self._embeddings = None

    def search_properties(self, query: str, n_results: int = 5) -> List[Dict]:
        """Return the listings most relevant to the query."""
        if not self.properties:
            return []

        # Semantic path
        if self._embeddings is not None:
            try:
                q = np.array(llm.embed([query])[0], dtype=np.float32)
                sims = self._cosine_sim(q, self._embeddings)
                order = np.argsort(sims)[::-1][:n_results]
                return [dict(self.properties[i]) for i in order]
            except Exception as e:
                print(f"⚠️  Semantic search failed ({e}) — falling back to keyword match")

        # Keyword fallback
        return self._keyword_search(query, n_results)

    @staticmethod
    def _cosine_sim(vec: np.ndarray, matrix: np.ndarray) -> np.ndarray:
        denom = (np.linalg.norm(matrix, axis=1) * np.linalg.norm(vec)) + 1e-10
        return (matrix @ vec) / denom

    def _keyword_search(self, query: str, n_results: int) -> List[Dict]:
        q = query.lower()
        scored = []
        for p in self.properties:
            text = self._searchable_text(p).lower()
            score = sum(1 for word in q.split() if word in text)
            scored.append((score, p))
        scored.sort(key=lambda x: x[0], reverse=True)
        return [dict(p) for _, p in scored[:n_results]]

    def count_properties(self) -> int:
        return len(self.properties)
