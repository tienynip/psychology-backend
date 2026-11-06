
from typing import Iterator
from neo4j import Driver, GraphDatabase, Session
from app.core.config import settings
_driver: Driver | None = None


def init_neo4j() -> None:
    global _driver
    if _driver is not None:
        return
    driver = GraphDatabase.driver(
        settings.NEO4J_URI,
        auth=(settings.NEO4J_USERNAME, settings.NEO4J_PASSWORD),
    )
    try:
        driver.verify_connectivity()
        _driver = driver
    except Exception:
        driver.close()
        raise


def close_neo4j() -> None:
    global _driver
    if _driver is not None:
        _driver.close()
        _driver = None


def get_driver() -> Driver:
    if _driver is None:
        raise RuntimeError("Neo4j chưa được khởi tạo (init_neo4j chưa chạy).")
    return _driver


def get_neo4j() -> Iterator[Session]:
    with get_driver().session(database=settings.NEO4J_DATABASE) as session:
        yield session


SCHEMA_STATEMENTS = [
    "CREATE CONSTRAINT entity_key IF NOT EXISTS "
    "FOR (e:Entity) REQUIRE (e.dataset_id, e.name) IS UNIQUE",

    "CREATE CONSTRAINT chunk_key IF NOT EXISTS "
    "FOR (c:Chunk) REQUIRE (c.dataset_id, c.chunk_id) IS UNIQUE",

    "CREATE CONSTRAINT source_key IF NOT EXISTS "
    "FOR (s:Source) REQUIRE (s.dataset_id, s.name) IS UNIQUE",

    "CREATE FULLTEXT INDEX entity_name_ft IF NOT EXISTS "
    "FOR (e:Entity) ON EACH [e.name, e.aliases]",

    "CREATE FULLTEXT INDEX chunk_text_ft IF NOT EXISTS "
    "FOR (c:Chunk) ON EACH [c.text, c.title]",
]


def ensure_schema() -> None:
    with get_driver().session(database=settings.NEO4J_DATABASE) as session:
        for stmt in SCHEMA_STATEMENTS:
            session.run(stmt).consume()
