__all__ = [
    "TFIDFScorer",
    "SemanticToolSelector",
    "create_tool_selector",
]

"""
Semantic Tool Search for Water.

When an agent has many tools (50+), sending all tool schemas to the LLM
adds noise and hurts selection accuracy.  This module provides a pure-Python
TF-IDF + cosine-similarity scorer that selects the most relevant subset of
tools for a given query or reasoning step, keeping the context window lean.

No external dependencies — uses only the Python standard library.
"""

import math
import re
from typing import Dict, List, Optional

from water.agents.tools import Tool, Toolkit


# ---------------------------------------------------------------------------
# Tokenisation helper
# ---------------------------------------------------------------------------

_SPLIT_RE = re.compile(r"[^a-z0-9]+")


def _tokenize(text: str) -> List[str]:
    """Lowercase and split on non-alphanumeric characters."""
    return [tok for tok in _SPLIT_RE.split(text.lower()) if tok]


# ---------------------------------------------------------------------------
# TF-IDF scorer
# ---------------------------------------------------------------------------


class TFIDFScorer:
    """
    Pure-Python TF-IDF cosine-similarity scorer.

    Args:
        documents: List of document strings to index.
    """

    def __init__(self, documents: List[str]) -> None:
        self._documents = documents
        self._n_docs = len(documents)

        # Tokenise every document and build the vocabulary.
        self._doc_tokens: List[List[str]] = [_tokenize(d) for d in documents]

        # Document frequency: how many documents contain each term.
        df: Dict[str, int] = {}
        for tokens in self._doc_tokens:
            seen = set(tokens)
            for term in seen:
                df[term] = df.get(term, 0) + 1
        self._df = df

        # IDF: log(N / df) — standard formulation.  Terms that appear in
        # every document get IDF = 0, which is correct (they carry no
        # discriminative signal).
        self._idf: Dict[str, float] = {}
        for term, freq in df.items():
            self._idf[term] = math.log(self._n_docs / freq) if freq else 0.0

        # Pre-compute TF-IDF vectors and their norms for each document.
        self._doc_vectors: List[Dict[str, float]] = []
        self._doc_norms: List[float] = []
        for tokens in self._doc_tokens:
            vec = self._tfidf_vector(tokens)
            self._doc_vectors.append(vec)
            self._doc_norms.append(self._norm(vec))

    # -- internal helpers ----------------------------------------------------

    def _tfidf_vector(self, tokens: List[str]) -> Dict[str, float]:
        """Build a sparse TF-IDF vector (dict) from a token list."""
        tf: Dict[str, int] = {}
        for t in tokens:
            tf[t] = tf.get(t, 0) + 1
        vec: Dict[str, float] = {}
        for term, count in tf.items():
            idf = self._idf.get(term, 0.0)
            vec[term] = count * idf
        return vec

    @staticmethod
    def _norm(vec: Dict[str, float]) -> float:
        """L2 norm of a sparse vector."""
        return math.sqrt(sum(v * v for v in vec.values())) if vec else 0.0

    @staticmethod
    def _cosine(
        vec_a: Dict[str, float],
        norm_a: float,
        vec_b: Dict[str, float],
        norm_b: float,
    ) -> float:
        """Cosine similarity between two sparse vectors."""
        if norm_a == 0.0 or norm_b == 0.0:
            return 0.0
        # Iterate over the smaller vector for efficiency.
        if len(vec_a) > len(vec_b):
            vec_a, norm_a, vec_b, norm_b = vec_b, norm_b, vec_a, norm_a
        dot = sum(w * vec_b.get(term, 0.0) for term, w in vec_a.items())
        return dot / (norm_a * norm_b)

    # -- public API ----------------------------------------------------------

    def score(self, query: str, doc_index: int) -> float:
        """Return the TF-IDF cosine similarity between *query* and the document at *doc_index*."""
        q_tokens = _tokenize(query)
        q_vec = self._tfidf_vector(q_tokens)
        q_norm = self._norm(q_vec)
        return self._cosine(
            q_vec, q_norm, self._doc_vectors[doc_index], self._doc_norms[doc_index]
        )

    def score_all(self, query: str) -> List[float]:
        """Score *query* against every document.  Returns a list of floats (one per document)."""
        q_tokens = _tokenize(query)
        q_vec = self._tfidf_vector(q_tokens)
        q_norm = self._norm(q_vec)
        return [
            self._cosine(q_vec, q_norm, dv, dn)
            for dv, dn in zip(self._doc_vectors, self._doc_norms)
        ]


# ---------------------------------------------------------------------------
# Semantic tool selector
# ---------------------------------------------------------------------------


class SemanticToolSelector:
    """
    Selects the most relevant tools for a query using TF-IDF similarity.

    Args:
        tools: Full list of available Tool instances.
        top_k: Maximum number of tools to return per query (excluding
               *always_include* tools, which are added unconditionally).
        always_include: Optional list of tool names that should always be
                        present in the selection regardless of score.
    """

    def __init__(
        self,
        tools: List[Tool],
        top_k: int = 5,
        always_include: Optional[List[str]] = None,
    ) -> None:
        self._tools = list(tools)
        self._top_k = top_k
        self._always_include: set = set(always_include or [])

        # Build the TF-IDF index from "name  description" for each tool.
        documents = [f"{t.name}  {t.description}" for t in self._tools]
        self._scorer = TFIDFScorer(documents)

        # Quick lookup by name.
        self._tool_map: Dict[str, Tool] = {t.name: t for t in self._tools}

    def select(self, query: str) -> List[Tool]:
        """Return the most relevant tools for *query*.

        Returns up to *top_k* tools ranked by TF-IDF cosine similarity, plus
        any tools listed in *always_include*.  The always-included tools do
        **not** count toward the *top_k* budget.
        """
        scores = self._scorer.score_all(query)

        # Pair each tool with its score and sort descending.
        scored = sorted(
            enumerate(scores), key=lambda pair: pair[1], reverse=True
        )

        selected: List[Tool] = []
        selected_names: set = set()

        # Always-include tools first.
        for name in self._always_include:
            tool = self._tool_map.get(name)
            if tool is not None:
                selected.append(tool)
                selected_names.add(name)

        # Top-k by score (skip already-included).
        for idx, _score in scored:
            if len(selected) - len(selected_names & self._always_include) >= self._top_k:
                break
            tool = self._tools[idx]
            if tool.name not in selected_names:
                selected.append(tool)
                selected_names.add(tool.name)

        return selected

    def to_toolkit(self, query: str) -> Toolkit:
        """Return a :class:`Toolkit` containing only the selected tools."""
        tools = self.select(query)
        return Toolkit(name="selected", tools=tools)


# ---------------------------------------------------------------------------
# Convenience factory
# ---------------------------------------------------------------------------


def create_tool_selector(
    tools: List[Tool],
    top_k: int = 5,
    always_include: Optional[List[str]] = None,
) -> SemanticToolSelector:
    """Create a :class:`SemanticToolSelector` — convenience factory."""
    return SemanticToolSelector(tools=tools, top_k=top_k, always_include=always_include)
