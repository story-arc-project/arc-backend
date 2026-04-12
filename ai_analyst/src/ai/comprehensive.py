"""
Career Analysis AI - COMPREHENSIVE Edition v1.0
================================================
종합 커리어 분석 전용 모듈

기능:
  - 복수 경력/자격증/활동 종합 분석
  - URL(Notion 포함) / 파일 / 직접 텍스트 입력
  - Google Search 기반 3단계 검증 (자격증, 동아리, 공모전, 채용공고)
  - 모든 출력은 순수 JSON

Hallucination 방지 원칙:
  - 실재 확인 불가 항목 생성 금지
  - URL 추측/조합 금지 → null만 허용
  - 동아리 최소 3개 이상 (학교 있을 때)
  - 종료된 공모전 현재형 서술 금지
  - 빈 배열 우선 (채우기용 임의 생성 절대 금지)

사용법:
  python career_comprehensive.py
  → 학교/학과 입력 후 URL, 파일, 또는 텍스트 붙여넣기
  → JSON 결과 출력 (stdout)
"""

import json
import re
import os
import io
import sys
import time
import threading
import urllib.request
import urllib.parse
import urllib.error
from html.parser import HTMLParser
from datetime import datetime, date
from collections import deque
from concurrent.futures import ThreadPoolExecutor, as_completed

from google import genai
from google.genai import types
import pypdf

# ──────────────────────────────────────────────
# Config
# ──────────────────────────────────────────────
GEMINI_API_KEY   = os.getenv("GEMINI_API_KEY")
client           = genai.Client(api_key=GEMINI_API_KEY)

_ANALYSIS_MODEL  = "gemini-2.5-pro"
_EMBEDDING_MODEL = "gemini-embedding-001"

# 크롤러 설정
_MAX_PAGES       = 30
_MAX_PDFS        = 5
_FETCH_TIMEOUT   = 15
_MAX_CONTENT_MB  = 1
_MIN_CRAWL_CHARS = 200

# 재시도 설정
_MAX_RETRIES    = 4
_RETRY_BASE_SEC = 5

# 병렬 처리 설정
_CRAWL_WORKERS  = 8   # 딥 크롤러 병렬 fetch 스레드 수
_VERIFY_WORKERS = 3   # URL 검증 병렬 스레드 수
_print_lock     = threading.Lock()  # 병렬 print 충돌 방지


# ══════════════════════════════════════════════
# 1  LLM 호출 헬퍼
# ══════════════════════════════════════════════
def _is_rate_limit(e: Exception) -> bool:
    s = str(e).lower()
    return any(k in s for k in ("429", "quota", "rate_limit", "rate limit", "resource_exhausted"))


def _call_with_retry(fn, *args, **kwargs):
    for attempt in range(_MAX_RETRIES):
        try:
            return fn(*args, **kwargs)
        except Exception as e:
            if _is_rate_limit(e) and attempt < _MAX_RETRIES - 1:
                wait = _RETRY_BASE_SEC * (2 ** attempt)
                print(f"  [Rate Limit] {wait}초 후 재시도 ({attempt + 1}/{_MAX_RETRIES - 1})...", flush=True)
                time.sleep(wait)
            else:
                raise


def _call_model(system_prompt: str, user_prompt: str,
                use_google_search: bool = False) -> dict:
    raw_text = ""
    try:
        tools = [types.Tool(google_search=types.GoogleSearch())] if use_google_search else None

        def _do():
            return client.models.generate_content(
                model=_ANALYSIS_MODEL,
                contents=user_prompt,
                config=types.GenerateContentConfig(
                    system_instruction=system_prompt if system_prompt else None,
                    temperature=0.1,
                    tools=tools,
                ),
            )

        resp = _call_with_retry(_do)
        raw_text = resp.text.strip()
        return json.loads(clean_json_response(raw_text))

    except json.JSONDecodeError as e:
        return {
            "status": "error",
            "message": f"JSON parse failed: {e.msg}",
            "raw_response": raw_text[:1000],
        }
    except Exception as e:
        return {"status": "error", "message": str(e)}


def _call_model_raw(user_prompt: str, system_prompt: str = "",
                    use_google_search: bool = False) -> str:
    try:
        tools = [types.Tool(google_search=types.GoogleSearch())] if use_google_search else None

        def _do():
            return client.models.generate_content(
                model=_ANALYSIS_MODEL,
                contents=user_prompt,
                config=types.GenerateContentConfig(
                    system_instruction=system_prompt if system_prompt else None,
                    temperature=0.0,
                    tools=tools,
                ),
            )

        resp = _call_with_retry(_do)
        return resp.text.strip()
    except Exception as e:
        return f"ERROR: {e}"


# ══════════════════════════════════════════════
# 1-b  Thread-safe print 헬퍼
# ══════════════════════════════════════════════
def _tprint(*args, **kwargs):
    """병렬 스레드에서 print가 섞이지 않도록 lock을 잡고 출력."""
    with _print_lock:
        print(*args, **kwargs)


# ══════════════════════════════════════════════
# 2  JSON 정제
# ══════════════════════════════════════════════
def clean_json_response(raw_text: str) -> str:
    raw_text = raw_text.strip()

    m = re.search(r"```(?:json)?\s*\n?(.*?)\n?\s*```", raw_text, re.DOTALL | re.IGNORECASE)
    if m:
        return m.group(1).strip()

    depth = 0
    start = -1
    for i, ch in enumerate(raw_text):
        if ch == "{":
            if depth == 0:
                start = i
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0 and start != -1:
                return raw_text[start:i + 1].strip()

    depth = 0
    start = -1
    for i, ch in enumerate(raw_text):
        if ch == "[":
            if depth == 0:
                start = i
            depth += 1
        elif ch == "]":
            depth -= 1
            if depth == 0 and start != -1:
                return raw_text[start:i + 1].strip()

    return raw_text


# ══════════════════════════════════════════════
# 3  학교 정보
# ══════════════════════════════════════════════
_SCHOOL_ALIASES = {
    "서울대": "서울대학교", "연세대": "연세대학교", "고려대": "고려대학교",
    "성균관대": "성균관대학교", "한양대": "한양대학교", "서강대": "서강대학교",
    "중앙대": "중앙대학교", "경희대": "경희대학교", "이화여대": "이화여자대학교",
    "한국외대": "한국외국어대학교", "외대": "한국외국어대학교",
    "시립대": "서울시립대학교", "건국대": "건국대학교", "동국대": "동국대학교",
    "홍익대": "홍익대학교", "숭실대": "숭실대학교", "국민대": "국민대학교",
    "세종대": "세종대학교", "광운대": "광운대학교", "명지대": "명지대학교",
    "인하대": "인하대학교", "아주대": "아주대학교", "부산대": "부산대학교",
    "경북대": "경북대학교", "전남대": "전남대학교", "충남대": "충남대학교",
    "충북대": "충북대학교", "전북대": "전북대학교", "강원대": "강원대학교",
    "제주대": "제주대학교", "울산대": "울산대학교", "한림대": "한림대학교",
    "단국대": "단국대학교", "상명대": "상명대학교", "가톨릭대": "가톨릭대학교",
    "카이스트": "KAIST", "포항공대": "POSTECH",
}


def normalize_school_name(name: str) -> str:
    if not name:
        return ""
    return _SCHOOL_ALIASES.get(name.strip(), name.strip())


def get_user_profile(raw_school: str, raw_dept: str) -> tuple[str, str]:
    print("\n[학교 / 학과 정보 입력]")
    print("─" * 45)
    school = normalize_school_name(raw_school) if raw_school else ""
    print(f"  -> 학교: {school}" if school else "  -> 학교 정보 없이 진행합니다.")
    department = raw_dept if raw_dept else ""
    print(f"  -> 학과: {department}" if department else "  -> 학과 정보 없이 진행합니다.")
    print("─" * 45)
    return school, department


# ══════════════════════════════════════════════
# 4  HTML 파서
# ══════════════════════════════════════════════
class _TextExtractor(HTMLParser):
    SKIP_TAGS = {"script", "style", "noscript", "meta", "link", "head"}

    def __init__(self, base_url: str = ""):
        super().__init__()
        self._skip = 0
        self._parts: list[str] = []
        self._links: list[str] = []
        self._base = base_url

    def handle_starttag(self, tag, attrs):
        tl = tag.lower()
        if tl in self.SKIP_TAGS:
            self._skip += 1
        if tl == "a":
            href = dict(attrs).get("href", "")
            if href and not href.startswith(("javascript:", "mailto:", "tel:")):
                self._links.append(urllib.parse.urljoin(self._base, href))

    def handle_endtag(self, tag):
        if tag.lower() in self.SKIP_TAGS and self._skip > 0:
            self._skip -= 1

    def handle_data(self, data):
        if self._skip == 0:
            s = data.strip()
            if s:
                self._parts.append(s)

    @property
    def text(self) -> str:
        return "\n".join(self._parts)

    @property
    def links(self) -> list[str]:
        return self._links


def _is_spa(html: str) -> bool:
    visible = len(re.sub(r"<[^>]+>", " ", html).strip())
    return visible < 2000 and html.lower().count("<script") >= 2


def _extract_links_from_raw_html(raw_html: str, base_url: str) -> list[str]:
    found = []
    for m in re.finditer(
        r'(?:href|src|data-href|data-src)\s*=\s*["\']([^"\']+)["\']',
        raw_html, re.IGNORECASE
    ):
        href = m.group(1).strip()
        if href.startswith(("javascript:", "mailto:", "tel:", "#")):
            continue
        found.append(urllib.parse.urljoin(base_url, href))
    return list(dict.fromkeys(found))


# ══════════════════════════════════════════════
# 5  Notion 전용 크롤러
# ══════════════════════════════════════════════
def _is_notion_url(url: str) -> bool:
    host = urllib.parse.urlparse(url).netloc.lower()
    return "notion.site" in host or "notion.so" in host


def _parse_notion_blocks(blocks: dict) -> str:
    lines: list[str] = []

    def _rich_text_to_str(rt) -> str:
        if not isinstance(rt, list):
            return ""
        parts = []
        for chunk in rt:
            if isinstance(chunk, list) and chunk:
                parts.append(str(chunk[0]))
            elif isinstance(chunk, str):
                parts.append(chunk)
        return "".join(parts).strip()

    TEXT_PROPS = ["title", "caption", "description"]
    SKIP_TYPES = {"image", "video", "file", "audio", "pdf", "embed", "bookmark",
                  "divider", "table_of_contents", "breadcrumb", "unsupported"}

    for block_id, block_wrapper in blocks.items():
        val = block_wrapper.get("value", {})
        if not isinstance(val, dict):
            continue
        btype = val.get("type", "")
        if btype in SKIP_TYPES:
            continue
        props = val.get("properties", {})
        if not isinstance(props, dict):
            continue

        for prop_key in TEXT_PROPS:
            if prop_key in props:
                text = _rich_text_to_str(props[prop_key])
                if text:
                    lines.append(text)
                break

    return "\n".join(lines)


def _extract_from_next_data(html: str) -> str:
    m = re.search(
        r'<script[^>]+id=["\']__NEXT_DATA__["\'][^>]*>\s*(.*?)\s*</script>',
        html, re.DOTALL | re.IGNORECASE
    )
    if not m:
        return ""

    try:
        data = json.loads(m.group(1))
    except json.JSONDecodeError:
        return ""

    record_map = (
        data.get("props", {})
            .get("pageProps", {})
            .get("recordMap", {})
    )
    if not record_map:
        record_map = data.get("props", {}).get("pageProps", {})

    blocks = record_map.get("block", {})
    if not blocks:
        return ""

    text = _parse_notion_blocks(blocks)
    print(f"    __NEXT_DATA__ 파싱 성공: {len(blocks)}개 블록, {len(text)} chars", flush=True)
    return text


def _extract_og_meta(html: str, url: str) -> str:
    parts = []
    patterns = [
        (r'<title[^>]*>(.*?)</title>', "페이지 제목"),
        (r'<meta[^>]+property=["\']og:title["\'][^>]+content=["\'](.*?)["\']', "OG 제목"),
        (r'<meta[^>]+property=["\']og:description["\'][^>]+content=["\'](.*?)["\']', "OG 설명"),
        (r'<meta[^>]+name=["\']description["\'][^>]+content=["\'](.*?)["\']', "메타 설명"),
    ]
    seen = set()
    for pattern, label in patterns:
        m = re.search(pattern, html, re.IGNORECASE | re.DOTALL)
        if m:
            val = m.group(1).strip()
            val = val.replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">").replace("&#39;", "'").replace("&quot;", '"')
            if val and val not in seen:
                parts.append(f"{label}: {val}")
                seen.add(val)

    path = urllib.parse.urlparse(url).path.rstrip("/")
    slug = path.split("/")[-1]
    slug_words = re.sub(r"-[0-9a-f]{20,}$", "", slug)
    slug_clean = re.sub(r"[-_]", " ", slug_words).strip()
    if slug_clean:
        parts.append(f"URL 슬러그(페이지명 힌트): {slug_clean}")

    return "\n".join(parts)


def crawl_notion_page(url: str) -> str:
    print(f"  [Notion 크롤러] 시작: {url}", flush=True)
    collected_parts: list[str] = []

    raw_bytes = _fetch_bytes(url)
    html = ""
    if raw_bytes:
        try:
            html = raw_bytes.decode("utf-8")
        except UnicodeDecodeError:
            html = raw_bytes.decode("euc-kr", errors="replace")

    if html:
        next_data_text = _extract_from_next_data(html)
        if next_data_text.strip():
            collected_parts.append(f"[Notion 블록 콘텐츠: {url}]\n{next_data_text}")

    og_text = _extract_og_meta(html, url)
    if og_text.strip():
        collected_parts.append(f"[Notion 메타정보: {url}]\n{og_text}")

    if html:
        parser = _TextExtractor(base_url=url)
        parser.feed(html)
        plain_text = parser.text.strip()
        if plain_text and len(plain_text) > 100:
            collected_parts.append(f"[Notion HTML 텍스트: {url}]\n{plain_text}")

    combined = "\n\n".join(collected_parts).strip()
    print(f"    추출 결과: {len(combined)} chars", flush=True)

    if len(combined) < _MIN_CRAWL_CHARS:
        print(f"    WARNING: 결과 빈약 → URL 힌트 보강", flush=True)
        path = urllib.parse.urlparse(url).path.rstrip("/")
        slug_raw = path.split("/")[-1]
        slug_clean = re.sub(r"[-_]", " ", re.sub(r"-[0-9a-f]{20,}$", "", slug_raw)).strip()
        hint = (
            f"[Notion 크롤링 제한 안내]\n"
            f"Notion 페이지 URL: {url}\n"
            f"페이지 제목/경로명: {slug_clean}\n"
            f"Notion은 JavaScript 렌더링 기반이라 완전한 크롤링이 제한될 수 있습니다.\n"
            f"위 페이지명과 수집된 정보를 바탕으로 최대한 추론하되, "
            f"추론 불가 항목은 반드시 빈 배열로 반환하십시오.\n"
        )
        combined = hint + "\n\n" + combined

    print(f"  [Notion 크롤러 완료] 총 {len(combined)} chars", flush=True)
    return combined


# ══════════════════════════════════════════════
# 6  딥 크롤러 (일반 웹사이트)
# ══════════════════════════════════════════════
def _fetch_bytes(url: str) -> bytes | None:
    try:
        req = urllib.request.Request(
            url,
            headers={
                "User-Agent": (
                    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
                ),
                "Accept": "text/html,application/xhtml+xml,application/pdf,*/*;q=0.8",
                "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8",
            },
        )
        with urllib.request.urlopen(req, timeout=_FETCH_TIMEOUT) as resp:
            return resp.read(int(_MAX_CONTENT_MB * 1024 * 1024))
    except Exception as e:
        print(f"    WARNING fetch failed [{url}]: {e}", flush=True)
        return None


def _parse_pdf_bytes(data: bytes) -> str:
    try:
        reader = pypdf.PdfReader(io.BytesIO(data))
        text = "\n".join(page.extract_text() or "" for page in reader.pages)
        print(f"    OK PDF parsed ({len(reader.pages)} pages, {len(text)} chars)", flush=True)
        return text
    except Exception as e:
        print(f"    WARNING PDF parse error: {e}", flush=True)
        return ""


def _parse_html_bytes(data: bytes, url: str) -> tuple[str, list[str], str]:
    try:
        html = data.decode("utf-8")
    except UnicodeDecodeError:
        html = data.decode("euc-kr", errors="replace")
    parser = _TextExtractor(base_url=url)
    parser.feed(html)
    return parser.text, parser.links, html


def _same_origin(a: str, b: str) -> bool:
    return urllib.parse.urlparse(a).netloc == urllib.parse.urlparse(b).netloc


def _is_pdf_url(url: str, data: bytes | None = None) -> bool:
    if url.lower().split("?")[0].endswith(".pdf"):
        return True
    return bool(data and data[:4] == b"%PDF")


def deep_crawl_site(start_url: str) -> str:
    print(f"  [딥 크롤러] 시작: {start_url}", flush=True)
    collected: list[str] = []
    visited: set[str] = set()
    pdf_count = 0

    raw = _fetch_bytes(start_url)
    if raw is None:
        return ""
    if _is_pdf_url(start_url, raw):
        text = _parse_pdf_bytes(raw)
        return f"[PDF: {start_url}]\n{text}" if text else ""

    main_text, main_links, main_html = _parse_html_bytes(raw, start_url)
    visited.add(start_url)
    if main_text.strip():
        collected.append(f"[Main: {start_url}]\n{main_text}")
        print(f"    Main page: {len(main_text)} chars", flush=True)

    if _is_spa(main_html):
        print("    SPA detected — using raw HTML link extraction", flush=True)

    raw_links = _extract_links_from_raw_html(main_html, start_url)
    all_start_links = list(dict.fromkeys(main_links + raw_links))

    queue: deque[str] = deque()
    seen: set[str] = set()
    for lnk in all_start_links:
        clean = lnk.split("#")[0].rstrip("/")
        if not clean or clean in seen or clean in visited:
            continue
        if clean.startswith(("mailto:", "tel:", "javascript:")):
            continue
        seen.add(clean)
        if _is_pdf_url(clean):
            queue.appendleft(clean)
        elif _same_origin(start_url, clean):
            queue.append(clean)

    print(f"    큐 초기 크기: {len(queue)}개 링크", flush=True)
    page_count = 0

    # ── 병렬 fetch: 배치 단위로 동시 다운로드 ──
    def _fetch_batch(batch: list) -> list:
        """URL 배치를 ThreadPoolExecutor로 동시 fetch. (url, raw) 쌍 반환."""
        with ThreadPoolExecutor(max_workers=_CRAWL_WORKERS) as ex:
            futures = {ex.submit(_fetch_bytes, u): u for u in batch}
            out = []
            for fut in as_completed(futures):
                u = futures[fut]
                try:
                    out.append((u, fut.result()))
                except Exception:
                    out.append((u, None))
        return out

    while queue and (page_count < _MAX_PAGES or pdf_count < _MAX_PDFS):
        # 남은 한도 내에서 최대 _CRAWL_WORKERS개씩 배치 처리
        remaining = min(
            _CRAWL_WORKERS,
            (_MAX_PAGES - page_count) + max(0, _MAX_PDFS - pdf_count),
        )
        batch = []
        while queue and len(batch) < remaining:
            u = queue.popleft()
            if u not in visited:
                visited.add(u)
                batch.append(u)
        if not batch:
            break

        for url, sub_raw in _fetch_batch(batch):
            if sub_raw is None:
                continue

            if _is_pdf_url(url, sub_raw):
                if pdf_count >= _MAX_PDFS:
                    _tprint(f"    PDF 한도 도달, 건너뜀: {url}", flush=True)
                    continue
                text = _parse_pdf_bytes(sub_raw)
                if text.strip():
                    collected.append(f"[PDF: {url}]\n{text}")
                    pdf_count += 1
                    _tprint(f"    PDF collected ({pdf_count}/{_MAX_PDFS}): {url}", flush=True)
                continue

            if page_count >= _MAX_PAGES:
                continue
            sub_text, sub_links, sub_html = _parse_html_bytes(sub_raw, url)
            page_count += 1
            if sub_text.strip():
                collected.append(f"[Page: {url}]\n{sub_text}")
                _tprint(f"    Page {page_count}: {url} ({len(sub_text)} chars)", flush=True)

            sub_raw_links = _extract_links_from_raw_html(sub_html, url)
            for lnk in list(dict.fromkeys(sub_links + sub_raw_links)):
                clean = lnk.split("#")[0].rstrip("/")
                if not clean or clean in seen or clean in visited:
                    continue
                if clean.startswith(("mailto:", "tel:", "javascript:")):
                    continue
                seen.add(clean)
                if _is_pdf_url(clean):
                    queue.appendleft(clean)
                elif _same_origin(start_url, clean):
                    queue.append(clean)

    result = "\n\n".join(collected)
    print(f"  [딥 크롤러 완료] {len(collected)}개 소스, {len(result)} chars", flush=True)
    return result


# ══════════════════════════════════════════════
# 7  파일 리더
# ══════════════════════════════════════════════
def read_file(path: str) -> str:
    if not os.path.isfile(path):
        print(f"  ERROR file not found: {path}", flush=True)
        return ""
    if path.lower().endswith(".pdf"):
        with open(path, "rb") as f:
            return _parse_pdf_bytes(f.read())
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            content = f.read()
        print(f"  OK file read ({len(content)} chars)", flush=True)
        return content
    except Exception as e:
        print(f"  ERROR reading file: {e}", flush=True)
        return ""


# ══════════════════════════════════════════════
# 8  입력 수집
# ══════════════════════════════════════════════
def _looks_like_url(s: str) -> bool:
    return bool(re.match(r"^https?://\S+", s) or re.match(r"^www\.\S+", s))


def _looks_like_filepath(s: str) -> bool:
    return "\n" not in s and os.path.isfile(s.strip())


def get_user_input(lines: list[str]) -> str:
    print("\n" + "-" * 65)
    print("  경력/활동/자격증 정보를 입력하세요.")
    print("  URL(노션 포함), 파일 경로, 또는 직접 텍스트 모두 가능합니다.")
    print("-" * 65 + "\n")

    raw = "\n".join(lines).strip()
    if not raw:
        return ""

    first_line = lines[0].strip() if lines else ""

    if len(lines) == 1 and _looks_like_url(first_line):
        url = first_line if first_line.startswith("http") else "https://" + first_line

        if _is_notion_url(url):
            print(f"\n  [자동 감지] Notion URL → Notion 전용 크롤러 시작", flush=True)
            content = crawl_notion_page(url)
        else:
            print(f"\n  [자동 감지] URL → 딥 크롤링 시작", flush=True)
            content = deep_crawl_site(url)

        if content.strip():
            return f"[SOURCE_URL: {url}]\n\n{content}"
        else:
            print(f"  WARNING: 크롤링 실패 → URL 힌트 모드로 진행", flush=True)
            return (
                f"[SOURCE_URL: {url}]\n"
                f"[크롤링 실패]\n"
                f"URL: {url}\n"
                f"URL 경로명과 도메인을 바탕으로 내용을 최대한 추론하십시오.\n"
                f"추론 불가 항목은 빈 배열로 반환하십시오."
            )

    if len(lines) == 1 and _looks_like_filepath(first_line):
        print(f"\n  [자동 감지] 파일 경로 → 읽는 중: {first_line}", flush=True)
        content = read_file(first_line.strip())
        return content if content.strip() else raw

    print(f"\n  [자동 감지] 텍스트 직접 입력 ({len(raw)}자)", flush=True)
    return raw


# ══════════════════════════════════════════════
# 9  Embedding
# ══════════════════════════════════════════════
def get_embedding(text: str):
    if not text:
        return None
    truncated = text[:10000]
    for kwargs in [
        {"content": truncated, "config": types.EmbedContentConfig(task_type="RETRIEVAL_DOCUMENT")},
        {"content": truncated},
        {"contents": truncated, "config": types.EmbedContentConfig(task_type="RETRIEVAL_DOCUMENT")},
    ]:
        try:
            result = client.models.embed_content(model=_EMBEDDING_MODEL, **kwargs)
            if hasattr(result, "embeddings") and result.embeddings:
                return result.embeddings[0].values
            if hasattr(result, "embedding") and result.embedding:
                return result.embedding.values
        except Exception:
            continue
    print("  WARNING embedding all fallbacks failed", flush=True)
    return None


# ══════════════════════════════════════════════
# 10  Hallucination 방지 규칙 (공통)
# ══════════════════════════════════════════════
_STRICT_HALLUCINATION_RULES = """
=== STRICT MODE: Hallucination 절대 금지 ===
규칙 1. 실재 확인 불가 항목은 생성 금지
  - 공모전·프로젝트: 코드 실행 시점(오늘) 기준으로 현재 접수 중이거나
    정기 개최(매년/반기)가 확인된 것만. 이름·주관기관이 불확실하면 배열에서 제외.
    과거에 종료된 공모전을 현재형으로 서술하지 말 것.
  - 자격증: 국가공인 또는 민간자격증으로 현재 실제 시행 중인 것만.
  - 동아리·학회: 지정 학교에 현재 실재하는 것만.
  - 채용공고: URL이 확인된 공고만.

규칙 2. URL 절대 금지 (코드 레벨에서 강제 차단)
  - URL 필드는 반드시 null만 반환. 추측·조합·변형·기억에 의한 생성 모두 금지.
  - 설령 URL이 기억난다고 해도 null로 반환할 것.
  - 시스템이 Google Search로 직접 확인하고 HTTP 접근 검증을 통과한 URL만 최종 사용됨.
  - 빈 문자열 ""도 금지. null 이외 어떤 값도 URL 필드에 넣지 말 것.

규칙 3. 동아리·학회 최소 추천 수
  - 학교 정보가 있을 때: 교내·연합·외부를 합산하여 최소 3개 이상 추천할 것.
  - 교내동아리/교내학회, 연합동아리/연합학회, 외부학회 중 가능한 타입을 균형 있게 포함.
  - 실재 여부가 확실하지 않으면 해당 항목은 제외하되, 제외로 인해 3개 미만이 되면
    실재가 확인 가능한 다른 항목으로 보충하여 3개를 채울 것.
  - 학교 정보가 없을 때: 연합동아리·외부학회 위주로 최소 2개 이상 추천.

규칙 4. 빈 배열 우선 (동아리 제외)
  - 동아리 이외 항목(자격증, 공모전, 채용공고): 추천할 항목이 없거나 확인 불가이면 [] 반환.
  - 채우기 위해 임의로 만들어내는 것은 빈 배열보다 훨씬 나쁘다.

규칙 5. 연도·마감일 날조 금지
  - 공모전 마감일·채용 마감일을 모르면 null 또는 "미정".
  - 연도를 추측해서 채우지 말 것.

규칙 6. 출력은 순수 JSON만
  - 마크다운 코드블록, 설명 텍스트, 주석 절대 포함 금지.
"""


# ══════════════════════════════════════════════
# 11  시스템 프롬프트 빌더
# ══════════════════════════════════════════════
def build_system_prompt_comprehensive(ref_date: date, school: str, department: str = "") -> str:
    rd = ref_date.strftime("%Y-%m-%d")
    school_str = school if school else "정보 없음"
    dept_str   = department if department else "정보 없음"

    club_count_rule = (
        f"- 동아리·학회는 반드시 '{school}'에 실재하는 것만 추천\n"
        f"- 다른 학교 동아리·학회 추천 절대 금지\n"
        f"- 연합동아리는 '{school}' 지부 존재가 확인된 것만\n"
        f"- 교내·연합·외부 타입을 균형 있게 섞어 최소 3개 이상 추천\n"
        if school else
        "- 학교 불명: 교내 동아리·학회 추천 금지, 연합·외부 위주로 최소 2개 이상 추천\n"
    )
    dept_rules = (
        f"- 자격증·공모전·동아리 추천 시 '{dept_str}' 전공·커리어 경로 최우선 반영\n"
        if department else ""
    )

    return (
        "당신은 대한민국 최고의 커리어 컨설턴트이자 데이터 분석가입니다.\n"
        f"코드 실행(분석) 기준일: {rd} — 이 날짜를 '오늘'로 간주하십시오.\n"
        f"\n=== 사용자 프로필 ===\n학교: {school_str}\n학과: {dept_str}\n"
        f"{club_count_rule}"
        f"{dept_rules}"
        f"{_STRICT_HALLUCINATION_RULES}\n"
        "=== 분석 항목 ===\n"
        "A. 역량 클러스터링 + STAR 이력서 초안\n"
        "B. 보유 항목 간 시너지 조합 (2~5개)\n"
        "C. 추가 추천: 자격증, 동아리·학회(최소 3개), 공모전(현재 시점 기준)\n"
        f"D. 채용공고 추천 ({rd} 이후 마감, URL 확인된 것만)\n"
        "E. 단기·중기·장기 액션 플랜\n"
        "F. 냉정한 보완점 진단 (critical_diagnosis) — 아래 지침 엄수\n\n"
        "=== 냉정한 보완점 진단(F) 작성 지침 ===\n"
        "목적: 사용자가 듣기 불편하더라도 반드시 알아야 할 진짜 약점을 직시하게 하는 것.\n"
        "절대 금지: 칭찬·위로·긍정적 포장 — F 섹션에는 좋은 말 하지 말 것.\n"
        "판단 기준 (모두 독립적으로 평가하고, 해당하는 항목만 포함):\n"
        "  [활동 수량] 직군 평균 대비 활동 총 개수가 부족한가?\n"
        "    → 구체적 수치로 표현 (예: '인턴 경험 0회 — 해당 직군 지원자 평균 1.5회')\n"
        "  [활동 깊이] 각 항목의 서술 내용이 너무 짧거나 수치/성과가 없는가?\n"
        "    → 어떤 항목이, 왜 얕은지 구체적으로 지적\n"
        "  [직무 연관성] 지원 직군과 무관한 활동만 있거나, 핵심 직무 경험이 비어있는가?\n"
        "    → 빈 직무 카테고리를 명시 (예: '데이터 분석 직군인데 SQL 경험 전무')\n"
        "  [스킬 공백] 해당 직군에서 필수로 요구되는 기술/자격이 보이지 않는가?\n"
        "    → 없는 스킬을 열거, 왜 치명적인지 설명\n"
        "  [기간/연속성] 경력 공백이 있거나 활동들 사이 단절이 심각한가?\n"
        "    → 공백 기간을 명시\n"
        "  [서류 품질] 입력된 내용이 이력서로서 설득력 없게 작성되어 있는가?\n"
        "    → 구체적으로 어떤 표현/항목이 문제인지 지적\n"
        "  [경쟁력 격차] 동일 직군·학교 수준 경쟁자 대비 눈에 띄는 차별점이 없는가?\n"
        "    → 경쟁자들이 보통 갖고 있는 것 중 없는 것을 열거\n"
        "severity 기준:\n"
        "  critical   : 이 상태로 지원하면 서류 탈락 가능성 높음\n"
        "  major      : 합격 가능성을 뚜렷이 낮추는 약점\n"
        "  minor      : 있으면 좋지만 없어도 당장 치명적이지 않은 부족함\n"
        "priority_action: 해당 약점을 개선하기 위해 지금 당장 해야 할 한 가지 행동 (동사로 시작)\n\n"
        "[출력] 순수 JSON만 (코드블록·설명 금지)\n\n"
        "{\n"
        '  "status": "success",\n'
        f'  "user_school": "{school_str}",\n'
        f'  "user_department": "{dept_str}",\n'
        '  "brief_summary": "핵심 한 줄 요약",\n'
        '  "detailed_summary": "심층 요약",\n'
        '  "keyword_clustering": {\n'
        '    "personality_tendency": ["성향"],\n'
        '    "core_competency": ["역량"],\n'
        '    "job_industry": ["직군"]\n'
        "  },\n"
        '  "experience_insights": {"motivation": "동기", "learning_points": "배움"},\n'
        '  "synergy_combinations": [\n'
        '    {"combination_title":"조합명","items":["항목1","항목2"],'
        '"synergy_reason":"이유","expected_effect":"효과","applicable_roles":["직무"]}\n'
        "  ],\n"
        '  "additional_recommendations": {\n'
        '    "certifications": [\n'
        '      {"name":"자격증명","reason":"연계 이유","expected_effect":"기대 효과",'
        '"estimated_duration":"취득 소요 기간"}\n'
        "    ],\n"
        '    "clubs_and_societies": [\n'
        "      {\n"
        '        "name": "동아리/학회명",\n'
        '        "type": "교내동아리/교내학회/연합동아리/연합학회/외부학회",\n'
        f'        "school_affiliation": "{school_str}",\n'
        '        "description": "실제 알고 있는 활동 내용 (불확실하면 빈 문자열)",\n'
        '        "reason": "추천 이유",\n'
        '        "expected_effect": "기대 효과",\n'
        '        "url": null,\n'
        '        "search_query": "검증용 검색어",\n'
        '        "search_verified": false\n'
        "      }\n"
        "    ],\n"
        '    "projects_and_contests": [\n'
        "      {\n"
        '        "name": "공모전명 (주관기관이 확인된 것만)",\n'
        '        "organizer": "주관기관명",\n'
        '        "reason": "추천 이유",\n'
        '        "expected_effect": "기대 효과",\n'
        '        "url": null,\n'
        '        "deadline": null,\n'
        '        "is_regular": true\n'
        "      }\n"
        "    ]\n"
        "  },\n"
        '  "resume_star_format": [\n'
        '    {"title":"경험명","S":"상황","T":"과제","A":"행동","R":"결과"}\n'
        "  ],\n"
        '  "action_plan": {"단기":"3개월 이내","중기":"6개월~1년","장기":"1년 이상"},\n'
        '  "critical_diagnosis": {\n'
        '    "one_line_verdict": "현재 이력 전반의 상태를 냉정하게 한 문장으로 (예: 활동은 있으나 직무 연관성과 깊이가 모두 부족한 상태)",\n'
        '    "weaknesses": [\n'
        "      {\n"
        '        "id": 1,\n'
        '        "category": "활동_수량|활동_깊이|직무_연관성|스킬_공백|기간_연속성|서류_품질|경쟁력_격차",\n'
        '        "severity": "critical|major|minor",\n'
        '        "title": "약점 제목 (10자 이내, 핵심만)",\n'
        '        "diagnosis": "왜 약점인지 냉정하고 구체적인 근거 (입력 데이터에서 확인된 사실 기반)",\n'
        '        "evidence": "입력에서 이 약점을 판단한 구체적 근거 (인용 또는 없음)",\n'
        '        "impact": "이 약점이 취업/커리어에 미치는 실질적 영향",\n'
        '        "priority_action": "지금 당장 해야 할 한 가지 구체적 행동 (동사로 시작)"\n'
        "      }\n"
        "    ],\n"
        '    "missing_experience_types": [\n'
        '      "현재 이력에서 완전히 빠진 경험 유형 (예: 인턴십, 팀 프로젝트, 수상 이력 등)"\n'
        "    ],\n"
        '    "content_quality_issues": [\n'
        "      {\n"
        '        "item": "문제가 있는 특정 이력/서술 항목명",\n'
        '        "issue": "구체적으로 무엇이 부실한가 (수치 없음/기간 불명/역할 불명 등)",\n'
        '        "improvement_hint": "이렇게 바꾸면 설득력이 생긴다 — 구체적 표현 예시 제시"\n'
        "      }\n"
        "    ],\n"
        '    "competitor_gap": "동일 직군·학교 수준 경쟁자 대비 현재 포트폴리오가 갖지 못한 결정적 차이점"\n'
        "  },\n"
        '  "valid_job_recommendations": [\n'
        "    {\n"
        '      "company": "회사명",\n'
        '      "role": "직무",\n'
        '      "deadline": "YYYY-MM-DD 또는 상시채용",\n'
        '      "why_match": "매칭 근거",\n'
        '      "url": null\n'
        "    }\n"
        "  ],\n"
        '  "missing_info_warning": null\n'
        "}"
    )



# ══════════════════════════════════════════════
# 12  Embedding 유틸리티
# ══════════════════════════════════════════════
# ══════════════════════════════════════════════
# 12-a  URL Hallucination 완전 차단 레이어
# ══════════════════════════════════════════════
#
# 설계 원칙:
#   - LLM이 반환한 URL은 절대 신뢰하지 않는다.
#   - 형식 검사(정규식) → 실제 HTTP 접근(HEAD/GET) 2단계를 모두 통과한 URL만 허용.
#   - 둘 중 하나라도 실패하면 None 반환 (hallucination URL을 사용자에게 노출 금지).
#   - 모든 URL 할당 지점에서 raw 문자열 대신 반드시 이 함수를 통과해야 한다.

_URL_VALID_PATTERN = re.compile(
    r"^https?://"                    # 반드시 http(s) 스킴
    r"(?:[A-Za-z0-9\-._~!$&'()*+,;=:@]|%[0-9A-Fa-f]{2})+"  # 호스트
    r"(?:/[^\s<>\x22{}|\^`\[\]]*)?$"  # 경로 (선택, \x22=쌍따옴표)
)

_URL_SKIP_PATTERNS = re.compile(
    r"example\.com|placeholder|dummy|your[-_]?url|"
    r"{{.*?}}|<.*?>|\.\.|\s",        # 템플릿·공백·점점 등
    re.IGNORECASE,
)


def _validate_url(raw: object, timeout: int = 6) -> str | None:
    """
    LLM이 반환한 URL raw 값을 2단계로 검증.

    중요: URL 검증 실패 = URL만 None 반환.
          동아리·학회·자격증·공모전 항목 자체를 탈락시키지 않는다.
          URL은 부가 정보이며, 실체 존재 여부는 Google Search 검증이 담당.
          (채용공고는 URL 없으면 지원 불가이므로 별도 처리)

    STEP 1 — 형식 검사 (즉시, 네트워크 없음)
      - None / "null" / "" / 비문자열 → None
      - http(s):// 스킴 없음 → None
      - 플레이스홀더·템플릿 패턴 탐지 → None
      - URL 길이 비정상(< 12 or > 500) → None

    STEP 2 — 실제 HTTP 접근 검증 (네트워크)
      - HEAD 요청 → 200~399 이면 OK
      - HEAD 미지원 시 GET fallback (최대 4KB 읽기)
      - 4xx / 5xx / 연결 실패 / 타임아웃 → None (hallucination URL 차단)
      - 리다이렉트가 다른 도메인으로 이동하면 → None (잘못된 링크 방지)

    반환: 검증 통과한 URL 문자열, 실패하면 None
    """
    # ── STEP 1: 형식 검사 ────────────────────────
    if raw is None:
        return None
    url = str(raw).strip()

    if not url or url.lower() in ("null", "none", "undefined", "", "n/a", "-"):
        return None
    if len(url) < 12 or len(url) > 500:
        return None
    if not _URL_VALID_PATTERN.match(url):
        return None
    if _URL_SKIP_PATTERNS.search(url):
        return None

    # ── STEP 2: 실제 HTTP 접근 ───────────────────
    parsed = urllib.parse.urlparse(url)
    original_netloc = parsed.netloc.lower()

    try:
        req = urllib.request.Request(
            url,
            method="HEAD",
            headers={
                "User-Agent": (
                    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
                ),
                "Accept": "*/*",
            },
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            final_url  = resp.geturl()
            status     = resp.status
            final_netloc = urllib.parse.urlparse(final_url).netloc.lower()

            # 도메인 변경 리다이렉트 차단 (예: 오래된 링크가 광고 페이지로 이동)
            if final_netloc and final_netloc != original_netloc:
                # www. 접두사 차이는 허용
                orig_clean  = original_netloc.removeprefix("www.")
                final_clean = final_netloc.removeprefix("www.")
                if orig_clean != final_clean:
                    print(
                        f"    [URL 검증] FAIL 도메인 변경: {original_netloc} → {final_netloc} ({url})",
                        flush=True,
                    )
                    return None

            if 200 <= status < 400:
                return final_url  # 리다이렉트 최종 URL 반환
            print(f"    [URL 검증] FAIL HTTP {status}: {url}", flush=True)
            return None

    except urllib.error.HTTPError as e:
        if e.code == 405:
            # HEAD 미지원 → GET fallback
            try:
                req2 = urllib.request.Request(
                    url,
                    headers={
                        "User-Agent": (
                            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
                        ),
                    },
                )
                with urllib.request.urlopen(req2, timeout=timeout) as resp2:
                    if 200 <= resp2.status < 400:
                        resp2.read(4096)  # 최소 읽기로 연결 확인
                        return url
            except Exception:
                pass
        print(f"    [URL 검증] FAIL HTTP {e.code}: {url}", flush=True)
        return None
    except Exception as e:
        print(f"    [URL 검증] FAIL {type(e).__name__}: {url}", flush=True)
        return None


def _validate_url_batch(url_dict: dict[str, object], timeout: int = 6) -> dict[str, str | None]:
    """
    {key: raw_url} 딕셔너리를 병렬로 검증.
    반환: {key: validated_url_or_None}
    최대 _VERIFY_WORKERS 스레드 사용.
    """
    if not url_dict:
        return {}

    def _one(key: str, raw: object) -> tuple[str, str | None]:
        return key, _validate_url(raw, timeout=timeout)

    with ThreadPoolExecutor(max_workers=min(_VERIFY_WORKERS, len(url_dict))) as ex:
        futures = {ex.submit(_one, k, v): k for k, v in url_dict.items()}
        results = {}
        for fut in as_completed(futures):
            key, validated = fut.result()
            results[key] = validated
    return results



def _cosine_similarity(a: list, b: list) -> float:
    """두 벡터의 코사인 유사도. 벡터가 없으면 0.0 반환."""
    if not a or not b or len(a) != len(b):
        return 0.0
    dot   = sum(x * y for x, y in zip(a, b))
    norm_a = sum(x * x for x in a) ** 0.5
    norm_b = sum(x * x for x in b) ** 0.5
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


def _embed_query(text: str) -> list | None:
    """단일 텍스트를 RETRIEVAL_QUERY 태스크로 임베딩."""
    if not text or not text.strip():
        return None
    truncated = text[:2000]
    for kwargs in [
        {"content": truncated, "config": types.EmbedContentConfig(task_type="RETRIEVAL_QUERY")},
        {"content": truncated},
    ]:
        try:
            result = client.models.embed_content(model=_EMBEDDING_MODEL, **kwargs)
            if hasattr(result, "embeddings") and result.embeddings:
                return list(result.embeddings[0].values)
            if hasattr(result, "embedding") and result.embedding:
                return list(result.embedding.values)
        except Exception:
            continue
    return None


def _embed_batch(texts: list[str]) -> list[list | None]:
    """
    텍스트 목록을 병렬로 임베딩. 실패한 항목은 None 반환.
    최대 _CRAWL_WORKERS 스레드 사용.
    """
    if not texts:
        return []

    def _one(text: str) -> list | None:
        return _embed_query(text)

    with ThreadPoolExecutor(max_workers=min(_CRAWL_WORKERS, len(texts))) as ex:
        futures = [ex.submit(_one, t) for t in texts]
        return [f.result() for f in futures]


def _filter_by_similarity(
    candidates: list[dict],
    profile_vec: list,
    name_key: str = "name",
    extra_keys: list[str] | None = None,
    threshold: float = 0.55,
    top_k: int = 10,
) -> list[dict]:
    """
    후보 목록을 profile_vec 과의 코사인 유사도로 필터링.
    - name_key: 기본 임베딩 텍스트 필드
    - extra_keys: 추가로 이어붙일 필드 목록 (맥락 보강용)
      예) extra_keys=["reason"] → "동아리명 추천이유" 로 임베딩
    - threshold 미만은 탈락
    - 유사도 내림차순으로 top_k 반환
    - profile_vec 없으면 원본 순서 그대로 반환 (안전 폴백)
    """
    if not profile_vec or not candidates:
        return candidates[:top_k]

    def _make_text(c: dict) -> str:
        parts = [c.get(name_key, "")]
        for k in (extra_keys or []):
            v = c.get(k, "")
            if v:
                parts.append(str(v))
        return " ".join(p for p in parts if p).strip()

    texts = [_make_text(c) for c in candidates]
    vecs  = _embed_batch(texts)

    scored = []
    for c, vec in zip(candidates, vecs):
        sim = _cosine_similarity(profile_vec, vec) if vec else 0.0
        c["_similarity"] = round(sim, 4)
        scored.append((sim, c))

    # threshold 미만 탈락
    passed = [(s, c) for s, c in scored if s >= threshold]
    if not passed:
        # 전원 탈락 시 threshold를 완화해 최소 1개는 보존 (완전 공백 방지)
        passed = sorted(scored, key=lambda x: -x[0])[:max(1, top_k // 2)]

    passed.sort(key=lambda x: -x[0])
    return [c for _, c in passed[:top_k]]


# ══════════════════════════════════════════════
# 13  채용공고 URL 접근성 검증
# ══════════════════════════════════════════════

def _verify_url_content(url: str, company: str, role: str, timeout: int = 10) -> dict:
    res = {"accessible": False, "content_match": False, "reason": ""}
    if not url or not url.startswith("http"):
        res["reason"] = "유효하지 않은 URL"
        return res
    try:
        req = urllib.request.Request(
            url, headers={"User-Agent": "Mozilla/5.0 (compatible; CareerBot/1.0)"}
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            if resp.status >= 400:
                res["reason"] = f"HTTP {resp.status}"
                return res
            res["accessible"] = True
            page = resp.read(80_000).decode("utf-8", errors="replace").lower()

        co       = company.lower().strip()
        co_clean = re.sub(r"\(주\)|주식회사|\s+", "", co)
        co_found = co in page or co_clean in page

        role_kws  = [k for k in re.split(r"[/\s·,]+", role.lower()) if len(k) >= 2]
        role_found = sum(1 for k in role_kws if k in page) >= max(1, len(role_kws) // 2)

        job_kws = ["채용", "지원", "모집", "recruit", "career", "apply", "job", "hiring"]
        is_job  = any(k in page for k in job_kws)

        if co_found and (role_found or is_job):
            res["content_match"] = True
        else:
            reasons = []
            if not co_found:
                reasons.append(f"회사명 '{company}' 미발견")
            if not role_found and not is_job:
                reasons.append("채용 관련 내용 미발견")
            res["reason"] = ", ".join(reasons)
    except urllib.error.HTTPError as e:
        res["reason"] = f"HTTP {e.code}"
    except Exception as e:
        res["reason"] = str(e)[:80]
    return res


def verify_job_urls(jobs: list) -> tuple[list, list]:
    """채용공고 URL 접근성을 _VERIFY_WORKERS 스레드로 병렬 검증."""
    verified, failed = [], []

    needs_check, no_url = [], []
    for job in jobs:
        raw_url = job.get("url") or ""
        if not raw_url or raw_url == "null":
            job["_fail_reason"] = "URL 미확보"
            no_url.append(job)
            continue
        # 형식 검사만 먼저 수행 (HTTP 접근은 _check_one에서)
        if not _URL_VALID_PATTERN.match(raw_url) or _URL_SKIP_PATTERNS.search(raw_url):
            job["_fail_reason"] = f"URL 형식 불량: {raw_url[:80]}"
            no_url.append(job)
            continue
        needs_check.append(job)

    for job in no_url:
        label = f"{job.get('company','')} | {job.get('role','')}"
        _tprint(f"    [{label}] -> FAIL: URL 미확보 -> 제외", flush=True)
        failed.append(job)

    if not needs_check:
        return verified, failed

    def _check_one(job: dict) -> tuple[dict, bool, str]:
        url     = job.get("url", "")
        company = job.get("company", "")
        role    = job.get("role", "")
        check   = _verify_url_content(url, company, role)
        ok      = check["accessible"] and check["content_match"]
        reason  = check["reason"] if check["accessible"] else f"접근 실패: {check['reason']}"
        return job, ok, reason

    total = len(needs_check)
    with ThreadPoolExecutor(max_workers=_VERIFY_WORKERS) as ex:
        futures  = {ex.submit(_check_one, job): job for job in needs_check}
        done_idx = 0
        for fut in as_completed(futures):
            done_idx += 1
            job, ok, reason = fut.result()
            label = f"{job.get('company','?')} | {job.get('role','?')}"
            if ok:
                _tprint(f"    [{done_idx}/{total}] {label} -> OK", flush=True)
                verified.append(job)
            else:
                _tprint(f"    [{done_idx}/{total}] {label} -> FAIL: {reason} -> 제외", flush=True)
                job["_fail_reason"] = reason
                failed.append(job)

    return verified, failed


# ══════════════════════════════════════════════
# 14  동아리·학회 — Embedding 클러스터링 기반 추천
# ══════════════════════════════════════════════

_CLUB_SIMILARITY_THRESHOLD = 0.50   # 코사인 유사도 하한
_CLUB_CANDIDATE_POOL       = 15     # 1차 LLM 후보 요청 수
_CLUB_TOP_K                = 8      # 유사도 필터 후 Google Search 넘길 최대 수
_CLUB_MIN_VERIFIED         = 3      # 최소 검증 통과 목표


def _build_profile_text(school: str, department: str, career_text: str) -> str:
    """
    임베딩용 프로필 텍스트 생성.

    우선순위:
      1순위 (80%): 관심사·경력·활동 — 동아리 연관성의 핵심 기준
      2순위 (20%): 전공 — 보조 힌트
      참고용 (미포함): 학교 — 유사도 계산에서 제외 (학교 필터는 별도 로직으로 처리)

    학교를 여기에 넣지 않는 이유:
      - "서울대학교"라는 단어가 임베딩에 포함되면 학교명이 들어간
        동아리(예: "서울대 합창단")가 과도하게 높은 유사도를 얻어
        관심사 기반 추천이 왜곡됨.
      - 학교 가입 가능성은 _club_school_eligible()로 소프트 점수 부여.
    """
    parts = []
    # 1순위: 관심사·경력·활동 — 반복하여 임베딩 공간에서 비중 강화
    if career_text:
        trimmed = career_text[:1200]
        parts.append(trimmed)
        parts.append(trimmed)   # 동일 텍스트 반복 → 코사인 유사도에서 비중 증가
    # 2순위: 전공 (관심 분야 힌트, 학교명은 제외)
    if department:
        parts.append(f"관심 전공 및 분야: {department}")
    return " ".join(parts)


def _build_interest_text(career_text: str) -> str:
    """
    동아리 관심사 매칭 전용 임베딩 텍스트.
    학교·전공을 완전히 제외하고 순수 관심사·활동·역량만 추출.
    """
    return career_text[:1000] if career_text else ""


def _generate_club_candidates(
    school: str,
    department: str,
    exclude_names: list,
    career_text: str = "",
    pool_size: int = _CLUB_CANDIDATE_POOL,
) -> list[dict]:
    """
    LLM + Google Search로 동아리·학회 후보 목록 생성.

    추천 기준 우선순위:
      1순위 — 해당 학교 학생이 가입 가능하고 유저의 관심사·활동과 연관된 곳
      2순위 — 학과·전공 관련성
    이름·타입·학교 소속·추천이유만 요청. 상세 설명은 검증 단계에서 채움.
    """
    exclude_str   = ", ".join(exclude_names) if exclude_names else "없음"
    interest_hint = f"\n[유저 관심사/경력 요약]\n{career_text[:400]}" if career_text else ""
    dept_hint     = f"전공: {department}" if department else ""

    # 가입 가능성 기준: 교내 + 연합(지부) + 외부 전국
    school_eligibility = (
        f"- '{school}' 재학생이 가입 가능한 교내동아리·교내학회\n"
        f"- '{school}' 지부가 확인되는 연합동아리·연합학회\n"
        f"- 누구나 가입 가능한 전국 단위 외부학회·협회\n"
        if school else
        "- 누구나 가입 가능한 연합동아리·연합학회·외부학회·협회\n"
    )

    prompt = (
        f"[사용자 정보]\n"
        f"학교: {school or '미상'}  /  {dept_hint or '학과 미상'}"
        f"{interest_hint}\n\n"
        f"[이미 제외된 항목]: {exclude_str}\n\n"
        f"아래 조건으로 동아리·학회 후보를 {pool_size}개 추천하세요.\n\n"
        "=== 추천 우선순위 ===\n"
        "1순위(필수): 해당 학교 학생이 실제로 가입할 수 있는가?\n"
        f"{school_eligibility}"
        "1순위(필수): 유저의 관심사·경력·활동과 얼마나 연관되는가?\n"
        "  → 위 [유저 관심사/경력 요약]을 참고하여 실질적 연관성이 높은 순으로 추천\n"
        "2순위(참고): 학과·전공과의 연관성\n\n"
        "=== 기타 조건 ===\n"
        "- 교내·연합·외부 타입 고루 포함\n"
        "- 정식 명칭이 확실하지 않은 동아리는 절대 포함 금지\n"
        "- reason 필드에는 유저의 관심사와 이 동아리가 어떻게 연결되는지 구체적으로 기술\n"
        "- 설명·URL은 빈 문자열·null로 두고, 이름·타입·추천이유만 정확히 기입\n\n"
        "순수 JSON 배열만 출력 (다른 텍스트 금지):\n"
        '[\n  {\n'
        '    "name": "동아리/학회 정식 명칭",\n'
        '    "type": "교내동아리|교내학회|연합동아리|연합학회|외부학회",\n'
        f'    "school_affiliation": "{school or ""}",\n'
        '    "description": "",\n'
        '    "reason": "유저 관심사와의 구체적 연결고리",\n'
        '    "expected_effect": "가입 시 기대 효과",\n'
        '    "url": null,\n'
        '    "search_query": "Google 검색어",\n'
        '    "search_verified": false\n'
        '  }\n]'
    )
    system = (
        "당신은 한국 대학교 동아리·학회 추천 전문가입니다.\n"
        "Google Search로 실재하는 동아리·학회만 후보로 제시하십시오.\n"
        "추천 시 유저의 관심사·경력과의 연관성을 최우선으로 고려하고,\n"
        "학교·학과 일치 여부는 가입 가능성 확인용으로만 사용하십시오.\n"
        "존재 여부가 불확실한 항목은 절대 포함하지 마십시오."
    )
    raw = _call_model_raw(prompt, system_prompt=system, use_google_search=True)
    try:
        parsed = json.loads(clean_json_response(raw))
        return [r for r in parsed if isinstance(r, dict) and r.get("name", "").strip()]
    except Exception as e:
        print(f"    WARNING: 동아리 후보 파싱 실패 ({e})", flush=True)
        return []


def _club_school_eligible(club: dict, user_school: str) -> tuple[bool, float]:
    """
    해당 학교 학생이 가입 가능한지 판단 + 학교 매칭 보너스 점수 반환.

    반환: (eligible: bool, school_bonus: float)
      eligible   = True  → 가입 가능 (검증 진행)
      eligible   = False → 가입 불가능한 타교 전용 동아리 (제외)
      school_bonus       → 유사도에 더할 가산점
        1.0: 교내 소속 정확히 일치
        0.5: 연합동아리 (지부 존재 가능)
        0.3: 외부학회 (누구나 가입 가능)
        0.0: 타교 전용 → eligible=False
    """
    ctype = club.get("type", "").lower()

    # 외부학회·협회: 누구나 가입 가능 → 항상 eligible
    if "외부" in ctype:
        return True, 0.3

    # 연합동아리·학회: 대부분 여러 학교 지부 → eligible, 중간 보너스
    if "연합" in ctype:
        return True, 0.5

    # 교내동아리·학회: 학교 일치 여부로 판단
    if not user_school:
        # 학교 정보 없으면 교내는 제외 (다른 학교 것일 수 있음)
        return False, 0.0

    affil = normalize_school_name(club.get("school_affiliation", ""))
    if affil == normalize_school_name(user_school):
        return True, 1.0   # 교내 소속 정확히 일치 → 최대 보너스

    # 소속 학교가 명시됐는데 다른 학교 → 가입 불가
    if affil:
        return False, 0.0

    # school_affiliation이 비어있으면 일단 통과 (검증 단계에서 확인)
    return True, 0.2


def _verify_clubs_google(school: str, clubs: list) -> list[dict]:
    """
    Google Search로 동아리 실재 여부 검증.
    검증 실패 항목은 제외, 성공 항목에 url·description 채움.
    """
    if not clubs:
        return []

    club_list = "\n".join(
        f"  {i+1}. {c.get('name','?')} (type={c.get('type','?')})"
        for i, c in enumerate(clubs)
    )
    prompt = (
        f"사용자 학교: '{school}'\n\n"
        f"[검증 대상]\n{club_list}\n\n"
        "Google Search로 각 항목을 검색하여 다음을 확인하세요:\n"
        "1. 실제 존재하는지 (verified: true/false)\n"
        "2. 다른 학교에만 있는지 (wrong_school: true/false)\n"
        "3. 공식 URL — Google Search 결과에서 실제로 접속한 페이지 URL만 기입. 기억·추측·조합은 null\n"
        "4. description — 확인된 실제 활동 내용, 불확실하면 빈 문자열\n"
        "5. actual_school — 검색으로 확인된 실제 소속 학교\n\n"
        "순수 JSON 배열만 출력:\n"
        '[\n  {"name":"동아리명","verified":true,"wrong_school":false,'
        '"actual_school":"","official_url":null,"description":"","evidence":"근거"}\n]'
    )
    system = (
        "당신은 한국 대학교 동아리·학회 정보 전문가입니다.\n"
        "Google Search 결과에 실제로 존재가 확인된 항목만 verified: true로 표시하십시오.\n"
        "확인되지 않으면 반드시 verified: false입니다.\n"
        "official_url 규칙: Google Search에서 실제로 열어본 페이지의 URL만 기입. "
        "기억에서 떠올린 URL, 추측한 URL, 조합한 URL은 모두 null. "
        "조금이라도 불확실하면 null. null이 오답보다 낫다."
    )
    raw = _call_model_raw(prompt, system_prompt=system, use_google_search=True)
    try:
        parsed = json.loads(clean_json_response(raw))
        return [r for r in parsed if isinstance(r, dict)]
    except Exception as e:
        print(f"    WARNING: 동아리 검증 응답 파싱 실패 ({e})", flush=True)
        return []


def verify_clubs_with_search(
    clubs: list,
    school: str,
    department: str = "",
    profile_vec: list | None = None,
    career_text: str = "",
) -> list[dict]:
    """
    동아리·학회 추천 파이프라인 (3단계):

      STEP 1. 후보 생성  — LLM + Google Search
                           관심사 1순위, 학교/전공 2순위로 후보 생성
      STEP 2. 복합 점수 필터  — 관심사 유사도(70%) + 학교 가입가능 보너스(30%)
                                 하드 필터 없음: 가입 불가능한 것만 제외
      STEP 3. Google Search 검증  — 실재·가입 가능성 최종 확인

    우선순위:
      1순위 — 유저 관심사·활동과 연관성이 높고 해당 학교 학생이 가입 가능한 곳
      2순위 — 학과·전공 관련성 (임베딩에 반영되나 비중 낮음)
    """
    print(f"\n  [동아리 추천] 시작 (학교: {school or '미상'}, 학과: {department or '미상'})", flush=True)

    # ── 관심사 전용 벡터 (학교·전공 제외) ────────
    interest_vec: list | None = None
    if career_text:
        interest_text = _build_interest_text(career_text)
        interest_vec  = _embed_query(interest_text)
        if interest_vec:
            print(f"    관심사 벡터 생성 완료 (dim={len(interest_vec)})", flush=True)

    # 관심사 벡터 실패 시 전체 프로필 벡터로 폴백
    if interest_vec is None and profile_vec is not None:
        interest_vec = profile_vec
        print(f"    관심사 벡터 없음 → 프로필 벡터로 폴백", flush=True)
    elif interest_vec is None:
        print(f"    WARNING: 유사도 벡터 없음 → 유사도 필터 스킵", flush=True)

    all_excluded: list[str] = []
    verified_result: list[dict] = []
    attempt = 0
    max_attempts = 3

    while len(verified_result) < _CLUB_MIN_VERIFIED and attempt < max_attempts:
        attempt += 1
        print(f"\n  [동아리 추천 시도 {attempt}/{max_attempts}]", flush=True)

        # ── STEP 1: 후보 생성 ──────────────────────
        raw_candidates = clubs if attempt == 1 and clubs else []
        if not raw_candidates:
            raw_candidates = _generate_club_candidates(
                school, department, all_excluded, career_text
            )

        if not raw_candidates:
            print(f"    후보 생성 실패 → 중단", flush=True)
            break

        print(f"    후보 {len(raw_candidates)}건 생성됨", flush=True)

        # ── STEP 2: 복합 점수 필터 ─────────────────
        # 2-a. 가입 가능성 체크 (완전 불가능한 것만 제외)
        eligible = []
        for c in raw_candidates:
            ok, bonus = _club_school_eligible(c, school)
            if ok:
                c["_school_bonus"] = bonus
                eligible.append(c)
            else:
                print(f"    [{c.get('name','?')}] 가입 불가 → 제외", flush=True)
                all_excluded.append(c.get("name", ""))

        print(
            f"    가입 가능 필터 후: {len(eligible)}건 "
            f"(제외: {len(raw_candidates)-len(eligible)}건)",
            flush=True,
        )

        if not eligible:
            clubs = []
            continue

        # 2-b. 관심사 유사도 계산 (이름 + 추천이유 조합으로 임베딩)
        if interest_vec:
            scored_list = _filter_by_similarity(
                eligible,
                interest_vec,
                name_key="name",
                extra_keys=["reason"],        # 추천이유까지 포함 → 맥락 강화
                threshold=_CLUB_SIMILARITY_THRESHOLD,
                top_k=_CLUB_TOP_K * 2,       # 보너스 재정렬 여유분 확보
            )
        else:
            for c in eligible:
                c.setdefault("_similarity", 0.5)
            scored_list = eligible[:_CLUB_TOP_K * 2]

        # 2-c. 복합 점수 = 관심사 유사도(70%) + 학교 보너스(30%) → 재정렬
        for c in scored_list:
            sim   = c.get("_similarity", 0.0)
            bonus = c.get("_school_bonus", 0.3)
            c["_combined_score"] = round(sim * 0.7 + bonus * 0.3, 4)

        scored_list.sort(key=lambda c: -c["_combined_score"])
        filtered = scored_list[:_CLUB_TOP_K]

        print(f"    복합 점수 정렬 후 상위 {len(filtered)}건 선정", flush=True)
        for c in filtered:
            print(
                f"      {c.get('name','?')}: "
                f"관심사={c.get('_similarity','?')} "
                f"학교보너스={c.get('_school_bonus','?')} "
                f"복합={c.get('_combined_score','?')}",
                flush=True,
            )

        # 이미 시도한 항목 제외
        already_names = {c.get("name", "") for c in verified_result}
        to_verify = [
            c for c in filtered
            if c.get("name", "") not in already_names
            and c.get("name", "") not in all_excluded
        ]

        if not to_verify:
            print(f"    검증할 신규 후보 없음 → 중단", flush=True)
            break

        # ── STEP 3: Google Search 실재 검증 ────────
        print(f"\n    [Google Search 검증] {len(to_verify)}건", flush=True)
        verify_results = _verify_clubs_google(school, to_verify)
        vmap = {r.get("name", ""): r for r in verify_results}

        newly_verified = []
        for club in to_verify:
            name = club.get("name", "")
            vr   = vmap.get(name, {})

            all_excluded.append(name)

            if vr.get("wrong_school"):
                print(f"      [{name}] -> FAIL: 다른 학교 전용", flush=True)
                continue
            if not vr.get("verified"):
                print(f"      [{name}] -> FAIL: 검색 미확인", flush=True)
                continue

            # 교내 전용이고 소속 학교가 다른 경우만 탈락
            # (연합·외부는 소속 불일치여도 통과)
            actual = normalize_school_name(vr.get("actual_school", ""))
            ctype  = club.get("type", "").lower()
            is_exclusive_mismatch = (
                actual
                and school
                and "외부" not in ctype
                and "연합" not in ctype
                and actual != normalize_school_name(school)
            )
            if is_exclusive_mismatch:
                print(f"      [{name}] -> FAIL: 교내 소속 불일치 ({actual})", flush=True)
                continue

            score_str = (
                f"관심사={club.get('_similarity','?')}, "
                f"복합={club.get('_combined_score','?')}"
            )
            print(f"      [{name}] -> OK ({score_str})", flush=True)
            club["search_verified"] = True
            # URL은 부가 정보 — 검증 실패해도 항목 자체는 유지, url만 None
            raw_url = vr.get("official_url")
            club["url"]         = _validate_url(raw_url) if raw_url else None
            club["description"] = vr.get("description", "").strip()
            if vr.get("evidence"):
                club["verification_evidence"] = vr["evidence"]
            newly_verified.append(club)

        verified_result.extend(newly_verified)
        print(
            f"    이번 시도 통과: {len(newly_verified)}건 / 누적: {len(verified_result)}건",
            flush=True,
        )
        clubs = []  # 다음 시도는 새로 생성

    # 최종 결과를 복합 점수 내림차순으로 정렬
    verified_result.sort(key=lambda c: -c.get("_combined_score", 0.0))
    print(
        f"\n  [동아리 추천 완료] 최종 {len(verified_result)}건 "
        f"(목표 {_CLUB_MIN_VERIFIED}건)",
        flush=True,
    )
    return verified_result


# ══════════════════════════════════════════════
# 15  공모전 — Embedding 클러스터링 기반 추천
# ══════════════════════════════════════════════

_CONTEST_SIMILARITY_THRESHOLD = 0.50
_CONTEST_CANDIDATE_POOL       = 12
_CONTEST_TOP_K                = 6


def _generate_contest_candidates(
    department: str,
    career_summary: str,
    ref_date: date,
    exclude_names: list,
    pool_size: int = _CONTEST_CANDIDATE_POOL,
) -> list[dict]:
    """LLM + Google Search로 공모전 후보 생성."""
    rd          = ref_date.strftime("%Y-%m-%d")
    exclude_str = ", ".join(exclude_names) if exclude_names else "없음"
    dept_hint   = f"전공: {department} / " if department else ""

    prompt = (
        f"오늘 날짜: {rd}\n"
        f"사용자 프로필: {dept_hint}경력 요약: {career_summary[:300]}\n"
        f"제외 목록: {exclude_str}\n\n"
        f"위 사용자에게 적합한 공모전·대회 후보를 {pool_size}개 생성하세요.\n"
        "조건:\n"
        f"- {rd} 기준 현재 접수 중이거나 {rd} 이후 개최 예정인 공모전만\n"
        "- 주관기관이 실재하고 확인 가능한 공모전만\n"
        "- 정기적으로 개최되는 공모전 우선\n"
        "- 이름·주관기관이 불확실하면 포함 금지\n\n"
        "순수 JSON 배열만 출력:\n"
        '[\n  {\n'
        '    "name": "공모전 정식 명칭",\n'
        '    "organizer": "주관기관명",\n'
        '    "reason": "추천 이유",\n'
        '    "expected_effect": "기대 효과",\n'
        '    "url": null,\n'
        '    "deadline": null,\n'
        '    "is_regular": true\n'
        '  }\n]'
    )
    system = (
        "당신은 한국 공모전·대회 정보 전문가입니다.\n"
        "Google Search로 실제 존재하고 현재 운영 중인 공모전만 후보로 제시하십시오.\n"
        "종료된 공모전, 주관기관 불명 공모전은 절대 포함하지 마십시오."
    )
    raw = _call_model_raw(prompt, system_prompt=system, use_google_search=True)
    try:
        parsed = json.loads(clean_json_response(raw))
        return [r for r in parsed if isinstance(r, dict) and r.get("name", "").strip()]
    except Exception as e:
        print(f"    WARNING: 공모전 후보 파싱 실패 ({e})", flush=True)
        return []


def _verify_contests_google(contests: list, ref_date: date) -> list[dict]:
    """Google Search로 공모전 실재·현황 검증."""
    if not contests:
        return []

    rd     = ref_date.strftime("%Y-%m-%d")
    c_list = "\n".join(
        f"  {i+1}. [{c.get('organizer','?')}] {c.get('name','?')}"
        for i, c in enumerate(contests)
    )
    prompt = (
        f"오늘 날짜(기준일): {rd}\n\n"
        f"[검증 대상]\n{c_list}\n\n"
        f"Google Search로 각 공모전을 '{rd}' 기준으로 검색하여:\n"
        "1. 실제 존재하고 정기 개최되는지 (verified: true/false)\n"
        "2. 주관기관이 실제 해당 기관인지 (organizer_confirmed: true/false)\n"
        f"3. {rd} 기준 현재 접수 중이거나 이후 개최 예정인지 (upcoming: true/false)\n"
        f"4. 마감일이 {rd} 이후이거나 상시인지 (deadline_ok: true/false)\n"
        "5. 공식 URL — Google Search에서 실제 접속 확인된 URL만. 기억·추측·조합은 null\n"
        "6. 마감일 — 확인된 경우 YYYY-MM-DD, 모르면 null\n\n"
        "순수 JSON 배열만 출력:\n"
        '[\n  {"name":"공모전명","verified":true,"organizer_confirmed":true,'
        '"upcoming":true,"deadline_ok":true,"official_url":null,'
        '"deadline":null,"evidence":"근거"}\n]'
    )
    system = (
        "당신은 한국 공모전·대회 정보 전문가입니다.\n"
        "Google Search 결과에 실제로 확인된 내용만 기입하십시오.\n"
        "official_url 규칙: Google Search에서 실제로 열어본 페이지의 URL만. 기억·추측·조합은 null. 불확실하면 null."
    )
    raw = _call_model_raw(prompt, system_prompt=system, use_google_search=True)
    try:
        parsed = json.loads(clean_json_response(raw))
        return [r for r in parsed if isinstance(r, dict)]
    except Exception as e:
        print(f"    WARNING: 공모전 검증 파싱 실패 ({e})", flush=True)
        return []


def verify_contests_with_search(
    contests: list,
    ref_date: date,
    department: str = "",
    profile_vec: list | None = None,
    career_text: str = "",
) -> list[dict]:
    """
    공모전 추천 파이프라인 (3단계):
      1. 후보 생성 (LLM + Google Search)
      2. Embedding 유사도 필터
      3. Google Search 실재·현황 검증
    """
    print(f"\n  [공모전 추천] 시작", flush=True)

    # 프로필 벡터
    if profile_vec is None:
        profile_text = _build_profile_text("", department, career_text)
        profile_vec  = _embed_query(profile_text) if profile_text.strip() else None

    all_excluded: list[str] = []
    verified_result: list[dict] = []
    attempt = 0
    max_attempts = 2

    while attempt < max_attempts:
        attempt += 1
        print(f"\n  [공모전 시도 {attempt}/{max_attempts}]", flush=True)

        raw_candidates = contests if attempt == 1 and contests else []
        if not raw_candidates:
            raw_candidates = _generate_contest_candidates(
                department, career_text, ref_date, all_excluded
            )

        if not raw_candidates:
            print(f"    후보 생성 실패 → 중단", flush=True)
            break

        print(f"    후보 {len(raw_candidates)}건 생성됨", flush=True)

        # Embedding 유사도 필터
        if profile_vec:
            # 공모전은 name + organizer 조합으로 쿼리
            for c in raw_candidates:
                c.setdefault("_query_text", f"{c.get('name','')} {c.get('organizer','')}")
            filtered = _filter_by_similarity(
                raw_candidates,
                profile_vec,
                name_key="_query_text",
                threshold=_CONTEST_SIMILARITY_THRESHOLD,
                top_k=_CONTEST_TOP_K,
            )
        else:
            filtered = raw_candidates[:_CONTEST_TOP_K]

        already_names = {c.get("name", "") for c in verified_result}
        to_verify = [
            c for c in filtered
            if c.get("name", "") not in already_names
            and c.get("name", "") not in all_excluded
        ]

        if not to_verify:
            break

        print(f"\n    [Google Search 검증] {len(to_verify)}건", flush=True)
        verify_results = _verify_contests_google(to_verify, ref_date)
        vmap = {r.get("name", ""): r for r in verify_results}

        for contest in to_verify:
            name  = contest.get("name", "")
            vr    = vmap.get(name, {})
            label = f"{contest.get('organizer','?')} | {name}"

            all_excluded.append(name)

            if not vr.get("verified"):
                print(f"      [{label}] -> FAIL: 실재 미확인", flush=True)
                continue
            if not vr.get("organizer_confirmed"):
                print(f"      [{label}] -> FAIL: 주관기관 불일치", flush=True)
                continue
            if not vr.get("deadline_ok", True):
                print(f"      [{label}] -> FAIL: 마감 지남", flush=True)
                continue

            print(f"      [{label}] -> OK", flush=True)
            # URL은 부가 정보 — 검증 실패해도 항목 자체는 유지, url만 None
            raw_url = vr.get("official_url")
            contest["url"]             = _validate_url(raw_url) if raw_url else None
            deadline                   = vr.get("deadline")
            contest["deadline"]        = deadline if deadline and deadline != "null" else None
            contest["search_verified"] = True
            verified_result.append(contest)

        contests = []

    print(f"\n  [공모전 추천 완료] 최종 {len(verified_result)}건", flush=True)
    return verified_result


# ══════════════════════════════════════════════
# 16  자격증 — Embedding 클러스터링 기반 추천
# ══════════════════════════════════════════════

_CERT_SIMILARITY_THRESHOLD = 0.50
_CERT_CANDIDATE_POOL       = 12
_CERT_TOP_K                = 6


def _generate_cert_candidates(
    department: str,
    career_summary: str,
    exclude_names: list,
    pool_size: int = _CERT_CANDIDATE_POOL,
) -> list[dict]:
    """LLM + Google Search로 자격증 후보 생성."""
    exclude_str = ", ".join(exclude_names) if exclude_names else "없음"
    dept_hint   = f"전공: {department} / " if department else ""

    prompt = (
        f"사용자 프로필: {dept_hint}경력 요약: {career_summary[:300]}\n"
        f"제외 목록: {exclude_str}\n\n"
        f"위 사용자에게 적합한 자격증 후보를 {pool_size}개 생성하세요.\n"
        "조건:\n"
        "- 현재 실제 시행 중인 국가공인 또는 공신력 있는 민간자격증만\n"
        "- 이름·주관기관이 확실하지 않으면 포함 금지\n"
        "- 폐지·중단된 자격증 포함 금지\n\n"
        "순수 JSON 배열만 출력:\n"
        '[\n  {\n'
        '    "name": "자격증 정식 명칭",\n'
        '    "reason": "추천 이유",\n'
        '    "expected_effect": "기대 효과",\n'
        '    "estimated_duration": "취득 소요 기간"\n'
        '  }\n]'
    )
    system = (
        "당신은 한국 자격증 정보 전문가입니다.\n"
        "Google Search로 현재 실제 시행 중인 자격증만 후보로 제시하십시오.\n"
        "폐지·중단·불확실한 자격증은 절대 포함하지 마십시오."
    )
    raw = _call_model_raw(prompt, system_prompt=system, use_google_search=True)
    try:
        parsed = json.loads(clean_json_response(raw))
        return [r for r in parsed if isinstance(r, dict) and r.get("name", "").strip()]
    except Exception as e:
        print(f"    WARNING: 자격증 후보 파싱 실패 ({e})", flush=True)
        return []


def _verify_certs_google(certs: list) -> list[dict]:
    """Google Search로 자격증 실재 여부 검증."""
    if not certs:
        return []

    c_list = "\n".join(f"  {i+1}. {c.get('name','?')}" for i, c in enumerate(certs))
    prompt = (
        f"[검증 대상 자격증]\n{c_list}\n\n"
        "Google Search로 각 자격증을 검색하여:\n"
        "1. 현재 실제 시행 중인 국가공인 또는 민간자격증인지 (verified: true/false)\n"
        "2. 주관기관 (issuer)\n"
        "3. 공식 URL — Google Search에서 실제 접속 확인된 URL만. 기억·추측·조합은 null\n\n"
        "순수 JSON 배열만 출력:\n"
        '[\n  {"name":"자격증명","verified":true,"issuer":"주관기관","official_url":null}\n]'
    )
    system = (
        "당신은 한국 자격증 정보 전문가입니다.\n"
        "Google Search 결과에 실제로 확인된 자격증만 verified: true로 표시하십시오.\n"
        "official_url 규칙: Google Search에서 실제로 열어본 페이지의 URL만. 기억·추측·조합은 null. 불확실하면 null."
    )
    raw = _call_model_raw(prompt, system_prompt=system, use_google_search=True)
    try:
        parsed = json.loads(clean_json_response(raw))
        return [r for r in parsed if isinstance(r, dict)]
    except Exception as e:
        print(f"    WARNING: 자격증 검증 파싱 실패 ({e})", flush=True)
        return []


def verify_certifications_with_search(
    certs: list,
    department: str = "",
    profile_vec: list | None = None,
    career_text: str = "",
) -> list[dict]:
    """
    자격증 추천 파이프라인 (3단계):
      1. 후보 생성 (LLM + Google Search)
      2. Embedding 유사도 필터
      3. Google Search 실재 검증
    """
    print(f"\n  [자격증 추천] 시작", flush=True)

    if profile_vec is None:
        profile_text = _build_profile_text("", department, career_text)
        profile_vec  = _embed_query(profile_text) if profile_text.strip() else None

    all_excluded: list[str] = []
    verified_result: list[dict] = []
    attempt = 0
    max_attempts = 2

    while attempt < max_attempts:
        attempt += 1
        print(f"\n  [자격증 시도 {attempt}/{max_attempts}]", flush=True)

        raw_candidates = certs if attempt == 1 and certs else []
        if not raw_candidates:
            raw_candidates = _generate_cert_candidates(
                department, career_text, all_excluded
            )

        if not raw_candidates:
            print(f"    후보 생성 실패 → 중단", flush=True)
            break

        print(f"    후보 {len(raw_candidates)}건 생성됨", flush=True)

        if profile_vec:
            filtered = _filter_by_similarity(
                raw_candidates,
                profile_vec,
                name_key="name",
                threshold=_CERT_SIMILARITY_THRESHOLD,
                top_k=_CERT_TOP_K,
            )
        else:
            filtered = raw_candidates[:_CERT_TOP_K]

        already_names = {c.get("name", "") for c in verified_result}
        to_verify = [
            c for c in filtered
            if c.get("name", "") not in already_names
            and c.get("name", "") not in all_excluded
        ]

        if not to_verify:
            break

        print(f"\n    [Google Search 검증] {len(to_verify)}건", flush=True)
        verify_results = _verify_certs_google(to_verify)
        vmap = {r.get("name", ""): r for r in verify_results}

        for cert in to_verify:
            name = cert.get("name", "")
            vr   = vmap.get(name, {})
            all_excluded.append(name)

            if not vr.get("verified"):
                print(f"      [{name}] -> FAIL: 실재 미확인", flush=True)
                continue

            print(f"      [{name}] -> OK ({vr.get('issuer','주관기관 미확인')})", flush=True)
            # URL은 부가 정보 — 검증 실패해도 항목 자체는 유지, url만 None
            raw_url = vr.get("official_url")
            cert["url"]    = _validate_url(raw_url) if raw_url else None
            cert["issuer"] = vr.get("issuer", "")
            verified_result.append(cert)

        certs = []

    print(f"\n  [자격증 추천 완료] 최종 {len(verified_result)}건", flush=True)
    return verified_result


# ══════════════════════════════════════════════
# 17  채용공고 AI 검증
# ══════════════════════════════════════════════

def verify_jobs_with_search(jobs: list, ref_date: date) -> list:
    if not jobs:
        return []

    jobs_with_url = [j for j in jobs if j.get("url") and j.get("url") != "null"]
    dropped = len(jobs) - len(jobs_with_url)
    if dropped:
        print(f"    URL 미확보 {dropped}건 사전 제외", flush=True)
    if not jobs_with_url:
        return []

    rd = ref_date.strftime("%Y-%m-%d")
    print(f"\n  [채용공고 Google Search 검증 - {len(jobs_with_url)}건]", flush=True)
    job_list = "\n".join(
        f"  {i+1}. {j.get('company','?')} | {j.get('role','?')} | "
        f"마감: {j.get('deadline','?')} | URL: {j.get('url','?')}"
        for i, j in enumerate(jobs_with_url)
    )
    prompt = (
        f"기준일: {rd}\n\n"
        f"[검증 대상]\n{job_list}\n\n"
        "Google Search로 각 채용공고를 실제 검색하여:\n"
        "1. 실제 존재하는지 (verified)\n"
        f"2. 마감일이 {rd} 이후인지 (deadline_confirmed)\n"
        "3. 실제 채용공고 URL — Google Search에서 직접 접속 확인한 URL만. 기억·추측·조합은 null\n\n"
        "순수 JSON 배열만 출력:\n"
        '[\n  {"company":"회사명","role":"직무","verified":true,'
        '"deadline_confirmed":true,"correct_url":null,"evidence":"근거"}\n]'
    )
    system = (
        "당신은 한국 채용 시장 전문가입니다.\n"
        "Google Search로 각 채용공고를 실제 검색·검증하십시오."
    )
    raw = _call_model_raw(prompt, system_prompt=system, use_google_search=True)

    try:
        vmap = {}
        for r in json.loads(clean_json_response(raw)):
            if isinstance(r, dict):
                vmap[f"{r.get('company','')}|{r.get('role','')}"] = r

        verified = []
        for job in jobs_with_url:
            key   = f"{job.get('company','')}|{job.get('role','')}"
            vr    = vmap.get(key, {})
            label = f"{job.get('company','?')} | {job.get('role','?')}"
            if not vr.get("verified"):
                print(f"    [{label}] -> FAIL: 공고 미확인", flush=True)
                continue
            if not vr.get("deadline_confirmed"):
                print(f"    [{label}] -> FAIL: 마감일 미확인", flush=True)
                continue
            # correct_url을 검증하여 유효한 경우만 교정
            raw_correct = vr.get("correct_url")
            if raw_correct and raw_correct != "null":
                validated_correct = _validate_url(raw_correct)
                if validated_correct and validated_correct != job.get("url"):
                    job["url"] = validated_correct
                    print(f"    [{label}] -> OK (URL 교정 검증됨)", flush=True)
                elif not validated_correct:
                    # 교정 URL이 검증 실패 → 기존 URL 유지 (기존 URL은 이미 verify_job_urls에서 검증됨)
                    print(f"    [{label}] -> OK (교정 URL 검증 실패, 기존 URL 유지)", flush=True)
                else:
                    print(f"    [{label}] -> OK", flush=True)
            else:
                print(f"    [{label}] -> OK", flush=True)
            verified.append(job)
        return verified
    except Exception as e:
        print(f"  WARNING: 채용공고 검증 실패 ({e})", flush=True)
        return []



# ══════════════════════════════════════════════
# 18  날짜 필터
# ══════════════════════════════════════════════
def filter_valid_jobs(jobs: list, ref_date: date) -> tuple[list, list]:
    valid, expired = [], []
    for job in jobs:
        dl = job.get("deadline", "")
        if not dl or dl in ("상시채용", "없음", "미정", "-", "null", None):
            job["is_valid"] = True
            valid.append(job)
            continue
        try:
            d = datetime.strptime(dl, "%Y-%m-%d").date()
            (valid if d >= ref_date else expired).append(job)
        except ValueError:
            valid.append(job)
    return valid, expired


# ══════════════════════════════════════════════
# 19  핵심 분석 함수
# ══════════════════════════════════════════════
def analyze_career_comprehensive(user_text: str, ref_date: date,
                                  school: str, department: str = "") -> dict:
    system_prompt = build_system_prompt_comprehensive(ref_date, school, department)
    rd = ref_date.strftime("%Y-%m-%d")

    profile_parts = []
    if school:
        profile_parts.append(f"학교: {school}")
        profile_parts.append(f"동아리·학회는 반드시 '{school}' 소속만 추천하십시오.")
    if department:
        profile_parts.append(f"학과: {department}")
        profile_parts.append(f"'{department}' 전공에 맞는 추천을 우선하십시오.")

    profile_ctx = ("\n[사용자 프로필]\n" + "\n".join(profile_parts) + "\n") if profile_parts else ""

    source_hint = ""
    if user_text.startswith("[SOURCE_URL:"):
        first_line_end = user_text.find("\n")
        source_url_line = user_text[:first_line_end] if first_line_end > 0 else user_text[:100]
        source_hint = (
            f"\n[입력 소스 안내]\n"
            f"사용자가 URL을 제출했습니다: {source_url_line}\n"
            f"아래 데이터는 해당 URL에서 크롤링한 결과입니다.\n"
            f"크롤링 제한으로 일부 정보가 누락될 수 있으며, 이 경우 URL 경로명(슬러그)을 "
            f"추가 맥락으로 활용하십시오. 단, 추론 불가 항목은 반드시 빈 배열로 반환하십시오.\n"
        )

    user_prompt = (
        f"아래 사용자 데이터를 분석하십시오.\n"
        f"오늘 날짜: {rd} — 모든 기준은 이 날짜 기준.\n"
        f"채용공고: {rd} 이후 마감 + URL 확인된 것만.\n"
        f"공모전: {rd} 기준 현재 접수 중이거나 {rd} 이후 개최 예정인 것만."
        f" 주관기관이 명확하게 확인된 것만 포함. 불확실하거나 이미 종료된 것은 빈 배열.\n"
        f"자격증: 현재 실제 시행 중인 것만. 불확실하면 빈 배열.\n"
        f"동아리·학회: 최소 3개 이상 추천. 교내·연합·외부 균형 있게.\n"
        f"critical_diagnosis: 입력 데이터에서 실제 확인된 사실에만 근거하여 냉정하게 작성."
        f" 존재하지 않는 약점을 만들어내지 말고, 반대로 명백한 약점을 완화하거나 숨기지도 말 것.\n"
        f"{source_hint}"
        f"{profile_ctx}\n"
        f"[사용자 데이터]\n{user_text}"
    )
    return _call_model(system_prompt, user_prompt, use_google_search=False)


# ══════════════════════════════════════════════
# 20  Main
# ══════════════════════════════════════════════
def main(user_input: list[str], school: str, department: str):
    ref_date = date.today()
    rd = ref_date.strftime("%Y-%m-%d")

    print("=" * 65)
    print("  Career Analysis AI - COMPREHENSIVE Edition v1.0")
    print(f"  모델: {_ANALYSIS_MODEL}  |  임베딩: {_EMBEDDING_MODEL}")
    print(f"  기준일: {rd} (자동)  |  Google Search 검증 활성화")
    print("=" * 65)

    school, department = get_user_profile(school, department)
    raw_content = get_user_input(user_input)

    if len(raw_content.strip()) < 10:
        error_result = {
            "status": "error",
            "message": "입력 데이터가 너무 짧습니다. 최소 10자 이상 입력하세요."
        }
        print(json.dumps(error_result, ensure_ascii=False, indent=2))
        return

    # ── [1] + [2] 동시 실행: 임베딩과 메인 분석은 서로 독립적 ──
    print("\n[1+2] 임베딩 생성 & 종합 분석 병렬 실행 중 (Gemini 2.5 Pro)...", flush=True)

    with ThreadPoolExecutor(max_workers=2) as ex:
        fut_embed  = ex.submit(get_embedding, raw_content)
        fut_result = ex.submit(
            analyze_career_comprehensive, raw_content, ref_date, school, department
        )
        vector = fut_embed.result()
        result = fut_result.result()

    if vector:
        print(f"  임베딩 OK (dim: {len(vector)})", flush=True)
    else:
        print("  WARNING: embedding skipped (분석은 계속 진행)", flush=True)

    verified_clubs: list    = []
    verified_contests: list = []
    verified_certs: list    = []

    if result.get("status") not in ("error", "insufficient_data"):
        additional = result.get("additional_recommendations", {})

        # ── 자격증 / 동아리 / 공모전 검증 3개를 병렬 실행 ──
        raw_certs    = additional.get("certifications", [])
        raw_clubs    = additional.get("clubs_and_societies", [])
        raw_contests = additional.get("projects_and_contests", [])

        # career_text: 임베딩 유사도 필터에 사용할 사용자 이력 요약 (앞 2000자)
        career_text = raw_content[:2000]

        print("\n  [3-way 병렬 검증] 자격증 | 동아리 | 공모전 동시 시작...", flush=True)
        with ThreadPoolExecutor(max_workers=3) as ex:
            fut_certs = ex.submit(
                verify_certifications_with_search,
                raw_certs, department, vector, career_text,
            )
            fut_clubs = ex.submit(
                verify_clubs_with_search,
                raw_clubs, school, department, vector, career_text,
            )
            fut_contests = ex.submit(
                verify_contests_with_search,
                raw_contests, date.today(), department, vector, career_text,
            )
            verified_certs    = fut_certs.result()
            verified_clubs    = fut_clubs.result()
            verified_contests = fut_contests.result()
        print("  [3-way 병렬 검증] 완료", flush=True)

        # 검증 결과를 result에 반영
        if "additional_recommendations" in result:
            result["additional_recommendations"]["certifications"]      = verified_certs
            result["additional_recommendations"]["clubs_and_societies"]  = verified_clubs
            result["additional_recommendations"]["projects_and_contests"] = verified_contests

        # 채용공고 검증
        all_jobs = result.get("valid_job_recommendations", [])
        ai_ok = verify_jobs_with_search(all_jobs, ref_date) if all_jobs else []

        if ai_ok:
            print("\n  [채용공고 URL + 내용 검증 중...]", flush=True)
            url_ok, url_fail = verify_job_urls(ai_ok)
            if url_fail:
                print(f"  {len(url_fail)}건 URL 검증 실패 → 제외", flush=True)
        else:
            url_ok = []

        valid_jobs, expired_jobs = filter_valid_jobs(url_ok, ref_date)
        result["verified_jobs"] = valid_jobs
        result["expired_jobs"]  = expired_jobs
        # 원본 키 정리 (내부 메타데이터 제거)
        result.pop("valid_job_recommendations", None)
    else:
        result["verified_jobs"] = []
        result["expired_jobs"]  = []

    # embedding 벡터는 JSON 출력에서 제외 (너무 길어 가독성 저하)
    result["embedding_dim"] = len(vector) if vector else None

    print("\n[3] 분석 완료!\n", flush=True)

    # ── 냉정 진단 요약 로그 (stderr로 출력해 JSON stdout과 분리) ──
    diag = result.get("critical_diagnosis", {})
    if diag:
        verdict = diag.get("one_line_verdict", "")
        if verdict:
            print(f"  [냉정 진단] {verdict}", file=sys.stderr)
        weaknesses = diag.get("weaknesses", [])
        critical_cnt = sum(1 for w in weaknesses if w.get("severity") == "critical")
        major_cnt    = sum(1 for w in weaknesses if w.get("severity") == "major")
        minor_cnt    = sum(1 for w in weaknesses if w.get("severity") == "minor")
        print(
            f"  [냉정 진단] 약점 — critical:{critical_cnt}  major:{major_cnt}  minor:{minor_cnt}",
            file=sys.stderr,
        )

    # ── 최종 JSON 출력 ──
    return json.dumps({
        "vector": vector,
        "result": result
    }, ensure_ascii=False, indent=2)