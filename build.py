#!/usr/bin/env python3
"""Build the public House Watch page (index.html) from tracker listing JSON files.

Usage: python3 build.py <dir with listing *.json files> [meta_run.json]

Each JSON file is one listing document exported from the tracker
(ArtifactData list with out_dir). Dismissed, failed and off-market
listings are left off the public page.
"""
import html, json, re, sys
from datetime import datetime
from pathlib import Path
from urllib.parse import quote

REPO = "https://github.com/SteveSnow/house-watch"
# Street View Static API key, restricted to https://stevesnow.github.io/* and the Street View Static API only.
SV_KEY = "AIzaSyDax9Uio9_visvmdKFMegrracv757NbjlI"

PRIVATE = [  # never published
    (re.compile(r"Merck(?: West Point)?(?: site)?", re.I), "the work site"),
    (re.compile(r"333 Llandrillo(?: R(?:oa)?d)?", re.I), "Bala Cynwyd"),
]

def scrub(v):
    s = "" if v is None else str(v)
    for rx, rep in PRIVATE:
        s = rx.sub(rep, s)
    return s

def e(v):
    return html.escape(scrub(v), quote=True)

def money(n):
    return f"${n:,.0f}" if isinstance(n, (int, float)) else "—"

def load(dir_):
    rows = []
    for p in sorted(Path(dir_).glob("*.json")):
        try:
            d = json.loads(p.read_text())
        except Exception:
            continue
        d = d.get("data", d) if isinstance(d, dict) else {}
        d.setdefault("id", p.stem)
        rows.append(d)
    return rows

def visible(r):
    return (r.get("userStatus") != "dismissed" and r.get("verdict") != "fail"
            and r.get("listingStatus", "active") in ("active", "", None))

def sources_table(r):
    src = r.get("sources") or []
    if not src:
        return ""
    out = []
    for s in src:
        def cell(val, ok, fmt=None):
            txt = fmt(val) if fmt else (val if val not in (None, "") else "—")
            return f'<td class="{"" if ok else "off"}">{e(txt)}</td>'
        price_ok = s.get("price") is None or s.get("price") == r.get("price")
        status_ok = not s.get("status") or str(s.get("status")).strip().lower() == "active"
        beds_ok = s.get("beds") is None or r.get("beds") is None or s.get("beds") == r.get("beds")
        mls_ok = not s.get("mls") or not r.get("mls") or s.get("mls") == r.get("mls")
        site = e(s.get("site"))
        if s.get("url"):
            site = f'<a href="{e(s["url"])}" target="_blank" rel="noopener">{site}</a>'
        out.append(f'<tr><td class="site">{site}</td>{cell(s.get("price"), price_ok, money)}'
                   f'{cell(s.get("status"), status_ok)}{cell(s.get("beds"), beds_ok)}'
                   f'{cell(s.get("mls"), mls_ok)}<td class="note">{e(s.get("note"))}</td></tr>')
    return ('<div class="src"><table><thead><tr><th>Listed on</th><th>Price</th><th>Status</th>'
            '<th>Beds</th><th>MLS #</th><th>Note</th></tr></thead><tbody>' + "".join(out) + "</tbody></table></div>")

FEAT_K = {"yes": ("good", "Open kitchen: yes"), "likely": ("good", "Open kitchen: likely"), "maybe": ("mid", "Open kitchen: maybe"),
          "no": ("", "Open kitchen: no"), "unknown": ("", "Open kitchen: not described")}
FEAT_P = {"walk-in": ("good", "Walk-in pantry: yes"), "likely": ("good", "Walk-in pantry: likely"), "pantry": ("mid", "Pantry, walk-in not stated"),
          "no": ("", "No pantry mentioned"), "unknown": ("", "Pantry: not described")}

def features(r):
    if not r.get("kitchenOpen") and not r.get("pantry"):
        return ""
    k = FEAT_K.get(r.get("kitchenOpen"), FEAT_K["unknown"]); p = FEAT_P.get(r.get("pantry"), FEAT_P["unknown"])
    return (f'<div class="feat"><div class="ft {k[0]}"><b>{k[1]}</b><span>{e(r.get("kitchenNote"))}</span></div>'
            f'<div class="ft {p[0]}"><b>{p[1]}</b><span>{e(r.get("pantryNote"))}</span></div></div>')

def card(r):
    match = r.get("verdict") == "match"
    pill = '<span class="pill match">Meets all criteria</span>' if match else '<span class="pill check">Needs a check</span>'
    saved = '<span class="pill saved">✓ Want to see</span>' if r.get("userStatus") == "saved" else ""
    links = []
    if r.get("url") or r.get("redfinUrl"):
        links.append(("Photos", r.get("url") or r.get("redfinUrl")))
    if isinstance(r.get("lat"), (int, float)) and isinstance(r.get("lng"), (int, float)):
        links.append(("Street View", f'https://www.google.com/maps/@?api=1&map_action=pano&viewpoint={r["lat"]},{r["lng"]}'))
    elif r.get("address"):
        links.append(("Map", "https://www.google.com/maps/search/?api=1&query=" + quote(f'{r["address"]}, {r.get("town","")}')))
    if r.get("redfinUrl"):
        links.append(("Redfin", r["redfinUrl"]))
    link_html = "".join(f'<a href="{e(u)}" target="_blank" rel="noopener">{t}</a>' for t, u in links)
    slug = r.get("id", "")
    def issue(kind):
        title = f'{kind}: {scrub(r.get("address",""))} [{slug}]'
        body = ("Click \"Submit new issue\" to record this. The daily search applies it the next morning "
                "and closes this issue.")
        return f"{REPO}/issues/new?title={quote(title)}&body={quote(body)}"
    see_on = r.get("userStatus") == "saved"
    actions = (f'<div class="actions"><a class="btn{" on" if see_on else ""}" href="{e(issue("UNSEE" if see_on else "SEE"))}" target="_blank" rel="noopener">'
               f'{"✓ Want to see (undo)" if see_on else "Want to see"}</a>'
               f'<a class="btn dismiss" href="{e(issue("DISMISS"))}" target="_blank" rel="noopener">Dismiss</a>'
               f'<span class="hint">Opens a GitHub form; applied by the next morning&rsquo;s update.</span></div>')
    photo = ""
    if isinstance(r.get("lat"), (int, float)) and isinstance(r.get("lng"), (int, float)):
        src = (f"https://maps.googleapis.com/maps/api/streetview?size=640x300&scale=2&fov=80&source=outdoor"
               f"&location={r['lat']},{r['lng']}&key={SV_KEY}")
        sv = f"https://www.google.com/maps/@?api=1&map_action=pano&viewpoint={r['lat']},{r['lng']}"
        photo = (f'<a class="photo" href="{e(sv)}" target="_blank" rel="noopener">'
                 f'<img src="{e(src)}" alt="Street View of {e(r.get("address"))}" loading="lazy" '
                 f'onerror="this.parentNode.remove()"></a>')
    addr = e(r.get("address"))
    if r.get("url"):
        addr = f'<a href="{e(r["url"])}" target="_blank" rel="noopener">{addr}</a>'
    flags = f'<p class="flags"><strong>Sites disagree:</strong> {e(r["flags"])}</p>' if r.get("flags") else ""
    notes = f'<p class="notes">{e(r["notes"])}</p>' if r.get("notes") else ""
    dl = "".join(f"<div><dt>{k}</dt><dd>{e(r.get(f))}</dd></div>" for k, f in [
        ("Taxes", "taxes"), ("Schools (GreatSchools)", "schools"), ("Nearest golf", "golf"),
        ("Highway", "highway"), ("Sidewalk", "sidewalk"), ("Drive to Bala Cynwyd", "drive"),
        ("Drive to work site", "merck")])
    return f"""<article class="card">
  {photo}
  <div class="top"><h2 class="addr">{addr}</h2><span class="price">{money(r.get("price"))}</span></div>
  <div class="meta">{pill}{saved}<span>{e(r.get("town"))}</span><span>{e(r.get("bedsBaths"))}</span><span>found {e(str(r.get("firstSeen",""))[:10])}</span>{link_html}</div>
  <dl>{dl}</dl>
  {features(r)}
  {flags}
  {sources_table(r)}
  {notes}
  {actions}
</article>"""

def build(rows, meta):
    rows = [r for r in rows if visible(r)]
    rows.sort(key=lambda r: (r.get("verdict") != "match", str(r.get("firstSeen", ""))), reverse=False)
    want = [r for r in rows if r.get("userStatus") == "saved"]
    rest = [r for r in rows if r.get("userStatus") != "saved"]
    matches = [r for r in rest if r.get("verdict") == "match"]
    checks = [r for r in rest if r.get("verdict") != "match"]
    def section(title, items, empty):
        body = "".join(card(r) for r in items) or f'<div class="empty">{empty}</div>'
        return f'<section><h2 class="sec">{title} <span class="count">{len(items)}</span></h2><div class="list">{body}</div></section>'
    run = scrub(meta.get("summary", "")) if meta else ""
    last = str(meta.get("lastRun", ""))[:16].replace("T", " ") if meta else ""
    built = datetime.now().strftime("%Y-%m-%d %H:%M")
    return TEMPLATE.format(
        run=html.escape(f"Last search {last} · {run}" if last else f"Updated {built}"),
        want=section("Want to see", want, "Nothing marked yet. Use “Want to see” on any house below."),
        matches=section("Meets all criteria", matches, "No full matches right now."),
        checks=section("Needs a check", checks, "Nothing waiting on a check."),
        built=html.escape(built))

TEMPLATE = """<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>House Watch</title>
<meta name="robots" content="noindex">
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Bricolage+Grotesque:opsz,wght@12..96,600;12..96,700&family=Instrument+Sans:wght@400;500;600&family=IBM+Plex+Mono:wght@400;500&display=swap">
<style>
:root{{--bg:#f3f5f4;--surface:#fff;--fg:#1b2422;--muted:#5d6b67;--line:#d7dedb;--accent:#1f6f5c;--accent-soft:#e1efe9;--warn:#a4660b;--warn-soft:#f8ecd8;
--display:"Bricolage Grotesque",ui-sans-serif,system-ui,sans-serif;--body:"Instrument Sans",ui-sans-serif,system-ui,sans-serif;--mono:"IBM Plex Mono",ui-monospace,Menlo,monospace;color-scheme:light}}
@media (prefers-color-scheme:dark){{:root{{--bg:#121816;--surface:#1a2220;--fg:#e4ebe8;--muted:#97a6a1;--line:#2c3734;--accent:#5fc3a6;--accent-soft:#1d3a32;--warn:#e2a64a;--warn-soft:#3a2d17;color-scheme:dark}}}}
*{{box-sizing:border-box}}body{{margin:0;background:var(--bg);color:var(--fg);font-family:var(--body);font-size:15px;line-height:1.5}}
.wrap{{max-width:900px;margin:0 auto;padding:28px max(16px,env(safe-area-inset-right)) 56px max(16px,env(safe-area-inset-left));display:grid;gap:24px}}
h1{{font-family:var(--display);font-size:clamp(28px,5vw,40px);margin:0;line-height:1.1}}
.sub{{color:var(--muted);margin:4px 0 0}}.run{{font-family:var(--mono);font-size:12.5px;color:var(--muted);margin-top:6px}}
.criteria{{display:flex;flex-wrap:wrap;gap:6px}}.chip{{font-family:var(--mono);font-size:12px;border:1px solid var(--line);border-radius:999px;padding:3px 10px;background:var(--surface)}}
.sec{{font-family:var(--display);font-size:20px;margin:0 0 10px}}.count{{font-family:var(--mono);font-size:14px;color:var(--muted)}}
.list{{display:grid;gap:14px}}.card{{background:var(--surface);border:1px solid var(--line);border-radius:12px;padding:16px 18px;display:grid;gap:10px;min-width:0}}
.top{{display:flex;flex-wrap:wrap;justify-content:space-between;gap:6px 16px;align-items:baseline}}
.addr{{font-family:var(--display);font-weight:600;font-size:19px;margin:0}}.addr a{{color:inherit;text-underline-offset:3px;text-decoration-color:var(--line)}}
.price{{font-family:var(--mono);font-size:16px;font-weight:500}}.meta{{display:flex;flex-wrap:wrap;gap:4px 14px;color:var(--muted);font-size:13.5px;align-items:center}}
.pill{{font-size:12px;font-weight:600;padding:2px 9px;border-radius:999px}}.pill.match{{background:var(--accent-soft);color:var(--accent)}}.pill.check{{background:var(--warn-soft);color:var(--warn)}}.pill.saved{{border:1px solid var(--accent);color:var(--accent)}}
dl{{display:grid;grid-template-columns:repeat(auto-fit,minmax(170px,1fr));gap:8px 18px;margin:0}}dt{{font-size:11px;text-transform:uppercase;letter-spacing:.06em;color:var(--muted)}}dd{{margin:0;font-family:var(--mono);font-size:13px;overflow-wrap:anywhere}}
.flags{{margin:0;font-size:13.5px;color:var(--warn);background:var(--warn-soft);border-radius:8px;padding:8px 10px}}
.src{{overflow-x:auto;border:1px solid var(--line);border-radius:8px}}.src table{{border-collapse:collapse;width:100%;font-size:13px;min-width:640px}}
.src th{{font-size:11px;text-transform:uppercase;letter-spacing:.06em;color:var(--muted);text-align:left;padding:6px 10px;border-bottom:1px solid var(--line)}}
.src td{{padding:6px 10px;border-bottom:1px solid var(--line);font-family:var(--mono);vertical-align:top}}.src tr:last-child td{{border-bottom:0}}
.src td.site{{font-family:var(--body);font-weight:600}}.src td.site a{{color:var(--accent)}}.src td.off{{background:var(--warn-soft);color:var(--warn);font-weight:600}}.src td.off::before{{content:"≠ "}}
.src td.note{{min-width:220px;font-family:var(--body);color:var(--muted);font-size:12.5px}}.notes{{margin:0;font-size:14px;border-top:1px dashed var(--line);padding-top:10px}}
.meta a{{color:var(--accent);font-weight:600}}
.feat{{display:grid;grid-template-columns:repeat(auto-fit,minmax(240px,1fr));gap:8px}}.ft{{border:1px solid var(--line);border-radius:8px;padding:8px 10px;font-size:13.5px;min-width:0}}
.ft b{{display:block;font-size:13px}}.ft span{{color:var(--muted);font-size:12.5px}}.ft.good{{border-color:var(--accent);background:var(--accent-soft)}}.ft.good b{{color:var(--accent)}}.ft.mid b{{color:var(--warn)}}
.photo{{display:block;margin:-16px -18px 0;border-radius:12px 12px 0 0;overflow:hidden;background:var(--line);aspect-ratio:640/300}}
.photo img{{display:block;width:100%;height:100%;object-fit:cover}}
.actions{{display:flex;flex-wrap:wrap;gap:8px;align-items:center}}
.btn{{font-size:13px;font-weight:600;border:1px solid var(--line);background:var(--bg);color:var(--fg);border-radius:8px;padding:5px 12px;text-decoration:none}}
.btn.on{{border-color:var(--accent);color:var(--accent);background:var(--accent-soft)}}.btn.dismiss{{color:var(--muted)}}
.hint{{font-size:12px;color:var(--muted)}}
.empty{{color:var(--muted);border:1px dashed var(--line);border-radius:12px;padding:20px;text-align:center}}footer{{font-size:12.5px;color:var(--muted)}}
</style></head><body><div class="wrap">
<header><h1>House Watch</h1><p class="sub">4-bedroom homes in the Philadelphia suburbs, checked every morning against our criteria.</p><div class="run">{run}</div></header>
<div class="criteria"><span class="chip">4+ bd</span><span class="chip">$750K–$1.25M</span><span class="chip">schools &gt;6 (E/M/H)</span><span class="chip">sidewalk</span><span class="chip">≥1,000 ft from highway</span><span class="chip">≥1 mi from golf</span><span class="chip">taxes &lt;$15K</span><span class="chip">commute limits</span></div>
{want}
{matches}
{checks}
<footer>In each “Listed on” table, a highlighted ≠ cell differs from the best current price, bedroom count or MLS number shown at the top of the card, or shows a status other than active. Golf distances are measured to the clubhouse, so a course edge can be up to half a mile closer. Drive times are estimates. Page built {built}.</footer>
</div></body></html>
"""

if __name__ == "__main__":
    rows = load(sys.argv[1])
    meta = {}
    if len(sys.argv) > 2 and Path(sys.argv[2]).exists():
        m = json.loads(Path(sys.argv[2]).read_text())
        meta = m.get("data", m)
    Path(__file__).with_name("index.html").write_text(build(rows, meta))
    print(f"Wrote index.html with {sum(visible(r) for r in rows)} listings")
