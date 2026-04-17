"""
Career Keyword Analyzer v2.1 - Colab Edition (Mixed Input Support)
===================================================================
키워드 기반 경력 분석 시스템 (Google Colab 전용)

v2.1 업데이트: 복합 입력 지원
  - 하나의 입력에서 URL, 파일 경로, 텍스트를 자동 분리하여 처리
  - URL은 딥 크롤링, 파일은 파일 읽기, 텍스트는 텍스트로 각각 처리 후 병합

사용법 (Colab에서):
  1. GEMINI_API_KEY 설정

  2. 경력 파싱 (복합 입력 지원):
       # URL만
       careers = parse_careers("https://example.com/portfolio")
       
       # 텍스트만
       careers = parse_careers("직접 텍스트 입력...")
       
       # 복합 입력 (URL + 텍스트 혼합)
       careers = parse_careers('''
           동아리명: 와플스튜디오
           활동기간: 2023.09~2024.01
           동아리소개: https://wafflestudio.com/
           
           - 김상협
           인턴: 엔젠바이오 2023.7월~8월
           ...
       ''')

  3. 여러 소스 병합:
       more    = parse_careers("추가 텍스트...")
       careers = merge_careers(careers, more)

  4. 키워드 기반 분석:
       result = analyze_keywords(["리더십", "문제해결"], careers)
       result = analyze_keywords(["협업"], careers, target="스타트업 PM")

  5. 추천 키워드 확인:
       show_keywords()
"""

import json
import re
import os
import io
import time
import hashlib
import urllib.request
import urllib.parse
from html.parser import HTMLParser
from datetime import datetime
from collections import deque
from typing import Optional

from google import genai
from google.genai import types

try:
    import pypdf
    HAS_PYPDF = True
except ImportError:
    HAS_PYPDF = False
    print("WARNING: pip install pypdf (PDF 파싱 기능 비활성화)")


# ══════════════════════════════════════════════
# Config
# ══════════════════════════════════════════════
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")  # ← 여기에 API 키 입력
client = None

_ANALYSIS_MODEL  = "gemini-2.5-flash"
_EMBEDDING_MODEL = "gemini-embedding-001"

_MAX_PAGES      = 30
_MAX_PDFS       = 5
_FETCH_TIMEOUT  = 15
_MAX_CONTENT_MB = 1
_MAX_RETRIES    = 4
_RETRY_BASE_SEC = 5

KEYWORD_CATEGORIES = {
    "역량": [
        "리더십", "협업", "팀워크", "커뮤니케이션", "문제해결", "창의성", "분석력",
        "기획력", "실행력", "적응력", "책임감", "도전정신", "자기주도", "꼼꼼함",
        "끈기", "열정", "유연성", "결단력", "전략적사고", "데이터기반의사결정"
    ],
    "직무": [
        "마케팅", "개발", "기획", "디자인", "데이터분석", "영업", "인사",
        "재무", "회계", "법무", "연구", "품질관리", "운영", "물류",
        "고객서비스", "콘텐츠", "브랜딩", "PR", "UX", "PM", "컨설팅"
    ],
    "산업": [
        "IT", "금융", "제조", "서비스", "유통", "교육", "의료",
        "스타트업", "대기업", "공공기관", "비영리", "미디어", "엔터테인먼트"
    ],
    "활동유형": [
        "인턴십", "프로젝트", "동아리", "봉사", "수상", "자격증", "연구",
        "창업", "공모전", "대외활동", "학회", "교환학생", "교육", "강연"
    ]
}


# ══════════════════════════════════════════════
# 1. LLM 호출 헬퍼
# ══════════════════════════════════════════════
def _init_client():
    global client
    if client is None:
        if not GEMINI_API_KEY:
            raise ValueError("❌ GEMINI_API_KEY가 설정되지 않았습니다.")
        client = genai.Client(api_key=GEMINI_API_KEY)
    return client


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


def _call_model(system_prompt: str, user_prompt: str) -> dict:
    _init_client()
    raw_text = ""
    try:
        def _do():
            return client.models.generate_content(
                model=_ANALYSIS_MODEL,
                contents=user_prompt,
                config=types.GenerateContentConfig(
                    system_instruction=system_prompt if system_prompt else None,
                    temperature=0.1,
                    max_output_tokens=8192,
                    response_mime_type="application/json",
                ),
            )
        resp = _call_with_retry(_do)
        raw_text = resp.text.strip()
        return json.loads(_clean_json_response(raw_text))
    except json.JSONDecodeError as e:
        return {"status": "error", "message": f"JSON parse failed: {e.msg}", "raw_response": raw_text[:2000]}
    except Exception as e:
        return {"status": "error", "message": str(e)}


def _clean_json_response(raw_text: str) -> str:
    raw_text = raw_text.strip()
    m = re.search(r"```(?:json)?\s*\n?(.*?)\n?\s*```", raw_text, re.DOTALL | re.IGNORECASE)
    if m:
        return m.group(1).strip()
    depth, start = 0, -1
    for i, ch in enumerate(raw_text):
        if ch == "{":
            if depth == 0:
                start = i
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0 and start != -1:
                return raw_text[start:i + 1].strip()
    return raw_text


# ══════════════════════════════════════════════
# 2. Embedding
# ══════════════════════════════════════════════
def get_embedding(text: str) -> Optional[list]:
    if not text or not text.strip():
        return None
    _init_client()
    truncated = text[:10000]
    for kwargs in [
        {"content": truncated, "config": types.EmbedContentConfig(task_type="RETRIEVAL_DOCUMENT")},
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


def cosine_similarity(a: list, b: list) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = sum(x * x for x in a) ** 0.5
    norm_b = sum(x * x for x in b) ** 0.5
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


# ══════════════════════════════════════════════
# 3. 크롤러
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


def _fetch_bytes(url: str) -> bytes | None:
    try:
        req = urllib.request.Request(
            url,
            headers={
                "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
                "Accept": "text/html,application/xhtml+xml,application/pdf,*/*;q=0.8",
            },
        )
        with urllib.request.urlopen(req, timeout=_FETCH_TIMEOUT) as resp:
            return resp.read(int(_MAX_CONTENT_MB * 1024 * 1024))
    except Exception as e:
        print(f"    WARNING fetch failed [{url}]: {e}", flush=True)
        return None


def _parse_pdf_bytes(data: bytes) -> str:
    if not HAS_PYPDF:
        return ""
    try:
        reader = pypdf.PdfReader(io.BytesIO(data))
        return "\n".join(page.extract_text() or "" for page in reader.pages)
    except Exception:
        return ""


def _parse_html_bytes(data: bytes, url: str) -> tuple[str, list[str]]:
    try:
        html = data.decode("utf-8")
    except UnicodeDecodeError:
        html = data.decode("euc-kr", errors="replace")
    parser = _TextExtractor(base_url=url)
    parser.feed(html)
    return parser.text, parser.links


def _same_origin(a: str, b: str) -> bool:
    return urllib.parse.urlparse(a).netloc == urllib.parse.urlparse(b).netloc


def _is_pdf_url(url: str, data: bytes | None = None) -> bool:
    if url.lower().split("?")[0].endswith(".pdf"):
        return True
    return bool(data and data[:4] == b"%PDF")


def _deep_crawl_site(start_url: str) -> str:
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

    main_text, main_links = _parse_html_bytes(raw, start_url)
    visited.add(start_url)
    if main_text.strip():
        collected.append(f"[Main: {start_url}]\n{main_text}")

    queue: deque[str] = deque()
    seen: set[str] = set()
    for lnk in main_links:
        clean = lnk.split("#")[0].rstrip("/")
        if clean and clean not in seen and clean not in visited:
            if not clean.startswith(("mailto:", "tel:", "javascript:")):
                seen.add(clean)
                if _is_pdf_url(clean):
                    queue.appendleft(clean)
                elif _same_origin(start_url, clean):
                    queue.append(clean)

    page_count = 0
    while queue and (page_count < _MAX_PAGES or pdf_count < _MAX_PDFS):
        url = queue.popleft()
        if url in visited:
            continue
        visited.add(url)

        sub_raw = _fetch_bytes(url)
        if sub_raw is None:
            continue

        if _is_pdf_url(url, sub_raw):
            if pdf_count >= _MAX_PDFS:
                continue
            text = _parse_pdf_bytes(sub_raw)
            if text.strip():
                collected.append(f"[PDF: {url}]\n{text}")
                pdf_count += 1
            continue

        if page_count >= _MAX_PAGES:
            continue
        sub_text, sub_links = _parse_html_bytes(sub_raw, url)
        page_count += 1
        if sub_text.strip():
            collected.append(f"[Page: {url}]\n{sub_text}")

    result = "\n\n".join(collected)
    print(f"  [딥 크롤러 완료] {len(collected)}개 소스, {len(result)} chars", flush=True)
    return result


# ══════════════════════════════════════════════
# 3-1. 복합 입력 처리 (NEW)
# ══════════════════════════════════════════════

# URL 패턴: http:// 또는 https:// 또는 www.로 시작하는 URL
_URL_PATTERN = re.compile(
    r'(https?://[^\s<>\[\]()\"\']+|www\.[^\s<>\[\]()\"\']+)',
    re.IGNORECASE
)

# 파일 경로 패턴: 일반적인 파일 경로 (절대/상대)
_FILE_PATH_PATTERN = re.compile(
    r'(?:^|(?<=\s))([/~]?(?:[\w.-]+/)*[\w.-]+\.(?:pdf|txt|md|json|csv|docx?|xlsx?|pptx?))(?=\s|$)',
    re.IGNORECASE | re.MULTILINE
)


def _extract_urls(text: str) -> list[str]:
    """텍스트에서 모든 URL을 추출합니다."""
    urls = []
    for match in _URL_PATTERN.finditer(text):
        url = match.group(1).strip()
        # 끝에 붙은 문장부호 제거
        url = url.rstrip('.,;:!?')
        if url not in urls:
            urls.append(url)
    return urls


def _extract_file_paths(text: str) -> list[str]:
    """텍스트에서 모든 파일 경로를 추출합니다."""
    paths = []
    for match in _FILE_PATH_PATTERN.finditer(text):
        path = match.group(1).strip()
        if path not in paths and os.path.isfile(path):
            paths.append(path)
    return paths


def _remove_patterns_from_text(text: str, patterns: list[str]) -> str:
    """텍스트에서 특정 패턴들을 제거합니다."""
    result = text
    for pattern in patterns:
        result = result.replace(pattern, " ")
    # 연속된 공백/줄바꿈 정리
    result = re.sub(r'\n{3,}', '\n\n', result)
    result = re.sub(r' {2,}', ' ', result)
    return result.strip()


def _read_file(filepath: str) -> str:
    """파일을 읽어서 문자열로 반환합니다."""
    print(f"  [파일 읽기] {filepath}", flush=True)
    try:
        if filepath.lower().endswith(".pdf"):
            with open(filepath, "rb") as f:
                content = _parse_pdf_bytes(f.read())
                return f"[FILE: {filepath}]\n{content}" if content else ""
        else:
            with open(filepath, "r", encoding="utf-8", errors="replace") as f:
                content = f.read()
                return f"[FILE: {filepath}]\n{content}" if content else ""
    except Exception as e:
        print(f"    WARNING: 파일 읽기 실패 [{filepath}]: {e}", flush=True)
        return ""


def _resolve_mixed_input(source: str) -> str:
    """
    복합 입력(URL + 파일경로 + 텍스트)을 처리합니다.
    
    처리 순서:
    1. 입력에서 URL들을 추출 → 각각 딥 크롤링
    2. 입력에서 파일 경로들을 추출 → 각각 파일 읽기
    3. URL/파일경로를 제외한 나머지 텍스트 보존
    4. 모든 결과를 합쳐서 반환
    
    Args:
        source: URL, 파일경로, 텍스트가 혼합된 입력
        
    Returns:
        모든 소스에서 추출한 내용을 합친 문자열
    """
    source = source.strip()
    if not source:
        return ""
    
    collected_parts: list[str] = []
    
    # 1. URL 추출 및 처리
    urls = _extract_urls(source)
    if urls:
        print(f"\n  [복합 입력] {len(urls)}개 URL 감지됨", flush=True)
        for url in urls:
            full_url = url if url.startswith("http") else "https://" + url
            print(f"    → 크롤링: {full_url}", flush=True)
            content = _deep_crawl_site(full_url)
            if content:
                collected_parts.append(f"[SOURCE_URL: {full_url}]\n{content}")
    
    # 2. 파일 경로 추출 및 처리
    file_paths = _extract_file_paths(source)
    if file_paths:
        print(f"\n  [복합 입력] {len(file_paths)}개 파일 감지됨", flush=True)
        for filepath in file_paths:
            content = _read_file(filepath)
            if content:
                collected_parts.append(content)
    
    # 3. URL과 파일 경로를 제거한 나머지 텍스트
    remaining_text = _remove_patterns_from_text(source, urls + file_paths)
    
    # 남은 텍스트가 의미 있는 길이면 추가
    if remaining_text and len(remaining_text.strip()) >= 10:
        print(f"\n  [복합 입력] 텍스트 {len(remaining_text)}자 감지됨", flush=True)
        collected_parts.append(f"[SOURCE_TEXT]\n{remaining_text}")
    
    # 4. 결과 합치기
    if not collected_parts:
        # 아무것도 추출되지 않았으면 원본 텍스트 그대로 반환
        print(f"\n  [텍스트 감지] {len(source)}자", flush=True)
        return source
    
    result = "\n\n" + "="*50 + "\n\n".join(collected_parts)
    print(f"\n  [복합 입력 완료] 총 {len(collected_parts)}개 소스, {len(result)} chars", flush=True)
    return result


def _resolve_input(source: str) -> str:
    """
    URL / 파일경로 / 텍스트 / 복합 입력을 받아 원문 문자열로 반환합니다.
    
    단일 입력(URL만, 파일만, 텍스트만)과 복합 입력 모두 처리합니다.
    """
    source = source.strip()
    if not source:
        return ""
    
    # 복합 입력 여부 확인: URL이나 파일 경로가 텍스트와 함께 있는지
    urls = _extract_urls(source)
    file_paths = _extract_file_paths(source)
    
    # URL/파일을 제외한 텍스트 길이 확인
    remaining = _remove_patterns_from_text(source, urls + file_paths)
    has_significant_text = len(remaining.strip()) >= 20
    
    # 복합 입력: URL/파일과 함께 의미 있는 텍스트가 있는 경우
    if (urls or file_paths) and has_significant_text:
        print(f"\n  [복합 입력 감지] URL {len(urls)}개, 파일 {len(file_paths)}개, 텍스트 있음", flush=True)
        return _resolve_mixed_input(source)
    
    # 단일 URL 입력
    if len(urls) == 1 and not file_paths and not has_significant_text:
        url = urls[0] if urls[0].startswith("http") else "https://" + urls[0]
        print(f"\n  [URL 감지] 크롤링 시작", flush=True)
        content = _deep_crawl_site(url)
        return f"[SOURCE_URL: {url}]\n\n{content}" if content else ""
    
    # 다중 URL 입력 (텍스트 없음)
    if urls and not file_paths and not has_significant_text:
        return _resolve_mixed_input(source)
    
    # 단일 파일 입력
    if os.path.isfile(source):
        print(f"\n  [파일 감지] 읽는 중: {source}", flush=True)
        if source.lower().endswith(".pdf"):
            with open(source, "rb") as f:
                return _parse_pdf_bytes(f.read())
        with open(source, "r", encoding="utf-8", errors="replace") as f:
            return f.read()
    
    # 파일 경로만 있는 경우
    if file_paths and not urls and not has_significant_text:
        return _resolve_mixed_input(source)
    
    # 순수 텍스트 입력
    print(f"\n  [텍스트 감지] {len(source)}자", flush=True)
    return source


# ══════════════════════════════════════════════
# 4. 중복 제거
# ══════════════════════════════════════════════
def generate_career_id(career: dict) -> str:
    """
    title + organization + period_start 조합으로 안정적인 ID를 생성합니다.
    동일한 경력은 항상 동일한 ID를 반환합니다.
    """
    title        = (career.get("title") or "").strip().lower()
    organization = (career.get("organization") or "").strip().lower()
    period_start = (career.get("period_start") or "").strip()

    # title이 없으면 description 앞 50자를 보조 키로 사용
    if not title:
        title = (career.get("description") or "")[:50].strip().lower()

    key = f"{title}|{organization}|{period_start}"
    return hashlib.md5(key.encode("utf-8")).hexdigest()[:12]


def deduplicate_careers(careers: list[dict]) -> list[dict]:
    """
    리스트 내 중복 경력을 제거하고 각 항목에 'id'를 부여해 반환합니다.
    동일 ID가 여러 개일 경우 마지막 항목을 유지합니다.
    """
    seen: dict[str, dict] = {}
    for career in careers:
        c = dict(career)
        c["id"] = generate_career_id(career)
        seen[c["id"]] = c
    return list(seen.values())


def merge_careers(existing: list[dict], new_careers: list[dict]) -> list[dict]:
    """
    두 경력 리스트를 중복 없이 병합합니다.
    동일 ID가 충돌하면 existing 항목을 우선합니다.
    """
    seen: dict[str, dict] = {}
    for career in existing:
        c = dict(career)
        c["id"] = generate_career_id(career)
        seen[c["id"]] = c

    added = 0
    for career in new_careers:
        c = dict(career)
        c["id"] = generate_career_id(career)
        if c["id"] not in seen:
            seen[c["id"]] = c
            added += 1

    print(f"  [병합 결과] 기존 {len(existing)}개 + 신규 {added}개 → 총 {len(seen)}개", flush=True)
    return list(seen.values())


# ══════════════════════════════════════════════
# 5. 경력 파싱 프롬프트
# ══════════════════════════════════════════════
def _career_parsing_prompt() -> str:
    return """당신은 경력 데이터 파싱 전문가이며 이브누입니다.

[임무]
사용자의 경력/활동 데이터에서 개별 경력 항목을 추출합니다.

[★ HALLUCINATION 절대 금지 ★]
1. 입력 데이터에서 확인된 내용만 추출합니다.
2. 없는 정보는 null 또는 빈 배열로 처리합니다.
3. 날짜가 불명확하면 null. 절대 추측하지 마세요.
4. 기관명/회사명은 원문 그대로 사용합니다.
5. 성과/수치는 원문에 명시된 것만 사용합니다.
6. 원문에 없는 역할/직책을 창작하지 않습니다.

[추출 항목]
- title: 경력/활동 제목 (간결하게, 30자 이내)
- category: 인턴십|프로젝트|동아리|봉사|수상|자격증|연구|창업|공모전|대외활동|학회|교육|기타
- organization: 소속 기관/회사 (원문 그대로, 없으면 null)
- role: 역할/직책 (원문 그대로, 없으면 null)
- period_start: YYYY-MM 또는 YYYY 형식. 불명확하면 null
- period_end: YYYY-MM 또는 YYYY 또는 "진행중". 불명확하면 null
- description: 활동 내용 요약 (2-3문장, 원문 기반)
- achievements: 성과/결과 목록 (배열, 원문에 명시된 것만)
- raw_content: 해당 경력의 원문 텍스트 (가공 없이)

[날짜 파싱 규칙]
- "2023년 1월" → "2023-01"
- "2023.01" / "2023/01" / "Jan 2023" → "2023-01"
- "2023" → "2023"
- "현재" / "Present" / "진행중" → "진행중"
- 날짜가 없거나 애매하면 → null

[출력 형식 - 순수 JSON만]
{
  "status": "success",
  "careers": [
    {
      "title": "...",
      "category": "...",
      "organization": "...",
      "role": "...",
      "period_start": "...",
      "period_end": "...",
      "description": "...",
      "achievements": ["..."],
      "raw_content": "..."
    }
  ]
}"""


# ══════════════════════════════════════════════
# 6. 키워드 분석 프롬프트
# ══════════════════════════════════════════════
def _keyword_analysis_prompt(keywords: list[str], target_scenario: str = "") -> str:
    keywords_str = ", ".join(keywords)
    target_hint  = f"\n목표 시나리오/직무: {target_scenario}" if target_scenario else ""

    return f"""당신은 키워드 기반 경력 분석 전문가입니다.

[핵심 임무]
사용자가 선택한 키워드를 기준으로, 경험 풀에서 해당 키워드를 보여줄 수 있는 근거를 역으로 찾아내고 분석합니다.

[분석 대상 키워드]
{keywords_str}{target_hint}

[★ HALLUCINATION 절대 금지 ★]
1. 원문에 없는 내용을 창작/추측하지 않습니다.
2. source_quote는 반드시 원문에서 그대로 인용합니다.
3. 원문에 없는 성과/수치/결과를 만들어내지 않습니다.
4. 근거가 부족하면 "근거 부족"으로 표시하고 과장하지 않습니다.
5. 확신도(confidence)는 근거 강도에 따라 정직하게 설정합니다.

[분석 원칙]
1. 키워드 단어 등장만으로 부합 판단 금지 (행동/결과/학습과 연결 필요)
2. 모든 평가/추천에 최소 1개 이상 근거 필수
3. 근거가 약하면 확신도를 낮춰 "가능성" 톤으로 표현
4. 경력 ID는 스토리라인/설명에서 절대 언급하지 않음
5. 날짜가 null인 경우 "시기 미상"으로 표시
6. source_quote는 원문에서 그대로 인용 (최소 15자 이상)
7. 한국어를 기본 출력 언어로 설정함
8. "데이터 분석"과 같이 특정 활동에 대해서 키워드 분석을 진행할 때는 과한 추론을 금지하고, 그 안에서 한 활동들이 서비스를 만들거나, 프로그램을 만든 경우와 같이 해당 분야로의 관련성을 가장 최우선으로 기준 삼아 판별함.

[출력 형식 - A~F 순서 고정, 순수 JSON만]
{{
  "status": "success",
  "analysis_date": "YYYY-MM-DD",
  "keywords": ["키워드1", "키워드2"],
  "target_scenario": "목표 시나리오",

  "A_keyword_definitions": [
    {{
      "keyword": "키워드명",
      "definition": "키워드 재정의 (1-2문장)",
      "synonyms": ["동의어", "유사표현"],
      "compliance_criteria": [
        {{
          "id": 1,
          "criterion": "부합 기준",
          "signal_description": "무엇을 보면 부합이라 보는지"
        }}
      ]
    }}
  ],

  "B_selection_criteria": {{
    "summary": "AI가 어떤 규칙으로 경험을 골랐는지 3-5줄 요약",
    "criteria": ["기준 매칭", "근거 강도", "반복성", "맥락 적합성"]
  }},

  "C_coverage": [
    {{
      "keyword": "키워드명",
      "related_count": 5,
      "total_count": 12,
      "coverage_percent": 41.7
    }}
  ],

  "D_matched_experiences": [
    {{
      "keyword": "키워드명",
      "experiences": [
        {{
          "career_title": "경력 제목",
          "organization": "소속 기관",
          "period": "YYYY-MM ~ YYYY-MM 또는 시기 미상",
          "relevance": "high|medium|low",
          "evidence": [
            {{
              "type": "사건|행동|성과|학습|증빙",
              "content": "이 경험이 키워드와 관련되는 이유",
              "source_quote": "원문 그대로 인용 (최소 15자)"
            }}
          ],
          "matched_criteria": [1, 3],
          "confidence": "high|medium|low",
          "confidence_reason": "확신도 낮은 이유 (low일 경우)"
        }}
      ]
    }}
  ],

  "E_storylines": [
    {{
      "keyword": "관련 키워드",
      "storyline_title": "스토리라인 제목",
      "structure": {{
        "start": "시작 (문제의식/관심)",
        "development": "전개 (경험 순서/역할/행동)",
        "evidence": "증거 (성과/산출물/피드백)",
        "growth": "성장/전환 (학습/개선)",
        "destination": "도착점 (현재 강점/지향점)"
      }},
      "used_experiences": {{
        "core": ["핵심 경력 제목 목록"],
        "supporting": ["보조 경력 제목 목록"]
      }},
      "key_quotes": [
        {{
          "career_title": "경력 제목",
          "quote": "원문 인용"
        }}
      ]
    }}
  ],

  "F_improvement_guide": {{
    "information_enhancement": [
      {{
        "target": "보강 대상 경력 제목",
        "missing": "부족한 정보",
        "how_to_add": "추가 방법",
        "reason": "이유"
      }}
    ],
    "experience_expansion": [
      {{
        "gap_description": "부족한 부분",
        "suggested_experience_type": "추천 경험 유형",
        "why_helpful": "이유",
        "examples": ["예시"]
      }}
    ],
    "keyword_specific_recommendations": [
      {{
        "keyword": "키워드명",
        "recommendations": [
          {{"type": "확장|보완", "title": "추천 활동명", "expected_effect": "기대 효과"}}
        ]
      }}
    ]
  }}
}}"""


# ══════════════════════════════════════════════
# 7. 공개 함수
# ══════════════════════════════════════════════

def parse_careers(input_data: str) -> list[dict]:
    """
    URL / 파일경로 / 텍스트 / 복합 입력을 받아 파싱된 경력 리스트를 반환합니다.
    
    복합 입력 지원:
    - URL + 텍스트 혼합
    - 여러 URL 동시 입력
    - 파일 경로 + 텍스트 혼합
    - URL + 파일 + 텍스트 모두 혼합

    Args:
        input_data: URL, 파일경로, 텍스트, 또는 이들의 조합

    Returns:
        경력 dict 리스트. 각 항목에 'id' 필드 자동 부여.

    Example:
        # 단일 URL
        careers = parse_careers("https://example.com/portfolio")
        
        # 단일 텍스트
        careers = parse_careers("2023년 삼성전자 인턴십...")
        
        # 복합 입력 (URL + 텍스트)
        careers = parse_careers('''
            동아리명: 와플스튜디오
            동아리소개: https://wafflestudio.com/
            
            인턴: 엔젠바이오 2023.7월~8월
        ''')
    """
    print("=" * 60)
    print("  경력 파싱 (v2.1 - Mixed Input Support)")
    print("=" * 60)

    raw_content = _resolve_input(input_data)
    if not raw_content or len(raw_content.strip()) < 10:
        print("[ERROR] 입력 데이터가 너무 짧습니다.")
        return []

    print("\n  [파싱 중...]", flush=True)
    result = _call_model(
        _career_parsing_prompt(),
        f"아래 텍스트에서 모든 경력/활동 항목을 추출하세요.\n\n[입력 데이터]\n{raw_content[:30000]}"
    )

    if result.get("status") == "error":
        print(f"  [ERROR] {result.get('message')}", flush=True)
        return []

    raw_careers = result.get("careers", [])
    careers = deduplicate_careers(raw_careers)

    print(f"\n[완료] {len(careers)}개 경력 반환 (원본 {len(raw_careers)}개 → 중복 제거 후 {len(careers)}개)")
    for i, c in enumerate(careers):
        print(f"  {i+1}. [{c.get('id')}] {c.get('title', '제목 없음')}")

    return careers


def analyze_keywords(
    keywords: list[str],
    careers: list[dict],
    target: str = "",
    pretty: bool = True
) -> dict:
    """
    키워드 리스트와 경력 리스트를 입력받아 분석 결과를 반환합니다.

    Args:
        keywords: 분석할 키워드 목록 (1~3개)
        careers:  parse_careers() 또는 merge_careers()의 반환값
        target:   목표 시나리오/직무 (선택)
        pretty:   True면 들여쓰기된 JSON 출력

    Returns:
        분석 결과 dict

    Example:
        careers = parse_careers("https://example.com")
        result  = analyze_keywords(["리더십", "문제해결"], careers)
        result  = analyze_keywords(["협업"], careers, target="스타트업 PM")
    """
    print("=" * 60)
    print("  키워드 기반 분석")
    print("=" * 60)

    if isinstance(keywords, str):
        keywords = [k.strip() for k in keywords.split(",") if k.strip()]
    if not keywords:
        print("[ERROR] 최소 1개 이상의 키워드가 필요합니다.")
        return {"status": "error", "message": "키워드가 필요합니다."}
    if len(keywords) > 3:
        print("[WARNING] 키워드는 최대 3개까지만 분석됩니다.")
        keywords = keywords[:3]
    if not careers:
        print("[ERROR] careers가 비어 있습니다. parse_careers()로 먼저 경력을 파싱하세요.")
        return {"status": "error", "message": "경력 데이터 없음"}

    print(f"\n분석 대상: {len(careers)}개 경력 / 키워드: {', '.join(keywords)}")
    if target:
        print(f"목표 시나리오: {target}")

    today_str = datetime.now().strftime("%Y-%m-%d")

    careers_text = ""
    for i, career in enumerate(careers, 1):
        careers_text += f"\n\n[경력 {i}] ID: {career.get('id', f'career_{i}')}\n"
        careers_text += f"제목: {career.get('title', '제목 없음')}\n"
        careers_text += f"카테고리: {career.get('category', '')}\n"
        careers_text += f"기관: {career.get('organization', '')}\n"
        careers_text += f"역할: {career.get('role', '')}\n"
        careers_text += f"기간: {career.get('period_start', '')} ~ {career.get('period_end', '')}\n"
        careers_text += f"설명: {career.get('description', '')}\n"
        achievements = career.get("achievements", [])
        if achievements:
            careers_text += f"성과: {', '.join(achievements) if isinstance(achievements, list) else achievements}\n"
        if career.get("raw_content"):
            careers_text += f"[원문]\n{career['raw_content'][:2000]}\n"

    user_prompt = f"""아래 경력 풀을 분석하여 키워드 기반 분석 결과를 생성하세요.

[오늘 날짜]
{today_str}

[분석 대상 키워드]
{', '.join(keywords)}

[목표 시나리오/직무]
{target if target else '(없음)'}

[전체 경력 풀 - {len(careers)}개]
{careers_text}

[중요 지시]
- analysis_date는 반드시 "{today_str}"로 설정하세요.
- source_quote는 원문에서 정확히 인용하세요 (최소 10자 이상).
- 원문에 없는 내용은 절대 인용하지 마세요.
"""

    result = _call_model(_keyword_analysis_prompt(keywords, target), user_prompt)

    if result.get("status") == "success":
        result["analysis_date"] = today_str
        print(f"  [분석 완료]", flush=True)
    else:
        print(f"  [분석 실패] {result.get('message', 'Unknown error')}", flush=True)

    print("\n" + "=" * 60)
    print("  분석 결과 (JSON)")
    print("=" * 60)
    print(json.dumps(result, ensure_ascii=False, indent=2 if pretty else None))

    return result


def show_keywords():
    """추천 키워드 목록을 출력합니다."""
    print("=" * 60)
    print("  추천 키워드 목록")
    print("=" * 60)
    for category, kws in KEYWORD_CATEGORIES.items():
        print(f"\n[{category}]")
        print(f"  {', '.join(kws)}")


def main(keywords: list[str], user_input: str):
    careers = parse_careers(user_input)
    return analyze_keywords(keywords, careers)