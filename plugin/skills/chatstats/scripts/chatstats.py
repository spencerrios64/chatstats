#!/usr/bin/env python3
"""chatstats - how much you use each AI: chats, messages, rough tokens, busiest months, common words.

usage: python chatstats.py EXPORT [EXPORT ...] [--price "ChatGPT=2.5,10" ...] [--csv numbers.csv]

EXPORT is a data export (.zip or .json) from Claude, ChatGPT, Gemini (Google Takeout,
My Activity as JSON), Grok or DeepSeek, or a chatvault archive. Standard library only.
Token counts are estimates (about 4 characters per token); only text is counted.
"""
import argparse
import csv
import html
import json
import re
import sys
import zipfile
from datetime import datetime, timezone
from pathlib import Path

def iso(v):
    if v is None or v == "":
        return None
    if isinstance(v, (int, float)):
        return datetime.fromtimestamp(v / 1000 if v > 1e11 else v, tz=timezone.utc).isoformat()
    if isinstance(v, dict):
        d = v.get("$date")
        n = d.get("$numberLong") if isinstance(d, dict) else d
        if n is None:
            return None
        try:
            return iso(float(n))
        except (TypeError, ValueError):
            return str(n)
    return str(v)


def strip_html(s):
    s = re.sub(r"(?i)<br\s*/?>|</(p|li|h\d|div|tr|pre)>", "\n", s)
    s = html.unescape(re.sub(r"<[^>]*>", "", s))
    return re.sub(r"\n{3,}", "\n\n", s).strip()


def parse_mapping(data):
    """ChatGPT and DeepSeek both export a 'mapping' tree of messages."""
    deepseek, convs = False, []
    for c in data:
        mp = c.get("mapping") or {}
        chain, node = [], c.get("current_node")
        if node:
            while node and mp.get(node):
                chain.append(mp[node])
                node = mp[node].get("parent")
            chain.reverse()
        else:
            node = "root" if "root" in mp else next((k for k, v in mp.items() if not v.get("parent")), None)
            seen = set()
            while node and mp.get(node) and node not in seen:
                seen.add(node)
                chain.append(mp[node])
                kids = mp[node].get("children") or []
                node = kids[-1] if kids else None
        msgs = []
        for e in chain:
            m = e.get("message")
            if not m:
                continue
            if isinstance(m.get("fragments"), list):
                deepseek = True
                for f in m["fragments"]:
                    role = {"REQUEST": "user", "RESPONSE": "assistant"}.get(f.get("type"))
                    text = str(f.get("content") or "").strip()
                    if role and text:
                        msgs.append((role, text))
                continue
            role = (m.get("author") or {}).get("role")
            if role not in ("user", "assistant"):
                continue
            parts = (m.get("content") or {}).get("parts") or []
            text = "\n".join(p for p in parts if isinstance(p, str)).strip()
            if text:
                msgs.append((role, text))
        date = c.get("create_time") or c.get("inserted_at") or c.get("update_time") or c.get("updated_at")
        convs.append({"title": c.get("title"), "date": iso(date), "messages": msgs})
    return [("DeepSeek" if deepseek else "ChatGPT", convs)]


def parse_claude(data):
    convs = []
    for c in data:
        msgs = []
        for m in c.get("chat_messages", []):
            text = (m.get("text") or "").strip()
            if not text:
                text = "\n".join(b.get("text", "") for b in m.get("content", []) if b.get("type") == "text").strip()
            if text:
                msgs.append(("user" if m.get("sender") == "human" else "assistant", text))
        convs.append({"title": c.get("name"), "date": iso(c.get("created_at")), "messages": msgs})
    return [("Claude", convs)]


def parse_grok(data):
    convs = []
    for c in data["conversations"]:
        info, msgs = c.get("conversation") or {}, []
        for r in c.get("responses") or []:
            m = r.get("response") or r
            text = str(m.get("message") or "").strip()
            if text:
                who = str(m.get("sender") or "").lower()
                msgs.append(("user" if who in ("human", "user") else "assistant", text))
        convs.append({"title": info.get("title"), "date": iso(info.get("create_time") or info.get("created_at")), "messages": msgs})
    return [("Grok", convs)]


def parse_gemini(data):
    """Takeout 'My Activity' has one entry per prompt and no chat ids: group by day."""
    days = {}
    for it in data:
        if not re.search("gemini", it.get("header") or "", re.I) or not it.get("title"):
            continue
        t = str(it.get("time") or "")
        turn = [("user", re.sub(r"^Prompted\s+", "", str(it["title"])).strip())]
        reply = "\n".join(strip_html(h.get("html") or "") for h in it.get("safeHtmlItem") or []).strip()
        if reply:
            turn.append(("assistant", reply))
        days.setdefault(t[:10] or "undated", []).append((t, turn))
    convs = [{"title": "Gemini prompts", "date": None if day == "undated" else day,
              "messages": [m for _, turn in sorted(turns, key=lambda x: x[0]) for m in turn]}
             for day, turns in days.items()]
    return [("Gemini", convs)] if convs else []


def parse_archive(data):
    names, by = {"claude": "Claude", "chatgpt": "ChatGPT"}, {}
    for c in data:
        src = str(c.get("source") or "other")
        by.setdefault(names.get(src, src[:1].upper() + src[1:]), []).append({
            "title": c.get("title"), "date": iso(c.get("created_at") or c.get("updated_at")),
            "messages": [(m["role"], m["text"]) for m in c.get("messages", []) if (m.get("text") or "").strip()]})
    return list(by.items())


def detect(doc):
    """Return [(ai_name, conversations)] for one parsed JSON document, or [] if it isn't a chat export."""
    if isinstance(doc, list) and doc and isinstance(doc[0], dict):
        f = doc[0]
        if "mapping" in f:
            return parse_mapping(doc)
        if "chat_messages" in f:
            return parse_claude(doc)
        if "header" in f and "title" in f and "time" in f:
            return parse_gemini(doc)
        if "messages" in f and "source" in f:
            return parse_archive(doc)
    if isinstance(doc, dict) and isinstance(doc.get("conversations"), list) \
            and any(isinstance(c, dict) and c.get("responses") for c in doc["conversations"]):
        return parse_grok(doc)
    return []


def read_export(path):
    """Return [(file name, parsed JSON)] for the chat files inside an export (.zip or .json)."""
    path = Path(path)
    if zipfile.is_zipfile(path):
        out = []
        with zipfile.ZipFile(path) as z:
            for n in z.namelist():
                m = re.search(r"(^|/)(conversations[^/]*|prod-grok-backend|MyActivity)\.json$", n, re.I)
                if not m or (m.group(2).lower() == "myactivity" and not re.search("gemini", n, re.I)):
                    continue
                out.append((n, json.loads(z.read(n))))
        return out
    return [(path.name, json.loads(path.read_text(encoding="utf-8")))]


def load_chats(paths):
    """Return (chats, problems). A chat is {ai, title, date, messages: [{role, text}]}."""
    chats, problems = [], []
    for p in paths:
        try:
            found = [g for _, doc in read_export(p) for g in detect(doc)]
        except (OSError, ValueError, KeyError, TypeError, zipfile.BadZipFile) as e:
            problems.append(f"{p}: could not read ({e})")
            continue
        if not found:
            problems.append(f"{p}: no chats recognised")
            continue
        for ai, convs in found:
            for c in convs:
                if c["messages"]:
                    chats.append({"ai": ai, "title": str(c["title"] or "Untitled"), "date": (c["date"] or "")[:10],
                                  "messages": [{"role": r, "text": t} for r, t in c["messages"]]})
    return chats, problems


STOP = set(("about above after again also always another anything around because been before being both cant could does doing dont down each else even ever every "
            "first from give goes going good have here into just know like look made make many more most much must need never okay only other over please really right same should show "
            "some something still such sure tell than thank thanks that their them then there these they thing things think this those through time using very want well were what when "
            "where which while will with without work works would yeah your yours youre thats didnt doesnt isnt wont ive lets untitled chat help find used").split())


def tok(chars):
    return int(chars / 4 + 0.5)


def words_of(text):
    return [w for w in re.findall(r"[^\W\d_]+", text.lower()) if 4 <= len(w) <= 20]


def stats(chats):
    per, months, freq, sizes = {}, {}, {}, []
    for c in chats:
        s = per.setdefault(c["ai"], {"ai": c["ai"], "chats": 0, "mine": 0, "theirs": 0, "my_chars": 0, "ai_chars": 0, "sent_chars": 0})
        seen, run = set(words_of(c["title"])), 0
        s["chats"] += 1
        for m in c["messages"]:
            n = len(m["text"])
            if m["role"] == "user":
                s["mine"] += 1
                s["my_chars"] += n
                seen.update(words_of(m["text"][:4000]))
            else:
                s["theirs"] += 1
                s["ai_chars"] += n
                s["sent_chars"] += run  # an API reply re-reads everything before it
            run += n
        for w in seen:
            if w not in STOP:
                freq[w] = freq.get(w, 0) + 1
        month = c["date"][:7] if c["date"] else "no date"
        months[month] = months.get(month, 0) + 1
        sizes.append({"title": c["title"], "ai": c["ai"], "date": c["date"], "tokens": tok(run)})
    dates = sorted(c["date"] for c in chats if c["date"])
    return {
        "per": sorted(per.values(), key=lambda s: -s["chats"]),
        "months": sorted(months.items()),
        "words": sorted(((w, n) for w, n in freq.items() if n > 1), key=lambda e: (-e[1], e[0]))[:40],
        "longest": sorted(sizes, key=lambda s: -s["tokens"])[:10],
        "first": dates[0] if dates else "", "last": dates[-1] if dates else "", "chats": len(chats),
    }


def cost(s, price):
    """price: (dollars per million tokens sent, dollars per million tokens received)."""
    a, b = price
    return (tok(s["sent_chars"]) * a + tok(s["ai_chars"]) * b) / 1e6


def parse_prices(items):
    prices = {}
    for it in items or []:
        try:
            name, rest = it.split("=", 1)
            a, b = rest.split(",", 1)
            prices[name.strip().lower()] = (float(a), float(b))
        except ValueError:
            sys.exit(f'--price wants AI=in,out like "ChatGPT=2.5,10" (got "{it}")')
    return prices


def table(head, rows):
    out = ["| " + " | ".join(head) + " |", "|" + "|".join("---" for _ in head) + "|"]
    out += ["| " + " | ".join(str(c) for c in r) + " |" for r in rows]
    return "\n".join(out)


def report(st, prices):
    msgs = sum(s["mine"] for s in st["per"])
    top = st["per"][0]
    line = f"{st['chats']:,} chats and {msgs:,} messages from you"
    if st["first"]:
        line += f", from {st['first']} to {st['last']}"
    line += f". You use {top['ai']} the most ({round(100 * top['chats'] / st['chats'])}% of chats)." if len(st["per"]) > 1 else "."
    out = [line, "", "## By AI", "",
           table(["AI", "Chats", "Your messages", "AI replies", "Tokens you wrote", "Tokens AI wrote"],
                 [[s["ai"], f"{s['chats']:,}", f"{s['mine']:,}", f"{s['theirs']:,}", f"{tok(s['my_chars']):,}", f"{tok(s['ai_chars']):,}"] for s in st["per"]]),
           "", "## Chats per month", "", table(["Month", "Chats"], [[m, n] for m, n in st["months"]]), "",
           "## Words that come up in the most chats", "",
           ", ".join(f"{w} ({n})" for w, n in st["words"]) or "No word appears in more than one chat yet.", "",
           "## Longest chats", "", table(["Chat", "AI", "Date", "Tokens"], [[c["title"][:80], c["ai"], c["date"] or "-", f"{c['tokens']:,}"] for c in st["longest"]])]
    if prices:
        rows = []
        for s in st["per"]:
            p = prices.get(s["ai"].lower())
            rows.append([s["ai"], f"{tok(s['sent_chars']):,}", f"{tok(s['ai_chars']):,}", f"${cost(s, p):,.2f}" if p else "-"])
        out += ["", "## Rough cost through the API (prices you gave)", "",
                table(["AI", "Tokens sent", "Tokens received", "Rough cost"], rows),
                "", "Tokens sent counts the whole chat so far for every reply, because an API re-reads the conversation each time."]
    return "\n".join(out) + "\n"


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("exports", nargs="+", help="export files (.zip or .json)")
    ap.add_argument("--price", action="append", metavar="AI=IN,OUT", help='dollars per million tokens sent and received, e.g. "Claude=3,15" (repeatable)')
    ap.add_argument("--csv", help="also write the per-AI and per-month numbers to this .csv file")
    a = ap.parse_args(argv)
    prices = parse_prices(a.price)
    chats, problems = load_chats(a.exports)
    for p in problems:
        print(p, file=sys.stderr)
    if not chats:
        print("No chats found.", file=sys.stderr)
        return 1
    st = stats(chats)
    sys.stdout.write(report(st, prices))
    if a.csv:
        with open(a.csv, "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(["AI", "Chats", "Your messages", "AI replies", "Tokens you wrote (est.)", "Tokens AI wrote (est.)", "Tokens sent via API (est.)"])
            for s in st["per"]:
                w.writerow([s["ai"], s["chats"], s["mine"], s["theirs"], tok(s["my_chars"]), tok(s["ai_chars"]), tok(s["sent_chars"])])
            w.writerow([])
            w.writerow(["Month", "Chats"])
            w.writerows(st["months"])
        print(f"\nwrote {a.csv}", file=sys.stderr)
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
