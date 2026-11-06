import argparse
import hashlib
import json
from pathlib import Path
from openai import OpenAI
from langchain_text_splitters import MarkdownHeaderTextSplitter
from app.core.config import settings
import re
from pydantic import BaseModel, ConfigDict, Field
from typing import Any, Optional, Literal
from app.db.neo4j import (
    close_neo4j,
    ensure_schema,
    get_driver,
    init_neo4j
)

BOOKS_DIR = Path("data/books")
DATASET_ID = settings.GRAPHRAG_DATASET_ID
OPENAI_MODEL = settings.OPENAI_MODEL

if not settings.OPENAI_API_KEY:
    raise ValueError("Thiếu OPENAI_API_KEY trong file .env")
client = OpenAI(api_key=settings.OPENAI_API_KEY)

HEADER_SPLITTER = MarkdownHeaderTextSplitter(
    headers_to_split_on=[
        ("#", "h1"),
        ("##", "h2"),
        ("###", "h3"),
    ],
    strip_headers=False,
)

def find_markdown_files(input_path: Path) -> list[Path]:
    if input_path.is_file() and input_path.suffix.lower() == ".md":
        return [input_path]
    if input_path.is_dir():
        return sorted(
            path
            for path in input_path.rglob("*")
            if path.is_file() and path.suffix.lower() == ".md"
        )
    raise FileNotFoundError(
        f"Không tìm thấy file Markdown hoặc thư mục: {input_path}"
    )
    
def load_chunks(file_path: Path, max_chars: int = 5000) -> list[dict]:
    text = file_path.read_text(encoding="utf-8")
    sections = HEADER_SPLITTER.split_text(text)
    chunks = []
    for section in sections:
        content = section.page_content.strip()
        if not content:
            continue
        metadata = section.metadata
        title = (
            metadata.get("h3") or metadata.get("h2") or metadata.get("h1") or file_path.stem
        )
        sentences = re.split(r"(?<=[.!?])\s+", content)
        current = []
        size = 0
        index = 1
        for sentence in sentences:
            sentence = sentence.strip()
            if not sentence:
                continue
            if current and size + len(sentence) + 1 > max_chars:
                chunk_text = " ".join(current)
                chunk_id = hashlib.sha256(f"{file_path.resolve()}:{chunk_text}".encode("utf-8")).hexdigest()
                chunks.append({
                    "chunk_id": chunk_id,
                    "title": title,
                    "text": chunk_text,
                })
                current = []
                size = 0
                index += 1
            current.append(sentence)
            size += len(sentence) + 1
        if current:
            chunk_text = " ".join(current)
            chunk_id = hashlib.sha256(f"{file_path.resolve()}:{chunk_text}".encode("utf-8")).hexdigest()
            chunks.append({
                "chunk_id": chunk_id,
                "title": title,
                "text": chunk_text,
            })
    return chunks

class Entity(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(description="The canonical name of the psychological entity mentioned in the source")
    type: Literal[
        "Concept", "Emotion", "Behavior", "Context", 
        "Problem", "Goal", "CopingStrategy", "Intervention", 
        "Exercise", "SupportStrategy", "Evidence",
    ] = Field(
        description="The node type, which must belong to the predefined psychology ontology"
    )
    description: str = Field(description="A concise description of the entity's meaning or role based on the source content")
    category: Optional[Literal["symptom", "emotion", "personality"]] = Field(description="Only for type Concept: symptom, emotion or personality. Use null for every other type")
    
class Relationship(BaseModel):
    model_config = ConfigDict(extra="forbid")
    source: str = Field(description="The exact name of the source entity, matching the name of an extracted entity")
    type: Literal[
        "TRIGGERS", "EXHIBITS", "EXPLAINS", 
        "MAY_RELATE_TO", "HAS_GOAL", "MAY_HELP_WITH", 
        "SUPPORTS", "USES", "HAS_EVIDENCE"
    ] = Field(description="The relationship type, which must belong to the predefined psychology ontology")
    target: str = Field(description="The exact name of the target entity, matching the name of an extracted entity")
    evidence: str = Field(description="A verbatim quote or a concise explanation from the source chunk that supports the relationship")

class GraphExtraction(BaseModel):
    model_config = ConfigDict(extra="forbid")
    entities: list[Entity]
    relationships: list[Relationship]

def first_parsed(response) -> GraphExtraction:
    parsed = response.output_parsed
    if parsed is None:
        raise RuntimeError(
            "OpenAI response did not contain parsed structured output"
        )
    return parsed

def extract_graph(chunk: dict) -> GraphExtraction:
    response = client.responses.parse(
        model=OPENAI_MODEL,
        input= [
            {
                "role": "system",
                "content": """
                Extract a psychology knowledge graph from the provided text.
                - Extract only entities and relationships supported by the source.
                - Use only the entity and relationship types defined in the schema.
                - Preserve the source's meaning and use consistent entity names.
                - Every relationship must include supporting evidence from the text.
                - Do not use external knowledge or invent information.
                - Omit unclear or unsupported entities and relationships.
                """
            },
            {
                "role": "user",
                "content": (
                    f"Source: {chunk['title']}\n"
                    f"Chunk ID: {chunk['chunk_id']}\n"
                    f"Text:\n{chunk['text']}"
                ),
            },
        ],
        text_format=GraphExtraction,
    )
    return first_parsed(response)

def save_chunk(session, chunk: dict, graph: GraphExtraction) -> None:
    entities = [entity.model_dump() for entity in graph.entities]
    relationships = [relationship.model_dump() for relationship in graph.relationships]
    # Save chunk
    session.run("MERGE (c:Chunk {dataset_id: $dataset_id, chunk_id: $chunk_id}) SET c.title = $title, c.text = $text", dataset_id=DATASET_ID, chunk_id=chunk["chunk_id"], title=chunk["title"], text=chunk["text"]).consume()
    # Save Entity
    session.run("UNWIND $entities AS entity MERGE (e:Entity {dataset_id: $dataset_id, name: entity.name}) SET e.type = entity.type, e.description = entity.description WITH e MATCH (c:Chunk {dataset_id: $dataset_id, chunk_id: $chunk_id}) MERGE (c)-[:MENTIONS]->(e)", dataset_id=DATASET_ID, chunk_id=chunk["chunk_id"], entities=entities).consume()
    # Save Relationship
    session.run("UNWIND $relationships AS rel MATCH (source:Entity {dataset_id: $dataset_id, name: rel.source}) MATCH (target:Entity {dataset_id: $dataset_id, name: rel.target}) MERGE (source)-[r:RELATED {dataset_id: $dataset_id, type: rel.type, chunk_id: $chunk_id}]->(target) SET r.evidence = rel.evidence", dataset_id=DATASET_ID, chunk_id=chunk["chunk_id"], relationships=relationships).consume()
    # Skip saved chunks
    session.run("MATCH (c:Chunk {dataset_id: $dataset_id, chunk_id: $chunk_id}) SET c.extracted = true", dataset_id=DATASET_ID, chunk_id=chunk["chunk_id"]).consume()



if __name__ == "__main__":
    # Load Markdown files and create chunks
    # markdown_files = find_markdown_files(BOOKS_DIR)
    # chunks = []
    # for file_path in markdown_files:
    #     chunks.extend(load_chunks(file_path))
    # print(f"Total Markdown files: {len(markdown_files)}")
    # print(f"Total chunks: {len(chunks)}")
    # init_neo4j()
    # ensure_schema()
    # failed = 0
    # try:
    #     with get_driver().session(database=settings.NEO4J_DATABASE) as session:
    #         done = {
    #             rec["id"]
    #             for rec in session.run(
    #                 "MATCH (c:Chunk {dataset_id: $d, extracted: true}) RETURN c.chunk_id AS id",
    #                 d=DATASET_ID,
    #             )
    #         }
    #         chunks = [c for c in chunks if c["chunk_id"] not in done]
    #         print(f"Đã có {len(done)} chunk, còn {len(chunks)} chunk cần xử lý")
    #         for i, chunk in enumerate(chunks, start=1):
    #             try:
    #                 graph = extract_graph(chunk)
    #                 save_chunk(session, chunk, graph)
    #             except Exception as exc:
    #                 failed += 1
    #                 print(f"[{i}/{len(chunks)}] LỖI: {exc}")
    #                 continue
    #             print(
    #                 f"[{i}/{len(chunks)}] "
    #                 f"{len(graph.entities)} entities, "
    #                 f"{len(graph.relationships)} relationships"
    #             )
    # finally:
    #     close_neo4j()
    # print(f"Knowledge graph stored in Neo4j. Chunk lỗi: {failed}")
    pass