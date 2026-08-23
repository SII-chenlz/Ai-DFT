"""Command-line interface for the DFT functional advisor."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from functional_advisor.advisor import FunctionalAdvisor, result_to_dict
from functional_advisor.llm import DeepSeekClient


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="dft-advisor",
        description="Recommend a DFT functional and generate VASP/QE input cards from a natural-language request.",
    )
    parser.add_argument("request", nargs="?", help="Natural-language system/task description.")
    parser.add_argument("--request-file", help="Read the request from a UTF-8 text file.")
    parser.add_argument("--code", choices=["vasp", "qe"], default="vasp", help="Target DFT code.")
    parser.add_argument("--structure-file", help="Path to POSCAR (VASP) or existing structure to embed.")
    parser.add_argument("--out-dir", default="output", help="Directory in which to write input files.")
    parser.add_argument("--json", action="store_true", help="Also print a JSON summary.")
    parser.add_argument("--no-llm", action="store_true", help="Force rule-based recommendation.")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    if args.request:
        request = args.request
    elif args.request_file:
        request = Path(args.request_file).read_text(encoding="utf-8")
    else:
        print("Error: provide a request or --request-file.", file=sys.stderr)
        return 2

    if args.request_file and not request.strip():
        print("Error: request file is empty.", file=sys.stderr)
        return 2

    client = DeepSeekClient()
    advisor = FunctionalAdvisor(client, use_llm=False if args.no_llm else None)
    result = advisor.recommend(
        request,
        code=args.code,
        structure_file=args.structure_file,
    )

    print(_format_result(result))
    if args.json:
        print("\n--- JSON ---")
        print(json.dumps(result_to_dict(result), indent=2, ensure_ascii=False))

    if args.out_dir:
        _write_inputs(result.inputs, Path(args.out_dir))
    return 0


def _format_result(result) -> str:
    rec = result.recommendation
    lines = [
        "Recommendation",
        f"  functional: {rec.functional}"
        + (f" + {rec.dispersion}" if rec.dispersion else ""),
    ]
    if rec.hubbard_u:
        lines.append(f"  Hubbard U: {rec.hubbard_u}")
    lines.extend(
        [
            f"  rationale: {rec.rationale}",
            f"  code: {result.job_spec.code}",
            f"  task: {result.job_spec.task}",
        ]
    )
    if rec.caveats:
        lines.append("  caveats:")
        lines.extend(f"    - {item}" for item in rec.caveats)
    for message in result.messages:
        lines.append(f"  info: {message}")
    return "\n".join(lines)


def _write_inputs(inputs: dict[str, str], out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    for filename, content in inputs.items():
        path = out_dir / filename
        path.write_text(content, encoding="utf-8")
        print(f"Wrote {path}")


if __name__ == "__main__":
    raise SystemExit(main())
