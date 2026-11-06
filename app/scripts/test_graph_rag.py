import sys
from app.db.neo4j import close_neo4j, init_neo4j
from app.services.retrieval import answer_with_graph_rag

question = sys.argv[1] if len(sys.argv) > 1 else "Tôi chơi liên quân thua bị cọc tức làm sao để bớt giận"

init_neo4j()
try:
    answer, retrieval = answer_with_graph_rag(question)
    # answer = answer_with_graph_rag(question)
    # print("Seed entities:", retrieval["seeds"])
    # print("Số fact:", len(retrieval["facts"]), "| Số đoạn sách:", len(retrieval["chunks"]))
    print("\n===== TRẢ LỜI =====")
    print(answer)
finally:
    close_neo4j()