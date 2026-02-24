from __future__ import annotations

import argparse
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Launch Tkinter mock GUI for outfit compatibility pipeline.")
    p.add_argument(
        "--config",
        default=str(ROOT / "configs" / "pipeline_config.json"),
        help="Path to pipeline config JSON",
    )
    p.add_argument(
        "--bg-method",
        default="",
        choices=["", "none", "rembg", "u2net", "u2netp", "isnet", "segformer"],
        help="Optional foreground method override",
    )
    return p.parse_args()


def main() -> None:
    args = parse_args()
    from outfit_pipeline.engine import OutfitCompatibilityPipeline
    from outfit_pipeline.gui import PipelineGui

    pipe = OutfitCompatibilityPipeline(config_path=args.config)
    if args.bg_method:
        pipe.set_foreground_method(args.bg_method)
    app = PipelineGui(pipeline=pipe)
    app.mainloop()


if __name__ == "__main__":
    main()
