"""SoundRadar-X CLI.

Commands:
  match  --wav FILE [--top N]     offline match one file
  live   [--device NAME] [--seconds N] [--overlay] [--wav FILE]
  validate                        run library self/noise tests
  items                           list library items
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from src import wavio  # noqa: E402
from src.dsp import feature_from_audio  # noqa: E402
from src.library import LIB_PATH, load_items  # noqa: E402
from src.live import LiveConfig, LiveEngine  # noqa: E402
from src.matcher import Matcher  # noqa: E402

def build_matcher(language: str = "zh") -> Matcher:
    from src.calibrate import build_calibrated_matcher

    m, _meta = build_calibrated_matcher(language=language)
    return m


def cmd_items(args: argparse.Namespace) -> None:
    items = load_items(args.lang)
    print(f"{len(items)} items in {LIB_PATH}")
    for it in items:
        tags = ",".join(it.get("tags") or [])
        print(
            f"  {it['id']}  {it['name'][:24]:24s}  "
            f"thr={it.get('threshold', 0.75):.2f}  "
            f"samples={len(it.get('samples', []))}  {tags}"
        )


def cmd_match(args: argparse.Namespace) -> None:
    m = build_matcher(args.lang)
    x, sr = wavio.read_wav(args.wav)
    feat = feature_from_audio(x, sr)
    rank = m.rank(feat, snr_db=args.snr)
    print(f"file: {args.wav}")
    for i, r in enumerate(rank[: args.top]):
        mark = "★" if r.accepted else " "
        print(
            f" {mark} {i+1:2d}. {r.name[:22]:22s}  score={r.score:.3f}  "
            f"Δ={r.margin:.3f}  thr={r.effective_threshold:.2f}  {r.reason}"
        )


def cmd_live(args: argparse.Namespace) -> None:
    from src.capture import WavSource, open_source

    items = load_items(args.lang)
    m = build_matcher(args.lang)
    cfg = LiveConfig(sr=args.sr)
    engine = LiveEngine(m, cfg)

    overlay = None
    beep = False
    find_icon = None
    beep_hit = None
    if args.overlay:
        from src.overlay import Overlay, OverlayConfig, beep_hit as _beep, find_icon_for_name

        find_icon = find_icon_for_name
        beep_hit = _beep
        overlay = Overlay(
            OverlayConfig(
                x=args.x if args.x is not None else 40,
                y=args.y if args.y is not None else 200,
                width=340,
                duration_ms=args.hold_ms,
                max_simultaneous=3,
                language=args.lang,
            )
        )
        overlay.start()
        beep = not args.no_beep
        if args.lang == "en":
            print("[HUD] Hidden until a match; cards fade after about 2.8 seconds.")
            print("[HUD] Use borderless windowed mode; exclusive fullscreen may cover the overlay.")
        else:
            print("[HUD] 平时隐藏，仅命中时弹卡片（约 2.8s 后消失）")
            print("[HUD] ⚠ 游戏请用「无边框窗口」，独占全屏会盖住悬浮窗")
        if not overlay.ok:
            print("[HUD] 警告：悬浮窗未启动", file=sys.stderr)

    kind = "wav" if args.wav else "loopback"
    print(f"[live] source={kind} sr={args.sr} items={len(m.templates)}")
    if args.lang == "en":
        print("[live] A card appears on each match (icon, item name, and score bar)." + (" + alert sound" if beep else ""))
    else:
        print("[live] 命中时：悬浮窗弹卡片（图标+名称+分数条）" + (" + 提示音" if beep else ""))
    try:
        source = open_source(kind=kind, path=args.wav, device=args.device, sr=args.sr)
    except Exception as e:
        print(f"[live] cannot open source: {e}", file=sys.stderr)
        print("[live] hint: use .venv\\Scripts\\python.exe and pip install soundcard", file=sys.stderr)
        raise SystemExit(2)

    block_frames = int(args.sr * 0.02)
    is_wav = isinstance(source, WavSource)
    t_end = None
    if not is_wav and args.seconds:
        t_end = time.time() + args.seconds

    import numpy as np

    def report_hit(r, snr: float | None = None) -> None:
        """One path for terminal + HUD + beep so they cannot desync."""
        snr_s = f"  snr={snr:.1f}dB" if snr is not None else ""
        print(
            f"★[HIT]★  {r.name}    score={r.score:.3f}  "
            f"margin={r.margin:.3f}  thr={r.effective_threshold:.2f}{snr_s}",
            flush=True,
        )
        if overlay is not None:
            try:
                icon = find_icon(items, r.item_id, r.name) if find_icon else None
                item = next((it for it in items if it.get("id") == r.item_id), {})
            except Exception:
                icon = None
                item = {}
            try:
                overlay.show_hit(
                    r.name,
                    r.score,
                    r.margin,
                    item_id=r.item_id,
                    icon_path=icon,
                    candidate_hints=item.get("candidateHints"),
                    unique=bool(item.get("unique")),
                )
            except Exception as e:
                print(f"[hud] show_hit failed: {e}", file=sys.stderr)
        if beep and beep_hit:
            try:
                beep_hit()
            except Exception:
                pass

    n_blocks = 0
    try:
        while True:
            if t_end and time.time() >= t_end:
                break
            block = source.read(block_frames)
            results = engine.feed(block)
            n_blocks += 1
            for r in results:
                if r.accepted:
                    report_hit(r, engine.current_snr_db())
                elif args.verbose:
                    print(
                        f"    .  {r.name[:18]:18s}  score={r.score:.3f}  "
                        f"Δ={r.margin:.3f}  {r.reason}",
                        flush=True,
                    )
            if is_wav and getattr(source, "finished", False):
                results = engine.feed(np.zeros(block_frames, dtype=np.float32))
                for r in results:
                    if r.accepted:
                        report_hit(r)
                break
            if n_blocks % 500 == 0:
                print(
                    f"[stat] blocks={n_blocks} events={engine.events_seen} "
                    f"hits={len(engine.hits)} snr~{engine.current_snr_db():.1f}dB",
                    flush=True,
                )
    except KeyboardInterrupt:
        print("\n[live] stopped")
    finally:
        source.close()
        if overlay:
            overlay.stop()
    print(f"[done] blocks={n_blocks} events={engine.events_seen} hits={len(engine.hits)}")


def cmd_hud() -> None:
    """Keep HUD alive 15s with sample cards — verify it stays on top."""
    import time

    from src.overlay import Overlay, OverlayConfig, find_icon_for_name

    items = load_items()
    ov = Overlay(OverlayConfig(x=40, y=120, duration_ms=6000, max_simultaneous=3))
    ov.start()
    print("[hud] 15 秒自检：左侧应始终有「● SR-HUD 在线」绿条")
    print("[hud] 若游戏里看不到：把显示模式改成「无边框窗口」")
    for name, sid, score, margin in [
        ("卡莫纳之星/宝石项链", "537b0217", 0.96, 0.40),
        ("花瓶", "388e122c", 1.00, 0.33),
        ("古董茶壶", "56dfb35b", 0.93, 0.28),
    ]:
        icon = find_icon_for_name(items, sid, name)
        ov.show_hit(name, score, margin, item_id=sid, icon_path=icon)
        time.sleep(0.5)
    time.sleep(12)
    ov.stop()
    print("[hud] done")


def cmd_calibrate(_args=None) -> None:
    from src.calibrate import build_calibrated_matcher, print_report

    _m, meta = build_calibrated_matcher()
    print_report(meta)


def cmd_demo() -> None:
    """Show the game hit HUD for a few seconds so you can place/check it."""
    import time

    from src.overlay import Overlay, OverlayConfig, find_icon_for_name

    items = load_items()
    ov = Overlay(OverlayConfig(x=40, y=200, width=340, duration_ms=5000, max_simultaneous=3))
    ov.start()
    print("[demo] 命中悬浮窗预览：屏幕左侧，约 6 秒后自动退出")
    print("[demo] 全屏游戏请用「无边框窗口」，独占全屏会盖住悬浮窗")
    samples = [
        ("卡莫纳之星/宝石项链", "537b0217", 0.92, 0.15),
        ("花瓶", "388e122c", 1.00, 0.31),
        ("古董茶壶", "56dfb35b", 0.88, 0.20),
    ]
    for name, sid, score, margin in samples:
        icon = find_icon_for_name(items, sid, name)
        ov.show_hit(name, score, margin, item_id=sid, icon_path=icon)
        time.sleep(0.35)
    time.sleep(5.5)
    ov.stop()
    print("[demo] done")


def main() -> None:
    p = argparse.ArgumentParser(prog="soundradar-x", description="Noise-tolerant sound matcher")
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("items", help="list library items")
    s.add_argument("--lang", choices=("zh", "en"), default="zh", help="display language")
    s.set_defaults(func=cmd_items)

    s = sub.add_parser("match", help="offline match a wav")
    s.add_argument("--wav", required=True)
    s.add_argument("--top", type=int, default=5)
    s.add_argument("--snr", type=float, default=None, help="estimated SNR dB for adaptive thr")
    s.add_argument("--lang", choices=("zh", "en"), default="zh", help="display language")
    s.set_defaults(func=cmd_match)

    s = sub.add_parser("live", help="real-time match")
    s.add_argument("--wav", help="offline wav instead of loopback")
    s.add_argument("--device", help="speaker name substring for loopback")
    s.add_argument("--seconds", type=float, default=None)
    s.add_argument("--sr", type=int, default=48000)
    s.add_argument("--overlay", action="store_true")
    s.add_argument("--no-beep", action="store_true")
    s.add_argument("--x", type=int, default=None, help="overlay left px (default 40)")
    s.add_argument("--y", type=int, default=None, help="overlay top px (default 200)")
    s.add_argument("--hold-ms", type=int, default=2800, help="hit card hold time ms")
    s.add_argument("--verbose", "-v", action="store_true", help="also print near-miss events")
    s.add_argument("--lang", choices=("zh", "en"), default="zh", help="display language")
    s.set_defaults(func=cmd_live)

    s = sub.add_parser("calibrate", help="show auto-calibrated thresholds & confusions")
    s.set_defaults(func=cmd_calibrate)

    s = sub.add_parser("hud", help="show HUD strip + test cards for 15s (check visibility)")
    s.set_defaults(func=lambda a: cmd_hud())

    s = sub.add_parser("demo", help="preview hit overlay HUD (no audio)")
    s.set_defaults(func=lambda a: cmd_demo())

    s = sub.add_parser("validate", help="run built-in library tests")
    args = p.parse_args()
    if args.cmd == "validate":
        import runpy

        runpy.run_path(str(ROOT / "tests" / "validate_matcher.py"), run_name="__main__")
        return
    args.func(args)


if __name__ == "__main__":
    main()
