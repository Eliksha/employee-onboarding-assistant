from backend.services import ingest, retriever


def test_build_and_search(env):
    n = ingest.build_index()
    assert n > 40
    hits = retriever.search("How many casual leaves do I get?", 4)
    assert len(hits) == 4
    assert any("Casual Leave" in h["section"] or "casual leaves" in h["section"].lower() for h in hits[:2])
    assert hits[0]["score"] >= hits[-1]["score"]
