from openai import OpenAI
from pydantic import BaseModel, ConfigDict, Field
from app.core.config import settings
from app.db.neo4j import get_driver
 
DATASET_ID = settings.GRAPHRAG_DATASET_ID
NEO4J_DATABASE = settings.NEO4J_DATABASE
OPENAI_MODEL = settings.OPENAI_MODEL
client = OpenAI(api_key=settings.OPENAI_API_KEY)

class LinkedEntities(BaseModel):
    model_config = ConfigDict(extra="forbid")
    entity_names: list[str] = Field(description="Zero or more exact names copied from the catalog")
    
def first_parsed(response) -> LinkedEntities:
    parsed = response.output_parsed
    if parsed is None:
        raise RuntimeError("OpenAI response did not contain parsed structured output")
    return parsed

def get_entity_catalog() -> list[str]:
    with get_driver().session(database=NEO4J_DATABASE) as session:
        return [record["name"] for record in session.run(
            "MATCH (e:Entity {dataset_id: $dataset_id}) RETURN e.name AS name ORDER BY name",
            dataset_id=DATASET_ID,
        )]

def link_question_entities(question: str) -> list[str]:
    catalog = get_entity_catalog()
    response = client.responses.parse(
        model=OPENAI_MODEL,
        input=[
                {"role": "system", "content": "Select every catalog entity needed to answer the question. Copy exact names only; never invent names."},
                {"role": "user", "content": f"Catalog:\n- " + "\n- ".join(catalog) + f"\n\nQuestion: {question}"},
        ],
        text_format=LinkedEntities,
    )
    selected = first_parsed(response).entity_names
    return [name for name in selected if name in catalog]

def retrieve_graph_context(question: str, max_facts: int = 30, max_chunks: int = 5) -> dict:
    seeds = link_question_entities(question)
    if not seeds:
        return {"seeds": [], "facts": [], "chunks": [], "context": "No matching graph entities."}
    with get_driver().session(database=NEO4J_DATABASE) as session:
        facts = [record.data() for record in session.run(
            """
                UNWIND $seeds AS seed
                MATCH (e:Entity {dataset_id: $dataset_id, name: seed})
                MATCH path=(e)-[:RELATED*1..3]-(other:Entity {dataset_id: $dataset_id})
                
                UNWIND relationships(path) AS r WITH DISTINCT r
                RETURN startNode(r).name AS source, r.type AS relationship, endNode(r).name AS target, r.evidence AS evidence, r.chunk_id AS chunk_id
                LIMIT $limit
            """,
            dataset_id=DATASET_ID,
            seeds=seeds,
            limit=max_facts,
        )]
        chunk_ids = list(dict.fromkeys(fact["chunk_id"] for fact in facts if fact.get("chunk_id")))[:max_chunks]
        source_chunks = [record.data() for record in session.run(
            """
                UNWIND $chunk_ids AS chunk_id
                MATCH (c:Chunk {dataset_id: $dataset_id, chunk_id: chunk_id})
                RETURN c.chunk_id AS chunk_id, c.title AS title, c.text AS text
            """,
            dataset_id=DATASET_ID,
            chunk_ids=chunk_ids,
        )]
    fact_lines = [f"- {f['source']} --{f['relationship']}--> {f['target']} | evidence: {f['evidence']} [{f['chunk_id'][:8]}]" for f in facts]
    chunk_lines = [f"[{c['chunk_id'][:8]}] {c['title']}: {c['text']}" for c in source_chunks]
    context = "GRAPH FACTS\n" + "\n".join(fact_lines) + "\n\nSOURCE CHUNKS\n" + "\n".join(chunk_lines)
    return {"seeds": seeds, "facts": facts, "chunks": source_chunks, "context": context}

def answer_with_graph_rag(question: str) -> tuple[str, dict]:
    retrieval = retrieve_graph_context(question)
    if not retrieval["facts"]:
        return "Tôi là một mô hình AI hỗ trợ tư vấn tâm lý, được thiết kế để cung cấp thông tin và hướng dẫn dựa trên kiến thức tâm lý học. Tôi không thể hỗ trợ yêu cầu này vì nó nằm ngoài phạm vi chuyên môn và chức năng của hệ thống.", retrieval
    response = client.responses.create(
        model=OPENAI_MODEL,
        input=[
            {
                "role": "system",
                "content": (
                    """
                    You are a psychological counseling AI. Respond empathetically using the provided GraphRAG materials.
                    ## 1. Knowledge
                    - Use only relevant graph facts and source documents.
                    - Never invent information, make unsupported assumptions, or diagnose users.
                    - Use multi-hop reasoning only when necessary.
                    - Acknowledge insufficient evidence.
                    - Never expose raw graph relationships or technical terms.
                    ## 2. Response
                    - Respond like ChatGPT: naturally, empathetically, conversationally, and flexibly according to the user's intent and context.
                    - Prioritize answering the user's actual needs rather than following rigid response structures.
                    - Use simple, natural Vietnamese. Avoid unnecessary English and academic terminology.
                    - Explain one concept through the user's actual experience, not theoretical definitions.
                    - Describe possible experiences, not confirmed diagnoses.
                    - Only recommend exercises or techniques supported by retrieved context.
                    - Ask one short, relevant follow-up question when more information is needed.
                    - Adjust the length and structure of your replies to suit each conversation, up to a maximum of 6 lines.
                    - Always express concepts, techniques, and entity names in natural Vietnamese. Never output their original English names unless explicitly requested by the user.
                    - Translate worksheet and technique names into natural Vietnamese unless the user asks for their original names.
                    ## 3. Safety
                    - If suicidal intent is detected, prioritize immediate safety and encourage contacting trusted people and emergency support.
                    - Never use generic motivational statements.
                    ## 4. Evidence
                    - When asked for evidence, cite the supported concept and source book using:
                    "Dựa vào phần '[Concept]' ở cuốn sách '[Book title]'."
                    - Never fabricate concepts, sources, or citations.
                    ## 5. Language
                    - Reply in the user's language.
                    """
                ),
            },
            {
                "role": "user",
                "content": f"Question: {question}\n\n{retrieval['context']}"
            }
        ]
    )
    return response.output_text, retrieval