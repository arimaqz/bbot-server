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
SENSITIVE_EVENT_KEYS = {
    "api_key",
    "apikey",
    "authorization",
    "body",
    "content",
    "cookie",
    "cookies",
    "headers",
    "password",
    "raw",
    "request",
    "response",
    "secret",
    "token",
}
SENSITIVE_PRESET_KEYS = {
    "api_key",
    "apikey",
    "api_token",
    "authorization",
    "cookie",
    "credentials",
    "password",
    "private_key",
    "secret",
    "token",
}
EVENT_SUMMARY_KEYS = (
    "name",
    "severity",
    "confidence",
    "url",
    "host",
    "port",
    "status_code",
    "title",
    "http_title",
    "redirect_location",
    "technology",
    "email",
    "username",
    "provider",
    "protocol",
    "path",
    "method",
    "location",
    "domain",
    "ip",
    "record",
    "record_type",
    "description",
)


def _date(timestamp):
    return datetime.fromtimestamp(timestamp, timezone.utc).strftime("%d %b %Y, %H:%M UTC") if timestamp else "—"


def _as_dict(value):
    if isinstance(value, dict):
        return value
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json")
    return dict(value)


def _preset_module_names(preset):
    names = []
    for key in ("modules", "output_modules"):
        value = preset.get(key) or []
        if isinstance(value, str):
            value = [value]
        names.extend(str(item) for item in value if item)
    return sorted(set(names), key=str.casefold)


def _configured_modules(scan):
    """Return only module names from the embedded preset; never expose its configuration."""
    preset_record = scan.get("preset") or {}
    return _preset_module_names(preset_record.get("preset") or {})


def _safe_preset_value(value, depth=0):
    """Preserve preset structure while replacing likely credentials."""
    if depth > 8:
        return "…"
    if isinstance(value, dict):
        cleaned = {}
        for key, item in value.items():
            normalized = str(key).lower().replace("-", "_")
            sensitive = normalized in SENSITIVE_PRESET_KEYS or any(
                normalized.endswith(f"_{name}") for name in SENSITIVE_PRESET_KEYS
            )
            cleaned[str(key)] = "[REDACTED]" if sensitive else _safe_preset_value(item, depth + 1)
        return cleaned
    if isinstance(value, (list, tuple, set)):
        return [_safe_preset_value(item, depth + 1) for item in value]
    if value is None or isinstance(value, (bool, int, float)):
        return value
    return str(value)[:2000]


def _module_anchor(name, index):
    slug = re.sub(r"[^a-z0-9_-]+", "-", str(name).lower()).strip("-") or "unknown"
    return f"module-{slug}-{index}"


def _host_key(value):
    """Normalize an event or asset host for exact host-level association."""
    return str(value or "").strip().casefold().rstrip(".")


def _module_counts_for_host(host, module_results):
    host_key = _host_key(host)
    return {
        module["name"]: sum(_host_key(result.get("host")) == host_key for result in module.get("results", []))
        for module in module_results
    }


def _result_count_label(value):
    count = int(value or 0)
    return f"{count:,} result" + ("" if count == 1 else "s") if count else "—"


def _safe_event_value(value, depth=0):
    """Bound and redact event data for portable reports."""
    if depth > 2:
        return "…"
    if isinstance(value, dict):
        cleaned = {}
        for key, item in value.items():
            normalized = str(key).lower().replace("-", "_")
            if any(sensitive in normalized for sensitive in SENSITIVE_EVENT_KEYS):
                continue
            cleaned[str(key)] = _safe_event_value(item, depth + 1)
            if len(cleaned) >= 20:
                cleaned["…"] = "additional fields omitted"
                break
        return cleaned
    if isinstance(value, (list, tuple, set)):
        values = [_safe_event_value(item, depth + 1) for item in list(value)[:20]]
        if len(value) > 20:
            values.append("…")
        return values
    if value is None or isinstance(value, (bool, int, float)):
        return value
    text = str(value)
    return text[:500] + ("…" if len(text) > 500 else "")


def _event_data(event):
    data = event.get("data_json")
    if data is None:
        data = event.get("data")
    return _safe_event_value(data)


def _event_summary(event, data):
    if isinstance(data, dict):
        selected = {key: data[key] for key in EVENT_SUMMARY_KEYS if key in data}
        status_tag = next((tag for tag in event.get("tags") or [] if re.fullmatch(r"status-\d{3}", str(tag))), None)
        if status_tag and "status_code" not in selected:
            selected["status_code"] = int(str(status_tag).removeprefix("status-"))
        return json.dumps(selected or data, ensure_ascii=False, sort_keys=True, default=str)[:1000]
    if data is not None:
        return str(data)[:1000]
    return "No printable event data"


def _build_module_results(events, configured_modules):
    grouped = {}
    for raw_event in events:
        event = _as_dict(raw_event)
        module = str(event.get("module") or "Unknown")
        data = _event_data(event)
        event_url = data.get("url", "") if isinstance(data, dict) else ""
        result = {
            "type": str(event.get("type") or "UNKNOWN"),
            "host": str(event.get("host") or ""),
            "port": event.get("port"),
            "url": str(event.get("url") or event_url),
            "timestamp": event.get("timestamp"),
            "tags": sorted(str(tag) for tag in (event.get("tags") or [])),
            "summary": _event_summary(event, data),
            "data": data,
        }
        grouped.setdefault(module, []).append(result)

    configured_set = set(configured_modules)
    module_names = sorted(
        set(configured_modules) | set(grouped),
        key=lambda name: (0 if name in configured_set else 1, name.casefold()),
    )
    modules = []
    for name in module_names:
        results = sorted(grouped.get(name, []), key=lambda item: (item.get("timestamp") or 0, item["type"]))
        timestamps = [item["timestamp"] for item in results if item.get("timestamp")]
        modules.append(
            {
                "name": name,
                "source": "preset" if name in configured_set else "automatic or dependency",
                "status": "results observed" if results else "no observed results",
                "event_count": len(results),
                "event_types": sorted({item["type"] for item in results}),
                "host_count": len({item["host"] for item in results if item["host"]}),
                "first_seen": min(timestamps) if timestamps else None,
                "last_seen": max(timestamps) if timestamps else None,
                "results": results,
            }
        )
    return modules


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
    module_results=None,
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
    module_results = module_results or []
    display_modules = [
        dict(module, anchor=_module_anchor(module["name"], index)) for index, module in enumerate(module_results)
    ]
    display_assets = []
    for item in asset_records:
        display_item = dict(item)
        if "module_counts" not in display_item:
            display_item["module_counts"] = _module_counts_for_host(display_item.get("host"), display_modules)
        display_assets.append(display_item)
    preset_modules = [module["name"] for module in display_modules if module.get("source") == "preset"]
    preset_definition = scan.get("preset", {}).get("definition") or {}
    preset_json = escape(json.dumps(preset_definition, indent=2, ensure_ascii=False, sort_keys=True, default=str))
    asset_module_headers = "".join(
        "<th><a class='module-link' href='#{anchor}'>{name}</a></th>".format(
            anchor=escape(str(module["anchor"]), quote=True),
            name=escape(str(module["name"])),
        )
        for module in display_modules
    )
    asset_rows = (
        "".join(
            "<tr><td>{host}</td><td>{ports}</td><td>{technologies}</td>{module_counts}</tr>".format(
                host=escape(str(item.get("host", ""))),
                ports=escape(", ".join(str(port) for port in item.get("open_ports", [])) or "—"),
                technologies=escape(", ".join(str(technology) for technology in item.get("technologies", [])) or "—"),
                module_counts="".join(
                    "<td class='module-count' data-module='{module}'>{count}</td>".format(
                        module=escape(str(module["name"]), quote=True),
                        count=_result_count_label(item["module_counts"].get(module["name"], 0)),
                    )
                    for module in display_modules
                ),
            )
            for item in display_assets
        )
        or f"<tr><td colspan='{3 + len(display_modules)}'>No assets recorded for this scope.</td></tr>"
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
    module_rows = (
        "".join(
            "<tr><td><a class='module-link' href='#{anchor}'>{name}</a></td><td>{source}</td>"
            "<td>{status}</td><td>{types}</td>"
            "<td>{events:,}</td><td>{hosts:,}</td></tr>".format(
                anchor=escape(str(item["anchor"]), quote=True),
                name=escape(str(item["name"])),
                source=escape(str(item["source"])),
                status=escape(str(item["status"])),
                types=escape(", ".join(item.get("event_types", [])) or "—"),
                events=int(item.get("event_count", 0)),
                hosts=int(item.get("host_count", 0)),
            )
            for item in display_modules
        )
        or "<tr><td colspan='6'>No scan-specific module evidence is available for this inventory snapshot.</td></tr>"
    )
    module_sections = "".join(
        "<details class='module-section' id='{anchor}' open><summary><span>{name}</span>"
        "<span class='module-summary'>{source} · {status} · {events:,} events</span></summary>"
        "<div class='module-body'><p class='muted small'>First seen {first_seen} · last seen {last_seen}</p>"
        "{search}<table><thead><tr><th>Time</th><th>Type</th><th>Host / URL</th>"
        "<th>Result fields</th></tr></thead><tbody>{rows}</tbody></table>"
        "<p class='muted small filter-status' aria-live='polite'></p></div></details>".format(
            anchor=escape(str(module["anchor"]), quote=True),
            name=escape(str(module["name"])),
            source=escape(str(module["source"])),
            status=escape(str(module["status"])),
            events=int(module.get("event_count", 0)),
            first_seen=escape(_date(module.get("first_seen"))),
            last_seen=escape(_date(module.get("last_seen"))),
            search=(
                "<label class='module-search-label'>Search this module's fields"
                "<input class='module-search' type='search' data-module-filter "
                "placeholder='Filter by host, URL, event type, status, or result value…'></label>"
                if module.get("results")
                else ""
            ),
            rows="".join(
                "<tr data-module-row data-search='{search_text}'><td>{time}</td><td>{type}</td>"
                "<td>{location}</td><td>{summary}</td></tr>".format(
                    search_text=escape(
                        " ".join(
                            str(value)
                            for value in (
                                result.get("type", ""),
                                result.get("host", ""),
                                result.get("port", ""),
                                result.get("url", ""),
                                " ".join(result.get("tags", [])),
                                result.get("summary", ""),
                                json.dumps(result.get("data"), ensure_ascii=False, default=str),
                            )
                        ),
                        quote=True,
                    ),
                    time=escape(_date(result.get("timestamp"))),
                    type=escape(str(result.get("type", "UNKNOWN"))),
                    location=escape(
                        result.get("url")
                        or (
                            f"{result.get('host')}:{result.get('port')}"
                            if result.get("host") and result.get("port")
                            else result.get("host") or "—"
                        )
                    ),
                    summary=escape(str(result.get("summary", ""))),
                )
                for result in module.get("results", [])
            )
            or "<tr><td colspan='4'>No events from this module were observed for the selected scan. "
            "This does not prove the module completed successfully.</td></tr>",
        )
        for module in display_modules
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
  .table-scroll {{ overflow-x: auto; }} .asset-table {{ min-width: max(100%, {540 + 120 * len(display_modules)}px); }}
  .asset-table th, .asset-table td {{ width: auto; }} .asset-table .module-count {{ white-space: nowrap; }}
  .badge.LOW {{ color: #172334; }} .small {{ font-size: 12px; }}
  a {{ color: #1769aa; }} .module-link {{ font-weight: 700; text-decoration: none; }}
  .module-link:hover {{ text-decoration: underline; }}
  details.module-section {{ background: white; border-radius: 16px; margin-top: 20px; scroll-margin-top: 16px; }}
  details.module-section > summary {{ cursor: pointer; display: flex; justify-content: space-between; gap: 20px;
    padding: 24px 30px; font-size: 20px; font-weight: 750; }}
  details.module-section > summary:hover {{ background: #f8fafc; border-radius: 16px; }}
  .module-summary {{ color: #667484; font-size: 12px; font-weight: 500; text-align: right; }}
  .module-body {{ padding: 0 30px 30px; }}
  .module-search-label {{ display: block; color: #667484; font-size: 12px; font-weight: 700; margin: 16px 0; }}
  .module-search {{ display: block; width: 100%; margin-top: 7px; border: 1px solid #cbd5df; border-radius: 8px;
    padding: 10px 12px; color: #172334; background: white; font: inherit; }}
  .module-search:focus {{ outline: 3px solid #b9dcf7; border-color: #1769aa; }}
  tr[hidden] {{ display: none; }}
  pre {{ white-space: pre-wrap; overflow-wrap: anywhere; background: #111d2b; color: #e8edf4; border-radius: 10px;
    padding: 18px; font-size: 12px; line-height: 1.45; }}
  @media print {{ body {{ background: white; }} main {{ padding: 0; }} header, section, .metric {{ break-inside: avoid; }}
    details.module-section {{ break-inside: auto; }} details.module-section > summary {{ padding-bottom: 8px; }}
    .module-body {{ display: block !important; }} .module-search-label, .filter-status {{ display: none; }} }}
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
<section><h2>Discovered assets</h2><p class='muted small'>All assets currently recorded for this scope. Module columns count scan events associated with that exact host.</p>
<div class='table-scroll'><table class='asset-table'><thead><tr><th>Asset</th><th>Open ports</th><th>Technologies</th>{asset_module_headers}</tr></thead><tbody>{asset_rows}</tbody></table></div></section>
<section><h2>Findings</h2><p class='muted small'>All active, unignored findings currently recorded for this scope.</p>
<table><thead><tr><th>Severity</th><th>Finding</th><th>Asset</th><th>Evidence summary</th></tr></thead><tbody>{finding_rows}</tbody></table></section>
<section><h2>Technologies</h2><p class='muted small'>All recorded technologies and the assets on which they were observed.</p>
<table><thead><tr><th>Technology</th><th>Host count</th><th>Assets</th></tr></thead><tbody>{tech_rows}</tbody></table></section>
<section><h2>Module coverage</h2><p class='muted small'>Scan-scoped event evidence grouped by the module that produced it. A module with no observed events may have completed without results, been skipped, or failed before emitting evidence.</p>
<table><thead><tr><th>Module</th><th>Enabled by</th><th>Status</th><th>Event types</th><th>Events</th><th>Hosts</th></tr></thead><tbody>{module_rows}</tbody></table></section>
{module_sections}
<section><h2>Scope &amp; methodology</h2><p><strong>Target:</strong> {escape(str(target["name"]))}<br>
<strong>Scope:</strong> {scope}<br><strong>Preset:</strong> {escape(str(scan["preset"]["name"]))}<br>
<strong>Effective preset modules:</strong> {escape(", ".join(preset_modules) or "None recorded")}<br>
<strong>Scan started:</strong> {_date(scan.get("started_at"))}<br>
<strong>Scan finished:</strong> {_date(scan.get("finished_at"))}</p>
<p class='muted small'>Sanitized preset definition. Credential-like values are replaced with <code>[REDACTED]</code>.</p>
<pre><code>{preset_json or "{}"}</code></pre>
<p class='muted small'>The numbers are based on {escaped_brand_name}'s stored asset and finding records. A missing finding
does not establish that an asset is secure. Validate and triage findings before distributing this report.</p></section>
</main><script>
(() => {{
  const revealHash = () => {{
    const target = document.getElementById(location.hash.slice(1));
    if (target && target.matches('details.module-section')) target.open = true;
  }};
  document.querySelectorAll('.module-link').forEach(link => link.addEventListener('click', () => {{
    const target = document.querySelector(link.getAttribute('href'));
    if (target) target.open = true;
  }}));
  document.querySelectorAll('[data-module-filter]').forEach(input => input.addEventListener('input', () => {{
    const section = input.closest('.module-section');
    const needle = input.value.trim().toLocaleLowerCase();
    let visible = 0;
    const rows = section.querySelectorAll('[data-module-row]');
    rows.forEach(row => {{
      const match = !needle || row.dataset.search.toLocaleLowerCase().includes(needle);
      row.hidden = !match;
      if (match) visible += 1;
    }});
    section.querySelector('.filter-status').textContent = needle ? `${{visible}} of ${{rows.length}} records shown` : '';
  }}));
  window.addEventListener('hashchange', revealHash);
  revealHash();
}})();
</script></body></html>"""


async def create_report(client, scan, directory=None):
    """Collect scoped queries through the public API and write the report."""
    snapshot = await collect_report(client, scan=scan)
    path = report_path(scan, directory)
    return write_report(snapshot, "html", path)


async def collect_report(client, *, scan=None, target=None, domain=None):
    """Query current inventory plus scan-scoped module events when a scan is selected."""
    scan_id = None
    configured_modules = []
    safe_preset = {}
    if scan is not None:
        scan = _as_dict(scan)
        scan_id = str(scan.get("id") or "")
        configured_modules = _configured_modules(scan)
        safe_preset = _safe_preset_value((scan.get("preset") or {}).get("preset") or {})
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
        "id": scan_id or None,
        "name": scan["name"],
        "status": scan["status"],
        "target": {
            "id": str(scan["target"].get("id", "")),
            "name": scan["target"]["name"],
            "target": scan["target"].get("target") or [],
            "seeds": scan["target"].get("seeds") or [],
        },
        "preset": {"name": scan["preset"]["name"], "definition": safe_preset},
        "modules": configured_modules,
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
    scan_events = []
    if scan_id and hasattr(client, "query_events"):
        scan_events = [
            event
            async for event in client.query_events(
                scan=scan_id,
                active=True,
                archived=True,
                sort=["timestamp"],
                fields=["type", "host", "port", "url", "timestamp", "tags", "module", "data", "data_json"],
            )
        ]
        effective_modules = set(configured_modules)
        for raw_event in scan_events:
            event = _as_dict(raw_event)
            data = event.get("data_json")
            if event.get("type") == "SCAN" and isinstance(data, dict):
                effective_modules.update(_preset_module_names(data.get("preset") or {}))
        configured_modules = sorted(effective_modules, key=str.casefold)
        scan["modules"] = configured_modules
    module_results = _build_module_results(scan_events, configured_modules)
    for asset in asset_records:
        asset["module_counts"] = _module_counts_for_host(asset["host"], module_results)
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
        "module_results": module_results,
        "module_event_count": sum(item["event_count"] for item in module_results),
        "definition": "Current active, unignored target or domain inventory; findings can originate from multiple scans. Module results are event evidence from the selected scan only.",
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
                module_results=snapshot.get("module_results", []),
            ),
            encoding="utf-8",
        )
    elif format == "json":
        path.write_text(json.dumps(snapshot, indent=2, default=str), encoding="utf-8")
    elif format == "csv":
        with path.open("w", encoding="utf-8", newline="") as stream:
            writer = csv.DictWriter(
                stream,
                fieldnames=(
                    "record_type",
                    "scope",
                    "severity",
                    "count",
                    "name",
                    "host",
                    "description",
                    "module",
                    "event_type",
                    "timestamp",
                    "status",
                ),
            )
            writer.writeheader()
            writer.writerow(
                {
                    "record_type": "report",
                    "scope": snapshot["scope"],
                    "name": snapshot.get("brand_name", bbcfg.name),
                }
            )
            writer.writerow(
                {
                    "record_type": "preset",
                    "scope": snapshot["scope"],
                    "name": snapshot["scan"]["preset"]["name"],
                    "description": json.dumps(
                        snapshot["scan"]["preset"].get("definition") or {},
                        ensure_ascii=False,
                        sort_keys=True,
                        default=str,
                    ),
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
                for module in snapshot.get("module_results", []):
                    writer.writerow(
                        {
                            "record_type": "asset_module_count",
                            "scope": snapshot["scope"],
                            "host": asset["host"],
                            "module": module["name"],
                            "count": asset.get("module_counts", {}).get(module["name"], 0),
                            "description": "Scan events associated with this exact host",
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
            for module in snapshot.get("module_results", []):
                writer.writerow(
                    {
                        "record_type": "module_summary",
                        "scope": snapshot["scope"],
                        "name": module["name"],
                        "module": module["name"],
                        "status": module["status"],
                        "count": module["event_count"],
                        "description": ", ".join(module.get("event_types", [])) or "No observed event types",
                    }
                )
                for result in module.get("results", []):
                    writer.writerow(
                        {
                            "record_type": "module_result",
                            "scope": snapshot["scope"],
                            "name": module["name"],
                            "module": module["name"],
                            "event_type": result["type"],
                            "timestamp": result.get("timestamp"),
                            "host": result.get("url") or result.get("host", ""),
                            "description": result.get("summary", ""),
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
    body.append(
        Paragraph(
            "Module columns count scan events associated with each exact host.",
            styles["ReportSmall"],
        )
    )
    asset_modules = snapshot.get("module_results", [])
    asset_rows = [["Asset", "Open ports", "Technologies", *[module["name"] for module in asset_modules]]]
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
                *[str(asset.get("module_counts", {}).get(module["name"], 0)) for module in asset_modules],
            ]
        )
    if len(asset_rows) == 1:
        asset_rows.append(["No assets recorded.", "", "", *["" for module in asset_modules]])
    if asset_modules:
        module_width = 245 / len(asset_modules)
        asset_widths = [105, 55, 90, *[module_width for module in asset_modules]]
    else:
        asset_widths = [205, 85, 205]
    asset_table = Table(asset_rows, colWidths=asset_widths, repeatRows=1)
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
    body.append(Paragraph("Module coverage", styles["ReportSection"]))
    body.append(
        Paragraph(
            "Scan-scoped event evidence grouped by producing module. No observed events does not prove successful execution.",
            styles["ReportSmall"],
        )
    )
    module_rows = [["Module", "Enabled by", "Status", "Event types", "Events", "Hosts"]]
    for module in snapshot.get("module_results", []):
        module_rows.append(
            [
                Paragraph(xml_escape(str(module["name"])), styles["ReportCell"]),
                Paragraph(xml_escape(str(module["source"])), styles["ReportCell"]),
                Paragraph(xml_escape(str(module["status"])), styles["ReportCell"]),
                Paragraph(xml_escape(", ".join(module.get("event_types", [])) or "—"), styles["ReportCell"]),
                str(module.get("event_count", 0)),
                str(module.get("host_count", 0)),
            ]
        )
    if len(module_rows) == 1:
        module_rows.append(["No scan-specific module evidence available.", "", "", "", "", ""])
    module_table = Table(module_rows, colWidths=[85, 75, 85, 155, 45, 45], repeatRows=1)
    module_table.setStyle(table_style)
    body.append(module_table)
    for module in snapshot.get("module_results", []):
        body.append(Paragraph("Module: " + xml_escape(str(module["name"])), styles["ReportSection"]))
        if not module.get("results"):
            body.append(
                Paragraph(
                    "No events from this module were observed for the selected scan. This does not prove the module completed successfully.",
                    styles["ReportSmall"],
                )
            )
            continue
        result_rows = [["Time", "Type", "Host / URL", "Result summary"]]
        for result in module["results"]:
            location = result.get("url") or (
                f"{result.get('host')}:{result.get('port')}"
                if result.get("host") and result.get("port")
                else result.get("host") or "—"
            )
            result_rows.append(
                [
                    Paragraph(xml_escape(_date(result.get("timestamp"))), styles["ReportCell"]),
                    Paragraph(xml_escape(str(result.get("type", "UNKNOWN"))), styles["ReportCell"]),
                    Paragraph(xml_escape(str(location)), styles["ReportCell"]),
                    Paragraph(xml_escape(str(result.get("summary", ""))), styles["ReportCell"]),
                ]
            )
        result_table = Table(result_rows, colWidths=[85, 85, 130, 195], repeatRows=1)
        result_table.setStyle(table_style)
        body.append(result_table)
    body.append(Paragraph("Scope &amp; methodology", styles["ReportSection"]))
    preset_modules = [
        module["name"] for module in snapshot.get("module_results", []) if module.get("source") == "preset"
    ]
    scan = snapshot["scan"]
    body.append(
        Paragraph(
            "<b>Target:</b> {target}<br/><b>Scope:</b> {scope}<br/><b>Preset:</b> {preset}<br/>"
            "<b>Effective preset modules:</b> {modules}<br/><b>Scan started:</b> {started}<br/>"
            "<b>Scan finished:</b> {finished}".format(
                target=xml_escape(str(scan["target"]["name"])),
                scope=scope,
                preset=xml_escape(str(scan["preset"]["name"])),
                modules=xml_escape(", ".join(preset_modules) or "None recorded"),
                started=xml_escape(_date(scan.get("started_at"))),
                finished=xml_escape(_date(scan.get("finished_at"))),
            ),
            styles["ReportCell"],
        )
    )
    body.append(
        Paragraph(
            "Sanitized preset definition. Credential-like values are replaced with [REDACTED].",
            styles["ReportSmall"],
        )
    )
    preset_json = json.dumps(
        scan["preset"].get("definition") or {}, indent=2, ensure_ascii=False, sort_keys=True, default=str
    )
    body.append(
        Paragraph(
            xml_escape(preset_json).replace(" ", "&#160;").replace("\n", "<br/>"),
            styles["ReportCell"],
        )
    )
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
