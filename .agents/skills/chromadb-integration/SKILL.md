---
name: chromadb-integration
description: How to set up ChromaDB for vector storage, manage collections, query with metadata filters, and handle index versioning
---

# ChromaDB Integration

## Overview

This skill guides integrating ChromaDB as the vector store for the codebase indexing engine. It covers collection management, upserting embeddings with metadata, querying with filters, incremental updates, and index versioning.

## Prerequisites

```bash
pip install chromadb
```

## Step-by-Step Instructions

### 1. Initialize ChromaDB Client

```python
import chromadb
from chromadb.config import Settings

def create_client(persist_dir: str = ".codeagent/vectordb") -> chromadb.ClientAPI:
    """Create a persistent ChromaDB client."""
    return chromadb.PersistentClient(
        path=persist_dir,
        settings=Settings(anonymized_telemetry=False),
    )
```

### 2. Collection Management with Index Versioning

Each indexed repo gets its own collection. Store embedding model info and schema version as collection metadata (FR-1.8, FR-1.9).

```python
SCHEMA_VERSION = 1  # Increment when metadata schema changes

def get_or_create_collection(
    client: chromadb.ClientAPI,
    repo_name: str,
    embedding_model: str,
    embedding_model_version: str,
) -> chromadb.Collection:
    """Get or create a collection with index versioning metadata."""
    collection_name = f"repo_{repo_name.replace('/', '_').replace('.', '_')}"

    try:
        collection = client.get_collection(name=collection_name)

        # Check for model mismatch (FR-1.8)
        meta = collection.metadata or {}
        stored_model = meta.get("embedding_model", "")
        stored_version = meta.get("embedding_model_version", "")
        stored_schema = meta.get("schema_version", 0)

        if stored_model != embedding_model or stored_version != embedding_model_version:
            print(f"⚠ Embedding model changed: {stored_model}→{embedding_model}. Full re-index required.")
            client.delete_collection(name=collection_name)
            return _create_fresh_collection(
                client, collection_name, embedding_model, embedding_model_version
            )

        if stored_schema < SCHEMA_VERSION:
            print(f"⚠ Schema version changed: {stored_schema}→{SCHEMA_VERSION}. Migration needed.")
            # Handle migration (re-process chunks with new metadata fields)
            collection.modify(metadata={
                **meta,
                "schema_version": SCHEMA_VERSION,
            })

        return collection

    except Exception:
        return _create_fresh_collection(
            client, collection_name, embedding_model, embedding_model_version
        )

def _create_fresh_collection(
    client: chromadb.ClientAPI,
    name: str,
    embedding_model: str,
    embedding_model_version: str,
) -> chromadb.Collection:
    return client.create_collection(
        name=name,
        metadata={
            "embedding_model": embedding_model,
            "embedding_model_version": embedding_model_version,
            "schema_version": SCHEMA_VERSION,
            "created_at": datetime.utcnow().isoformat(),
        },
    )
```

### 3. Upserting Embeddings with Metadata

```python
def upsert_chunks(
    collection: chromadb.Collection,
    chunks: list[CodeChunk],
    embeddings: list[list[float]],
    git_sha: str,
) -> None:
    """Upsert code chunks with embeddings and metadata."""
    # ChromaDB supports batch upsert — process in batches of 100
    batch_size = 100
    for i in range(0, len(chunks), batch_size):
        batch_chunks = chunks[i:i + batch_size]
        batch_embeddings = embeddings[i:i + batch_size]

        collection.upsert(
            ids=[_chunk_id(c) for c in batch_chunks],
            embeddings=batch_embeddings,
            documents=[c.source for c in batch_chunks],
            metadatas=[
                {
                    "file_path": c.file_path,
                    "chunk_type": c.chunk_type,
                    "name": c.name,
                    "start_line": c.start_line,
                    "end_line": c.end_line,
                    "language": c.language,
                    "git_sha": git_sha,
                    "has_docstring": c.docstring is not None,
                }
                for c in batch_chunks
            ],
        )

def _chunk_id(chunk: CodeChunk) -> str:
    """Generate a stable ID for a chunk."""
    return f"{chunk.file_path}::{chunk.chunk_type}::{chunk.name}::{chunk.start_line}"
```

### 4. Querying with Metadata Filters

```python
def query_similar(
    collection: chromadb.Collection,
    query_embedding: list[float],
    top_k: int = 10,
    language: str | None = None,
    file_path: str | None = None,
    chunk_type: str | None = None,
) -> list[dict]:
    """Query similar chunks with optional metadata filters."""
    where_filter = {}
    if language:
        where_filter["language"] = language
    if chunk_type:
        where_filter["chunk_type"] = chunk_type
    if file_path:
        where_filter["file_path"] = {"$contains": file_path}

    results = collection.query(
        query_embeddings=[query_embedding],
        n_results=top_k,
        where=where_filter if where_filter else None,
        include=["documents", "metadatas", "distances"],
    )

    # Flatten results into a list of dicts
    chunks = []
    for i in range(len(results["ids"][0])):
        chunks.append({
            "id": results["ids"][0][i],
            "source": results["documents"][0][i],
            "metadata": results["metadatas"][0][i],
            "distance": results["distances"][0][i],
            "similarity": 1 - results["distances"][0][i],  # cosine: distance = 1 - similarity
        })
    return chunks
```

### 5. Incremental Updates

```python
def get_stale_files(
    collection: chromadb.Collection,
    current_git_sha: str,
) -> set[str]:
    """Find files in the collection whose git SHA doesn't match current."""
    all_items = collection.get(include=["metadatas"])
    stale_files = set()
    for meta in all_items["metadatas"]:
        if meta.get("git_sha") != current_git_sha:
            stale_files.add(meta["file_path"])
    return stale_files

def delete_file_chunks(collection: chromadb.Collection, file_path: str) -> None:
    """Remove all chunks for a specific file before re-indexing it."""
    results = collection.get(where={"file_path": file_path})
    if results["ids"]:
        collection.delete(ids=results["ids"])
```

### 6. Index Health Check (FR-1.10)

```python
def get_index_status(collection: chromadb.Collection) -> dict:
    """Return index health information for `codeagent index --status`."""
    meta = collection.metadata or {}
    count = collection.count()
    return {
        "collection_name": collection.name,
        "chunk_count": count,
        "embedding_model": meta.get("embedding_model", "unknown"),
        "embedding_model_version": meta.get("embedding_model_version", "unknown"),
        "schema_version": meta.get("schema_version", 0),
        "created_at": meta.get("created_at", "unknown"),
    }
```

## Common Pitfalls

- **Collection names** — ChromaDB restricts names to `[a-zA-Z0-9_-]`, 3–63 chars. Sanitise repo names before using as collection names
- **Batch sizes** — ChromaDB can handle up to ~5000 items per upsert, but 100 is safer for memory. Use 100 as default
- **Distance metric** — ChromaDB defaults to L2 distance. For cosine similarity (recommended for text embeddings), specify `metadata={"hnsw:space": "cosine"}` when creating the collection
- **ID stability** — chunk IDs must be deterministic. Use `file_path::type::name::line` so re-indexing the same code produces the same IDs (upsert instead of duplicate)
- **Metadata types** — ChromaDB only supports `str`, `int`, `float`, `bool` in metadata. No nested objects or lists
