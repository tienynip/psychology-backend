import pandas as pd
from app.core.config import settings
from app.db.neo4j import init_neo4j, close_neo4j, get_driver

DATASET_ID = settings.GRAPHRAG_DATASET_ID
NEO4J_DATABASE = settings.NEO4J_DATABASE


def inspect_graph():
    init_neo4j()
    driver = get_driver()
    try:
        with driver.session(database=NEO4J_DATABASE) as session:
            graph_rows = [record.data() for record in session.run(
                """
                MATCH (a:Entity {dataset_id: $dataset_id})-[r:RELATED]->(b:Entity {dataset_id: $dataset_id})
                RETURN a.name AS source, r.type AS relationship, b.name AS target,
                       r.evidence AS evidence, r.chunk_id AS chunk_id
                ORDER BY source, relationship, target
                """,
                dataset_id=DATASET_ID,
            )]
        edges_df = pd.DataFrame(graph_rows)

        print(f"{len(edges_df)} graph edges")
        print(edges_df)
    finally:
        close_neo4j()

if __name__ == "__main__":
    inspect_graph()