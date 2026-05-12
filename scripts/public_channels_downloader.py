import argparse
import os
import re
import subprocess
import sys
import time
from pathlib import Path
from urllib.parse import urlparse

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

# حداکثر سایز هر قطعه برای فایل‌های بزرگ (95 MB)
CHUNK_SIZE_MB = 95
MAX_FILE_MB = 95  # گیتهاب max 100MB — ما 95 برای اطمینان

# پسوندهای هر نوع فایل
FILE_TYPE_MAP = {
    "video":  [".mp4", ".mkv", ".avi", ".mov", ".webm", ".flv", ".ts", ".m4v"],
    "voice":  [".ogg", ".oga", ".opus", ".mp3", ".m4a", ".aac", ".wav", ".flac"],
    "photo":  [".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp", ".tiff"],
    "file":   [],  # هر چیز دیگه‌ای
}


def detect_file_type(filename: str) -> str:
    ext = Path(filename).suffix.lower()
    for ftype, exts in FILE_TYPE_MAP.items():
        if ext in exts:
            return ftype
    return "file"


def parse_post_url(url: str) -> tuple[str, str]:
    """
    از لینک پست، channel و post_id رو جدا می‌کنه.
    مثال: https://t.me/channelname/123 → ('channelname', '123')
    """
    url = url.strip().rstrip("/")
    # حذف پارامترهای اضافه
    url = url.split("?")[0]

    patterns = [
        r"t\.me/([^/]+)/(\d+)",
        r"telegram\.me/([^/]+)/(\d+)",
    ]
    for pat in patterns:
        m = re.search(pat, url)
        if m:
            return m.group(1), m.group(2)

    print(f"[!] Cannot parse URL: {url}")
    sys.exit(1)


def fetch_post(channel: str, post_id: str) -> dict:
    """
    صفحه t.me/s/channel رو می‌خونه و اطلاعات پست رو برمی‌گردونه.
    """
    # t.me/s/channel?before=X+1 تا پست X نشون داده بشه
    next_id = int(post_id) + 1
    url = f"https://t.me/s/{channel}?before={next_id}"
    print(f"[+] Fetching post page: {url}")

    try:
        resp = requests.get(url, headers=HEADERS, timeout=30)
        resp.raise_for_status()
    except Exception as e:
        print(f"[!] Failed to fetch page: {e}")
        sys.exit(1)

    soup = BeautifulSoup(resp.text, "lxml")

    # پیدا کردن پست با data-post مشخص
    target_post = f"{channel}/{post_id}"
    el = soup.find(attrs={"data-post": target_post})

    if not el:
        # گاهی data-post فقط عدده
        el = soup.find(attrs={"data-post": post_id})

    if not el:
        # تلاش برای پیدا کردن آخرین پست در صفحه
        all_posts = soup.select(".tgme_widget_message")
        if all_posts:
            el = all_posts[-1]
            print(f"[~] Exact post not found, using last post on page")
        else:
            print(f"[!] Post {post_id} not found in channel @{channel}")
            print(f"[!] Make sure the channel is public and the post ID is correct")
            sys.exit(1)

    result = {
        "channel": channel,
        "post_id": post_id,
        "video": "",
        "video_thumb": "",
        "video_duration": "",
        "photos": [],
        "doc_url": "",
        "doc_title": "",
        "doc_extra": "",
        "voice_url": "",
        "text": "",
    }

    # ── ویدیو ──
    video_el = el.select_one("video")
    if video_el:
        result["video"] = video_el.get("src", "")
        thumb = el.select_one(".tgme_widget_message_video_thumb")
        if thumb:
            style = thumb.get("style", "")
            m = re.search(r"url\('(.+?)'\)", style)
            result["video_thumb"] = m.group(1) if m else ""
        dur = el.select_one(".tgme_widget_message_video_duration")
        result["video_duration"] = dur.get_text(strip=True) if dur else ""

    # ── صدا / ویس ──
    audio_el = el.select_one("audio")
    if audio_el:
        result["voice_url"] = audio_el.get("src", "")

    # ── عکس‌ها ──
    for ph in el.select(".tgme_widget_message_photo_wrap"):
        style = ph.get("style", "")
        m = re.search(r"url\('(.+?)'\)", style)
        if m:
            result["photos"].append(m.group(1))

    # ── فایل/سند ──
    doc_el = el.select_one(".tgme_widget_message_document")
    if doc_el:
        title_el = doc_el.select_one(".tgme_widget_message_document_title")
        extra_el = doc_el.select_one(".tgme_widget_message_document_extra")
        result["doc_title"] = title_el.get_text(strip=True) if title_el else ""
        result["doc_extra"] = extra_el.get_text(strip=True) if extra_el else ""
        # لینک دانلود فایل
        link = el.select_one("a.tgme_widget_message_document_wrap")
        if link:
            result["doc_url"] = link.get("href", "")

    # ── متن ──
    text_el = el.select_one(".tgme_widget_message_text")
    if text_el:
        result["text"] = text_el.get_text(separator="\n", strip=True)

    return result


def get_file_size_mb(url: str) -> float:
    """سایز فایل رو با HEAD request می‌گیره (MB)"""
    try:
        resp = requests.head(url, headers=HEADERS, timeout=15, allow_redirects=True)
        content_length = resp.headers.get("content-length", 0)
        return int(content_length) / (1024 * 1024)
    except Exception:
        return 0.0


def make_filename(channel: str, post_id: str, original: str, index: int = 0) -> str:
    """اسم فایل استاندارد می‌سازه"""
    ext = Path(original).suffix.lower() if "." in original else ""
    if not ext:
        ext = ".bin"
    idx = f"_{index+1:02d}" if index > 0 else ""
    # حذف کاراکترهای غیرمجاز
    safe_channel = re.sub(r"[^\w\-]", "_", channel)
    return f"{safe_channel}_{post_id}{idx}{ext}"


def download_file(url: str, dest: Path) -> bool:
    """فایل رو با wget دانلود می‌کنه"""
    print(f"[+] Downloading: {url}")
    print(f"    → {dest}")

    dest.parent.mkdir(parents=True, exist_ok=True)

    cmd = [
        "wget",
        "--quiet",
        "--show-progress",
        "--timeout=60",
        "--tries=3",
        "--user-agent", HEADERS["User-Agent"],
        "-O", str(dest),
        url,
    ]

    try:
        result = subprocess.run(cmd, timeout=1800)  # 30 دقیقه timeout
        if result.returncode != 0:
            print(f"[!] wget failed with code {result.returncode}")
            if dest.exists():
                dest.unlink()
            return False
        print(f"[✓] Downloaded: {dest} ({dest.stat().st_size / 1024 / 1024:.1f} MB)")
        return True
    except subprocess.TimeoutExpired:
        print(f"[!] Download timed out")
        if dest.exists():
            dest.unlink()
        return False
    except Exception as e:
        print(f"[!] Download error: {e}")
        return False


def split_large_file(filepath: Path) -> list[Path]:
    """
    اگه فایل بزرگ‌تر از 95MB بود، با 7z به قطعات تقسیم می‌کنه.
    گیتهاب max 100MB — ما 95 برای اطمینان.
    """
    size_mb = filepath.stat().st_size / (1024 * 1024)
    if size_mb <= MAX_FILE_MB:
        return [filepath]

    print(f"[!] File is {size_mb:.1f} MB — splitting into {CHUNK_SIZE_MB}MB parts...")

    archive_path = str(filepath) + ".7z"
    cmd = [
        "7z", "a",
        f"-v{CHUNK_SIZE_MB}m",  # هر قطعه 95MB
        "-mx=0",                 # بدون فشرده‌سازی (سریع‌تر)
        archive_path,
        str(filepath),
    ]

    try:
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            print(f"[!] 7z failed: {result.stderr}")
            return [filepath]  # اگه split شکست خورد، همون فایل رو برگردون

        # حذف فایل اصلی
        filepath.unlink()

        # پیدا کردن قطعات
        parts = sorted(filepath.parent.glob(f"{filepath.name}.7z.*"))
        if not parts:
            # بعضی نسخه‌های 7z پسوند متفاوت دارن
            parts = sorted(filepath.parent.glob(f"{filepath.name}.7z*"))

        print(f"[✓] Split into {len(parts)} parts")
        for p in parts:
            print(f"    {p.name} ({p.stat().st_size / 1024 / 1024:.1f} MB)")

        return parts

    except Exception as e:
        print(f"[!] Split error: {e}")
        return [filepath]


def write_readme(out_dir: Path, post_info: dict, downloaded_files: list[dict]):
    """یه README.md داخل پوشه دانلود می‌سازه"""
    channel = post_info["channel"]
    post_id = post_info["post_id"]
    post_url = f"https://t.me/{channel}/{post_id}"

    lines = []
    lines.append(f"# ⬇️ دانلود از @{channel}")
    lines.append("")
    lines.append(f"**پست:** [{post_url}]({post_url})")
    lines.append(f"**کانال:** [@{channel}](https://t.me/{channel})")
    lines.append("")

    if post_info.get("text"):
        lines.append("## 📝 متن پست")
        lines.append("")
        lines.append(post_info["text"])
        lines.append("")

    if downloaded_files:
        lines.append("## 📁 فایل‌های دانلود شده")
        lines.append("")
        for f in downloaded_files:
            fpath = f["path"]
            fname = fpath.name
            fsize = fpath.stat().st_size / (1024 * 1024)
            rel_path = fpath.relative_to(out_dir.parent.parent)  # نسبت به root مخزن
            lines.append(f"- 📄 [{fname}]({rel_path}) — `{fsize:.1f} MB`")
            if f.get("is_part"):
                lines.append(f"  > ⚠️ این فایل به دلیل حجم زیاد به قطعات تقسیم شده. برای استخراج نیاز به 7-Zip دارید.")
        lines.append("")

    lines.append("---")
    lines.append(f"*دانلود شده با TG Reader — {__import__('datetime').datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}*")

    readme_path = out_dir / "README.md"
    readme_path.write_text("\n".join(lines), encoding="utf-8")
    print(f"[✓] README saved: {readme_path}")


def main():
    parser = argparse.ArgumentParser(description="Telegram Post File Downloader")
    parser.add_argument("--url", required=True, help="لینک پست تلگرام")
    args = parser.parse_args()

    url = args.url.strip()
    print(f"[*] Post URL: {url}")

    # parse کردن URL
    channel, post_id = parse_post_url(url)
    print(f"[*] Channel: @{channel}, Post ID: {post_id}")

    # دریافت اطلاعات پست
    post_info = fetch_post(channel, post_id)

    # بررسی اینکه چیزی برای دانلود هست
    has_content = any([
        post_info["video"],
        post_info["voice_url"],
        post_info["photos"],
        post_info["doc_url"],
    ])

    if not has_content:
        print("[!] No downloadable content found in this post")
        print(f"    Text: {post_info['text'][:100] if post_info['text'] else '(empty)'}")
        print("[!] Note: Files in private channels cannot be downloaded")
        sys.exit(1)

    # ساخت پوشه خروجی: downloads/channelname_postid_date/
    from datetime import datetime
    date_str = datetime.utcnow().strftime("%Y-%m-%d_%H-%M")
    out_dir_name = f"{channel}_{post_id}_{date_str}"
    root_downloads = Path("downloads")
    out_dir = root_downloads / out_dir_name
    out_dir.mkdir(parents=True, exist_ok=True)

    downloaded_files = []

    # ── دانلود ویدیو ──
    if post_info["video"]:
        vid_url = post_info["video"]
        size_mb = get_file_size_mb(vid_url)
        print(f"[*] Video size: {size_mb:.1f} MB")

        # اسم فایل از URL
        url_path = urlparse(vid_url).path
        original_name = Path(url_path).name or f"video_{post_id}.mp4"
        filename = make_filename(channel, post_id, original_name)

        dest = out_dir / "video" / filename
        if download_file(vid_url, dest):
            parts = split_large_file(dest)
            is_split = len(parts) > 1
            for p in parts:
                downloaded_files.append({"path": p, "type": "video", "is_part": is_split})

    # ── دانلود ویس/صدا ──
    if post_info["voice_url"]:
        voice_url = post_info["voice_url"]
        url_path = urlparse(voice_url).path
        original_name = Path(url_path).name or f"voice_{post_id}.ogg"
        filename = make_filename(channel, post_id, original_name)

        dest = out_dir / "voice" / filename
        if download_file(voice_url, dest):
            downloaded_files.append({"path": dest, "type": "voice", "is_part": False})

    # ── دانلود عکس‌ها ──
    for i, photo_url in enumerate(post_info["photos"]):
        url_path = urlparse(photo_url).path
        original_name = Path(url_path).name or f"photo_{post_id}_{i+1}.jpg"
        filename = make_filename(channel, post_id, original_name, i)

        dest = out_dir / "photo" / filename
        if download_file(photo_url, dest):
            downloaded_files.append({"path": dest, "type": "photo", "is_part": False})

    # ── دانلود فایل/سند ──
    if post_info["doc_url"]:
        doc_url = post_info["doc_url"]
        # اسم فایل از عنوان سند یا URL
        if post_info["doc_title"]:
            # پاک‌سازی اسم فایل
            safe_name = re.sub(r'[^\w\-\.]', '_', post_info["doc_title"])
            ext = Path(urlparse(doc_url).path).suffix or ".bin"
            if not safe_name.endswith(ext):
                safe_name += ext
            filename = f"{channel}_{post_id}_{safe_name}"
        else:
            url_path = urlparse(doc_url).path
            original_name = Path(url_path).name or f"file_{post_id}.bin"
            filename = make_filename(channel, post_id, original_name)

        ftype = detect_file_type(filename)
        dest = out_dir / ftype / filename
        size_mb = get_file_size_mb(doc_url)
        print(f"[*] File size: {size_mb:.1f} MB")

        if download_file(doc_url, dest):
            parts = split_large_file(dest)
            is_split = len(parts) > 1
            for p in parts:
                downloaded_files.append({"path": p, "type": ftype, "is_part": is_split})

    # ── نتیجه نهایی ──
    if not downloaded_files:
        print("[!] No files were successfully downloaded")
        sys.exit(1)

    print(f"\n[✓] Successfully downloaded {len(downloaded_files)} file(s):")
    for f in downloaded_files:
        print(f"    {f['type']:8} → {f['path']}")

    # ساخت README
    write_readme(out_dir, post_info, downloaded_files)

    print("\n[✓] Done! Files saved to:", out_dir)


if __name__ == "__main__":
    main()
