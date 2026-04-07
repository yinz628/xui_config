import argparse
import json
from pathlib import Path

from xui_port_pool_generator.pipeline import run_pipeline


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate Xray config from mapping.yaml and subscription sources."
    )
    parser.add_argument("--mapping", default="mapping.yaml")
    parser.add_argument("--template", default="config.json")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    result = run_pipeline(
        mapping_path=Path(args.mapping),
        template_path=Path(args.template),
        workdir=Path.cwd(),
    )
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
