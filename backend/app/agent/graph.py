from langgraph.graph import END, START, StateGraph

from app.agent.deps import AgentDeps
from app.agent.nodes import build_nodes
from app.agent.state import AgentState


def build_graph(deps: AgentDeps):
    """plan -> retrieve -> grade -(insufficient)-> retrieve ... -> compute -> synthesize -> verify."""
    nodes = build_nodes(deps)
    cfg = deps.config
    g = StateGraph(AgentState)
    for name, fn in nodes.items():
        g.add_node(name, fn)

    g.add_edge(START, "plan")
    g.add_conditional_edges(
        "plan",
        lambda s: "finalize" if s.get("out_of_scope") else "retrieve",
        {"finalize": "finalize", "retrieve": "retrieve"},
    )
    g.add_edge("retrieve", "grade")
    g.add_conditional_edges(
        "grade",
        lambda s: "compute" if s["sufficient"] or s["rounds"] >= cfg.max_rounds else "retrieve",
        {"compute": "compute", "retrieve": "retrieve"},
    )
    g.add_edge("compute", "synthesize")
    g.add_edge("synthesize", "verify")
    g.add_conditional_edges(
        "verify",
        lambda s: (
            "finalize"
            if s["grounded"] or s["synth_attempts"] >= cfg.max_synth_attempts
            else "synthesize"
        ),
        {"finalize": "finalize", "synthesize": "synthesize"},
    )
    g.add_edge("finalize", END)
    return g.compile()
