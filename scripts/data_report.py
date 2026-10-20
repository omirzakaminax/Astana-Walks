"""Write the data-quality and naming audit for data/pois.json (or another file).

Usage (PowerShell, from the project folder):
    .venv\\Scripts\\python scripts\\data_report.py
    .venv\\Scripts\\python scripts\\data_report.py --data tests\\e2e\\e2e_pois.json --out data\\reports\\fixture
Writes <out>/data_quality.md and <out>/data_quality.json (default out: data/reports). Read-only.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from walks import config  # noqa: E402
from walks.data import DatasetError, load_dataset  # noqa: E402
from walks.report import data_quality, naming_audit, to_markdown  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", type=Path, default=config.DATA_PATH)
    ap.add_argument("--out", type=Path, default=config.PROJECT_ROOT / "data" / "reports")
    a = ap.parse_args()
    try:
        ds = load_dataset(a.data)
    except DatasetError as exc:
        print(f"Cannot load the dataset: {exc}")
        return 1
    dq, na = data_quality(ds), naming_audit(ds)
    a.out.mkdir(parents=True, exist_ok=True)
    (a.out / "data_quality.json").write_text(json.dumps({"data_quality": dq, "naming": na}, ensure_ascii=False, indent=1),
                                            encoding="utf-8")
    (a.out / "data_quality.md").write_text(to_markdown(dq, na, str(a.data)), encoding="utf-8")
    print(f"{dq['places']} places{' (SYNTHETIC)' if dq['synthetic'] else ''}; English names: "
          f"{na['display_name_source_by_language']['en']}; legacy names demoted: {na['records_with_legacy_unverified_names']}")
    print(f"Written: {a.out / 'data_quality.md'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
