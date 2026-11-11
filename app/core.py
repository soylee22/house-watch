"""Private, observation-based property monitor. No portal crawling or mail sending."""
from __future__ import annotations

import csv
import hashlib
import html
import json
import os
import re
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[2]
STATE = ROOT / "private/house-watch"
TOWNS = {
    "Linslade": {"county": "Bedfordshire", "lat": 51.918, "lon": -0.678, "station": "Leighton Buzzard"},
    "Didcot": {"county": "Oxfordshire", "lat": 51.609, "lon": -1.244, "station": "Didcot Parkway"},
    "Flitwick": {"county": "Bedfordshire", "lat": 52.003, "lon": -0.495, "station": "Flitwick"},
    "Hitchin": {"county": "Hertfordshire", "lat": 51.952, "lon": -0.276, "station": "Hitchin"},
    "Fleet": {"county": "Hampshire", "lat": 51.283, "lon": -0.842, "station": "Fleet"},
}
NOW = lambda: datetime.now(timezone.utc).isoformat(timespec="seconds")

SCHEMA = """
PRAGMA foreign_keys=ON;
CREATE TABLE IF NOT EXISTS metadata(key TEXT PRIMARY KEY,value TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS properties(id TEXT PRIMARY KEY,created TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS listings(key TEXT PRIMARY KEY,property_id TEXT NOT NULL REFERENCES properties(id),url TEXT NOT NULL,source TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS observations(id TEXT PRIMARY KEY,listing_key TEXT NOT NULL REFERENCES listings(key),observed_at TEXT NOT NULL,received_at TEXT NOT NULL,payload TEXT NOT NULL,provenance TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS obs_time ON observations(listing_key,observed_at);
CREATE TABLE IF NOT EXISTS events(id TEXT PRIMARY KEY,property_id TEXT NOT NULL,kind TEXT NOT NULL,observed_at TEXT NOT NULL,old_value TEXT,new_value TEXT,provenance TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS feedback(property_id TEXT NOT NULL,person TEXT NOT NULL CHECK(person IN ('Lee','Min')),reaction TEXT NOT NULL CHECK(reaction IN ('like','maybe','no','watch')),notes TEXT NOT NULL,updated TEXT NOT NULL,PRIMARY KEY(property_id,person));
CREATE TABLE IF NOT EXISTS runs(id INTEGER PRIMARY KEY,source TEXT NOT NULL,started TEXT NOT NULL,success INTEGER NOT NULL,observations INTEGER NOT NULL,detail TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS messages(id TEXT PRIMARY KEY,observed_at TEXT NOT NULL,subject TEXT NOT NULL,parsed INTEGER NOT NULL,warnings TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS outbox(key TEXT PRIMARY KEY,created TEXT NOT NULL,status TEXT NOT NULL,recipients TEXT NOT NULL,subject TEXT NOT NULL,html TEXT NOT NULL,plain TEXT NOT NULL,provider_id TEXT);
CREATE TABLE IF NOT EXISTS transactions(id TEXT PRIMARY KEY,price INTEGER NOT NULL,date TEXT NOT NULL,postcode TEXT,type TEXT,new_build TEXT,tenure TEXT,number TEXT,unit TEXT,street TEXT,town TEXT,district TEXT,category TEXT,release TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS transaction_geography(transaction_id TEXT PRIMARY KEY REFERENCES transactions(id) ON DELETE CASCADE,locality TEXT NOT NULL,postal_town TEXT NOT NULL,market TEXT NOT NULL,evidence TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS transaction_lookup ON transactions(town,type,street,date);
CREATE TABLE IF NOT EXISTS episodes(id TEXT PRIMARY KEY,property_id TEXT NOT NULL,first_observed TEXT NOT NULL,last_observed TEXT NOT NULL,start_known INTEGER NOT NULL DEFAULT 0,reason TEXT NOT NULL);
"""


@contextmanager
def connect(state=STATE):
    state = Path(state)
    state.mkdir(parents=True, exist_ok=True, mode=0o700)
    db = sqlite3.connect(state / "watch.sqlite", timeout=30)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA journal_mode=WAL")
    db.executescript(SCHEMA)
    db.execute("INSERT OR REPLACE INTO metadata VALUES('schema_version','1')")
    try:
        yield db
        db.commit()
    except BaseException:
        db.rollback()
        raise
    finally:
        db.close()


def stable(*parts):
    return hashlib.sha256(json.dumps(parts, sort_keys=True, ensure_ascii=False).encode()).hexdigest()[:24]


def canonical_url(url):
    p = urlsplit(html.unescape(url).strip())
    if p.scheme not in ("http", "https") or not p.hostname or p.username or p.password:
        raise ValueError("A public HTTP(S) listing link is required")
    return urlunsplit(("https", p.netloc.lower(), re.sub(r"/+", "/", p.path).rstrip("/"), "", ""))


def clean(text):
    return re.sub(r"\s+", " ", html.unescape(str(text or ""))).strip()


def town_for(address, subject=""):
    for name in TOWNS:
        if re.search(r"\b" + name + r"\b", address, re.I):
            return name, "address"
    # An alert search is not proof that a recommended nearby address is in town.
    if re.search(r"\bLeighton Buzzard\b", address, re.I) and re.search(r"\bLinslade\b", subject, re.I):
        return "Linslade", "search boundary unverified"
    return None, "outside or unknown"


def parse_email(message):
    """Read the user's existing alert HTML, never fetch a linked portal page."""
    from bs4 import BeautifulSoup

    subject = clean(message.get("subject"))
    raw = message.get("html", "")
    if "for sale" not in subject.lower() and "weekly property update" not in subject.lower():
        return [], ["Not a sale alert"]
    # Providers use explicit card comments. End markers occur once per card.
    # Some daily emails repeat END but omit BEGIN on the second and later cards.
    # Split on card ends so these cards cannot disappear silently.
    blocks = re.split(r"<!--[^>]*(?:PROPERTY LISTING|LISTING CARD)[^>]*END[^>]*-->", raw, flags=re.I)[:-1]
    out, warnings = [], []
    for block in blocks:
        starts=list(re.finditer(r'<!--[^>]*(?:PROPERTY LISTING|LISTING CARD)[^>]*BEGIN[^>]*-->',block,re.I))
        if starts:
            block=block[starts[-1].end():]
        soup = BeautifulSoup(block, "html.parser")
        text = clean(soup.get_text(" ", strip=True))
        links = [a.get("href", "") for a in soup.find_all("a")]
        links = [u for u in links if re.search(r"zoopla\.co\.uk/(?:for-sale|new-homes)/details/\d+", u)]
        if not links:
            continue
        url = canonical_url(links[0])
        # Weekly cards include short features; daily cards include a property title.
        bed = re.search(r"\b(\d+)\s*(?:bed(?:room)?s?)\b", text, re.I)
        bath = re.search(r"\b(\d+)\s*baths?\b", text, re.I)
        prices = re.findall(r"£\s*([\d,]+)", text)
        price = int(prices[0].replace(",", "")) if prices else None
        title = re.search(r"\b\d+\s*bed\s+(.+?)\s+for sale\s+(.+?)(?=View property|Call agent|\d{4,5}\s*\d{6}|$)", text, re.I)
        address = clean(title.group(2)) if title else ""
        if not address:
            anchors = [clean(a.get_text(" ", strip=True)) for a in soup.find_all("a", href=True) if re.search(r"/details/\d+", a["href"])]
            candidates = [a for a in anchors if re.search(r"\b[A-Z]{1,2}\d[A-Z\d]?\b", a) and not a.startswith("£")]
            address = min(candidates, key=len) if candidates else ""
        town, location_evidence = town_for(address, subject)
        if town is None:
            warnings.append("Card outside the five towns or missing usable address")
            continue
        kind = title.group(1).lower() if title else "unknown"
        if "link" in kind and "detached" in kind:
            kind = "link-detached"
        elif "semi" in kind:
            kind = "semi-detached"
        elif "detached" in kind:
            kind = "detached"
        elif "terrace" in kind or "town house" in kind or "townhouse" in kind:
            kind = "terraced"
        elif any(x in kind for x in ("flat", "maisonette", "apartment")):
            kind = "flat"
        else:
            kind = "unknown"
        recommendation = "similar_listing" in links[0] and "weekly" not in subject.lower()
        if recommendation:
            warnings.append("Nearby recommendation retained for review only")
        boundary_warning = bool(re.search(r"\bSt\.? Ippolyts\b|\bStotfold\b|\bLower Stondon\b|\bChurch Crookham\b", address, re.I))
        out.append(dict(url=url, source="Zoopla email", title=address or "Address unknown", town=town,
                        bedrooms=int(bed.group(1)) if bed else None, bathrooms=int(bath.group(1)) if bath else None,
                        price=price, house_type=kind, parking="unknown", status="advertised in email",
                        tenure="unknown", area_m2=None, observed_at=message["observed_at"],
                        provenance="gmail:" + message["id"], location_evidence=location_evidence,
                        recommendation=recommendation, boundary_warning=boundary_warning, qualifier="offers over" if "offers over" in text.lower() else "guide" if "guide price" in text.lower() else "asking",
                        excerpt=text[:1200], neighbourhood="unverified"))
        cut = re.search(r"reduced by\s*£\s*([\d,]+)",text,re.I)
        if cut:
            out[-1]['advertised_reduction'] = int(cut.group(1).replace(',',''))
    expected = re.search(r"(?:New listings?:|Price reduced:)\s*(\d+)", subject, re.I)
    if expected and len(out)<int(expected.group(1)):
        warnings.append(f"Email advertises {expected.group(1)} matches, but {len(out)} supported-town cards were recovered. Discovery is incomplete")
    if not out:
        warnings.append("No supported eligible-town cards parsed. Alert body may be incomplete")
    return out, warnings


def validate(item):
    item = dict(item)
    item["url"] = canonical_url(item["url"])
    if item.get("town") not in TOWNS:
        raise ValueError("Town must be one of the five search places")
    if item.get('house_type','unknown') not in ('detached','semi-detached','link-detached','terraced','flat','unknown'):
        raise ValueError('Unsupported house type')
    if item.get('status','').lower() in ('sold stc','sale agreed','sold subject to contract'):
        item['status']='SSTC'
    for k in ("price", "bedrooms", "bathrooms", "area_m2"):
        v = item.get(k)
        if v is not None and (isinstance(v, bool) or not isinstance(v, (int, float)) or v <= 0):
            raise ValueError(f"Invalid {k}")
    if not item.get("provenance"):
        raise ValueError("Provenance is required")
    ts = datetime.fromisoformat(item.get("observed_at", NOW()).replace("Z", "+00:00"))
    if ts.tzinfo is None:
        raise ValueError("Observation timestamp needs a timezone")
    item["observed_at"] = ts.astimezone(timezone.utc).isoformat(timespec="seconds")
    return item


def ingest(db, items):
    inserted = 0
    for raw in sorted(items, key=lambda x: x.get("observed_at", "")):
        item = validate(raw)
        url = item["url"]
        key = stable(url)
        pid = item.pop("property_id", None)
        existing = db.execute("SELECT property_id FROM listings WHERE key=?", (key,)).fetchone()
        if existing:
            pid = existing[0]
        elif pid:
            if not db.execute("SELECT 1 FROM properties WHERE id=?", (pid,)).fetchone():
                raise ValueError("Explicit linked property does not exist")
        else:
            pid = stable("property", url)
            db.execute("INSERT OR IGNORE INTO properties VALUES(?,?)", (pid, NOW()))
        db.execute("INSERT OR IGNORE INTO listings VALUES(?,?,?,?)", (key, pid, url, item.get("source", "manual")))
        oid = stable(key, item["observed_at"], item["provenance"], item)
        if db.execute("SELECT 1 FROM observations WHERE id=?", (oid,)).fetchone():
            continue
        db.execute("INSERT INTO observations VALUES(?,?,?,?,?,?)", (oid, key, item["observed_at"], NOW(), json.dumps(item, ensure_ascii=False), item["provenance"]))
        inserted += 1
        # Rebuild the timeline so backfills/out-of-order arrivals cannot invent changes.
        rebuild_events(db, pid)
    return inserted


def timeline(db, pid):
    return [json.loads(r[0]) for r in db.execute("SELECT o.payload FROM observations o JOIN listings l ON l.key=o.listing_key WHERE l.property_id=? ORDER BY o.observed_at,o.received_at,o.id", (pid,))]


def rebuild_events(db, pid):
    rows = timeline(db, pid)
    db.execute("DELETE FROM events WHERE property_id=?", (pid,))
    prev = None
    for item in rows:
        changes = [("first observed", None, item.get("price"))] if prev is None else []
        if prev:
            for field, label in (("price", "price changed"), ("status", "status changed")):
                if item.get(field) is not None and prev.get(field) is not None and item[field] != prev[field]:
                    changes.append((label, prev[field], item[field]))
        for kind, old, new in changes:
            eid = stable(pid, kind, item["observed_at"], old, new)
            db.execute("INSERT OR IGNORE INTO events VALUES(?,?,?,?,?,?,?)", (eid, pid, kind, item["observed_at"], json.dumps(old), json.dumps(new), item["provenance"]))
        if item.get('advertised_reduction'):
            eid=stable(pid,'advertised reduction',item['observed_at'],item['advertised_reduction'])
            db.execute('INSERT OR IGNORE INTO events VALUES(?,?,?,?,?,?,?)',(eid,pid,'advertised reduction',item['observed_at'],json.dumps(None),json.dumps(item['advertised_reduction']),item['provenance']))
        prev = item
    if rows:
        db.execute("INSERT OR REPLACE INTO episodes VALUES(?,?,?,?,0,?)", (stable(pid, "initial episode"), pid, rows[0]["observed_at"], rows[-1]["observed_at"], "Observed marketing history. Original launch and separate campaigns unverified"))


def import_mail(db, messages):
    total, warnings = 0, []
    for m in sorted(messages, key=lambda x: x["observed_at"]):
        if db.execute("SELECT 1 FROM messages WHERE id=?", (m["id"],)).fetchone():
            continue
        items, issues = parse_email(m)
        total += ingest(db, items)
        db.execute("INSERT INTO messages VALUES(?,?,?,?,?)", (m["id"], m["observed_at"], m["subject"], len(items), json.dumps(issues)))
        warnings.extend(issues)
    db.execute("INSERT INTO runs(source,started,success,observations,detail) VALUES(?,?,?,?,?)", ("mailbox", NOW(), 1, total, json.dumps({"messages":len(messages),"warnings":len(warnings),"coverage":"Partial personal-alert history, not a current whole-market feed"})))
    return {"observations_added": total, "messages": len(messages), "warnings":len(warnings)}


def eligibility(p):
    reasons = []
    if p.get("bedrooms") is None:
        reasons.append("Bedrooms unknown")
    elif p["bedrooms"] < 4:
        return "excluded", ["Fewer than four bedrooms"]
    if p.get("price") is None:
        reasons.append("Asking price unknown")
    elif p["price"] > 700000:
        return "excluded", ["Above £700,000 discovery ceiling"]
    if p.get("house_type") == "flat":
        return "excluded", ["Flat or maisonette"]
    if p.get("house_type", "unknown") == "unknown":
        reasons.append("House type needs checking")
    if p.get("recommendation"):
        reasons.append("Nearby recommendation")
    if p.get('price_max') and p['price_max']>700000:
        reasons.append('Advertised price range crosses £700,000')
    if p.get("location_evidence") == "search boundary unverified":
        reasons.append("Linslade boundary needs checking")
    if p.get("boundary_warning"):
        reasons.append("Neighbouring settlement: town boundary needs checking")
    if p.get("status") in ("withdrawn", "SSTC", "sold", "unavailable", "completed", "under offer"):
        return "archive", ["Not advertised available"]
    restricted = re.search(r"shared ownership|retirement|cash.only|auction|tenanted", p.get("excerpt", ""), re.I)
    if restricted:
        reasons.append("Purchase condition: " + restricted.group(0))
    return ("review" if reasons else "eligible"), reasons


def inventory(db):
    out = []
    for row in db.execute("SELECT id FROM properties"):
        rows = timeline(db, row[0])
        if not rows:
            continue
        p = {}
        # Older richer observations can fill blanks, but provenance remains accessible.
        for obs in rows:
            for k, v in obs.items():
                if k=='location_evidence' and p.get(k)=='address' and v!='address':
                    continue
                if k=='status' and obs.get('source')=='Zoopla email' and p.get(k) in ('SSTC','withdrawn','unavailable','completed','sold'):
                    continue
                if v is not None and v != "unknown" and v != "unverified":
                    p[k] = v
                    p.setdefault('field_provenance',{})[k]={'observed_at':obs['observed_at'],'source':obs.get('provenance')}
                elif k not in p:
                    p[k] = v
        p.update(id=row[0], first_seen=rows[0]["observed_at"], last_seen=rows[-1]["observed_at"], observations=len(rows))
        p["eligibility"], p["review_reasons"] = eligibility(p)
        p["feedback"] = [dict(r) for r in db.execute("SELECT person,reaction,notes,updated FROM feedback WHERE property_id=?", (p["id"],))]
        p["events"] = [dict(r) for r in db.execute("SELECT * FROM events WHERE property_id=? ORDER BY observed_at DESC", (p["id"],))]
        p["station"] = TOWNS[p["town"]]["station"]
        p["county"] = TOWNS[p["town"]]["county"]
        p["age_days"] = max(0, (datetime.now(timezone.utc)-datetime.fromisoformat(p["last_seen"])).days)
        p["fit_reasons"] = fit_reasons(p)
        p['offroad_parking']=offroad_parking(p)
        out.append(p)
    def order(p):
        return (-sum(f["reaction"] in ("like", "watch") for f in p["feedback"]), p.get("price") or 10**9, -(p.get("bedrooms") or 0), p["title"])
    return sorted(out, key=order)


def offroad_parking(p):
    value=p.get('parking','unknown') or 'unknown'
    if value=='unknown':return None
    if re.search(r'\bno\b|communal|on.street|street.only',value,re.I):return False
    return bool(re.search(r'driveway|off.road|off.street|private parking|allocated parking',value,re.I))


def fit_reasons(p):
    r = []
    if p.get("price") and p["price"] <= 600000:
        r.append("Within the earlier £600k reference")
    if p.get("house_type") == "detached":
        r.append("Preferred detached type")
    if offroad_parking(p):
        r.append("Advertised off-road parking")
    else:
        r.append("Parking needs checking")
    if p.get("neighbourhood", "").lower() == "ladygrove":
        r.append("Priority Ladygrove pocket")
    r.append("Exact station route unverified" if not p.get("station_walk_min") else "Station access is an advertised estimate")
    return r


def frontier(items, objective="bedrooms"):
    rows = [p for p in items if p["eligibility"] == "eligible" and p.get("price") and p.get(objective)]
    def dominates(a, b):
        return a["price"] <= b["price"] and a[objective] >= b[objective] and (a["price"] < b["price"] or a[objective] > b[objective])
    return [p["id"] for p in rows if not any(dominates(q,p) for q in rows)]


def feedback(db, pid, person, reaction, notes=""):
    if not db.execute("SELECT 1 FROM properties WHERE id=?", (pid,)).fetchone():
        raise ValueError("Unknown property")
    if person not in ("Lee", "Min") or reaction not in ("like", "maybe", "no", "watch"):
        raise ValueError("Invalid feedback")
    db.execute("INSERT OR REPLACE INTO feedback VALUES(?,?,?,?,?)", (pid, person, reaction, str(notes)[:4000], NOW()))


def import_sales(db, paths):
    from research_data import classify_market
    n = 0
    for path in paths:
        with open(path, newline="", encoding="utf-8-sig") as f:
            for row in csv.reader(f):
                if len(row) < 15:
                    continue
                if len(row)>15 and row[15] == "D":
                    db.execute("DELETE FROM transactions WHERE id=?", (row[0],))
                    continue
                market,evidence=classify_market(row[10],row[11])
                if not market or row[4] not in ("D", "S", "T"):
                    # A correction can move a previously included transaction out of scope.
                    db.execute("DELETE FROM transactions WHERE id=?", (row[0],))
                    continue
                db.execute("INSERT OR REPLACE INTO transactions VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)", (row[0],int(row[1]),row[2][:10],row[3],row[4],row[5],row[6],row[7],row[8],row[9],row[11],row[12],row[14],Path(path).name))
                db.execute("INSERT OR REPLACE INTO transaction_geography VALUES(?,?,?,?,?)",(row[0],row[10],row[11],market,evidence))
                n += 1
    return n


def comparable_sales(db, p, limit=12):
    kinds = {"detached":"D", "semi-detached":"S", "terraced":"T"}
    kind = kinds.get(p.get("house_type"))
    if not kind:
        return {"rows":[], "note":"Confirm house type before matching completed sales", "value_flag":False}
    towns = ("LINSLADE", "LEIGHTON BUZZARD") if p["town"] == "Linslade" else (p["town"].upper(),)
    street = re.split(r",", p["title"])[0].upper().strip()
    marks = ",".join("?" for _ in towns)
    rows = [dict(r) for r in db.execute(f"SELECT t.* FROM transactions t LEFT JOIN transaction_geography g ON g.transaction_id=t.id WHERE (g.market=? OR (g.market IS NULL AND t.town IN ({marks}))) AND type=? AND category='A' AND tenure='F' AND new_build='N' ORDER BY (street=?) DESC,date DESC LIMIT ?", (p['town'],*towns,kind,street,limit))]
    for r in rows:
        r["same_street"] = r["street"] == street
    return {"rows":rows, "note":"Same type, freehold, established homes. Street matches first, then recent market sales. Area, bedrooms, condition and HPI adjustment unavailable. These are context, not a valuation.", "value_flag":False, "coverage":"Imported official sales. Check each sale date and source release."}


def snapshot(db):
    items = inventory(db)
    towns = []
    for name, data in TOWNS.items():
        rows = [p for p in items if p["town"]==name]
        towns.append(dict(name=name, **data, total=len(rows), eligible=sum(p["eligibility"]=="eligible" for p in rows), latest=max((p["last_seen"] for p in rows), default=None)))
    return {"generated":NOW(), "properties":items, "towns":towns, "frontier_bedrooms":frontier(items), "frontier_area":frontier(items,"area_m2"),
            "runs":[dict(r) for r in db.execute("SELECT * FROM runs ORDER BY id DESC LIMIT 20")],
            "sales_count":db.execute("SELECT COUNT(*) FROM transactions").fetchone()[0],
            "messages":db.execute("SELECT COUNT(*) FROM messages").fetchone()[0],
            "coverage":"Partial observed history. Inclusion does not confirm present availability. Town markers are not property locations.",
            "delivery":[dict(r) for r in db.execute("SELECT key,created,status,subject,provider_id FROM outbox ORDER BY created DESC LIMIT 8")]}


def digest(db, recipients, day=None, initial=False):
    database=db.execute('PRAGMA database_list').fetchone()[2]
    settings=Path(database).parent/'settings.json'
    if settings.exists() and json.loads(settings.read_text()).get('delivery_owner')=='github-actions' and os.environ.get('GITHUB_ACTIONS')!='true':
        raise RuntimeError('Daily email is owned by GitHub Actions. Local digest preparation is disabled to prevent duplicate sends')
    day = day or datetime.now(ZoneInfo('Europe/London')).date().isoformat()
    items = inventory(db)
    all_fit = [p for p in items if p["eligibility"]=="eligible"]
    # A current-day email observation is not necessarily a newly marketed house.
    candidates = [p for p in all_fit if initial or any(datetime.fromisoformat(e["observed_at"]).astimezone(ZoneInfo('Europe/London')).date().isoformat()==day for e in p["events"])]
    candidates.sort(key=lambda p:(p.get("price",0)>600000, -(p["house_type"]=="detached"), -bool(offroad_parking(p)), p.get("price") or 10**9))
    if initial:
        # The first brief introduces all five places instead of five similar new-build plots.
        top=[]
        for town in TOWNS:
            options=[p for p in candidates if p['town']==town]
            if options:top.append(options[0])
        top=(top+[p for p in candidates if p not in top])[:5]
    else:
        top = candidates[:5]
    esc = lambda x: html.escape(str(x))
    subject = f"House Watch · {len(candidates)} homes to review · {day}"
    content = [f"<h1>House Watch</h1><p>{esc(day)} · Five places · Four-plus bedrooms · Up to £700,000</p>",
               "<p><strong>Partial observed inventory.</strong> Listings below were advertised at the shown observation dates. Current availability and exact station routes need checking. £700,000 is a search ceiling, not a spending target.</p>"]
    plain = [subject, "Partial observed inventory. Availability requires checking."]
    for p in top:
        title = f"£{p['price']:,} · {p['bedrooms']} beds · {p['house_type']} · {p['title']}"
        content.append(f"<section style='padding:20px 0;border-top:1px solid #ddd'><h2>{esc(title)}</h2><p>{esc(p['town'])}, {esc(p['county'])} · Last observed {esc(p['last_seen'][:10])}</p><p>{esc(' · '.join(p['fit_reasons']))}</p><p>Parking: {esc(p.get('parking','unknown'))}. Size: {esc(str(p.get('area_m2'))+' m²' if p.get('area_m2') else 'unknown')}.</p><p><a href='{esc(p['url'])}'>Original listing</a></p></section>")
        plain.extend([title, p['last_seen'][:10], " · ".join(p['fit_reasons']), p['url'], ""])
    if not top:
        content.append("<p>No newly observed qualifying homes in the imported sources today.</p>")
        plain.append("No newly observed qualifying homes in the imported sources today.")
    status_changes=[(p,e) for p in items for e in p['events'] if e['kind']=='status changed' and datetime.fromisoformat(e['observed_at']).astimezone(ZoneInfo('Europe/London')).date().isoformat()==day]
    if status_changes:
        content.append('<h2>Status changes to know about</h2>')
        for p,e in status_changes[:8]:
            note=f"{p['title']}: {json.loads(e['new_value'])}. This is an observed advertising status, not a confirmed completion."
            content.append('<p>'+esc(note)+'</p>');plain.append(note)
    counts = {t:sum(p['town']==t for p in all_fit) for t in TOWNS}
    content.append("<h2>Known qualifying observations</h2><p>"+esc(" · ".join(f"{t}: {n}" for t,n in counts.items()))+"</p><p>Zero means no supported observations, not no houses for sale. Prices and selling conditions can change.</p><p>Open the private board on Lee's Mac: http://127.0.0.1:8768 . This address is not accessible from another device. Replies can include a listing link and Lee/Min reactions.</p><p>Statistical bargain flags are disabled until historical features and validation support them.</p>")
    latest_runs=[dict(r) for r in db.execute('SELECT * FROM runs WHERE id IN (SELECT MAX(id) FROM runs GROUP BY source)')]
    failures=sorted({r['source'].split(' [')[0] for r in latest_runs if not r['success']})
    coverage_note='Existing personal email searches use older filters, including a £650k limit. Flitwick and Fleet currently have a small direct-agent watchlist rather than native-alert coverage. The £650k to £700k band and the wider market are not comprehensively covered.'
    if failures:coverage_note+=' Some pages could not be updated from: '+', '.join(failures)+'. Their listings retain the last known observation.'
    content.append('<h2>Coverage check</h2><p>'+esc(coverage_note)+'</p>')
    doc = "<!doctype html><html lang='en-GB'><meta charset='utf-8'><body style='font:16px/1.6 Arial,sans-serif;color:#183b38;max-width:720px;margin:24px auto;padding:20px'>"+"".join(content)+"</body></html>"
    plain.extend(["Known observations: "+str(counts), "Private board on Lee's Mac: http://127.0.0.1:8768", coverage_note, "No predictive bargain flags enabled."])
    key = stable("initial" if initial else "daily", day, sorted(recipients))
    old = db.execute("SELECT * FROM outbox WHERE key=?", (key,)).fetchone()
    if not old:
        db.execute("INSERT INTO outbox VALUES(?,?,?,?,?,?,?,NULL)", (key,NOW(),"prepared",json.dumps(recipients),subject,doc,"\n".join(plain)))
    elif old['status']=='prepared':
        db.execute('UPDATE outbox SET subject=?,html=?,plain=? WHERE key=?',(subject,doc,'\n'.join(plain),key))
    return dict(db.execute("SELECT * FROM outbox WHERE key=?", (key,)).fetchone())


def backup(db, destination):
    db.commit()
    p=Path(destination)
    p.parent.mkdir(parents=True, exist_ok=True)
    other=sqlite3.connect(p)
    try:
        db.backup(other)
    finally:
        other.close()
