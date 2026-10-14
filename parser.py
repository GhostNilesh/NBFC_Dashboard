"""Parser for the compiled NBFC financial workbook.

The workbook is treated as a presentation model. Segment sheets contain merged
company headers, repeated year headers, metric labels on the left and values in
company-specific column blocks. The parser converts them into tidy records.

Run:
    python parser.py "Financials- NBFC updated.xlsx" --output nbfc_parsed.csv
"""
from __future__ import annotations

import argparse
import json
import math
import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Iterable, Optional

import pandas as pd
from openpyxl import load_workbook
from openpyxl.cell.cell import MergedCell
from openpyxl.utils import get_column_letter

YEAR_RE = re.compile(
    r"^(?:Q[1-4]\s*)?FY\s*[-']?\s*(?:19|20)?\d{2}(?:\s*\([A-Z]+\))?$|"
    r"^(?:19|20)\d{2}(?:\s*\([A-Z]+\))?$",
    re.I,
)
YEAR_SEARCH_RE = re.compile(r"(?:Q[1-4]\s*)?FY\s*[-']?\s*(?:19|20)?\d{2}|(?:19|20)\d{2}", re.I)

SECTION_NAMES = {
    "financials", "profitability", "capitalization", "capitalisation",
    "operational efficiency", "loan book performance", "return indicators",
    "spread", "asset quality", "provisioning", "liquidity", "gearing",
    "product mix", "aum mix", "borrowings", "key ratios", "ratios",
}
SKIP_LABELS = {"particulars", "rs in crores", "rs in crore", "in rs crores", "in crores"}


@dataclass(frozen=True)
class CompanyBlock:
    company: str
    header_row: int
    start_col: int
    end_col: int


@dataclass
class ParseIssue:
    sheet: str
    level: str
    message: str
    cell: str = ""


def clean_text(value: Any) -> str:
    if value is None:
        return ""
    text = str(value).replace("\n", " ").replace("\r", " ")
    return re.sub(r"\s+", " ", text).strip()


def canonical_year(value: Any) -> Optional[str]:
    text = clean_text(value)
    if not text or not YEAR_SEARCH_RE.search(text):
        return None
    text = text.upper().replace("AUD.", "").replace("AUD", "").strip()
    status = ""
    mstatus = re.search(r"\(([A-Z]+)\)", text)
    if mstatus:
        status = f" ({mstatus.group(1)})"
        text = re.sub(r"\s*\([A-Z]+\)\s*", "", text)
    q = ""
    mq = re.search(r"Q([1-4])", text)
    if mq:
        q = f"Q{mq.group(1)}"
    my = re.search(r"FY\s*[-']?\s*((?:19|20)?\d{2})", text)
    if not my:
        my = re.search(r"((?:19|20)\d{2})", text)
    if not my:
        return None
    y = my.group(1)
    if len(y) == 2:
        y = "20" + y
    return f"{q + ' ' if q else ''}FY{y[-2:]}{status}"


def is_year(value: Any) -> bool:
    text = clean_text(value)
    return bool(text and (YEAR_RE.match(text) or canonical_year(text)))


def normalize_segment(sheet_name: str, title: str) -> str:
    candidate = title or sheet_name
    candidate = re.sub(r"^NBFC\s*[-:]\s*", "", candidate, flags=re.I)
    return clean_text(candidate).title()


def is_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and not (
        isinstance(value, float) and math.isnan(value)
    )


def safe_cached_value(value: Any) -> Any:
    if isinstance(value, str):
        v = clean_text(value)
        if v.lower() in {"na", "n.a.", "n/a", "nm", "-", "--", "#div/0!", "#n/a", "#value!"}:
            return None
    return value


def find_segment_title(ws) -> str:
    for r in range(1, min(ws.max_row, 8) + 1):
        for c in range(1, min(ws.max_column, 12) + 1):
            v = clean_text(ws.cell(r, c).value)
            if v and "NBFC" in v.upper():
                return v
    return ws.title


def _year_density(ws, row: int, start_col: int, end_col: int) -> tuple[int, int]:
    vals = [ws.cell(row, c).value for c in range(start_col, end_col + 1)]
    nonempty = sum(clean_text(v) != "" for v in vals)
    years = sum(is_year(v) for v in vals)
    return years, nonempty


def detect_company_blocks(ws, issues: list[ParseIssue]) -> list[CompanyBlock]:
    """Detect merged company headers followed by year headings.

    Supports the segment sheets in the supplied workbook and also falls back to
    unmerged company labels when a contiguous run of year columns is present.
    """
    blocks: list[CompanyBlock] = []
    max_header_row = min(ws.max_row, 12)

    for merged in ws.merged_cells.ranges:
        if merged.min_row != merged.max_row or merged.min_row > max_header_row:
            continue
        name = clean_text(ws.cell(merged.min_row, merged.min_col).value)
        if not name or name.lower() in SKIP_LABELS or "NBFC" in name.upper() or "RS IN" in name.upper():
            continue
        score = 0
        for rr in range(merged.min_row + 1, min(merged.min_row + 5, ws.max_row) + 1):
            years, _ = _year_density(ws, rr, merged.min_col, merged.max_col)
            score = max(score, years)
        if score:
            blocks.append(CompanyBlock(name, merged.min_row, merged.min_col, merged.max_col))

    if not blocks:
        for r in range(1, max_header_row + 1):
            c = 1
            while c <= ws.max_column:
                name = clean_text(ws.cell(r, c).value)
                if not name or is_year(name) or name.lower() in SKIP_LABELS or "NBFC" in name.upper():
                    c += 1
                    continue
                year_row = None
                for rr in range(r + 1, min(r + 4, ws.max_row) + 1):
                    if is_year(ws.cell(rr, c).value):
                        year_row = rr
                        break
                if year_row is None:
                    c += 1
                    continue
                end = c
                while end + 1 <= ws.max_column and is_year(ws.cell(year_row, end + 1).value):
                    end += 1
                blocks.append(CompanyBlock(name, r, c, end))
                c = end + 1

    # Remove nested/duplicate detections and preserve left-to-right order.
    unique: dict[tuple[int, int], CompanyBlock] = {}
    for b in sorted(blocks, key=lambda x: (x.start_col, x.header_row, -x.end_col)):
        unique.setdefault((b.start_col, b.end_col), b)
    result = sorted(unique.values(), key=lambda x: x.start_col)
    if not result:
        issues.append(ParseIssue(ws.title, "error", "No company blocks detected"))
    return result


def detect_year_rows(ws, block: CompanyBlock) -> list[int]:
    rows = []
    for r in range(block.header_row + 1, ws.max_row + 1):
        years, nonempty = _year_density(ws, r, block.start_col, block.end_col)
        # At least one year and year labels dominate non-empty cells in the block.
        if years >= 1 and (nonempty == 0 or years / nonempty >= 0.60):
            rows.append(r)
    # Adjacent rows sometimes contain audit status, so only retain actual year rows.
    return rows


def label_column_for_row(ws, row: int, first_data_col: int) -> Optional[int]:
    # Prefer a cell that explicitly says Particulars in nearby header rows.
    for rr in range(max(1, row - 4), row + 1):
        for c in range(1, first_data_col):
            if clean_text(ws.cell(rr, c).value).lower() == "particulars":
                return c
    # Otherwise choose rightmost text cell to the left of data.
    for c in range(first_data_col - 1, 0, -1):
        if clean_text(ws.cell(row, c).value):
            return c
    return first_data_col - 1 if first_data_col > 1 else None


def find_table_unit(ws, year_row: int, block: CompanyBlock, next_year_row: int) -> str:
    stop = min(next_year_row, year_row + 5, ws.max_row + 1)
    for r in range(year_row + 1, stop):
        for c in range(block.start_col, block.end_col + 1):
            text = clean_text(ws.cell(r, c).value)
            if re.search(r"(?:rs\.?|₹).*crore|crores?|lakhs?|millions?", text, re.I):
                return text
    return ""


def infer_section(label: str, previous: str) -> str:
    low = label.lower().strip(":")
    if low in SECTION_NAMES:
        return label
    return previous


def likely_section_row(ws_values: Iterable[Any], label: str) -> bool:
    low = label.lower().strip(":")
    present = [safe_cached_value(v) for v in ws_values]
    meaningful = [v for v in present if clean_text(v) != ""]
    return low in SECTION_NAMES or not meaningful


def value_kind(metric: str, number_format: str, unit: str) -> str:
    m = metric.lower()
    nf = number_format or ""
    if "%" in nf or any(k in m for k in ["margin", "roa", "roe", "npa %", "npa%", "car", "cost to income", "coverage ratio", "yield", "spread", "stage 1 %", "stage 2 %", "stage 3 %", "credit cost", "tnw/loan"]):
        return "percentage"
    if "x" in nf.lower() or "leverage" in m:
        return "multiple"
    if unit:
        return "amount"
    return "number"


def parse_segment_sheet(ws_formula, ws_values, include_blank_values: bool = False) -> tuple[list[dict[str, Any]], list[ParseIssue]]:
    issues: list[ParseIssue] = []
    records: list[dict[str, Any]] = []
    title = find_segment_title(ws_values)
    segment = normalize_segment(ws_values.title, title)
    blocks = detect_company_blocks(ws_values, issues)
    if not blocks:
        return records, issues

    first_data_col = min(b.start_col for b in blocks)
    for block in blocks:
        year_rows = detect_year_rows(ws_values, block)
        if not year_rows:
            issues.append(ParseIssue(ws_values.title, "warning", f"No year rows detected for {block.company}"))
            continue

        for idx, year_row in enumerate(year_rows):
            next_year_row = year_rows[idx + 1] if idx + 1 < len(year_rows) else ws_values.max_row + 1
            unit = find_table_unit(ws_values, year_row, block, next_year_row)
            label_col = label_column_for_row(ws_values, year_row, first_data_col)
            if label_col is None:
                issues.append(ParseIssue(ws_values.title, "warning", f"No particulars column for {block.company}", f"row {year_row}"))
                continue

            year_by_col = {c: canonical_year(ws_values.cell(year_row, c).value) for c in range(block.start_col, block.end_col + 1)}
            year_by_col = {c: y for c, y in year_by_col.items() if y}
            if not year_by_col:
                continue

            current_section = "Financials" if idx == 0 else "Ratios"
            # Skip header/audit/unit rows; find metric rows up to the next year header.
            for r in range(year_row + 1, next_year_row):
                label = clean_text(ws_values.cell(r, label_col).value)
                if not label:
                    # Some files shift labels one column left/right.
                    candidates = []
                    for lc in range(max(1, label_col - 1), min(first_data_col, label_col + 2)):
                        t = clean_text(ws_values.cell(r, lc).value)
                        if t:
                            candidates.append((lc, t))
                    if candidates:
                        _, label = candidates[-1]
                if not label or label.lower() in SKIP_LABELS or is_year(label):
                    continue

                row_vals = [ws_values.cell(r, c).value for c in year_by_col]
                if likely_section_row(row_vals, label):
                    current_section = infer_section(label, current_section)
                    continue

                for c, year in year_by_col.items():
                    cached = safe_cached_value(ws_values.cell(r, c).value)
                    formula = ws_formula.cell(r, c).value
                    if not include_blank_values and cached is None:
                        continue
                    cell = ws_values.cell(r, c)
                    num_format = cell.number_format or ""
                    kind = value_kind(label, num_format, unit)
                    records.append({
                        "Segment": segment,
                        "Sheet": ws_values.title,
                        "Company": block.company,
                        "Section": current_section,
                        "Metric": label,
                        "Year": year,
                        "YearRaw": clean_text(ws_values.cell(year_row, c).value),
                        "Value": cached,
                        "Formula": formula if isinstance(formula, str) and formula.startswith("=") else None,
                        "Unit": unit or ("Percent" if kind == "percentage" else ""),
                        "ValueKind": kind,
                        "NumberFormat": num_format,
                        "SourceCell": f"{get_column_letter(c)}{r}",
                        "CompanyHeaderCell": f"{get_column_letter(block.start_col)}{block.header_row}",
                        "YearHeaderCell": f"{get_column_letter(c)}{year_row}",
                    })
    return records, issues


def parse_workbook(
    path: str | Path,
    segment_sheet_prefix: str = "NBFC-",
    include_blank_values: bool = False,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Parse all segment sheets and return (records, issues)."""
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(path)
    wb_formula = load_workbook(path, data_only=False, read_only=False)
    wb_values = load_workbook(path, data_only=True, read_only=False)

    all_records: list[dict[str, Any]] = []
    all_issues: list[ParseIssue] = []
    segment_sheets = [s for s in wb_values.sheetnames if s.upper().startswith(segment_sheet_prefix.upper())]
    if not segment_sheets:
        raise ValueError(f"No sheets start with {segment_sheet_prefix!r}")

    for sheet_name in segment_sheets:
        recs, issues = parse_segment_sheet(
            wb_formula[sheet_name], wb_values[sheet_name], include_blank_values=include_blank_values
        )
        all_records.extend(recs)
        all_issues.extend(issues)

    df = pd.DataFrame(all_records)
    if not df.empty:
        df["ValueNumeric"] = pd.to_numeric(df["Value"], errors="coerce")
        df = df.sort_values(["Segment", "Company", "Section", "Metric", "Year", "SourceCell"], kind="stable").reset_index(drop=True)
    issues_df = pd.DataFrame([asdict(x) for x in all_issues])
    return df, issues_df


def export_results(df: pd.DataFrame, issues: pd.DataFrame, output: str | Path) -> None:
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    suffix = output.suffix.lower()
    if suffix == ".csv":
        df.to_csv(output, index=False, encoding="utf-8-sig")
        issues.to_csv(output.with_name(output.stem + "_issues.csv"), index=False, encoding="utf-8-sig")
    elif suffix in {".xlsx", ".xlsm"}:
        with pd.ExcelWriter(output, engine="openpyxl") as writer:
            df.to_excel(writer, sheet_name="ParsedData", index=False)
            issues.to_excel(writer, sheet_name="ParseIssues", index=False)
    elif suffix == ".parquet":
        df.to_parquet(output, index=False)
        issues.to_parquet(output.with_name(output.stem + "_issues.parquet"), index=False)
    else:
        raise ValueError("Output extension must be .csv, .xlsx or .parquet")


def get_metric(df: pd.DataFrame, company: str, metric_pattern: str, year: Optional[str] = None) -> pd.DataFrame:
    """Convenience query used later by the Streamlit dashboard."""
    mask = df["Company"].eq(company) & df["Metric"].str.contains(metric_pattern, case=False, regex=True, na=False)
    if year:
        mask &= df["Year"].eq(year)
    return df.loc[mask].copy()


def main() -> None:
    ap = argparse.ArgumentParser(description="Parse compiled NBFC workbook into tidy data")
    ap.add_argument("workbook", help="Path to the compiled .xlsx workbook")
    ap.add_argument("--output", default="nbfc_parsed.csv", help=".csv, .xlsx or .parquet output")
    ap.add_argument("--prefix", default="NBFC-", help="Segment sheet prefix")
    ap.add_argument("--include-blanks", action="store_true", help="Keep records whose cached value is blank")
    ap.add_argument("--summary-json", default="", help="Optional path for machine-readable parse summary")
    args = ap.parse_args()

    df, issues = parse_workbook(args.workbook, args.prefix, args.include_blanks)
    export_results(df, issues, args.output)
    summary = {
        "records": int(len(df)),
        "segments": int(df["Segment"].nunique()) if not df.empty else 0,
        "companies": int(df["Company"].nunique()) if not df.empty else 0,
        "metrics": int(df["Metric"].nunique()) if not df.empty else 0,
        "issues": int(len(issues)),
        "output": str(Path(args.output).resolve()),
    }
    print(json.dumps(summary, indent=2))
    if args.summary_json:
        Path(args.summary_json).write_text(json.dumps(summary, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
