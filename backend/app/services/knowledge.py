from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

import boto3
import numpy as np
from pypdf import PdfReader
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.enums import FibrosisStage
from app.db.models import KnowledgeChunk

BLOCK_TITLES = [
    "Stage Explanation",
    "Symptoms Education",
    "Risk Factors",
    "Suggested Follow-Up Guidance",
    "Red Flag Warning",
]


@dataclass
class ChunkRecord:
    source_doc: str
    page_number: int
    text: str


def chunk_text(text: str, chunk_size: int = 600, overlap: int = 80) -> list[str]:
    words = text.split()
    if not words:
        return []
    chunks: list[str] = []
    i = 0
    while i < len(words):
        chunk_words = words[i : i + chunk_size]
        chunks.append(" ".join(chunk_words))
        if i + chunk_size >= len(words):
            break
        i += max(chunk_size - overlap, 1)
    return chunks


def parse_pdf_chunks(pdf_path: Path) -> Iterable[ChunkRecord]:
    reader = PdfReader(str(pdf_path))
    for page_idx, page in enumerate(reader.pages):
        text = page.extract_text() or ""
        text = " ".join(text.split())
        for chunk in chunk_text(text, chunk_size=600, overlap=80):
            yield ChunkRecord(source_doc=pdf_path.name, page_number=page_idx + 1, text=chunk)


def _hash_embedding(text: str, dim: int = 256) -> list[float]:
    vec = np.zeros(dim, dtype=np.float32)
    for token in text.lower().split():
        idx = int(hashlib.md5(token.encode("utf-8")).hexdigest(), 16) % dim
        vec[idx] += 1.0
    norm = np.linalg.norm(vec)
    if norm > 0:
        vec = vec / norm
    return vec.astype(float).tolist()


def embed_text(text: str, settings: Settings) -> list[float]:
    client = boto3.client("bedrock-runtime", region_name=settings.aws_region)
    body = {
        "inputText": text,
    }
    try:
        response = client.invoke_model(
            modelId=settings.bedrock_embedding_model_id,
            contentType="application/json",
            accept="application/json",
            body=json.dumps(body),
        )
        payload = json.loads(response["body"].read().decode("utf-8"))
        vector = payload.get("embedding")
        if isinstance(vector, list):
            return [float(x) for x in vector]
    except Exception:
        pass
    return _hash_embedding(text)


def ingest_journals(db: Session, settings: Settings) -> dict[str, int]:
    stats = {"docs": 0, "chunks": 0}
    pdf_files = sorted(settings.journals_path.glob("*.pdf"))
    for pdf in pdf_files:
        stats["docs"] += 1
        chunk_idx = 0
        for rec in parse_pdf_chunks(pdf):
            existing = db.scalar(
                select(KnowledgeChunk).where(
                    KnowledgeChunk.source_doc == rec.source_doc,
                    KnowledgeChunk.page_number == rec.page_number,
                    KnowledgeChunk.chunk_index == chunk_idx,
                )
            )
            if existing:
                chunk_idx += 1
                continue
            emb = embed_text(rec.text, settings)
            db.add(
                KnowledgeChunk(
                    source_doc=rec.source_doc,
                    page_number=rec.page_number,
                    chunk_index=chunk_idx,
                    text=rec.text,
                    embedding=emb,
                    metadata_json={"tokens": len(rec.text.split())},
                )
            )
            stats["chunks"] += 1
            chunk_idx += 1
    db.commit()
    return stats


def _cosine_similarity(a: np.ndarray, b: np.ndarray) -> float:
    if a.size == 0 or b.size == 0:
        return 0.0
    if a.shape[0] != b.shape[0]:
        dim = min(a.shape[0], b.shape[0])
        a = a[:dim]
        b = b[:dim]
    denom = (np.linalg.norm(a) * np.linalg.norm(b))
    if denom <= 0:
        return 0.0
    return float(np.dot(a, b) / denom)


def retrieve_chunks(db: Session, query: str, settings: Settings, top_k: int = 5) -> list[KnowledgeChunk]:
    q_emb = np.array(embed_text(query, settings), dtype=np.float32)
    chunks = db.scalars(select(KnowledgeChunk)).all()
    scored: list[tuple[KnowledgeChunk, float]] = []
    for chunk in chunks:
        emb = chunk.embedding or []
        score = _cosine_similarity(q_emb, np.array(emb, dtype=np.float32))
        scored.append((chunk, score))
    scored.sort(key=lambda x: x[1], reverse=True)
    return [item[0] for item in scored[:top_k]]


def synthesize_blocks(
    *,
    fibrosis_stage: FibrosisStage | None,
    retrieved: list[KnowledgeChunk],
) -> list[dict]:
    if not retrieved:
        retrieved = [
            KnowledgeChunk(
                id="N/A",
                source_doc="No Source",
                page_number=0,
                chunk_index=0,
                text="No supporting literature has been ingested yet.",
                embedding=[],
                metadata_json={},
            )
        ]

    stage_text = fibrosis_stage.value if fibrosis_stage else "unknown stage"
    top = retrieved[0]
    secondary = retrieved[1] if len(retrieved) > 1 else top

    content = {
        "Stage Explanation": (
            f"Predicted fibrosis stage is {stage_text}. Correlated literature discusses progression "
            f"patterns and interpretation guidance in this stage context."
        ),
        "Symptoms Education": (
            "Common symptoms can vary by etiology and stage; asymptomatic presentation is possible. "
            "Correlate imaging output with labs and clinical exam."
        ),
        "Risk Factors": (
            "Key risk factors include cardiometabolic burden, inflammatory activity, and underlying "
            "liver disease etiology."
        ),
        "Suggested Follow-Up Guidance": (
            "Recommend specialist review, longitudinal monitoring, and confirmatory evaluation when "
            "confidence is low or progression risk is elevated."
        ),
        "Red Flag Warning": (
            "Escalate urgently if decompensation signs or severe-stage indicators are present."
        ),
    }

    blocks: list[dict] = []
    for title in BLOCK_TITLES:
        blocks.append(
            {
                "title": title,
                "content": f"{content[title]}\nEvidence snippets: {top.text[:240]} {secondary.text[:180]}",
                "citations": [
                    {"source_doc": top.source_doc, "page_number": top.page_number},
                    {"source_doc": secondary.source_doc, "page_number": secondary.page_number},
                ],
            }
        )
    return blocks
