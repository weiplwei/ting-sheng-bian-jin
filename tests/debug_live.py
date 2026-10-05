"""Debug live vs offline features on the same clip."""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src import wavio
from src.dsp import feature_from_audio, extract_event
from src.live import LiveConfig, LiveEngine
from src.matcher import Matcher, match_score, split_feats

ROOT = Path(__file__).resolve().parents[1]
path = ROOT / "data/library/_raw/items/537b0217/samples/0001.wav"

x, sr = wavio.read_wav(path)
print("file", path, "len", len(x) / sr)

items = __import__("json").loads((ROOT / "data/library/items.json").read_text(encoding="utf-8"))
m = Matcher()
m.build_from_items(items, wavio.read_wav)

off_feat = feature_from_audio(x, sr)
print("\nOFFLINE rank:")
for r in m.rank(off_feat)[:4]:
    print(f"  {r.name[:18]:18s} {r.score:.3f} {r.reason}")

# simulate live
engine = LiveEngine(m, LiveConfig(sr=sr))
# feed in 20ms hops
hop = int(sr * 0.02)
for i in range(0, len(x), hop):
    block = x[i : i + hop]
    if block.size < hop:
        block = np.pad(block, (0, hop - block.size))
    results = engine.feed(block)
    for r in results:
        print(f"\nLIVE event score top: {r.name} {r.score:.3f} reason={r.reason}")
        for rr in m.rank(feature_from_audio(engine.ring[-int(0.45*sr):], sr))[:4]:
            print(f"  via-ring {rr.name[:18]:18s} {rr.score:.3f}")

# compare features
ev = extract_event(x, sr)
print("\nextract_event", ev, "dur", (ev[1]-ev[0])/sr)
chunk = engine.ring[-int(0.45 * sr) :]
live_feat = feature_from_audio(chunk, sr)
print("offline feat shape", off_feat.shape, "live feat shape", live_feat.shape)
lf, ls = split_feats(live_feat)
tf, ts = split_feats(off_feat)
print("match_score(live, offline_tpl_self)", match_score(live_feat, off_feat))
print("shapes frames", lf.shape, tf.shape)
# best template scores for live feat
print("\nLIVE-feat vs each item:")
for r in m.rank(live_feat)[:6]:
    print(f"  {r.name[:18]:18s} {r.score:.3f} Δ={r.margin:.3f} {r.reason}")
