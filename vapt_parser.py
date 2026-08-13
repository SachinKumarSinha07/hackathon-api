"""
VAPT Report Parser  --  deterministic .xlsx -> JSON extractor.

Design rule: NEVER guess. Resolve columns by header text, cross-validate every
number against an independent source in the workbook, and fail loudly rather
than emit a plausible-looking wrong record.

Usage:
    python vapt_parser.py <report.xlsx> [--out out.json] [--media-dir ./poc]
Exit codes:
    0 = PASSED  (safe to auto-ingest)
    1 = WARNINGS (ingest, but flag for human review)
    2 = FAILED  (do NOT ingest; route to manual review queue)
"""

import argparse
import hashlib
import json
import re
import sys
from datetime import datetime, date, timezone
from pathlib import Path

import openpyxl

try:
    import PIL  # noqa: F401
    HAVE_PILLOW = True
except ImportError:
    HAVE_PILLOW = False

PARSER_VERSION = "1.0.0"
TEMPLATE_ID = "ymsi-webapp-vapt-v1"

# ---------------------------------------------------------------- severity map

SEVERITY_MAP = {
    "critical": ("CRITICAL", 5),
    "high": ("HIGH", 4),
    "medium": ("MEDIUM", 3),
    "low": ("LOW", 2),
    "informational": ("INFO", 1),
    "info": ("INFO", 1),
}

# Column header -> canonical field. Matching is normalized (lowercase, stripped,
# whitespace collapsed) so stray tabs/newlines in headers don't break anything.
DETAIL_COLUMNS = {
    "s. no": "serial",
    "s.no": "serial",
    "sr. no": "serial",
    "vulnerability name": "title",
    "vulnerabilities name": "title",
    "severity": "severity_raw",
    "affected url / apk": "affected_raw",
    "affected url/apk": "affected_raw",
    "affected url": "affected_raw",
    "vulnerability description": "description",
    "description": "description",
    "impact": "impact",
    "mitigation": "mitigation",
    "reference link": "reference_raw",
    "reference links": "reference_raw",
    "responsible pic": "responsible_pic",
    "remarks": "remarks",
    "target resolution date": "target_resolution_date",
}

REQUIRED_FIELDS = ["serial", "title", "severity_raw", "description"]

URL_RE = re.compile(r"https?://[^\s,;\]\)]+", re.IGNORECASE)


# ---------------------------------------------------------------- helpers

def norm(s):
    """Normalize a header/label for matching."""
    if s is None:
        return ""
    return re.sub(r"\s+", " ", str(s).replace("\xa0", " ")).strip().lower()


def clean(v):
    """Clean a cell value for output. Returns None for empties."""
    if v is None:
        return None
    if isinstance(v, (datetime, date)):
        return v.isoformat()
    if isinstance(v, str):
        s = v.replace("\xa0", " ").strip()
        return s if s else None
    return v


class Report:
    """Collects validation results. Any error => FAILED."""

    def __init__(self):
        self.checks = []
        self.errors = []
        self.warnings = []

    def check(self, name, passed, detail="", fatal=True):
        self.checks.append({"name": name, "passed": bool(passed), "detail": detail})
        if not passed:
            (self.errors if fatal else self.warnings).append(
                {"check": name, "detail": detail}
            )
        return passed

    def warn(self, name, detail):
        self.warnings.append({"check": name, "detail": detail})

    @property
    def status(self):
        if self.errors:
            return "FAILED"
        if self.warnings:
            return "WARNINGS"
        return "PASSED"


# ---------------------------------------------------------------- parsing

def parse_severity(raw, rep, ctx):
    """'Critical - Level 5' -> ('CRITICAL', 5). Unknown => error, never a guess."""
    if raw is None:
        rep.check(f"severity_present[{ctx}]", False, "severity cell is empty")
        return None, None, None
    text = norm(raw)
    word = text.split("-")[0].strip()
    if word not in SEVERITY_MAP:
        rep.check(
            f"severity_recognized[{ctx}]", False,
            f"unrecognized severity value: {raw!r}"
        )
        return None, None, str(raw).strip()
    label, level = SEVERITY_MAP[word]
    # If the string also declares a level number, it must agree with our map.
    m = re.search(r"level\s*(\d)", text)
    if m and int(m.group(1)) != level:
        rep.check(
            f"severity_level_consistent[{ctx}]", False,
            f"{raw!r}: text says level {m.group(1)}, mapping says {level}"
        )
    return label, level, str(raw).strip()


def find_header_row(ws, expected_headers, max_scan=15):
    """Locate the header row by looking for known header labels. Returns
    (row_index, {col_index: canonical_field})."""
    best = (None, {})
    for r in range(1, min(ws.max_row, max_scan) + 1):
        mapping = {}
        for c in range(1, ws.max_column + 1):
            key = norm(ws.cell(r, c).value)
            if key in expected_headers:
                mapping[c] = expected_headers[key]
        if len(mapping) > len(best[1]):
            best = (r, mapping)
    return best


def split_multi(raw):
    """Affected-asset / reference cells hold newline-separated values plus
    free-text notes like '(All API Endpoints)'. Keep URLs and notes separate."""
    if not raw:
        return [], []
    urls, notes = [], []
    for line in str(raw).split("\n"):
        line = line.strip()
        if not line:
            continue
        found = URL_RE.findall(line)
        if found:
            urls.extend(u.rstrip(".,;") for u in found)
        else:
            notes.append(line.strip("()").strip())
    # de-dupe, preserve order
    seen, out = set(), []
    for u in urls:
        if u not in seen:
            seen.add(u)
            out.append(u)
    return out, notes


def parse_metadata(wb, rep):
    """Cover Sheet + Testing Details -> report header block.
    Label-driven, not coordinate-driven, so inserted rows don't break it."""
    meta = {
        "application_name": None, "target": None, "report_date": None,
        "overall_severity": None, "security_analyst": None,
        "practice_head": None, "project_manager": None,
        "testing_approver": None, "conducted_by": None, "tools_used": [],
        "engagement_title": None,
    }

    if "Testing Details" in wb.sheetnames:
        ws = wb["Testing Details"]
        label_field = {
            "security analyst": "security_analyst",
            "practice head": "practice_head",
            "project manager": "project_manager",
            "test url / apk": "target",
            "test url/apk": "target",
            "testing approver pratice head": "testing_approver",
            "testing approver practice head": "testing_approver",
            "testing conducted by": "conducted_by",
            "testing tools used": "_tools",
        }
        for row in ws.iter_rows(values_only=True):
            if not row or row[0] is None:
                continue
            key = norm(row[0])
            if key in label_field:
                val = clean(row[1]) if len(row) > 1 else None
                if label_field[key] == "_tools":
                    meta["tools_used"] = [
                        t.strip() for t in str(val or "").split(",") if t.strip()
                    ]
                else:
                    meta[label_field[key]] = val
            elif meta["engagement_title"] is None and "vapt" in key:
                meta["engagement_title"] = clean(row[0])
    else:
        rep.check("sheet_testing_details", False, "'Testing Details' sheet missing")

    if "Cover Sheet" in wb.sheetnames:
        ws = wb["Cover Sheet"]
        for row in ws.iter_rows(values_only=True):
            cells = [c for c in row if c is not None]
            for i, c in enumerate(cells):
                t = str(c).strip()
                if t.lower().startswith("application name"):
                    meta["application_name"] = t.split(":", 1)[-1].strip() or None
                elif t.lower().startswith("date -") or t.lower().startswith("date-"):
                    meta["report_date"] = t.split("-", 1)[-1].strip()
                elif norm(t) == "severity rating:" and i + 1 < len(cells):
                    meta["overall_severity"] = str(cells[i + 1]).strip()
    else:
        rep.check("sheet_cover", False, "'Cover Sheet' sheet missing", fatal=False)

    rep.check(
        "metadata_target_present", bool(meta["target"] or meta["application_name"]),
        "neither Test URL nor Application name could be read",
    )
    return meta


def parse_summary(wb, rep):
    """Vulnerability Summary -> declared per-severity counts + title list.
    The Count column is vertically merged per severity block; openpyxl returns
    the value only on the anchor row, which is exactly what we want."""
    if "Vulnerability Summary" not in wb.sheetnames:
        rep.check("sheet_summary", False, "'Vulnerability Summary' sheet missing")
        return {"rows": [], "declared_counts": {}, "scale": []}

    ws = wb["Vulnerability Summary"]
    hdr_row, colmap = find_header_row(ws, {
        "s.no": "serial", "s. no": "serial",
        "vulnerabilities name": "title", "vulnerability name": "title",
        "severity": "severity_raw", "count": "count",
    }, max_scan=12)

    if not rep.check("summary_header_found", hdr_row is not None
                     and {"serial", "title", "severity_raw"} <= set(colmap.values()),
                     f"header row={hdr_row}, mapped={sorted(set(colmap.values()))}"):
        return {"rows": [], "declared_counts": {}, "scale": []}

    inv = {v: k for k, v in colmap.items()}
    rows, declared, current = [], {}, None
    for r in range(hdr_row + 1, ws.max_row + 1):
        serial = ws.cell(r, inv["serial"]).value
        title = clean(ws.cell(r, inv["title"]).value)
        if serial is None and title is None:
            continue
        if not isinstance(serial, (int, float)):
            break  # end of table (CVSS scale block follows)
        sev_raw = ws.cell(r, inv["severity_raw"]).value
        label, level, raw = parse_severity(sev_raw, rep, f"summary r{r}")
        if label:
            current = label
        cnt = ws.cell(r, inv["count"]).value if "count" in inv else None
        if isinstance(cnt, (int, float)) and current:
            declared[current] = int(cnt)
        rows.append({"serial": int(serial), "title": title,
                     "severity": label, "severity_raw": raw, "row": r})

    # CVSS scale block
    scale = []
    for r in range(1, ws.max_row + 1):
        if norm(ws.cell(r, 1).value) == "s.no" and r > hdr_row:
            for rr in range(r + 1, ws.max_row + 1):
                sev = clean(ws.cell(rr, 2).value)
                desc = clean(ws.cell(rr, 3).value)
                if sev:
                    scale.append({"severity": sev, "description": desc})
            break

    return {"rows": rows, "declared_counts": declared, "scale": scale}


def parse_details(wb, rep):
    """Detailed Vulnerability Report -> the finding records (source of truth)."""
    sheet = next((s for s in wb.sheetnames
                  if norm(s).startswith("detailed vulnerability")), None)
    if not rep.check("sheet_detail", sheet is not None,
                     "'Detailed Vulnerability Report' sheet missing"):
        return []

    ws = wb[sheet]
    hdr_row, colmap = find_header_row(ws, DETAIL_COLUMNS)
    mapped = set(colmap.values())
    rep.check("detail_header_found", hdr_row is not None,
              f"header row={hdr_row}")
    missing = [f for f in REQUIRED_FIELDS if f not in mapped]
    rep.check("detail_required_columns", not missing,
              f"missing required columns: {missing}" if missing else "all present")
    if missing or hdr_row is None:
        return []

    inv = {v: k for k, v in colmap.items()}
    findings = []
    for r in range(hdr_row + 1, ws.max_row + 1):
        serial = ws.cell(r, inv["serial"]).value
        if serial is None:
            continue
        if not isinstance(serial, (int, float)):
            rep.warn("detail_nonnumeric_serial", f"row {r}: serial={serial!r}")
            continue

        rec = {f: clean(ws.cell(r, inv[f]).value) for f in inv}
        flags = []

        label, level, sev_raw = parse_severity(rec.get("severity_raw"), rep, f"detail r{r}")
        urls, notes = split_multi(rec.get("affected_raw"))
        refs, _ = split_multi(rec.get("reference_raw"))
        # mitigation cells sometimes embed the reference URL inline
        mit_urls, _ = split_multi(rec.get("mitigation"))
        for u in mit_urls:
            if u not in refs:
                refs.append(u)

        for f in ("title", "description", "impact", "mitigation"):
            if not rec.get(f):
                flags.append(f"missing_{f}")
        if not urls and not notes:
            flags.append("no_affected_asset")

        findings.append({
            "id": f"F-{int(serial):03d}",
            "serial": int(serial),
            "title": rec.get("title"),
            "severity": {"normalized": label, "level": level, "raw": sev_raw},
            "affected_assets": urls,
            "affected_notes": notes,
            "affected_raw": rec.get("affected_raw"),
            "description": rec.get("description"),
            "impact": rec.get("impact"),
            "mitigation": rec.get("mitigation"),
            "reference_links": refs,
            "responsible_pic": rec.get("responsible_pic"),
            "remarks": rec.get("remarks"),
            "target_resolution_date": rec.get("target_resolution_date"),
            "status": "OPEN",
            "poc": {"present": False, "image_count": 0, "images": []},
            "source": {"sheet": sheet, "row": r},
            "flags": flags,
        })
    return findings


def parse_pocs(wb_vals, wb_img, findings, rep, media_dir=None):
    """POCs sheet: label rows (serial, title) followed by anchored screenshots.
    Each image is attributed to the nearest preceding label row.

    NOTE: two workbook loads are mandatory here. The serial column contains
    FORMULAS (=A1+1); a raw load returns the formula string, a data_only load
    returns the number but drops the images. Labels come from wb_vals,
    images from wb_img.

    NOTE: Pillow is a hard requirement. Without it openpyxl's find_images()
    discards every embedded image SILENTLY, so ws._images comes back empty and
    the attribution check would trivially pass at '0 of 0'.
    """
    rep.check(
        "poc_image_support_available", HAVE_PILLOW,
        "Pillow is not installed; openpyxl silently drops all embedded images. "
        "Install it with: pip install Pillow",
    )
    if "POCs" not in wb_vals.sheetnames:
        rep.warn("sheet_pocs", "'POCs' sheet missing")
        return
    ws_v = wb_vals["POCs"]
    ws = wb_img["POCs"]

    labels = []
    for r in range(1, ws_v.max_row + 1):
        a, b = ws_v.cell(r, 1).value, ws_v.cell(r, 2).value
        if isinstance(a, (int, float)):
            labels.append({"serial": int(a), "title": clean(b), "row": r})
    labels.sort(key=lambda x: x["row"])

    total_images = len(getattr(ws, "_images", []))
    # Guards against the formula/cached-value trap above: if labels silently
    # collapse, these fire instead of the parse quietly under-reporting.
    rep.check(
        "poc_labels_resolved", len(labels) >= len(findings),
        f"{len(labels)} POC labels for {len(findings)} findings "
        f"(a much smaller number usually means formula cells were read raw)",
        fatal=False,
    )

    by_serial = {f["serial"]: f for f in findings}
    if media_dir:
        Path(media_dir).mkdir(parents=True, exist_ok=True)

    counters = {}
    for img in getattr(ws, "_images", []):
        arow = img.anchor._from.row + 1
        owner = None
        for lb in labels:
            if lb["row"] <= arow:
                owner = lb
            else:
                break
        if owner is None or owner["serial"] not in by_serial:
            rep.warn("poc_orphan_image", f"image at row {arow} has no matching finding")
            continue
        f = by_serial[owner["serial"]]
        n = counters.get(f["serial"], 0) + 1
        counters[f["serial"]] = n
        name = f"{f['id']}_poc_{n:02d}.png"
        if media_dir:
            try:
                data = img._data()
                Path(media_dir, name).write_bytes(data)
            except Exception as e:  # noqa: BLE001
                rep.warn("poc_extract_failed", f"{name}: {e}")
        f["poc"]["images"].append({"file": name, "sheet_row": arow})
        f["poc"]["image_count"] = n
        f["poc"]["present"] = True

    attributed = sum(f["poc"]["image_count"] for f in findings)
    rep.check(
        "poc_images_all_attributed", attributed == total_images,
        f"{attributed} of {total_images} embedded images mapped to a finding",
    )

    # Title drift between POC labels and the detail sheet is a real signal.
    for lb in labels:
        f = by_serial.get(lb["serial"])
        if f and lb["title"] and f["title"]:
            if norm(lb["title"]) != norm(f["title"]):
                f["flags"].append("poc_title_mismatch")
                rep.warn("poc_title_mismatch",
                         f"#{lb['serial']}: POC={lb['title']!r} vs detail={f['title']!r}")


# ---------------------------------------------------------------- validation

def cross_validate(findings, summary, rep):
    """The accuracy layer. Every assertion here compares two INDEPENDENT
    places in the workbook. Agreement is strong evidence the parse is right."""
    computed = {}
    for f in findings:
        s = f["severity"]["normalized"]
        if s:
            computed[s] = computed.get(s, 0) + 1

    srows = summary["rows"]
    declared = summary["declared_counts"]

    rep.check("detail_rows_present", len(findings) > 0, f"{len(findings)} findings parsed")

    rep.check(
        "count_detail_vs_summary_rows", len(findings) == len(srows),
        f"detail sheet has {len(findings)} findings, summary sheet lists {len(srows)}",
    )

    if declared:
        total_declared = sum(declared.values())
        rep.check(
            "count_total_vs_declared", total_declared == len(findings),
            f"summary Count column totals {total_declared}, detail sheet has {len(findings)}",
        )
        for sev, n in declared.items():
            rep.check(
                f"count_by_severity[{sev}]", computed.get(sev, 0) == n,
                f"summary declares {n} {sev}, detail sheet contains {computed.get(sev, 0)}",
            )
    else:
        rep.warn("declared_counts_absent", "no Count column values found in summary")

    # Serials must be 1..N with no gaps or dupes.
    serials = [f["serial"] for f in findings]
    rep.check("serials_unique", len(set(serials)) == len(serials),
              f"duplicate serials: {sorted({s for s in serials if serials.count(s) > 1})}")
    rep.check("serials_contiguous", serials == list(range(1, len(serials) + 1)),
              f"expected 1..{len(serials)}, got {serials[:5]}...")

    # Per-finding severity must agree between the two sheets.
    smap = {r["serial"]: r for r in srows}
    for f in findings:
        s = smap.get(f["serial"])
        if not s:
            rep.warn("finding_not_in_summary", f"#{f['serial']} {f['title']!r}")
            continue
        if s["severity"] != f["severity"]["normalized"]:
            rep.check(
                f"severity_agrees[#{f['serial']}]", False,
                f"summary={s['severity']} vs detail={f['severity']['normalized']}",
            )
        if s["title"] and f["title"] and norm(s["title"]) != norm(f["title"]):
            f["flags"].append("summary_title_mismatch")
            rep.warn("title_mismatch",
                     f"#{f['serial']}: summary={s['title']!r} vs detail={f['title']!r}")

    for f in findings:
        if f["flags"]:
            rep.warn("finding_flagged", f"{f['id']}: {', '.join(f['flags'])}")


def build_dashboard(findings, summary):
    order = ["CRITICAL", "HIGH", "MEDIUM", "LOW", "INFO"]
    counts = {k: 0 for k in order}
    for f in findings:
        s = f["severity"]["normalized"]
        if s in counts:
            counts[s] += 1
    return {
        "total_findings": len(findings),
        "severity_counts": counts,
        "severity_counts_declared": summary["declared_counts"],
        "counts_reconciled": all(
            summary["declared_counts"].get(k, counts[k]) == counts[k] for k in counts
        ),
        "findings_with_poc": sum(1 for f in findings if f["poc"]["present"]),
        "findings_without_poc": sum(1 for f in findings if not f["poc"]["present"]),
        "total_affected_assets": len(
            {u for f in findings for u in f["affected_assets"]}
        ),
        "status_counts": {"OPEN": len(findings), "IN_PROGRESS": 0,
                          "RESOLVED": 0, "RISK_ACCEPTED": 0},
        "flagged_for_review": sum(1 for f in findings if f["flags"]),
    }


# ---------------------------------------------------------------- entry point

def parse_file(path, media_dir=None):
    rep = Report()
    src = Path(path)
    sha = hashlib.sha256(src.read_bytes()).hexdigest()

    wb_vals = openpyxl.load_workbook(path, data_only=True)
    wb_img = openpyxl.load_workbook(path)  # second pass: images need the raw load

    meta = parse_metadata(wb_vals, rep)
    summary = parse_summary(wb_vals, rep)
    findings = parse_details(wb_vals, rep)
    parse_pocs(wb_vals, wb_img, findings, rep, media_dir)
    cross_validate(findings, summary, rep)

    return {
        "schema_version": "1.0",
        "parser": {
            "version": PARSER_VERSION,
            "template_id": TEMPLATE_ID,
            "parsed_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            "source_file": src.name,
            "source_sha256": sha,
        },
        "validation": {
            "status": rep.status,
            "checks_run": len(rep.checks),
            "checks_failed": sum(1 for c in rep.checks if not c["passed"]),
            "errors": rep.errors,
            "warnings": rep.warnings,
            "checks": rep.checks,
        },
        "report": meta,
        "dashboard": build_dashboard(findings, summary),
        "findings": findings,
        "severity_scale": summary["scale"],
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("xlsx")
    ap.add_argument("--out", default=None)
    ap.add_argument("--media-dir", default=None)
    args = ap.parse_args()

    result = parse_file(args.xlsx, args.media_dir)
    text = json.dumps(result, indent=2, ensure_ascii=False)
    if args.out:
        Path(args.out).write_text(text, encoding="utf-8")
    else:
        print(text)

    st = result["validation"]["status"]
    print(f"\n[{st}] {result['dashboard']['total_findings']} findings | "
          f"{len(result['validation']['errors'])} errors, "
          f"{len(result['validation']['warnings'])} warnings", file=sys.stderr)
    return {"PASSED": 0, "WARNINGS": 1, "FAILED": 2}[st]


if __name__ == "__main__":
    sys.exit(main())