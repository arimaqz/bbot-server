"""Executive snapshot reports from the current target inventory."""

from datetime import datetime, timezone
from html import escape
from pathlib import Path, PurePosixPath, PureWindowsPath
import os
import re
import csv
import json
from xml.sax.saxutils import escape as xml_escape

from bbot_server.config import BBOT_SERVER_CONFIG as bbcfg


SEVERITIES = ("CRITICAL", "HIGH", "MEDIUM", "LOW", "INFO")


def _date(timestamp):
    return datetime.fromtimestamp(timestamp, timezone.utc).strftime("%d %b %Y, %H:%M UTC") if timestamp else "—"


def report_path(scan, directory=None):
    directory = Path(directory) if directory is not None else Path.home() / "bbot-reports"
    slug = re.sub(r"[^a-zA-Z0-9_-]+", "-", scan["name"]).strip("-")[:60] or "scan"
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S-%f")
    return directory / f"{slug}-{stamp}.html"


def report_display_path(path):
    """Return the host-visible report path when running inside Docker."""
    path = Path(path)
    host_directory = os.getenv("BBOT_REPORTS_HOST_DIR")
    if not host_directory:
        return str(path)
    if "\\" in host_directory or re.match(r"^[a-zA-Z]:", host_directory):
        return str(PureWindowsPath(host_directory) / path.name)
    return str(PurePosixPath(host_directory) / path.name)


def render_report(
    scan,
    assets,
    counts,
    findings,
    technologies=None,
    generated_at=None,
    brand_name=None,
    asset_records=None,
):
    """Render a standalone, printable HTML report. All external data is escaped."""
    generated_at = generated_at or datetime.now(timezone.utc).timestamp()
    brand_name = brand_name or bbcfg.name
    escaped_brand_name = escape(brand_name)
    target = scan["target"]
    total = sum(counts.get(level, 0) for level in SEVERITIES)
    serious = counts.get("CRITICAL", 0) + counts.get("HIGH", 0)
    finding_rows = (
        "".join(
            "<tr><td><span class='badge {severity}'>{severity}</span></td><td>{name}</td><td>{host}</td>"
            "<td>{description}</td></tr>".format(
                severity=escape(str(f.get("severity", "INFO")).upper()),
                name=escape(str(f.get("name", ""))),
                host=escape(str(f.get("host", ""))),
                description=escape(str(f.get("description", ""))[:240]),
            )
            for f in findings
        )
        or "<tr><td colspan='4'>No active, unignored findings recorded for this target.</td></tr>"
    )
    bars = "".join(
        f"<div class='bar-row'><span>{level.title()}</span><div class='track'><div class='{level}' "
        f"style='width:{100 * counts.get(level, 0) / max(total, 1):.1f}%'></div></div>"
        f"<strong>{counts.get(level, 0):,}</strong></div>"
        for level in SEVERITIES
    )
    scope = ", ".join(escape(str(s)) for s in (target.get("target") or target.get("seeds") or [])) or "Unspecified"
    asset_records = asset_records or []
    technologies = technologies or []
    asset_rows = (
        "".join(
            "<tr><td>{host}</td><td>{ports}</td><td>{technologies}</td></tr>".format(
                host=escape(str(item.get("host", ""))),
                ports=escape(", ".join(str(port) for port in item.get("open_ports", [])) or "—"),
                technologies=escape(", ".join(str(technology) for technology in item.get("technologies", [])) or "—"),
            )
            for item in asset_records
        )
        or "<tr><td colspan='3'>No assets recorded for this scope.</td></tr>"
    )
    tech_rows = (
        "".join(
            "<tr><td>{name}</td><td>{count:,}</td><td>{hosts}</td></tr>".format(
                name=escape(str(item["name"])),
                count=int(item.get("host_count", len(item.get("hosts", [])))),
                hosts=escape(", ".join(str(host) for host in item.get("hosts", [])) or "—"),
            )
            for item in technologies
        )
        or "<tr><td colspan='3'>No technologies recorded.</td></tr>"
    )
    return f"""<!doctype html>
<html lang='en'><head><meta charset='utf-8'><meta name='viewport' content='width=device-width, initial-scale=1'>
<title>{escaped_brand_name} | {escape(str(target["name"]))} security snapshot</title>
<style>
  :root {{ color-scheme: light; font-family: Inter, system-ui, sans-serif; color: #172334; }}
  * {{ box-sizing: border-box; }} body {{ margin: 0; background: #f3f5f8; line-height: 1.5; }}
  main {{ max-width: 1060px; margin: 0 auto; padding: 48px 32px; }}
  header {{ background: #152437; color: white; padding: 48px; border-radius: 18px; }}
  .eyebrow {{ color: #ffac4c; font-weight: 750; letter-spacing: .12em; text-transform: uppercase; font-size: 12px; }}
  h1 {{ font-size: 38px; line-height: 1.14; margin: 16px 0; }} h2 {{ font-size: 22px; margin: 0 0 18px; }}
  .muted {{ color: #667484; }} header .muted {{ color: #c1ccda; }}
  section {{ background: white; padding: 30px; border-radius: 16px; margin-top: 20px; break-inside: avoid; }}
  .metrics {{ display: grid; grid-template-columns: repeat(3, 1fr); gap: 16px; margin-top: 20px; }}
  .metric {{ background: white; border-radius: 16px; padding: 24px; }}
  .metric strong {{ display: block; font-size: 36px; }} .metric span {{ color: #667484; }}
  .bar-row {{ display: grid; grid-template-columns: 90px 1fr 45px; gap: 16px; align-items: center; margin: 12px 0; }}
  .track {{ background: #edf0f4; border-radius: 6px; height: 12px; overflow: hidden; }}
  .track div {{ height: 100%; }} .CRITICAL {{ background: #7b319f; }} .HIGH {{ background: #d54848; }}
  .MEDIUM {{ background: #e49434; }} .LOW {{ background: #e4c657; }} .INFO {{ background: #4a9dc7; }}
  table {{ width: 100%; border-collapse: collapse; text-align: left; font-size: 13px; table-layout: fixed; }}
  th, td {{ padding: 13px 9px; border-bottom: 1px solid #e9edf1; vertical-align: top; overflow-wrap: anywhere; }}
  th {{ color: #667484; }} th:nth-child(1) {{ width: 100px; }} th:nth-child(3) {{ width: 150px; }}
  .badge {{ color: white; font-size: 11px; padding: 4px 6px; border-radius: 4px; }}
  .badge.LOW {{ color: #172334; }} .small {{ font-size: 12px; }}
  @media print {{ body {{ background: white; }} main {{ padding: 0; }} header, section, .metric {{ break-inside: avoid; }} }}
</style></head><body><main>
<header><div class='eyebrow'>{escaped_brand_name} / Security overview</div>
<h1>{escape(str(target["name"]))}</h1>
<div class='muted'>Prepared {_date(generated_at)} · Scan {escape(str(scan["name"]))} · {escape(str(scan["status"]))}</div></header>
<div class='metrics'><div class='metric'><strong>{assets:,}</strong><span>In-scope assets</span></div>
<div class='metric'><strong>{total:,}</strong><span>Active findings</span></div>
<div class='metric'><strong>{serious:,}</strong><span>Critical or high findings</span></div></div>
<section><h2>Executive summary</h2><p>The current inventory for this target includes {assets:,} assets and {total:,}
active, unignored findings. {serious:,} are rated critical or high and should be prioritized for review.</p>
<p class='muted'>This is a snapshot of the target's accumulated inventory at the time shown above. Findings can
come from multiple scans and are not attributed solely to the named scan. Counts reflect active records;
archived and ignored findings are excluded. Discovery coverage depends on the configured scan preset and scope.</p></section>
<section><h2>Findings by severity</h2>{bars}</section>
<section><h2>Discovered assets</h2><p class='muted small'>All assets currently recorded for this scope.</p>
<table><thead><tr><th>Asset</th><th>Open ports</th><th>Technologies</th></tr></thead><tbody>{asset_rows}</tbody></table></section>
<section><h2>Findings</h2><p class='muted small'>All active, unignored findings currently recorded for this scope.</p>
<table><thead><tr><th>Severity</th><th>Finding</th><th>Asset</th><th>Evidence summary</th></tr></thead><tbody>{finding_rows}</tbody></table></section>
<section><h2>Technologies</h2><p class='muted small'>All recorded technologies and the assets on which they were observed.</p>
<table><thead><tr><th>Technology</th><th>Host count</th><th>Assets</th></tr></thead><tbody>{tech_rows}</tbody></table></section>
<section><h2>Scope &amp; methodology</h2><p><strong>Target:</strong> {escape(str(target["name"]))}<br>
<strong>Scope:</strong> {scope}<br><strong>Preset:</strong> {escape(str(scan["preset"]["name"]))}<br>
<strong>Scan started:</strong> {_date(scan.get("started_at"))}<br>
<strong>Scan finished:</strong> {_date(scan.get("finished_at"))}</p>
<p class='muted small'>The numbers are based on {escaped_brand_name}'s stored asset and finding records. A missing finding
does not establish that an asset is secure. Validate and triage findings before distributing this report.</p></section>
</main></body></html>"""


async def create_report(client, scan, directory=None):
    """Collect scoped queries through the public API and write the report."""
    snapshot = await collect_report(client, scan=scan)
    path = report_path(scan, directory)
    return write_report(snapshot, "html", path)


async def collect_report(client, *, scan=None, target=None, domain=None):
    """Query a target or domain. A scan selects its target, not its own events."""
    if scan is not None:
        target = scan["target"]
    if (target is None) == (domain is None):
        raise ValueError("Choose exactly one target or domain")
    if target is not None:
        filters = {"target_id": str(target["id"])}
        if scan is None:
            scan = {
                "name": "Target inventory",
                "status": "SNAPSHOT",
                "target": target,
                "preset": {"name": "Multiple sources"},
                "started_at": None,
                "finished_at": None,
            }
    else:
        domain = domain.strip().lower()
        if not domain or any(char.isspace() for char in domain):
            raise ValueError("Enter a valid domain or subdomain")
        filters = {"domain": domain}
        scan = {
            "name": "Domain inventory",
            "status": "SNAPSHOT",
            "target": {"name": domain, "target": [domain]},
            "preset": {"name": "Multiple sources"},
            "started_at": None,
            "finished_at": None,
        }
    # Scan records embed their full preset, including possible credentials. Never export it.
    scan = {
        "name": scan["name"],
        "status": scan["status"],
        "target": {
            "id": str(scan["target"].get("id", "")),
            "name": scan["target"]["name"],
            "target": scan["target"].get("target") or [],
            "seeds": scan["target"].get("seeds") or [],
        },
        "preset": {"name": scan["preset"]["name"]},
        "started_at": scan.get("started_at"),
        "finished_at": scan.get("finished_at"),
    }
    assets = await client.count_assets(**filters)
    asset_records = [
        asset
        async for asset in client.query_assets(
            **filters,
            sort=["host"],
            fields=["host", "open_ports", "technologies"],
        )
    ]
    asset_records = sorted(
        (
            {
                "host": str(asset.get("host", "")),
                "open_ports": sorted(asset.get("open_ports") or []),
                "technologies": sorted(str(technology) for technology in (asset.get("technologies") or [])),
            }
            for asset in asset_records
        ),
        key=lambda asset: asset["host"],
    )
    open_ports = [{"host": asset["host"], "port": port} for asset in asset_records for port in asset["open_ports"]]
    counts = {}
    for level, score in zip(SEVERITIES, (5, 4, 3, 2, 1)):
        counts[level] = await client.count_findings(**filters, min_severity=score, max_severity=score, ignored=False)
    findings = [
        f
        async for f in client.query_findings(
            **filters,
            ignored=False,
            sort=["-severity_score"],
            fields=["name", "host", "description", "severity_score"],
        )
    ]
    for finding in findings:
        finding["severity"] = SEVERITIES[5 - finding["severity_score"]]
    stats = await client.get_stats(**filters)
    technologies = await client.get_technologies_summary(**filters)
    technology_summary = [
        {
            "name": str(item["technology"]),
            "host_count": len(item.get("hosts") or []),
            "hosts": sorted(str(host) for host in (item.get("hosts") or [])),
        }
        for item in technologies
    ]
    return {
        "brand_name": bbcfg.name,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "scope_type": "target" if target is not None else "domain",
        "scope": target["name"] if target is not None else domain,
        "scan": scan,
        "assets": assets,
        "asset_records": asset_records,
        "open_ports": open_ports,
        "severity_counts": counts,
        "findings": findings,
        "stats": stats,
        "technologies": technology_summary,
        "definition": "Current active, unignored target or domain inventory; findings can originate from multiple scans.",
    }


def write_report(snapshot, format, path):
    """Write one portable executive report in the requested format."""
    if format not in ("html", "pdf", "json", "csv"):
        raise ValueError(f"Unsupported report format: {format}")
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if format == "html":
        path.write_text(
            render_report(
                snapshot["scan"],
                snapshot["assets"],
                snapshot["severity_counts"],
                snapshot["findings"],
                snapshot["technologies"],
                brand_name=snapshot.get("brand_name"),
                asset_records=snapshot.get("asset_records", []),
            ),
            encoding="utf-8",
        )
    elif format == "json":
        path.write_text(json.dumps(snapshot, indent=2, default=str), encoding="utf-8")
    elif format == "csv":
        with path.open("w", encoding="utf-8", newline="") as stream:
            writer = csv.DictWriter(
                stream, fieldnames=("record_type", "scope", "severity", "count", "name", "host", "description")
            )
            writer.writeheader()
            writer.writerow(
                {
                    "record_type": "report",
                    "scope": snapshot["scope"],
                    "name": snapshot.get("brand_name", bbcfg.name),
                }
            )
            writer.writerow({"record_type": "assets", "scope": snapshot["scope"], "count": snapshot["assets"]})
            for asset in snapshot.get("asset_records", []):
                writer.writerow(
                    {
                        "record_type": "asset",
                        "scope": snapshot["scope"],
                        "host": asset["host"],
                        "description": "Open ports: {ports}; Technologies: {technologies}".format(
                            ports=", ".join(str(port) for port in asset.get("open_ports", [])) or "none",
                            technologies=", ".join(asset.get("technologies", [])) or "none",
                        ),
                    }
                )
            for item in snapshot.get("open_ports", []):
                writer.writerow(
                    {
                        "record_type": "open_port",
                        "scope": snapshot["scope"],
                        "name": item["port"],
                        "host": item["host"],
                    }
                )
            for level in SEVERITIES:
                writer.writerow(
                    {
                        "record_type": "severity_total",
                        "scope": snapshot["scope"],
                        "severity": level,
                        "count": snapshot["severity_counts"].get(level, 0),
                    }
                )
            for finding in snapshot["findings"]:
                writer.writerow(
                    {
                        "record_type": "priority_finding",
                        "scope": snapshot["scope"],
                        "severity": finding["severity"],
                        "name": finding.get("name", ""),
                        "host": finding.get("host", ""),
                        "description": finding.get("description", ""),
                    }
                )
            for item in snapshot["technologies"]:
                hosts = item.get("hosts") or [""]
                for host in hosts:
                    writer.writerow(
                        {
                            "record_type": "technology",
                            "scope": snapshot["scope"],
                            "name": item["name"],
                            "host": host,
                            "count": item.get("host_count", len(item.get("hosts", []))),
                        }
                    )
    else:
        _write_pdf(snapshot, path)
    return path


def _write_pdf(snapshot, path):
    from reportlab.lib import colors
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.pagesizes import A4
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    from reportlab.lib.fonts import addMapping
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, KeepTogether

    font_dir = Path(__file__).parent / "fonts"
    if "BBOTDejaVu" not in pdfmetrics.getRegisteredFontNames():
        pdfmetrics.registerFont(TTFont("BBOTDejaVu", str(font_dir / "DejaVuSans.ttf")))
        pdfmetrics.registerFont(TTFont("BBOTDejaVu-Bold", str(font_dir / "DejaVuSans-Bold.ttf")))
        addMapping("BBOTDejaVu", 0, 0, "BBOTDejaVu")
        addMapping("BBOTDejaVu", 1, 0, "BBOTDejaVu-Bold")
    styles = getSampleStyleSheet()
    styles["Normal"].fontName = "BBOTDejaVu"
    styles["Title"].fontName = "BBOTDejaVu-Bold"
    styles["Heading2"].fontName = "BBOTDejaVu-Bold"
    styles.add(
        ParagraphStyle(
            name="ReportTitle",
            parent=styles["Title"],
            fontSize=23,
            leading=28,
            textColor=colors.HexColor("#152437"),
            spaceAfter=18,
        )
    )
    styles.add(
        ParagraphStyle(
            name="ReportSection",
            parent=styles["Heading2"],
            fontSize=13,
            textColor=colors.HexColor("#152437"),
            spaceBefore=19,
            spaceAfter=8,
        )
    )
    styles.add(ParagraphStyle(name="ReportCell", parent=styles["Normal"], fontSize=8, leading=11, wordWrap="CJK"))
    styles.add(
        ParagraphStyle(
            name="ReportSmall", parent=styles["Normal"], fontSize=8, leading=12, textColor=colors.HexColor("#667484")
        )
    )
    body = []
    brand_name = str(snapshot.get("brand_name", bbcfg.name))
    escaped_brand_name = xml_escape(brand_name)
    scope = xml_escape(str(snapshot["scope"]))
    counts = snapshot["severity_counts"]
    total = sum(counts.values())
    serious = counts.get("CRITICAL", 0) + counts.get("HIGH", 0)
    body.extend(
        [
            Paragraph(escaped_brand_name + " / SECURITY OVERVIEW", styles["ReportSmall"]),
            Paragraph(scope + " - Security snapshot", styles["ReportTitle"]),
            Paragraph(
                "Prepared " + xml_escape(snapshot["generated_at"][:19].replace("T", " ")) + " UTC",
                styles["ReportSmall"],
            ),
            Spacer(1, 16),
        ]
    )
    cards = Table(
        [[f"{snapshot['assets']:,} in-scope assets", f"{total:,} active findings", f"{serious:,} critical / high"]],
        colWidths=[165, 165, 165],
    )
    cards.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#edf1f5")),
                ("TEXTCOLOR", (0, 0), (-1, -1), colors.HexColor("#152437")),
                ("FONTSIZE", (0, 0), (-1, -1), 10),
                ("FONTNAME", (0, 0), (-1, -1), "BBOTDejaVu"),
                ("TOPPADDING", (0, 0), (-1, -1), 17),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 17),
            ]
        )
    )
    body.extend(
        [
            cards,
            Paragraph("Executive summary", styles["ReportSection"]),
            Paragraph(
                f"This {xml_escape(snapshot['scope_type'])} currently has {snapshot['assets']:,} assets and {total:,} active, unignored findings. "
                f"Review the {serious:,} critical or high findings first.",
                styles["Normal"],
            ),
            Paragraph(xml_escape(snapshot["definition"]), styles["ReportSmall"]),
            Paragraph("Findings by severity", styles["ReportSection"]),
        ]
    )
    severity_table = Table(
        [["Severity", "Count"]] + [[level.title(), str(counts.get(level, 0))] for level in SEVERITIES],
        colWidths=[340, 155],
    )
    severity_table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#152437")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("FONTNAME", (0, 0), (-1, -1), "BBOTDejaVu"),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f3f5f8")]),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
                ("TOPPADDING", (0, 0), (-1, -1), 8),
            ]
        )
    )
    table_style = TableStyle(
        [
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#152437")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("FONTNAME", (0, 0), (-1, -1), "BBOTDejaVu"),
            ("FONTSIZE", (0, 0), (-1, -1), 8),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f3f5f8")]),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
            ("TOPPADDING", (0, 0), (-1, -1), 7),
        ]
    )
    body.append(severity_table)
    body.append(Paragraph("Discovered assets", styles["ReportSection"]))
    asset_rows = [["Asset", "Open ports", "Technologies"]]
    for asset in snapshot.get("asset_records", []):
        asset_rows.append(
            [
                Paragraph(xml_escape(str(asset.get("host", ""))), styles["ReportCell"]),
                Paragraph(
                    xml_escape(", ".join(str(port) for port in asset.get("open_ports", [])) or "—"),
                    styles["ReportCell"],
                ),
                Paragraph(
                    xml_escape(", ".join(str(item) for item in asset.get("technologies", [])) or "—"),
                    styles["ReportCell"],
                ),
            ]
        )
    if len(asset_rows) == 1:
        asset_rows.append(["No assets recorded.", "", ""])
    asset_table = Table(asset_rows, colWidths=[205, 85, 205], repeatRows=1)
    asset_table.setStyle(table_style)
    body.append(asset_table)

    body.extend(
        [
            Paragraph("Findings", styles["ReportSection"]),
            Paragraph(
                "All active, unignored findings currently recorded for this scope.",
                styles["ReportSmall"],
            ),
        ]
    )
    if snapshot["findings"]:
        for finding in snapshot["findings"]:
            body.append(
                KeepTogether(
                    [
                        Paragraph(
                            f"<b>{xml_escape(finding['severity'])} - {xml_escape(str(finding.get('name', '')))}</b>",
                            styles["ReportCell"],
                        ),
                        Paragraph(xml_escape(str(finding.get("host", ""))), styles["ReportSmall"]),
                        Paragraph(xml_escape(str(finding.get("description", ""))[:240]), styles["ReportCell"]),
                        Spacer(1, 9),
                    ]
                )
            )
    else:
        body.append(Paragraph("No active findings recorded for this scope.", styles["Normal"]))
    body.append(Paragraph("Technologies", styles["ReportSection"]))
    technology_rows = [["Technology", "Host count", "Assets"]]
    for item in snapshot["technologies"]:
        technology_rows.append(
            [
                Paragraph(xml_escape(str(item["name"])), styles["ReportCell"]),
                str(item.get("host_count", len(item.get("hosts", [])))),
                Paragraph(
                    xml_escape(", ".join(str(host) for host in item.get("hosts", [])) or "—"), styles["ReportCell"]
                ),
            ]
        )
    if len(technology_rows) == 1:
        technology_rows.append(["No technologies recorded.", "", ""])
    technology_table = Table(technology_rows, colWidths=[170, 75, 250], repeatRows=1)
    technology_table.setStyle(table_style)
    body.append(technology_table)
    body.append(
        Paragraph(
            "Discovery coverage depends on scan configuration. Absence of findings does not establish security.",
            styles["ReportSmall"],
        )
    )

    def footer(canvas, doc):
        canvas.setFont("BBOTDejaVu", 8)
        canvas.setFillColor(colors.HexColor("#667484"))
        canvas.drawString(48, 34, brand_name + " - target inventory snapshot")
        canvas.drawRightString(A4[0] - 48, 34, f"Page {doc.page}")

    SimpleDocTemplate(str(path), pagesize=A4, leftMargin=48, rightMargin=48, topMargin=48, bottomMargin=56).build(
        body, onFirstPage=footer, onLaterPages=footer
    )
