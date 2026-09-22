from typing import TypedDict

from langgraph.graph import StateGraph, START, END

from .embeddings import embed_query
from .db import search_chunks
from .llm import answer_question


class CodeState(TypedDict):
    question: str
    answer: str
    sources: list[dict]


def retrieve(state):
    embedding = embed_query(state["question"])

    sources = search_chunks(
        embedding,
        limit=6,
    )

    return {
        "sources": sources
    }


def analyze(state):
    answer = answer_question(
        state["question"],
        state["sources"],
    )

    return {
        "answer": answer
    }


graph = StateGraph(CodeState)

graph.add_node("retrieve", retrieve)
graph.add_node("analyze", analyze)

graph.add_edge(START, "retrieve")
graph.add_edge("retrieve", "analyze")
graph.add_edge("analyze", END)

code_graph = graph.compile()