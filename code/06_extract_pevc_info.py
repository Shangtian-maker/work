import os
import re
import csv
import json

BASE_DIR = r"C:\Users\lenovo\Desktop\project"

MARKDOWN_FILE = os.path.join(BASE_DIR, "markdown_files", "companyA.md")
CANDIDATE_JSON = os.path.join(
    BASE_DIR, "outputs", "week1_candidate_texts", "companyA_relevant_sections.json"
)
OUTPUT_JSON = os.path.join(
    BASE_DIR, "outputs", "week1_sample_json", "companyA_structured.json"
)
LOG_FILE = os.path.join(BASE_DIR, "logs", "extraction_log.csv")


ROUND_PATTERN = re.compile(
    r"(天使轮|种子轮|Pre[-－]?A轮|A轮|B轮|C轮|D轮|E轮|战略融资|战略投资)"
)

DATE_PATTERNS = [
    re.compile(r"(\d{4})年(\d{1,2})月(\d{1,2})日"),
    re.compile(r"(\d{4})[-/.](\d{1,2})[-/.](\d{1,2})"),
    re.compile(r"(\d{4})年(\d{1,2})月"),
    re.compile(r"(\d{4})[-/.](\d{1,2})"),
    re.compile(r"(\d{4})年"),
]

AMOUNT_PATTERN = re.compile(
    r"(\d+(?:\.\d+)?)\s*(亿元|亿|万元|万|元|人民币元|人民币万元|人民币亿元)"
)

SHARE_PRICE_PATTERN = re.compile(
    r"(?:每股价格|认购价格|转让价格|增资价格|价格|发行价格)"
    r"[为：:\s]*?(\d+(?:\.\d+)?)\s*(?:元/股|元每股|元)"
)

RATIO_PATTERN = re.compile(r"(\d+(?:\.\d+)?)\s*%")

SHARES_PATTERN = re.compile(r"(\d+(?:\.\d+)?)\s*(万股|股)")

INVESTOR_PATTERN = re.compile(
    r"([\u4e00-\u9fa5A-Za-z0-9（）()·\-]{2,50}?"
    r"(?:资本|基金|投资|创投|创业投资|合伙企业|有限合伙|资产管理|管理中心|集团|公司|产业基金))"
)

EVENT_KEYWORDS = [
    "增资", "股权转让", "股份转让", "认购", "入股", "出资",
    "受让", "转让", "融资", "投资", "工商变更", "股东会决议",
    "增资协议", "投资协议", "股权转让协议"
]


def read_file(path):
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def normalize_date(text):
    for p in DATE_PATTERNS:
        m = p.search(text)
        if not m:
            continue

        parts = m.groups()

        if len(parts) == 3:
            y, mo, d = parts
            return f"{int(y):04d}-{int(mo):02d}-{int(d):02d}"

        if len(parts) == 2:
            y, mo = parts
            return f"{int(y):04d}-{int(mo):02d}"

        if len(parts) == 1:
            y = parts[0]
            return f"{int(y):04d}"

    return None


def infer_date_type(text):
    if "协议" in text or "签署" in text:
        return "协议签署日"
    if "工商" in text or "变更" in text:
        return "工商变更日"
    if "股东会" in text or "决议" in text:
        return "股东会决议日"
    return "未说明"


def amount_to_yuan(text):
    if not text:
        return None

    m = AMOUNT_PATTERN.search(text)
    if not m:
        return None

    num = float(m.group(1))
    unit = m.group(2)

    if "亿" in unit:
        return num * 100000000
    if "万" in unit:
        return num * 10000
    return num


def extract_first_amount(text):
    m = AMOUNT_PATTERN.search(text)
    if not m:
        return None
    return amount_to_yuan(m.group(0))


def extract_share_price(text):
    m = SHARE_PRICE_PATTERN.search(text)
    return float(m.group(1)) if m else None


def extract_ratio(text):
    m = RATIO_PATTERN.search(text)
    return float(m.group(1)) / 100 if m else None


def extract_shares(text):
    m = SHARES_PATTERN.search(text)
    if not m:
        return None

    num = float(m.group(1))
    unit = m.group(2)

    if unit == "万股":
        return num * 10000
    return num


def extract_pre_money_valuation(text):
    m = re.search(
        r"投前估值[^，。；;]*?(\d+(?:\.\d+)?\s*(?:亿元|亿|万元|万|元))",
        text
    )
    return amount_to_yuan(m.group(1)) if m else None


def extract_post_money_valuation(text):
    m = re.search(
        r"投后估值[^，。；;]*?(\d+(?:\.\d+)?\s*(?:亿元|亿|万元|万|元))",
        text
    )
    return amount_to_yuan(m.group(1)) if m else None


def extract_company_info(markdown_text):
    head = markdown_text[:5000]

    def find(pattern):
        m = re.search(pattern, head)
        return m.group(1).strip() if m else None

    return {
        "company_name": find(r"(?:公司名称|发行人名称|发行人)[:：]\s*([^\n，。]+)"),
        "stock_code": find(r"(?:股票代码|证券代码)[:：]\s*([A-Za-z0-9\.]+)"),
        "exchange": find(r"(?:上市地点|上市交易所|交易所)[:：]\s*([^\n，。]+)"),
        "board": find(r"(?:上市板块|板块)[:：]\s*([^\n，。]+)"),
        "listing_date": None,
        "prospectus_title": find(r"(.*招股说明书.*)"),
        "prospectus_url": None,
        "prospectus_version": None,
        "prospectus_date": normalize_date(head)
    }


def infer_event_type(text):
    has_increase = any(k in text for k in ["增资", "认购", "出资", "入股", "投资"])
    has_transfer = any(k in text for k in ["股权转让", "股份转让", "转让", "受让"])

    if has_increase and has_transfer:
        return "增资及股权转让"
    if has_increase:
        return "增资"
    if has_transfer:
        return "股权转让"
    return "其他"


def extract_disclosed_round(text):
    m = ROUND_PATTERN.search(text)
    return m.group(1) if m else "未披露"


def infer_round(text, disclosed_round):
    if disclosed_round != "未披露":
        return None, None

    if "首次" in text and any(k in text for k in ["外部投资", "融资", "增资", "投资者"]):
        return "可能为首轮外部融资", "文本出现“首次”及外部投资/融资/增资相关表述，但未直接披露轮次"

    if "战略投资" in text or "战略投资者" in text:
        return "可能为战略融资", "文本出现“战略投资/战略投资者”表述，但未直接披露轮次"

    return None, None


def classify_investor(name):
    if not name:
        return "无法判断", "uncertain"

    if any(k in name for k in ["资本", "基金", "创投", "创业投资", "有限合伙", "合伙企业"]):
        return "VC/PE", "yes"

    if "员工持股" in name or "持股平台" in name:
        return "员工持股平台", "no"

    if "政府" in name or "引导基金" in name:
        return "政府基金", "uncertain"

    if "公司" in name or "集团" in name:
        return "产业资本", "uncertain"

    return "无法判断", "uncertain"


def extract_investors(event_text):
    names = []

    for m in INVESTOR_PATTERN.findall(event_text):
        name = m.strip("，。；;：:（）() ")
        if name not in names and name not in ["本公司", "发行人公司", "目标公司"]:
            names.append(name)

    investors = []

    for name in names:
        investor_type, is_pevc = classify_investor(name)

        idx = event_text.find(name)
        nearby = event_text[max(0, idx - 80): idx + len(name) + 120] if idx >= 0 else event_text

        investors.append({
            "investor_original_name": name,
            "investor_short_name": None,
            "investor_type": investor_type,
            "is_pevc": is_pevc,
            "investment_amount": extract_first_amount(nearby),
            "shares_acquired": extract_shares(nearby),
            "shareholding_ratio_after_event": extract_ratio(nearby),
            "exit_status_before_ipo": "无法判断"
        })

    return investors


def split_events(section_text):
    parts = re.split(r"(?<=[。；;])|\n+", section_text)
    parts = [p.strip() for p in parts if p.strip()]

    event_texts = []

    for i, part in enumerate(parts):
        if any(k in part for k in EVENT_KEYWORDS):
            text = part

            if i > 0 and normalize_date(parts[i - 1]):
                text = parts[i - 1] + text

            if i + 1 < len(parts):
                next_part = parts[i + 1]
                if AMOUNT_PATTERN.search(next_part) or RATIO_PATTERN.search(next_part):
                    text = text + next_part

            event_texts.append(text)

    if not event_texts and any(k in section_text for k in EVENT_KEYWORDS):
        event_texts = [section_text]

    unique = []
    seen = set()

    for t in event_texts:
        key = re.sub(r"\s+", "", t)
        if key not in seen:
            seen.add(key)
            unique.append(t)

    return unique


def make_event(event_order, event_text, section_hierarchy):
    disclosed_round = extract_disclosed_round(event_text)
    inferred_round, round_basis = infer_round(event_text, disclosed_round)

    pre_money = extract_pre_money_valuation(event_text)
    post_money = extract_post_money_valuation(event_text)

    return {
        "event_order": event_order,
        "event_date": normalize_date(event_text),
        "date_type": infer_date_type(event_text),
        "event_type": infer_event_type(event_text),
        "disclosed_round": disclosed_round,
        "inferred_round": inferred_round,
        "round_inference_basis": round_basis,
        "total_investment_amount": extract_first_amount(event_text),
        "currency": "CNY" if extract_first_amount(event_text) is not None else None,
        "share_price": extract_share_price(event_text),
        "pre_money_valuation": pre_money,
        "post_money_valuation": post_money,
        "valuation_basis": event_text if pre_money is not None or post_money is not None else None,
        "investors": extract_investors(event_text),
        "source_section": " > ".join(section_hierarchy) if section_hierarchy else None,
        "source_page": None,
        "evidence_text": event_text,
        "confidence": "medium"
    }


def extract_events_from_sections(candidate_data):
    all_events = []
    event_order = 1

    for sec in candidate_data.get("relevant_sections", []):
        content = sec.get("content", [])
        section_text = "\n".join(content) if isinstance(content, list) else str(content)
        section_hierarchy = sec.get("title_hierarchy", [])

        event_texts = split_events(section_text)

        for event_text in event_texts:
            event = make_event(event_order, event_text, section_hierarchy)
            all_events.append(event)
            event_order += 1

    return all_events


def write_log(row):
    os.makedirs(os.path.dirname(LOG_FILE), exist_ok=True)

    fieldnames = ["file_name", "events_extracted", "success", "error"]

    with open(LOG_FILE, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerow(row)


def main():
    try:
        markdown_text = read_file(MARKDOWN_FILE)

        with open(CANDIDATE_JSON, "r", encoding="utf-8") as f:
            candidate_data = json.load(f)

        company_info = extract_company_info(markdown_text)
        financing_events = extract_events_from_sections(candidate_data)

        structured_data = {
            "company": company_info,
            "financing_events": financing_events,
            "processing": {
                "download_status": "success",
                "parse_status": "success",
                "locate_status": "success",
                "extract_status": "success" if financing_events else "partial",
                "review_status": "unchecked",
                "notes": None if financing_events else "未识别出融资事件"
            }
        }

        os.makedirs(os.path.dirname(OUTPUT_JSON), exist_ok=True)

        with open(OUTPUT_JSON, "w", encoding="utf-8") as f:
            json.dump(structured_data, f, ensure_ascii=False, indent=2)

        write_log({
            "file_name": os.path.basename(MARKDOWN_FILE),
            "events_extracted": len(financing_events),
            "success": True,
            "error": ""
        })

        print(f"提取完成，共提取 {len(financing_events)} 条融资事件")
        print(f"结构化 JSON 保存到：{OUTPUT_JSON}")
        print(f"日志保存到：{LOG_FILE}")

    except Exception as e:
        write_log({
            "file_name": os.path.basename(MARKDOWN_FILE),
            "events_extracted": 0,
            "success": False,
            "error": str(e)
        })

        print(f"提取失败：{e}")


if __name__ == "__main__":
    main()