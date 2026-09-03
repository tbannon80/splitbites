import os
import re
import math
import hashlib
from typing import List, Optional

EMBEDDING_DIM = 1536

def generate_deterministic_embedding(text: str, dim: int = EMBEDDING_DIM) -> List[float]:
    """
    Generates a deterministic, semantic-aware 1536-dimensional unit vector from text.
    Designed for homelab/offline environments without requiring external API access.
    Produces vectors normalized to unit length (L2 norm = 1.0) compatible with pgvector cosine distance.
    """
    vec = [0.0] * dim
    clean_text = text.lower()
    tokens = re.findall(r'\b[a-z0-9_-]+\b', clean_text)
    if not tokens:
        tokens = ["empty"]

    # Generate unigrams and bigrams
    ngrams = tokens + [f"{tokens[i]}_{tokens[i+1]}" for i in range(len(tokens) - 1)]

    # Semantic feature hashing using multiple salted hash functions
    for term in ngrams:
        # 4 independent hash projections per term for smooth dense representation
        for seed in (17, 31, 79, 137):
            h = hashlib.sha256(f"{seed}:{term}".encode("utf-8")).digest()
            idx = int.from_bytes(h[:4], "little") % dim
            sign = 1.0 if (h[4] & 1) else -1.0
            
            # Boost dietary and key protein terms
            weight = 1.0
            if any(k in term for k in ("gluten", "vegan", "vegetarian", "keto", "protein", "chicken", "beef", "salmon", "tofu", "shrimp", "pork")):
                weight = 2.0
            vec[idx] += sign * weight

    # L2 unit normalization: ||v||_2 = 1.0
    norm = math.sqrt(sum(x * x for x in vec))
    if norm > 0:
        return [round(x / norm, 6) for x in vec]
    else:
        vec[0] = 1.0
        return vec

async def get_embedding(text: str, dim: int = EMBEDDING_DIM) -> List[float]:
    """
    Returns a 1536-dim embedding vector.
    Uses OpenAI API if OPENAI_API_KEY is configured, otherwise uses the deterministic generator.
    """
    api_key = os.getenv("OPENAI_API_KEY")
    if api_key:
        try:
            import httpx
            async with httpx.AsyncClient(timeout=10.0) as client:
                res = await client.post(
                    "https://api.openai.com/v1/embeddings",
                    headers={"Authorization": f"Bearer {api_key}"},
                    json={"input": text, "model": "text-embedding-3-small"}
                )
                if res.status_code == 200:
                    data = res.json()
                    return data["data"][0]["embedding"]
        except Exception as e:
            print(f"[embedding] Warning: OpenAI API failed ({e}), falling back to deterministic embedding.")

    return generate_deterministic_embedding(text, dim=dim)
