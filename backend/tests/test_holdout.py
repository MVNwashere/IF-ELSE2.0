from collections import Counter

from synth.holdout import AS_OF, FIRST_ID, GOALS, holdout_customers


def _sig(data):
    return [(c.id, c.ground_truth["events"], len(t), round(sum(x.amount for x in t), 2), b) for c, t, b in data]


def test_holdout_is_deterministic():
    assert _sig(holdout_customers()) == _sig(holdout_customers())


def test_holdout_shape():
    data = holdout_customers()
    assert 250 <= len(data) <= 350
    ids = [c.id for c, _, _ in data]
    assert len(set(ids)) == len(ids) and min(ids) >= FIRST_ID
    tx_ids = [t.id for _, txs, _ in data for t in txs]
    assert len(set(tx_ids)) == len(tx_ids)
    pos, near = Counter(), Counter()
    for c, txs, _ in data:
        assert c.ground_truth["holdout"] is True
        assert all(t.date <= AS_OF for t in txs), c.id
        assert all(t.customer_id == c.id for t in txs)
        for e in c.ground_truth["events"]:
            kind, goal = e["type"].split(":", 1)
            assert goal in GOALS
            (pos if kind == "goal" else near)[goal] += 1
    assert all(pos[g] >= 5 for g in GOALS), pos
    share = sum(1 for c, _, _ in data if any(e["type"].startswith("near_miss:") for e in c.ground_truth["events"]))
    assert 0.3 <= share / len(data) <= 0.5
