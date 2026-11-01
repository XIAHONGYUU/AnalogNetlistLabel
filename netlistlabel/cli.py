"""Command-line interface for NetlistLabel."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import __version__
from .compare import compare_files, write_compare
from .evaluate import evaluate_files, write_evaluation
from .infer import annotate
from .review import build_review_packet, load_annotation
from .overlay import overlay_filename, write_annotated_sp
from .report import write_json, write_markdown
from .spice import parse_file
from .taxonomy import ROLES


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="netlistlabel",
        description="Evidence-backed semantic annotation for unknown analog SPICE netlists.",
    )
    parser.add_argument("--version", action="version", version=f"netlistlabel {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    analyze = sub.add_parser("analyze", help="annotate one netlist and write JSON/Markdown/overlay")
    analyze.add_argument("netlist", help="input SPICE netlist (read-only)")
    analyze.add_argument("--out", "-o", default="", help="output directory (default: out/<design>)")
    analyze.add_argument("--name", default=None, help="override the design name")
    analyze.add_argument("--quiet", action="store_true", help="only print the output directory")

    compare = sub.add_parser("compare", help="compare an inferred annotation with a reference annotation")
    compare.add_argument("raw", help="raw, generic-name netlist")
    compare.add_argument("reference", help="annotated reference netlist (role=...)")
    compare.add_argument("--out", "-o", default="", help="output directory (default: out/compare)")

    review = sub.add_parser("review", help="build a human review packet and gold.json skeleton")
    review.add_argument("annotation", help="annotation.json produced by analyze")
    review.add_argument("--out", "-o", default="", help="output directory (default: out/review/<design>)")
    review.add_argument("--devices", type=int, default=20, help="number of devices to sample")
    review.add_argument("--nets", type=int, default=12, help="number of nets to sample")
    review.add_argument("--ports", type=int, default=0, help="number of ports (0 = all)")
    review.add_argument("--seed", type=int, default=7)

    evaluate = sub.add_parser("evaluate", help="score an annotation against a human gold.json")
    evaluate.add_argument("prediction", help="annotation.json")
    evaluate.add_argument("gold", help="reviewed gold.json")
    evaluate.add_argument("--out", "-o", default="", help="output directory (default: out/eval/<design>)")

    roles = sub.add_parser("roles", help="print the role taxonomy and a2l mapping")
    roles.add_argument("--markdown", action="store_true", help="print a Markdown table")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        if args.command == "analyze":
            return _analyze(args)
        if args.command == "compare":
            return _compare(args)
        if args.command == "review":
            return _review(args)
        if args.command == "evaluate":
            return _evaluate(args)
        if args.command == "roles":
            return _roles(args)
    except FileNotFoundError as exc:
        print(f"netlistlabel: {exc}", file=sys.stderr)
        return 2
    except ValueError as exc:
        print(f"netlistlabel: {exc}", file=sys.stderr)
        return 2
    parser.print_help()
    return 1


def _analyze(args: argparse.Namespace) -> int:
    netlist = parse_file(args.netlist, name=args.name)
    annotation = annotate(netlist)
    out_dir = Path(args.out) if args.out else Path("out") / annotation.design["name"]
    out_dir.mkdir(parents=True, exist_ok=True)

    json_path = write_json(annotation, out_dir / "annotation.json")
    md_path = write_markdown(annotation, out_dir / "annotation.md")
    overlay_path = write_annotated_sp(netlist, annotation, out_dir / overlay_filename(annotation.design["name"]))

    if args.quiet:
        print(out_dir)
        return 0

    coverage = annotation.coverage
    print(f"NetlistLabel {__version__}")
    print(f"  design: {annotation.design['name']}")
    print(f"  devices: {coverage['devices_total']} ({coverage['mos_total']} MOS); ports: {coverage['ports_total']}; nets: {coverage['nets_total']}")
    print(
        "  port class coverage: {known}/{total} = {rate:.1%}; net class coverage: {nknown}/{ntotal} = {nrate:.1%}".format(
            known=coverage["ports_classified"],
            total=coverage["ports_total"],
            rate=coverage["port_class_coverage"],
            nknown=coverage["nets_class_known"],
            ntotal=coverage["nets_total"],
            nrate=coverage["net_class_coverage"],
        )
    )
    print(
        "  role coverage: {known}/{total} = {rate:.1%}; MOS {mos_known}/{mos_total} = {mos_rate:.1%}".format(
            known=coverage["roles_known"],
            total=coverage["devices_total"],
            rate=coverage["role_coverage"],
            mos_known=coverage["mos_roles_known"],
            mos_total=coverage["mos_total"],
            mos_rate=coverage["mos_role_coverage"],
        )
    )
    print(f"  matched devices: {coverage['matched_devices']} ({coverage['match_coverage']:.1%})")
    print(f"  review items: {coverage['review_items']}")
    print(f"  blocks: {', '.join(block.id for block in annotation.blocks) or 'none'}")
    print(f"  artifacts: {json_path}, {md_path}, {overlay_path}")
    return 0


def _compare(args: argparse.Namespace) -> int:
    _annotation, result = compare_files(args.raw, args.reference)
    out_dir = Path(args.out) if args.out else Path("out") / "compare"
    json_path, md_path = write_compare(result, out_dir)
    summary = result["summary"]
    print("NetlistLabel comparison")
    print(f"  compared devices: {summary['compared_devices']}")
    print(f"  exact role agreement: {summary['exact_role_agree']}/{summary['compared_devices']} = {summary['exact_role_rate']:.1%}")
    print(f"  a2l-role agreement: {summary['a2l_role_agree']}/{summary['compared_devices']} = {summary['a2l_role_rate']:.1%}")
    print(f"  partition pair agreement: {summary['partition_pair_agreement']:.1%}")
    print(f"  exact match groups: {summary['exact_match_groups']} (precision {summary['match_group_precision']:.1%}, recall {summary['match_group_recall']:.1%})")
    print(f"  artifacts: {json_path}, {md_path}")
    print("  note: the reference is not ground truth; disagreements need review.")
    return 0


def _review(args: argparse.Namespace) -> int:
    annotation = load_annotation(args.annotation)
    design = annotation.get("design", {}).get("name", "design")
    out_dir = Path(args.out) if args.out else Path("out") / "review" / design
    md_path, gold_path, csv_path = build_review_packet(
        annotation,
        out_dir,
        device_count=args.devices,
        net_count=args.nets,
        port_count=args.ports,
        seed=args.seed,
    )
    print("NetlistLabel review packet")
    print(f"  design: {design}")
    print(f"  packet: {md_path}")
    print(f"  gold:   {gold_path}")
    print(f"  csv:    {csv_path}")
    print("  next: edit review.csv (recommended) or gold.json, then run netlistlabel evaluate.")
    return 0


def _evaluate(args: argparse.Namespace) -> int:
    result = evaluate_files(args.prediction, args.gold)
    design = result.get("design", "design")
    out_dir = Path(args.out) if args.out else Path("out") / "eval" / design
    json_path, md_path = write_evaluation(result, out_dir)
    print("NetlistLabel evaluation")
    print(f"  design: {design}")
    print(f"  reviewed: {result.get('reviewed_total', 0)}")
    print(f"  device strict accuracy: {_pct(result.get('device_strict_accuracy'))}")
    print(f"  device lenient accuracy: {_pct(result.get('device_lenient_accuracy'))}")
    print(f"  net class accuracy: {_pct(result.get('net_class_accuracy'))}")
    print(f"  port direction accuracy: {_pct(result.get('port_direction_accuracy'))}")
    print(f"  artifacts: {json_path}, {md_path}")
    return 0


def _pct(value: object) -> str:
    if value is None:
        return "—"
    return f"{float(value):.1%}"


def _roles(args: argparse.Namespace) -> int:
    if args.markdown:
        print("| role | Chinese | English | a2l_role | description |")
        print("| --- | --- | --- | --- | --- |")
        for info in ROLES.values():
            print(f"| {info.id} | {info.zh} | {info.en} | {info.a2l_role or '—'} | {info.description} |")
    else:
        for info in ROLES.values():
            print(f"{info.id:16s} {info.zh:10s} a2l_role={info.a2l_role or '-'}")
    return 0