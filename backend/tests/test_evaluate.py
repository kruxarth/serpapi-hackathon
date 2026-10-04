from reviewring.evaluate import classify_losses, inject, simulate, synthetic_bases, wilson


def test_wilson_interval():
    lo, hi = wilson(0, 30)
    assert lo == 0.0 and 0.10 < hi < 0.12
    lo, hi = wilson(15, 30)
    assert lo < 0.5 < hi


def test_planted_ring_is_caught_and_reproducible():
    base = synthetic_bases(1)[0]
    inp, members = inject(base.input, k=8, m=4, camouflage="low", timing="same week", seed=1)
    sim = simulate(inp, k1=8, b=2, k2=15)
    losses = classify_losses(sim, members)
    assert losses["caught"] >= 6
    assert sum(losses.values()) == 8
    again = classify_losses(
        simulate(inject(base.input, k=8, m=4, camouflage="low", timing="same week", seed=1)[0], k1=8, b=2, k2=15),
        members,
    )
    assert again == losses
    assert base.input.target_reviews != inp.target_reviews  # the base itself is untouched


def test_clean_base_stops_early_and_flags_nothing():
    base = synthetic_bases(1)[0]
    sim = simulate(base.input, k1=8, b=2, k2=15)
    assert sim.early_stop and sim.report["level"]["level"] == "Low"
    assert sim.searches == 5 + 10


def test_losses_when_budget_too_small():
    base = synthetic_bases(1)[0]
    inp, members = inject(base.input, k=12, m=4, camouflage="none", timing="same week", seed=3)
    sim = simulate(inp, k1=8, b=2, k2=15, cap_histories=4, no_early_stop=True)
    losses = classify_losses(sim, members)
    assert losses["not_chosen"] >= 8
