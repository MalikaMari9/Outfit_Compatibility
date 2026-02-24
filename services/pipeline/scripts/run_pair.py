from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from outfit_pipeline.engine import OutfitCompatibilityPipeline


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Pair outfit compatibility calculator (top + bottom).")
    p.add_argument("--top-image", required=True, help="Path to top clothing image")
    p.add_argument("--bottom-image", required=True, help="Path to bottom clothing image")
    p.add_argument(
        "--config",
        default=str(ROOT / "configs" / "pipeline_config.json"),
        help="Path to pipeline config JSON",
    )
    p.add_argument(
        "--json-out",
        default="",
        help="Optional JSON output path",
    )
    p.add_argument(
        "--public-output",
        action="store_true",
        help="Redact local filesystem paths in output payload",
    )
    p.add_argument(
        "--bg-method",
        default="",
        choices=["", "none", "rembg", "u2net", "u2netp", "isnet", "segformer"],
        help="Optional foreground method override",
    )
    p.add_argument(
        "--defer-llm",
        action="store_true",
        help="Skip Ollama explanation during this call.",
    )
    return p.parse_args()


def main() -> None:
    args = parse_args()
    pipe = OutfitCompatibilityPipeline(config_path=args.config)
    if args.bg_method:
        pipe.set_foreground_method(args.bg_method)
    result = pipe.score_pair(
        top_image=args.top_image,
        bottom_image=args.bottom_image,
        include_llm=not args.defer_llm,
    )
    payload = result.to_public_dict() if args.public_output else result.to_dict()

    print(json.dumps(payload, indent=2))
    if args.json_out:
        out_path = Path(args.json_out)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        print(f"\nSaved: {out_path}")


if __name__ == "__main__":
    main()
