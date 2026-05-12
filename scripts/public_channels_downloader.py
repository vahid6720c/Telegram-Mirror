import argparse
import re
import subprocess
import sys
import zipfile
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup

# ═══════════════════════════════════════════════════════════
#  ثابت‌ها
# ═══════════════════════════════════════════════════════════

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
}

MAX_FILE_MB   = 100   # حد مجاز گیتهاب
CHUNK_SIZE_MB = 95    # اندازه هر قطعه زیپ

MIME_TO_EXT = {
    "video/mp4":                  ".mp4",
    "video/webm":                 ".webm",
    "video/x-matroska":           ".mkv",
    "video/quicktime":            ".mov",
    "video/x-msvideo":            ".avi",
    "audio/ogg":                  ".ogg",
    "audio/mpeg":                 ".mp3",
    "audio/mp4":                  ".m4a",
    "audio/aac":                  ".aac",
    "audio/wav":                  ".wav",
    "audio/flac":                 ".flac",
    "image/jpeg":                 ".jpg",
    "image/png":                  ".png",
    "image/webp":                 ".webp",
    "image/gif":                  ".gif",
    "application/pdf":            ".pdf",
    "application/zip":            ".zip",
    "application/x-rar-compressed": ".rar",
    "application/x-7z-compressed":  ".7z",
    "application/msword":         ".doc",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": ".docx",
    "application/vnd.ms-excel":   ".xls",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": ".xlsx",
    "application/octet-stream":   "",   # نامشخص — بعداً از Content-Disposition
}


# ═══════════════════════════════════════════════════════════
#  توابع کمکی
# ═══════════════════════════════════════════════════════════

def safe_name(text: str) -> str:
    """کاراکترهای غیرمجاز سیستم‌فایل را حذف می‌کند"""
    return re.sub(r'[^\w\-\.]', '_', text).strip('_')


def parse_post_url(url: str) -> tuple[str, str]:
    """
    لینک پست تلگرام را پارس می‌کند.
    خروجی: (channel, post_id)
    """
    url = url.strip().rstrip("/").split("?")[0]
    for pat in [r"t\.me/([^/]+)/(\d+)", r"telegram\.me/([^/]+)/(\d+)"]:
        m = re.search(pat, url)
        if m:
            return m.group(1), m.group(2)
    print(f"[!] Cannot parse URL: {url}")
    sys.exit(1)


def get_remote_info(url: str) -> dict:
    """
    با یک HEAD request، اطلاعات فایل روی سرور را برمی‌گرداند:
      size_mb, ext, original_filename
    """
    info = {"size_mb": 0.0, "ext": "", "original_filename": ""}
    try:
        resp = requests.head(url, headers=HEADERS, timeout=20, allow_redirects=True)

        # سایز
        cl = resp.headers.get("content-length", 0)
        info["size_mb"] = int(cl) / (1024 * 1024) if cl else 0.0

        # پسوند از Content-Type
        ct = resp.headers.get("content-type", "").split(";")[0].strip().lower()
        info["ext"] = MIME_TO_EXT.get(ct, "")

        # اسم اصلی از Content-Disposition
        cd = resp.headers.get("content-disposition", "")
        m = re.search(r'filename\*?=["\']?(?:UTF-8\'\')?([^"\';\s]+)', cd, re.IGNORECASE)
        if m:
            info["original_filename"] = m.group(1).strip()

    except Exception as e:
        print(f"[~] HEAD request failed: {e}")

    return info


def resolve_ext(url: str, fallback_ext: str = "") -> str:
    """
    پسوند فایل را به ترتیب اولویت تعیین می‌کند:
      ۱. پسوند موجود در URL
      ۲. Content-Type هدر
      ۳. fallback_ext
      ۴. رشته خالی (بدون پسوند)
    """
    # از URL
    url_ext = Path(urlparse(url).path).suffix.lower()
    if url_ext and len(url_ext) <= 6:
        return url_ext

    # از سرور
    info = get_remote_info(url)
    if info["ext"]:
        return info["ext"]

    # از اسم اصلی سرور
    if info["original_filename"]:
        orig_ext = Path(info["original_filename"]).suffix.lower()
        if orig_ext:
            return orig_ext

    return fallback_ext


def make_filename(channel: str, post_id: str, url: str,
                  fallback_ext: str = "", index: int = 0) -> str:
    """اسم فایل استاندارد می‌سازد"""
    ext = resolve_ext(url, fallback_ext)
    idx = f"_{index+1:02d}" if index > 0 else ""
    return f"{safe_name(channel)}_{post_id}{idx}{ext}"


# ═══════════════════════════════════════════════════════════
#  دریافت اطلاعات پست
# ═══════════════════════════════════════════════════════════

def fetch_post(channel: str, post_id: str) -> dict:
    """صفحه t.me/s را می‌خواند و اطلاعات پست را برمی‌گرداند"""
    next_id = int(post_id) + 1
    url = f"https://t.me/s/{channel}?before={next_id}"
    print(f"[+] Fetching: {url}")

    try:
        resp = requests.get(url, headers=HEADERS, timeout=30)
        resp.raise_for_status()
    except Exception as e:
        print(f"[!] Failed to fetch page: {e}")
        sys.exit(1)

    soup = BeautifulSoup(resp.text, "lxml")

    # پیدا کردن المان پست
    el = (
        soup.find(attrs={"data-post": f"{channel}/{post_id}"})
        or soup.find(attrs={"data-post": post_id})
    )
    if not el:
        all_posts = soup.select(".tgme_widget_message")
        if all_posts:
            el = all_posts[-1]
            print("[~] Exact post not found — using last post on page")
        else:
            print(f"[!] Post {post_id} not found in @{channel}")
            sys.exit(1)

    result = {
        "channel":        channel,
        "post_id":        post_id,
        "video_url":      "",
        "voice_url":      "",
        "photos":         [],
        "doc_url":        "",
        "doc_title":      "",
        "doc_ext":        "",
        "text":           "",
    }

    # ویدیو
    video_el = el.select_one("video")
    if video_el:
        result["video_url"] = video_el.get("src", "")

    # صدا / ویس
    audio_el = el.select_one("audio")
    if audio_el:
        result["voice_url"] = audio_el.get("src", "")

    # عکس‌ها
    for ph in el.select(".tgme_widget_message_photo_wrap"):
        style = ph.get("style", "")
        m = re.search(r"url\('(.+?)'\)", style)
        if m:
            result["photos"].append(m.group(1))

    # فایل/سند
    doc_el = el.select_one(".tgme_widget_message_document")
    if doc_el:
        title_el = doc_el.select_one(".tgme_widget_message_document_title")
        extra_el = doc_el.select_one(".tgme_widget_message_document_extra")
        result["doc_title"] = title_el.get_text(strip=True) if title_el else ""
        result["doc_ext"]   = extra_el.get_text(strip=True) if extra_el else ""
        link = el.select_one("a.tgme_widget_message_document_wrap")
        if link:
            result["doc_url"] = link.get("href", "")

    # متن
    text_el = el.select_one(".tgme_widget_message_text")
    if text_el:
        result["text"] = text_el.get_text(separator="\n", strip=True)

    return result


# ═══════════════════════════════════════════════════════════
#  دانلود
# ═══════════════════════════════════════════════════════════

def download_file(url: str, dest: Path) -> bool:
    """فایل را با wget دانلود می‌کند"""
    dest.parent.mkdir(parents=True, exist_ok=True)
    print(f"[↓] {dest.name}")

    cmd = [
        "wget", "--quiet", "--show-progress",
        "--timeout=60", "--tries=3",
        "--user-agent", HEADERS["User-Agent"],
        "-O", str(dest), url,
    ]
    try:
        r = subprocess.run(cmd, timeout=3600)
        if r.returncode != 0:
            print(f"[!] wget failed (code {r.returncode})")
            dest.unlink(missing_ok=True)
            return False
        mb = dest.stat().st_size / (1024 * 1024)
        print(f"[✓] {dest.name}  ({mb:.1f} MB)")
        return True
    except subprocess.TimeoutExpired:
        print("[!] Download timed out")
        dest.unlink(missing_ok=True)
        return False
    except Exception as e:
        print(f"[!] Download error: {e}")
        dest.unlink(missing_ok=True)
        return False


# ═══════════════════════════════════════════════════════════
#  تقسیم فایل بزرگ به قطعات زیپ
# ═══════════════════════════════════════════════════════════

def split_to_zip_parts(filepath: Path) -> list[Path]:
    """
    فایل‌های بزرگ‌تر از MAX_FILE_MB را به قطعات زیپ CHUNK_SIZE_MB مگابایتی تقسیم می‌کند.
    فایل اصلی حذف می‌شود و لیست قطعات برگردانده می‌شود.
    """
    size_mb = filepath.stat().st_size / (1024 * 1024)
    if size_mb <= MAX_FILE_MB:
        return [filepath]

    print(f"[!] {filepath.name} is {size_mb:.1f} MB — splitting into {CHUNK_SIZE_MB}MB zip parts...")

    chunk_bytes = CHUNK_SIZE_MB * 1024 * 1024
    parts: list[Path] = []
    part_num = 1

    with open(filepath, "rb") as src:
        while True:
            chunk = src.read(chunk_bytes)
            if not chunk:
                break
            part_name = f"{filepath.name}.part{part_num:03d}.zip"
            part_path = filepath.parent / part_name

            with zipfile.ZipFile(part_path, "w", zipfile.ZIP_STORED) as zf:
                zf.writestr(filepath.name, chunk)

            part_mb = part_path.stat().st_size / (1024 * 1024)
            print(f"    [✓] {part_name}  ({part_mb:.1f} MB)")
            parts.append(part_path)
            part_num += 1

    filepath.unlink()
    print(f"[✓] Split into {len(parts)} parts")
    return parts


# ═══════════════════════════════════════════════════════════
#  ساخت README
# ═══════════════════════════════════════════════════════════

def write_readme(out_dir: Path, post_info: dict, files: list[dict]):
    channel  = post_info["channel"]
    post_id  = post_info["post_id"]
    post_url = f"https://t.me/{channel}/{post_id}"

    lines = [
        f"# ⬇️ دانلود از @{channel}",
        "",
        f"**پست:** [{post_url}]({post_url})",
        f"**کانال:** [@{channel}](https://t.me/{channel})",
        "",
    ]

    if post_info.get("text"):
        lines += ["## 📝 متن پست", "", post_info["text"], ""]

    if files:
        lines += ["## 📁 فایل‌های دانلود شده", ""]
        for f in files:
            p     = f["path"]
            mb    = p.stat().st_size / (1024 * 1024)
            rel   = p.relative_to(out_dir.parent.parent)
            lines.append(f"- 📄 [{p.name}]({rel})  —  `{mb:.1f} MB`")
            if f.get("is_part"):
                lines.append(
                    "  > ⚠️ این فایل به دلیل حجم زیاد به قطعات زیپ تقسیم شده است.\n"
                    "  > برای بازیابی فایل اصلی، همه قطعات را دانلود کرده و\n"
                    "  > هر قطعه را جداگانه با WinRAR یا 7-Zip استخراج کنید."
                )
        lines.append("")

    lines += [
        "---",
        f"*دانلود شده با [Telegram Mirror](https://github.com/FALKON-CODE/Telegram-Mirror)"
        f" — {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}*",
    ]

    readme = out_dir / "README.md"
    readme.write_text("\n".join(lines), encoding="utf-8")
    print(f"[✓] README saved: {readme}")


# ═══════════════════════════════════════════════════════════
#  اجرای اصلی
# ═══════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(description="Telegram Post Downloader")
    parser.add_argument("--url", required=True, help="لینک پست تلگرام")
    args = parser.parse_args()

    url = args.url.strip()
    print(f"[*] URL: {url}")

    channel, post_id = parse_post_url(url)
    print(f"[*] Channel: @{channel}  |  Post: {post_id}")

    post_info = fetch_post(channel, post_id)

    has_content = any([
        post_info["video_url"],
        post_info["voice_url"],
        post_info["photos"],
        post_info["doc_url"],
    ])
    if not has_content:
        print("[!] No downloadable content found in this post")
        print("[!] Note: private channel content cannot be accessed")
        sys.exit(1)

    # پوشه خروجی
    date_str = datetime.utcnow().strftime("%Y-%m-%d_%H-%M")
    out_dir  = Path("downloads") / f"{safe_name(channel)}_{post_id}_{date_str}"

    downloaded: list[dict] = []

    # ── ویدیو ──────────────────────────────────────────────
    if post_info["video_url"]:
        vid_url  = post_info["video_url"]
        filename = make_filename(channel, post_id, vid_url, fallback_ext=".mp4")
        dest     = out_dir / "video" / filename

        if download_file(vid_url, dest):
            for p in split_to_zip_parts(dest):
                downloaded.append({"path": p, "type": "video",
                                   "is_part": p != dest})

    # ── صدا / ویس ──────────────────────────────────────────
    if post_info["voice_url"]:
        voice_url = post_info["voice_url"]
        filename  = make_filename(channel, post_id, voice_url, fallback_ext=".ogg")
        dest      = out_dir / "voice" / filename

        if download_file(voice_url, dest):
            for p in split_to_zip_parts(dest):
                downloaded.append({"path": p, "type": "voice",
                                   "is_part": p != dest})

    # ── عکس‌ها ─────────────────────────────────────────────
    for i, photo_url in enumerate(post_info["photos"]):
        filename = make_filename(channel, post_id, photo_url,
                                 fallback_ext=".jpg", index=i)
        dest = out_dir / "photo" / filename

        if download_file(photo_url, dest):
            # عکس‌ها معمولاً کوچک‌اند ولی چک می‌کنیم
            for p in split_to_zip_parts(dest):
                downloaded.append({"path": p, "type": "photo",
                                   "is_part": p != dest})

    # ── فایل/سند ───────────────────────────────────────────
    if post_info["doc_url"]:
        doc_url = post_info["doc_url"]

        if post_info["doc_title"]:
            # اسم اصلی سند + پسوند واقعی از سرور
            ext      = resolve_ext(doc_url, fallback_ext="")
            base     = safe_name(post_info["doc_title"])
            # اگه خود عنوان پسوند داره، اضافه نکن
            if not base.lower().endswith(ext):
                base += ext
            filename = f"{safe_name(channel)}_{post_id}_{base}"
        else:
            filename = make_filename(channel, post_id, doc_url)

        # نوع پوشه بر اساس پسوند
        ext_lower = Path(filename).suffix.lower()
        if ext_lower in (".mp4", ".mkv", ".avi", ".mov", ".webm"):
            ftype = "video"
        elif ext_lower in (".ogg", ".mp3", ".m4a", ".aac", ".wav", ".flac"):
            ftype = "voice"
        elif ext_lower in (".jpg", ".jpeg", ".png", ".webp", ".gif"):
            ftype = "photo"
        else:
            ftype = "file"

        dest = out_dir / ftype / filename

        if download_file(doc_url, dest):
            for p in split_to_zip_parts(dest):
                downloaded.append({"path": p, "type": ftype,
                                   "is_part": p != dest})

    # ── نتیجه ──────────────────────────────────────────────
    if not downloaded:
        print("[!] No files were successfully downloaded")
        sys.exit(1)

    print(f"\n[✓] {len(downloaded)} file(s) downloaded:")
    for f in downloaded:
        print(f"    {f['type']:6} → {f['path']}")

    write_readme(out_dir, post_info, downloaded)
    print(f"\n[✓] Done! Saved to: {out_dir}")


if __name__ == "__main__":
    main()
