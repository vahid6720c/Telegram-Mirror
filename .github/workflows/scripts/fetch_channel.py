import argparse
import json
import os
import re
import time
from datetime import datetime
from pathlib import Path

import requests
from bs4 import BeautifulSoup

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
}

def parse_message(el):
    """Parse a single message bubble from t.me/s/channel HTML."""
    msg = {}

    # ID
    msg_id = el.get("data-post", "")
    msg["id"] = msg_id

    # Date
    date_el = el.select_one(".tgme_widget_message_date time")
    if date_el:
        msg["date_raw"] = date_el.get("datetime", "")
        try:
            dt = datetime.fromisoformat(msg["date_raw"].replace("Z", "+00:00"))
            msg["date"] = dt.strftime("%H:%M · %d %b %Y")
        except Exception:
            msg["date"] = msg["date_raw"]
    else:
        msg["date"] = ""
        msg["date_raw"] = ""

    # Views
    views_el = el.select_one(".tgme_widget_message_views")
    msg["views"] = views_el.get_text(strip=True) if views_el else ""

    # Text
    text_el = el.select_one(".tgme_widget_message_text")
    if text_el:
        # Preserve links
        for a in text_el.find_all("a"):
            href = a.get("href", "")
            a.replace_with(f'<a href="{href}" target="_blank" rel="noopener">{a.get_text()}</a>')
        msg["text"] = str(text_el)
        msg["text_plain"] = text_el.get_text(separator="\n", strip=True)
    else:
        msg["text"] = ""
        msg["text_plain"] = ""

    # Photo
    photo_el = el.select_one(".tgme_widget_message_photo_wrap")
    if photo_el:
        style = photo_el.get("style", "")
        m = re.search(r"url\('(.+?)'\)", style)
        msg["photo"] = m.group(1) if m else ""
    else:
        msg["photo"] = ""

    # Video
    video_el = el.select_one("video")
    if video_el:
        msg["video"] = video_el.get("src", "")
        # thumbnail
        thumb = el.select_one(".tgme_widget_message_video_thumb")
        if thumb:
            style = thumb.get("style", "")
            m = re.search(r"url\('(.+?)'\)", style)
            msg["video_thumb"] = m.group(1) if m else ""
        else:
            msg["video_thumb"] = ""
    else:
        msg["video"] = ""
        msg["video_thumb"] = ""

    # Document / file
    doc_el = el.select_one(".tgme_widget_message_document")
    if doc_el:
        title_el = doc_el.select_one(".tgme_widget_message_document_title")
        extra_el = doc_el.select_one(".tgme_widget_message_document_extra")
        msg["doc_title"] = title_el.get_text(strip=True) if title_el else ""
        msg["doc_extra"] = extra_el.get_text(strip=True) if extra_el else ""
        # link
        link_el = doc_el.find_parent("a") or el.select_one("a[href*='tg://']")
        msg["doc_url"] = link_el.get("href", "") if link_el else ""
    else:
        msg["doc_title"] = ""
        msg["doc_extra"] = ""
        msg["doc_url"] = ""

    # Forwarded
    fwd_el = el.select_one(".tgme_widget_message_forwarded_from")
    msg["forwarded_from"] = fwd_el.get_text(strip=True) if fwd_el else ""

    # Reply
    reply_el = el.select_one(".tgme_widget_message_reply")
    msg["reply_text"] = reply_el.get_text(strip=True) if reply_el else ""

    # Sticker
    sticker_el = el.select_one(".tgme_widget_message_sticker_wrap")
    if sticker_el:
        img = sticker_el.select_one("img")
        msg["sticker"] = img.get("src", "") if img else ""
    else:
        msg["sticker"] = ""

    # Poll
    poll_el = el.select_one(".tgme_widget_message_poll")
    if poll_el:
        question_el = poll_el.select_one(".tgme_widget_message_poll_question")
        options = poll_el.select(".tgme_widget_message_poll_option_text")
        msg["poll_question"] = question_el.get_text(strip=True) if question_el else ""
        msg["poll_options"] = [o.get_text(strip=True) for o in options]
    else:
        msg["poll_question"] = ""
        msg["poll_options"] = []

    # Multiple photos (album)
    album_photos = el.select(".tgme_widget_message_photo_wrap")
    msg["album"] = []
    for ph in album_photos:
        style = ph.get("style", "")
        m = re.search(r"url\('(.+?)'\)", style)
        if m:
            msg["album"].append(m.group(1))

    # Message URL
    msg_url_el = el.select_one(".tgme_widget_message_date")
    msg["url"] = msg_url_el.get("href", "") if msg_url_el else ""

    return msg


def fetch_channel(channel: str, count: int) -> tuple[list, dict]:
    """Fetch messages from a public Telegram channel."""
    messages = []
    channel_info = {"name": channel, "title": "", "description": "", "avatar": "", "members": ""}

    base_url = f"https://t.me/s/{channel}"
    before = None

    print(f"[+] Fetching channel: @{channel}")

    while len(messages) < count:
        url = base_url if before is None else f"{base_url}?before={before}"
        print(f"    → GET {url}")

        try:
            resp = requests.get(url, headers=HEADERS, timeout=30)
            resp.raise_for_status()
        except Exception as e:
            print(f"[!] Request error: {e}")
            break

        soup = BeautifulSoup(resp.text, "lxml")

        # Channel info (first request only)
        if before is None:
            title_el = soup.select_one(".tgme_channel_info_header_title")
            if title_el:
                channel_info["title"] = title_el.get_text(strip=True)

            desc_el = soup.select_one(".tgme_channel_info_description")
            if desc_el:
                channel_info["description"] = desc_el.get_text(strip=True)

            avatar_el = soup.select_one(".tgme_page_photo_image img, .tgme_channel_info_header_image img")
            if avatar_el:
                channel_info["avatar"] = avatar_el.get("src", "")

            members_el = soup.select_one(".tgme_channel_info_counter .counter_value")
            if members_el:
                channel_info["members"] = members_el.get_text(strip=True)

        # Messages
        bubbles = soup.select(".tgme_widget_message_wrap")
        if not bubbles:
            print("[!] No messages found — channel may be private or not exist.")
            break

        page_messages = []
        for b in bubbles:
            inner = b.select_one(".tgme_widget_message")
            if inner:
                page_messages.append(parse_message(inner))

        if not page_messages:
            break

        messages = page_messages + messages

        # Find earliest ID for pagination
        ids = [int(m["id"].split("/")[-1]) for m in page_messages if m["id"]]
        if not ids:
            break

        before = min(ids)

        if len(messages) >= count:
            break

        time.sleep(0.8)  # polite delay

    # Trim to requested count (keep newest)
    messages = messages[-count:]
    print(f"[+] Collected {len(messages)} messages")
    return messages, channel_info


def render_html(messages: list, channel_info: dict, channel: str) -> str:
    """Render messages into a Telegram-styled HTML page."""
    template = Path("scripts/template.html").read_text(encoding="utf-8")

    # Build message HTML
    msgs_html = ""
    for m in reversed(messages):  # newest last
        msgs_html += render_message(m, channel)

    now = datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")

    avatar = channel_info.get("avatar", "")
    if avatar:
        avatar_html = f'<img class="ch-avatar" src="{avatar}" alt="avatar" onerror="this.style.display=\'none\'"/>'
    else:
        first_letter = (channel_info.get("title") or channel)[0].upper()
        avatar_html = f'<div class="ch-avatar-placeholder">{first_letter}</div>'

    desc = channel_info.get("description", "")
    desc_html = f'<div class="ch-desc">{desc}</div>' if desc else ""

    html = template.replace("{{CHANNEL_NAME}}", channel)
    html = html.replace("{{CHANNEL_TITLE}}", channel_info.get("title") or f"@{channel}")
    html = html.replace("{{CHANNEL_DESCRIPTION}}", desc)
    html = html.replace("{{AVATAR_HTML}}", avatar_html)
    html = html.replace("{{DESC_HTML}}", desc_html)
    html = html.replace("{{CHANNEL_MEMBERS}}", channel_info.get("members", ""))
    html = html.replace("{{MESSAGES}}", msgs_html)
    html = html.replace("{{FETCH_TIME}}", now)
    html = html.replace("{{MSG_COUNT}}", str(len(messages)))

    return html


def render_message(m: dict, channel: str) -> str:
    parts = []
    parts.append(f'<div class="msg-wrap" id="msg-{m["id"].split("/")[-1] if m["id"] else ""}">')
    parts.append('<div class="msg-bubble">')

    # Forwarded
    if m.get("forwarded_from"):
        parts.append(f'<div class="msg-forward">↪ Forwarded from: <b>{m["forwarded_from"]}</b></div>')

    # Reply
    if m.get("reply_text"):
        parts.append(f'<div class="msg-reply"><span>{m["reply_text"]}</span></div>')

    # Sticker
    if m.get("sticker"):
        parts.append(f'<div class="msg-sticker"><img src="{m["sticker"]}" alt="sticker" loading="lazy"/></div>')

    # Album (multiple photos)
    if m.get("album") and len(m["album"]) > 1:
        parts.append('<div class="msg-album">')
        for ph in m["album"]:
            parts.append(
                f'<a href="{ph}" download target="_blank" class="album-item">'
                f'<img src="{ph}" loading="lazy" alt="photo"/>'
                f'<span class="dl-badge">⬇</span></a>'
            )
        parts.append("</div>")
    elif m.get("photo"):
        parts.append(
            f'<div class="msg-photo">'
            f'<a href="{m["photo"]}" download target="_blank">'
            f'<img src="{m["photo"]}" loading="lazy" alt="photo"/>'
            f'<span class="dl-overlay">⬇ دانلود</span></a></div>'
        )

    # Video
    if m.get("video"):
        thumb = m.get("video_thumb", "")
        parts.append(
            f'<div class="msg-video">'
            f'<video controls preload="none" poster="{thumb}">'
            f'<source src="{m["video"]}"></video>'
            f'<a class="dl-btn" href="{m["video"]}" download target="_blank">⬇ دانلود ویدیو</a>'
            f'</div>'
        )

    # Document
    if m.get("doc_title"):
        parts.append(
            f'<div class="msg-doc">'
            f'<span class="doc-icon">📄</span>'
            f'<div class="doc-info">'
            f'<span class="doc-title">{m["doc_title"]}</span>'
            f'<span class="doc-extra">{m["doc_extra"]}</span>'
            f'</div>'
            f'<a class="doc-dl" href="{m["doc_url"]}" target="_blank">⬇</a>'
            f'</div>'
        )

    # Poll
    if m.get("poll_question"):
        opts_html = "".join(f'<li class="poll-opt">{o}</li>' for o in m.get("poll_options", []))
        parts.append(
            f'<div class="msg-poll">'
            f'<div class="poll-question">📊 {m["poll_question"]}</div>'
            f'<ul class="poll-opts">{opts_html}</ul>'
            f'</div>'
        )

    # Text
    if m.get("text"):
        parts.append(f'<div class="msg-text">{m["text"]}</div>')

    # Footer
    parts.append('<div class="msg-footer">')
    if m.get("views"):
        parts.append(f'<span class="msg-views">👁 {m["views"]}</span>')
    if m.get("date"):
        link = m.get("url", "#")
        parts.append(f'<a class="msg-date" href="{link}" target="_blank">{m["date"]}</a>')
    parts.append("</div>")  # footer

    parts.append("</div>")  # bubble
    parts.append("</div>")  # wrap

    return "\n".join(parts)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--channel", required=True)
    parser.add_argument("--count", type=int, default=100)
    args = parser.parse_args()

    channel = args.channel.lstrip("@").strip()
    count = max(10, min(args.count, 200))

    messages, channel_info = fetch_channel(channel, count)

    if not messages:
        print("[!] No messages to render.")
        return

    html = render_html(messages, channel_info, channel)

    out_dir = Path("output")
    out_dir.mkdir(exist_ok=True)

    out_file = out_dir / "index.html"
    out_file.write_text(html, encoding="utf-8")

    # Save raw JSON too
    data = {"channel": channel_info, "messages": messages, "fetched_at": datetime.utcnow().isoformat()}
    (out_dir / "data.json").write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"[✓] Saved to {out_file}")


if __name__ == "__main__":
    main()
