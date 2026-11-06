from app.core.config import settings
from app.db.neo4j import close_neo4j, ensure_schema, get_driver, init_neo4j


def main() -> None:
    init_neo4j()
    try:
        ensure_schema()
        with get_driver().session(database=settings.NEO4J_DATABASE) as s:
            r = s.run("RETURN 1 AS ok")
            ok = r.single()["ok"]
            r = s.run(
                "MATCH (n {dataset_id: $d}) RETURN count(n) AS n",
                d=settings.GRAPHRAG_DATASET_ID,
            )
            n = r.single()["n"]
            r = s.run("SHOW INDEXES YIELD name RETURN collect(name) AS names")
            idx = r.single()["names"]

        print("Kết nối OK:", ok == 1)
        print(f"Số node của dataset '{settings.GRAPHRAG_DATASET_ID}':", n)
        print("Index/constraint hiện có:", sorted(idx))
    finally:
        close_neo4j()

if __name__ == "__main__":
    main()