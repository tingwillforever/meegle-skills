#!/usr/bin/env python3
"""RDHS 产研健康度极速查询与诊断工具 (rdhs_query.py)

专为 AI Agent 和产研效能分析设计：
1. 自动调用 Meegle CLI 拉取实时度量底表，支持会话级短缓存（默认 0 秒实时直连）。
2. 内置 10429 频率限制自动重试与退避机制。
3. 动态结合主数据清洗规则（自动剔除交付定制与测试业务线，只考核 In Progress 在研标准产品）。
4. 真实角色解析：严格从 role_owners 读取【产品代表】与【项目管理代表】，绝不误读卡片 owner 建卡人。
5. 内置 7 阶归因判定引擎与 4 级治理分档计算。
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

CACHE_DIR = Path(os.path.expanduser("~/.cache/meegle-rdhs"))
CACHE_TTL = 0  # 默认 0 秒：确保每次调用 100% 直连飞书项目拉取此时此刻最新实时数据
TREND_MONTHS = 6

CURRENT_CHART_ID = "7659618575337915254"
LAST_CHART_ID = "7681204196376314742"
BG_TREND_CHART_ID = "7688169549312557942"
LINE_TREND_CHART_ID = "7688177041702650742"
SECONDARY_LINE_TREND_CHART_ID = "7688220298042147702"
PROJECT_KEY = "cbg_product_develop"
MASTER_TYPE_KEY = "693f665435b354b7ca0085dc"

# 角色映射表
ROLE_MAP = {
    "role_01773a": "产品代表",
    "role_57dcb8": "产品经理",
    "role_424751": "研发代表",
    "role_0ba52c": "系统架构师",
    "role_8d8f90": "项目管理代表",
    "role_4292f5": "PMO"
}

# 7-tier attribution labels
ATTR_DATA_MISSING = "过程数据缺失"
ATTR_VALUE_CHAIN_BROKEN = "价值链路不完整"
ATTR_BACKLOG_HEAVY = "需求积压"
ATTR_QUALITY_RISK = "质量管理风险"
ATTR_RELEASE_DEFICIT = "发布闭环不足"
ATTR_PACE_SLOW = "研发节奏偏慢"
ATTR_PROCESS_OPTIMIZE = "过程能力优化"

USER_CACHE_FILE = CACHE_DIR / "user_names.json"

def run_meegle_cmd(args: List[str], max_retries: int = 3) -> Any:
    cmd = ["meegle"] + args + ["--format", "json"]
    for attempt in range(max_retries):
        try:
            res = subprocess.run(cmd, capture_output=True, text=True, check=False)
            if res.returncode != 0:
                err_text = res.stdout + "\n" + res.stderr
                if "10429" in err_text or "Frequency Limit" in err_text:
                    time.sleep(1.5 * (attempt + 1))
                    continue
                if attempt == max_retries - 1:
                    raise RuntimeError(f"Meegle CLI failed: {err_text}")
                time.sleep(1)
                continue
            data = json.loads(res.stdout)
            if isinstance(data, dict) and data.get("error"):
                err_msg = json.dumps(data["error"], ensure_ascii=False)
                if "10429" in err_msg and attempt < max_retries - 1:
                    time.sleep(1.5 * (attempt + 1))
                    continue
                raise RuntimeError(f"Meegle API error: {err_msg}")
            if isinstance(data, dict) and "data" in data:
                return data["data"]
            return data
        except json.JSONDecodeError:
            if attempt == max_retries - 1:
                raise RuntimeError(f"Failed to parse Meegle output as JSON: {res.stdout}")
            time.sleep(1)
    raise RuntimeError("Meegle CLI timed out after retries.")

def get_cached_or_fetch(key: str, fetch_fn, ttl: int = CACHE_TTL, refresh: bool = False) -> Any:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cache_file = CACHE_DIR / f"{key}.json"
    now = time.time()
    if not refresh and ttl > 0 and cache_file.exists():
        try:
            mtime = cache_file.stat().st_mtime
            if now - mtime < ttl:
                with open(cache_file, "r", encoding="utf-8") as f:
                    return json.load(f)
        except Exception:
            pass

    data = fetch_fn()
    try:
        with open(cache_file, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False)
    except Exception:
        pass
    return data

def get_chart_data(chart_id: str, ttl: int = CACHE_TTL, refresh: bool = False) -> Tuple[List[str], List[Dict[str, Any]]]:
    raw = get_cached_or_fetch(
        f"chart_{chart_id}",
        lambda: run_meegle_cmd(["chart", "get", "--project-key", PROJECT_KEY, "--chart-id", chart_id]),
        ttl=ttl,
        refresh=refresh
    )
    quota_titles = raw.get("quota_titles", []) if isinstance(raw, dict) else []
    chart_list = raw.get("chart_data_list", []) if isinstance(raw, dict) else []
    rows = chart_list[0] if chart_list else []
    return quota_titles, rows

def get_business_lines(ttl: int = CACHE_TTL, refresh: bool = False) -> Dict[str, str]:
    raw = get_cached_or_fetch(
        "business_lines",
        lambda: run_meegle_cmd(["space", "business-lines", "--project-key", PROJECT_KEY]),
        ttl=3600 if ttl == 0 else ttl,  # 业务线树结构极为稳定，默认安全缓存1小时
        refresh=refresh
    )
    b_map: Dict[str, str] = {}
    def traverse(nodes: List[Dict[str, Any]], prefix: str = ""):
        for n in nodes:
            full_name = f"{prefix}/{n['name']}" if prefix else n["name"]
            b_map[n["id"]] = full_name
            if n.get("children"):
                traverse(n["children"], full_name)
    nodes = raw if isinstance(raw, list) else (raw.get("data", []) if isinstance(raw, dict) else [])
    traverse(nodes)
    return b_map

def resolve_user_names(user_keys: List[str]) -> Dict[str, str]:
    if not user_keys:
        return {}
    known: Dict[str, str] = {}
    if USER_CACHE_FILE.exists():
        try:
            with open(USER_CACHE_FILE, "r", encoding="utf-8") as f:
                known = json.load(f)
        except Exception:
            pass

    to_query = [k for k in set(user_keys) if k and k not in known]
    if to_query:
        # Batch query in chunks of 10
        for i in range(0, len(to_query), 10):
            chunk = to_query[i:i+10]
            try:
                res = run_meegle_cmd(["user", "query", "--user-keys", ",".join(chunk)])
                user_list = res if isinstance(res, list) else (res.get("data", []) if isinstance(res, dict) else [])
                for u in user_list:
                    uk = str(u.get("user_key", ""))
                    name_cn = u.get("name_cn", "") or u.get("name", {}).get("zh_cn", "")
                    simple_name = name_cn.split()[0] if name_cn else uk
                    known[uk] = simple_name
            except Exception:
                pass
        try:
            with open(USER_CACHE_FILE, "w", encoding="utf-8") as f:
                json.dump(known, f, ensure_ascii=False)
        except Exception:
            pass
    return known

def get_product_master(ttl: int = CACHE_TTL, refresh: bool = False) -> Dict[str, Dict[str, Any]]:
    raw = get_cached_or_fetch(
        "product_master",
        lambda: run_meegle_cmd([
            "workitem", "search-filter",
            "--project-key", PROJECT_KEY,
            "--work-item-type-keys", MASTER_TYPE_KEY,
            "--page-size", "200"
        ]),
        ttl=ttl,
        refresh=refresh
    )
    items = raw if isinstance(raw, list) else (raw.get("data", []) if isinstance(raw, dict) else [])
    b_lines = get_business_lines(ttl=ttl, refresh=refresh)
    
    # Pre-collect all user keys inside role_owners
    all_role_users: List[str] = []
    for it in items:
        for f in it.get("fields", []):
            if f.get("field_key") == "role_owners":
                for r in f.get("field_value") or []:
                    for o in r.get("owners") or []:
                        all_role_users.append(str(o))
    user_map = resolve_user_names(all_role_users)

    master: Dict[str, Dict[str, Any]] = {}
    for it in items:
        f_map = {f["field_key"]: f for f in it.get("fields", [])}
        bid = f_map.get("business", {}).get("field_value")
        p_attr = f_map.get("field_22acd7", {}).get("field_value", {}).get("label", "标准产品")
        status = it.get("work_item_status", {}).get("state_key", "")
        b_path = b_lines.get(bid, "其他业务线")
        
        # Parse real role owners
        ro_list = f_map.get("role_owners", {}).get("field_value") or []
        roles: Dict[str, List[str]] = {}
        for r in ro_list:
            rid = r.get("role")
            rname = ROLE_MAP.get(rid, rid)
            owners = [user_map.get(str(o), str(o)) for o in (r.get("owners") or [])]
            if owners:
                roles[rname] = owners

        # Determine primary responsible person (优先产品代表 -> 产品经理 -> 项目管理代表)
        prod_rep = roles.get("产品代表", [])
        prod_mgr = roles.get("产品经理", [])
        pm_rep = roles.get("项目管理代表", [])
        
        primary_owner = ""
        if prod_rep:
            primary_owner = f"{','.join(prod_rep)} (产品代表)"
        elif prod_mgr:
            primary_owner = f"{','.join(prod_mgr)} (产品经理)"
        elif pm_rep:
            primary_owner = f"{','.join(pm_rep)} (项目管理)"
        else:
            primary_owner = "未指定"

        master[it["name"].strip()] = {
            "id": it["id"],
            "business_id": bid,
            "business_path": b_path,
            "status": status,
            "is_in_progress": (status == "In Progress"),
            "product_attr": p_attr,
            "is_custom": (p_attr == "交付定制"),
            "roles": roles,
            "owner": primary_owner,
            "prod_rep": ",".join(prod_rep) if prod_rep else "-",
            "pm_rep": ",".join(pm_rep) if pm_rep else "-"
        }
    return master

def evaluate_attribution(metrics: Dict[str, Any]) -> Tuple[str, str, str]:
    participants = float(metrics.get("有效参与人数") or 0)
    throughput = float(metrics.get("人均需求吞吐量") or 0)
    defect_close = float(metrics.get("人均缺陷关闭量") or 0)
    chain_score = float(metrics.get("链路闭环得分(25')") or 0)
    backlog_ratio = float(metrics.get("积压需求占比") or 0)
    severe_ratio = float(metrics.get("严重缺陷占比") or 0)
    delivery_score = float(metrics.get("交付闭环得分(15')") or 0)
    time_score = float(metrics.get("时效节奏合理性(20')") or 0)

    if participants == 0:
        main_tag = ATTR_DATA_MISSING
        detail = "有效参与人数为 0，提卡未挂载实际责任人或未进入度量"
        step = "规划失序（责任角色缺失）"
    elif throughput == 0 or chain_score < 15:
        main_tag = ATTR_VALUE_CHAIN_BROKEN
        if defect_close > 0:
            detail = f"人均需求吞吐量为 0，人均缺陷关闭 {defect_close:.1f}；团队只修Bug未交付需求，价值链路断裂"
        else:
            detail = "人均需求吞吐与人均缺陷关闭均为 0，无实际交付产出"
        step = "交付断链（无需求验收交付）"
    elif backlog_ratio > 0.30:
        main_tag = ATTR_BACKLOG_HEAVY
        detail = f"积压需求占比 {backlog_ratio*100:.1f}% > 30%，大量需求停滞在途中未闭环"
        step = "在途失控（僵尸需求超期滞留）"
    elif severe_ratio > 0.15:
        main_tag = ATTR_QUALITY_RISK
        detail = f"严重缺陷占比 {severe_ratio*100:.1f}% > 15%，严重缺陷比例超标"
        step = "质量失守（严重致命缺陷超标）"
    elif delivery_score < 8:
        main_tag = ATTR_RELEASE_DEFICIT
        detail = f"交付闭环得分 {delivery_score:.0f} < 8 分，上线发布未按规范关联发布计划"
        step = "发版脱节（发版未挂发布计划）"
    elif time_score < 10:
        main_tag = ATTR_PACE_SLOW
        detail = f"时效节奏得分 {time_score:.0f} < 10 分，需求交付周期或开发周期过长"
        step = "周期失控（在途超长、排期停滞）"
    else:
        main_tag = ATTR_PROCESS_OPTIMIZE
        detail = "各单项指标基本健全，需进一步微调颗粒度与时效节奏"
        step = "拆解粗糙（单需求包袱过大）"

    if main_tag != ATTR_BACKLOG_HEAVY and backlog_ratio > 0.30:
        total_req = int(float(metrics.get("需求总量") or 0))
        detail += f"（叠加积压风险：需求总量 {total_req}，积压占比 {backlog_ratio*100:.1f}%）"

    return main_tag, detail, step

def get_tier(rdhs: float) -> Tuple[str, str]:
    if rdhs >= 70:
        return "常规跟踪", "达标"
    elif rdhs >= 60:
        return "持续优化", "P2"
    elif rdhs >= 45:
        return "风险改进", "P1"
    else:
        return "重点治理", "P0"

def parse_chart_rows(quota_titles: List[str], rows: List[Dict[str, Any]], master: Dict[str, Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    prods: Dict[str, Dict[str, Any]] = {}
    valid_rows: Dict[Tuple[str, str], Dict[str, Any]] = {}
    fallback_rows: Dict[str, Dict[str, Any]] = {}

    for r in rows:
        dim = r.get("dim", {})
        b_name = dim.get("0", "").strip()
        p_name = dim.get("1", "").strip()
        if not p_name or p_name == "(空)":
            continue
        vals = r.get("value", {})
        metric_dict: Dict[str, Any] = {}
        for idx, title in enumerate(quota_titles):
            metric_dict[title] = vals.get(str(idx), "0")
        
        row_obj = {
            "business_line_chart": b_name,
            "product_name": p_name,
            "is_zero_spec": r.get("is_zero_spec", False),
            "metrics": metric_dict,
            "rdhs": float(metric_dict.get("RDHS(100')", 0) or 0)
        }
        
        if not r.get("is_zero_spec", False):
            valid_rows[(b_name, p_name)] = row_obj
        if p_name not in fallback_rows or not r.get("is_zero_spec", False):
            fallback_rows[p_name] = row_obj

    for pname, minfo in master.items():
        b_top = minfo["business_path"].split("/")[0] if minfo.get("business_path") else ""
        if (b_top, pname) in valid_rows:
            prods[pname] = valid_rows[(b_top, pname)]
        elif pname in fallback_rows:
            prods[pname] = fallback_rows[pname]

    for (b_name, pname), row_obj in valid_rows.items():
        if pname not in prods:
            prods[pname] = row_obj

    return prods

def is_eligible_product(master_info: Optional[Dict[str, Any]]) -> bool:
    """RDHS 聚合只纳入在研、非交付定制、非测试业务线产品。"""
    return bool(
        master_info
        and master_info.get("is_in_progress")
        and not master_info.get("is_custom")
        and "测试业务线" not in master_info.get("business_path", "")
    )

def summarize_scope(
    matched: List[Tuple[str, Optional[Dict[str, Any]], Optional[Dict[str, Any]], Optional[Dict[str, Any]]]]
) -> Dict[str, Any]:
    measured = [item for item in matched if item[1] is not None]
    missing = [item[0] for item in matched if item[1] is None]
    avg = sum(item[1]["rdhs"] for item in measured) / len(measured) if measured else None
    paired = [item for item in matched if item[1] is not None and item[2] is not None]
    paired_current_avg = sum(item[1]["rdhs"] for item in paired) / len(paired) if paired else None
    paired_last_avg = sum(item[2]["rdhs"] for item in paired) / len(paired) if paired else None
    tiers = {"P0": 0, "P1": 0, "P2": 0, "达标": 0}
    for _, current, _, _ in measured:
        tiers[get_tier(current["rdhs"])[1]] += 1
    return {
        "average_rdhs": avg,
        "comparison_count": len(paired),
        "comparison_current_average": paired_current_avg,
        "last_average_rdhs": paired_last_avg,
        "eligible_count": len(matched),
        "measured_count": len(measured),
        "coverage": len(measured) / len(matched) if matched else 0,
        "missing_products": missing,
        "tiers": tiers,
    }

def parse_trend_rows(
    quota_titles: List[str],
    rows: List[Dict[str, Any]],
    business_line: Optional[str] = None,
    secondary_line: Optional[str] = None,
) -> List[Dict[str, Any]]:
    current_month = datetime.now().strftime("%Y-%m")
    parsed: List[Dict[str, Any]] = []
    for row in rows:
        dim = row.get("dim", {})
        month = dim.get("0", "")
        if len(month) != 7 or month >= current_month:
            continue
        if business_line is not None and dim.get("1") != business_line:
            continue
        if secondary_line is not None and dim.get("2") != secondary_line:
            continue
        values = row.get("value", {})
        parsed.append({
            "month": month,
            "metrics": {title: values.get(str(index), "0") for index, title in enumerate(quota_titles)},
        })
    return sorted(parsed, key=lambda item: item["month"])[-TREND_MONTHS:]

def trend_value(metrics: Dict[str, Any], *names: str) -> float:
    for name in names:
        if name in metrics:
            return float(metrics.get(name) or 0)
    return 0.0

def format_trend_judgement(rows: List[Dict[str, Any]]) -> List[str]:
    if len(rows) < 2:
        return []
    previous, current = rows[-2]["metrics"], rows[-1]["metrics"]
    previous_month, current_month = rows[-2]["month"], rows[-1]["month"]
    throughput_before = trend_value(previous, "人均需求吞吐量")
    throughput_now = trend_value(current, "人均需求吞吐量")
    demand_before = trend_value(previous, "需求吞吐量", "需求总量")
    demand_now = trend_value(current, "需求吞吐量", "需求总量")
    delivery_before = trend_value(previous, "需求交付周期")
    delivery_now = trend_value(current, "需求交付周期")
    severe_before = trend_value(previous, "严重缺陷占比") * 100
    severe_now = trend_value(current, "严重缺陷占比") * 100
    if demand_before == 0 and demand_now == 0:
        delivery_text = "- **时效**：连续两月无需求完成，交付周期暂无有效样本"
    else:
        delivery_text = (
            f"- **时效**：需求交付周期 {delivery_before:.2f} → {delivery_now:.2f} 天"
            f"（{'缩短' if delivery_now < delivery_before else '拉长' if delivery_now > delivery_before else '持平'}）"
        )
    return [
        f"- **产出**（{previous_month} → {current_month}）：人均需求吞吐 {throughput_before:.2f} → {throughput_now:.2f}，需求完成量 {demand_before:.0f} → {demand_now:.0f}",
        delivery_text,
        f"- **质量**：严重缺陷占比 {severe_before:.1f}% → {severe_now:.1f}%（{'改善' if severe_now < severe_before else '恶化' if severe_now > severe_before else '持平'}）",
    ]

def format_trend_report(title: str, rows: List[Dict[str, Any]]) -> str:
    if not rows:
        return f"### {title}月度趋势\n未找到可用的完整月趋势数据。"

    lines = [f"### {title}月度关键结果趋势（近 {len(rows)} 个完整月）", *format_trend_judgement(rows), ""]
    lines.extend([
        "| 月份 | 有效人数 | 需求完成量 | 人均需求吞吐 | 需求交付周期 | 需求开发周期 | 严重缺陷占比 | 缺陷逃逸率 | 发布完成量 |",
        "| :--- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ])
    for row in rows:
        metrics = row["metrics"]
        lines.append(
            f"| {row['month']} | {int(trend_value(metrics, '有效参与人数'))} | "
            f"{int(trend_value(metrics, '需求吞吐量', '需求总量'))} | "
            f"{trend_value(metrics, '人均需求吞吐量'):.2f} | "
            f"{trend_value(metrics, '需求交付周期'):.2f} 天 | "
            f"{trend_value(metrics, '需求开发周期'):.2f} 天 | "
            f"{trend_value(metrics, '严重缺陷占比') * 100:.1f}% | "
            f"{trend_value(metrics, '缺陷逃逸率') * 100:.1f}% | "
            f"{int(trend_value(metrics, '发布完成量'))} |"
        )
    lines.extend([
        "",
        "> 口径说明：月度趋势覆盖整体历史业务数据；RDHS 依赖治理后的产品主数据。两者用于交叉印证，不强行对账。",
    ])
    return "\n".join(lines)

def product_facts(current: Dict[str, Any]) -> Tuple[float, float, float, float, float]:
    metrics = current["metrics"]
    return (
        trend_value(metrics, "有效参与人数"),
        trend_value(metrics, "人均需求吞吐量"),
        trend_value(metrics, "人均缺陷关闭量"),
        trend_value(metrics, "需求在途时长"),
        trend_value(metrics, "积压需求占比"),
    )

def select_governance_entries(
    matched: List[Tuple[str, Optional[Dict[str, Any]], Optional[Dict[str, Any]], Optional[Dict[str, Any]]]]
) -> Dict[str, List[Tuple[str, Optional[Dict[str, Any]], Optional[Dict[str, Any]]]]]:
    status: List[Tuple[str, Optional[Dict[str, Any]], Optional[Dict[str, Any]]]] = []
    delivery: List[Tuple[str, Optional[Dict[str, Any]], Optional[Dict[str, Any]]]] = []
    backlog: List[Tuple[str, Optional[Dict[str, Any]], Optional[Dict[str, Any]]]] = []
    for pname, current, _, master_info in matched:
        if not current:
            status.append((pname, current, master_info))
            continue
        participants, throughput, defects, in_transit, backlog_ratio = product_facts(current)
        missing_roles = bool(master_info and master_info.get("prod_rep", "-") == "-" and master_info.get("pm_rep", "-") == "-")
        if participants <= 2 and throughput == 0 and defects == 0:
            status.append((pname, current, master_info))
        elif participants > 0 and throughput == 0:
            delivery.append((pname, current, master_info))
        elif missing_roles:
            status.append((pname, current, master_info))
        elif in_transit > 60 or backlog_ratio > 0.30:
            backlog.append((pname, current, master_info))
    status.sort(key=lambda item: (item[1] is not None, item[1]["rdhs"] if item[1] else 0))
    delivery.sort(key=lambda item: (-product_facts(item[1])[0], item[1]["rdhs"]))
    backlog.sort(key=lambda item: (-max(product_facts(item[1])[3] / 60, product_facts(item[1])[4] / 0.30), -product_facts(item[1])[0]))
    return {"状态/数据待核实": status[:2], "交付断链": delivery[:2], "积压失控": backlog[:2]}

def format_governance_entries(
    matched: List[Tuple[str, Optional[Dict[str, Any]], Optional[Dict[str, Any]], Optional[Dict[str, Any]]]]
) -> str:
    lines = [
        "### 当前治理切口",
        "| 类型 | 产品 | 关键事实 | 责任角色 | 第一动作 |",
        "| :--- | :--- | :--- | :--- | :--- |",
    ]
    count = 0
    for category, entries in select_governance_entries(matched).items():
        for pname, current, master_info in entries:
            count += 1
            product_rep = master_info.get("prod_rep", "-") if master_info else "-"
            project_rep = master_info.get("pm_rep", "-") if master_info else "-"
            roles = f"产品：{product_rep}；项目：{project_rep}"
            if not current:
                facts = "未进入当前 RDHS 度量"
                action = "核实产品主数据、在研状态和度量关联"
            else:
                participants, throughput, defects, in_transit, backlog_ratio = product_facts(current)
                if category == "状态/数据待核实":
                    if product_rep == "-" and project_rep == "-":
                        facts = f"产品与项目责任角色均缺失；{participants:.0f} 人参与"
                        action = "先补齐责任角色，再确认真实在研状态和治理计划"
                    else:
                        facts = f"{participants:.0f} 人参与；需求/缺陷吞吐均为 0"
                        action = "先确认是否真实在研，再决定补闭环或调整状态"
                elif category == "交付断链":
                    facts = f"{participants:.0f} 人参与；需求吞吐 0；人均关闭缺陷 {defects:.2f}"
                    if product_rep == "-" and project_rep == "-":
                        action = "先补齐责任角色，再逐项核查并验收已交付需求"
                    else:
                        action = "逐项核查在途需求，优先完成已交付需求验收"
                else:
                    facts = f"在途 {in_transit:.1f} 天；积压率 {backlog_ratio * 100:.1f}%"
                    action = "对超期需求逐项决定继续、缩期或终止"
            lines.append(f"| **{category}** | **{pname}** | {facts} | {roles} | {action} |")
    if count == 0:
        lines.append("| — | — | 暂未发现明显断链、积压或数据缺口 | — | 保持当前节奏 |")
    return "\n".join(lines)

def format_scope_summary(
    title: str,
    matched: List[Tuple[str, Optional[Dict[str, Any]], Optional[Dict[str, Any]], Optional[Dict[str, Any]]]],
    compare: bool = False,
) -> str:
    summary = summarize_scope(matched)
    average = summary["average_rdhs"]
    average_text = f"{average:.1f} 分" if average is not None else "—"
    tier_text = get_tier(average)[0] if average is not None else "无有效度量"
    compare_text = ""
    if compare and summary["comparison_current_average"] is not None and summary["last_average_rdhs"] is not None:
        delta = summary["comparison_current_average"] - summary["last_average_rdhs"]
        compare_text = (
            f"；同口径 {summary['comparison_count']} 款产品较上月 {delta:+.1f} 分"
            f"（{summary['last_average_rdhs']:.1f} → {summary['comparison_current_average']:.1f}）"
        )
    return "\n".join([
        f"## 📊 {title} RDHS 当下健康度",
        f"- **产品 RDHS 算术平均**：**{average_text}**（{tier_text}）{compare_text}",
        f"- **度量覆盖**：{summary['measured_count']} / {summary['eligible_count']} 款产品（{summary['coverage'] * 100:.1f}%）",
        f"- **产品分布**：P0 {summary['tiers']['P0']}｜P1 {summary['tiers']['P1']}｜P2 {summary['tiers']['P2']}｜达标 {summary['tiers']['达标']}",
    ])

def format_business_line_summary(
    matched: List[Tuple[str, Optional[Dict[str, Any]], Optional[Dict[str, Any]], Optional[Dict[str, Any]]]]
) -> str:
    groups: Dict[str, List[Tuple[str, Optional[Dict[str, Any]], Optional[Dict[str, Any]], Optional[Dict[str, Any]]]]] = {}
    for item in matched:
        path = item[3].get("business_path", "其他业务线") if item[3] else "其他业务线"
        groups.setdefault(path.split("/")[0], []).append(item)
    lines = [
        "### 一级业务线概览",
        "| 一级业务线 | 产品平均 RDHS | P0 产品 | 度量覆盖 |",
        "| :--- | ---: | ---: | ---: |",
    ]
    ranked = []
    for line_name, products in groups.items():
        summary = summarize_scope(products)
        ranked.append((summary["average_rdhs"] if summary["average_rdhs"] is not None else -1, line_name, summary))
    for average, line_name, summary in sorted(ranked):
        average_text = f"{average:.1f}" if average >= 0 else "—"
        lines.append(
            f"| **{line_name}** | {average_text} | {summary['tiers']['P0']} | "
            f"{summary['measured_count']} / {summary['eligible_count']}（{summary['coverage'] * 100:.1f}%） |"
        )
    return "\n".join(lines)

def format_full_leaderboard(
    matched: List[Tuple[str, Optional[Dict[str, Any]], Optional[Dict[str, Any]], Optional[Dict[str, Any]]]]
) -> str:
    summary = summarize_scope(matched)
    lines = [
        f"### 完整产品诊断榜单（共 {summary['eligible_count']} 款）",
        "| 产品型号/名称 | 业务线归属 | 属性/状态 | RDHS得分 | 治理分档 | 产品代表 | 项目管理代表 |",
        "| :--- | :--- | :--- | :---: | :---: | :--- | :--- |",
    ]
    for pname, current, _, master_info in sorted(matched, key=lambda item: item[1]["rdhs"] if item[1] else -1):
        if not current:
            lines.append(
                f"| **{pname}** | {master_info.get('business_path', '-') if master_info else '-'} | 缺失度量 | **—** | "
                f"未度量 / 数据治理 | {master_info.get('prod_rep', '-') if master_info else '-'} | "
                f"{master_info.get('pm_rep', '-') if master_info else '-'} |"
            )
            continue
        tier_name, priority = get_tier(current["rdhs"])
        path = master_info.get("business_path", current["business_line_chart"]) if master_info else current["business_line_chart"]
        product_attr = master_info.get("product_attr", "标准产品") if master_info else "标准产品"
        status = "在研" if master_info and master_info.get("is_in_progress") else "存量"
        product_rep = master_info.get("prod_rep", "-") if master_info else "-"
        project_rep = master_info.get("pm_rep", "-") if master_info else "-"
        lines.append(
            f"| **{pname}** | {path} | {product_attr}({status}) | **{current['rdhs']:.0f} 分** | "
            f"`{tier_name}({priority})` | {product_rep} | {project_rep} |"
        )
    if summary["missing_products"]:
        lines.extend(["", f"- **未度量产品**：{'、'.join(summary['missing_products'])}（不计入平均值，作为数据治理项）"])
    return "\n".join(lines)

def format_product_candidates(
    query: str,
    matched: List[Tuple[str, Optional[Dict[str, Any]], Optional[Dict[str, Any]], Optional[Dict[str, Any]]]],
) -> str:
    lines = [
        f"## “{query}”匹配到 {len(matched)} 款产品，请选择具体产品",
        "| 产品 | 业务归属 | RDHS |",
        "| :--- | :--- | ---: |",
    ]
    for pname, current, _, master_info in matched:
        path = master_info.get("business_path", "-") if master_info else "-"
        score = f"{current['rdhs']:.0f} 分" if current else "未度量"
        lines.append(f"| **{pname}** | {path} | {score} |")
    return "\n".join(lines)

def format_product_report(p_name: str, cur_item: Optional[Dict[str, Any]], last_item: Optional[Dict[str, Any]], master_info: Optional[Dict[str, Any]]) -> str:
    if not cur_item:
        return f"未在当前月度量图表中找到产品【{p_name}】的记录。"

    metrics = cur_item["metrics"]
    rdhs_cur = cur_item["rdhs"]
    tier_name, tier_p = get_tier(rdhs_cur)
    
    last_rdhs_str = "-"
    delta_str = "-"
    if last_item:
        rdhs_last = last_item["rdhs"]
        last_rdhs_str = f"{rdhs_last:.0f} 分"
        delta = rdhs_cur - rdhs_last
        if delta > 0:
            delta_str = f"+{delta:.0f} 分 🟢"
        elif delta < 0:
            delta_str = f"{delta:.0f} 分 🔴"
        else:
            delta_str = "持平"

    main_tag, detail, step = evaluate_attribution(metrics)
    
    b_path = master_info.get("business_path", cur_item["business_line_chart"]) if master_info else cur_item["business_line_chart"]
    p_attr = master_info.get("product_attr", "标准产品") if master_info else "标准产品"
    status_str = "在研 (In Progress)" if (master_info and master_info.get("is_in_progress")) else "存量维护/其他"
    
    roles_str = ""
    if master_info and master_info.get("roles"):
        roles_parts = [f"{r}: {','.join(names)}" for r, names in master_info["roles"].items() if r != "PMO"]
        roles_str = " | ".join(roles_parts)
    if not roles_str:
        roles_str = master_info.get("owner", "未指定") if master_info else "未指定"

    def dim_status(score: float, max_s: float) -> str:
        ratio = score / max_s if max_s > 0 else 0
        if ratio >= 0.8:
            return "🟢 优秀"
        elif ratio >= 0.5:
            return "🟡 中游"
        else:
            return "🔴 严重偏低"

    s_chain = float(metrics.get("链路闭环得分(25')", 0))
    s_deliv = float(metrics.get("交付闭环得分(15')", 0))
    s_time = float(metrics.get("时效节奏合理性(20')", 0))
    s_grain = float(metrics.get("颗粒度对齐度(20')", 0))
    s_qual = float(metrics.get("质量敏锐度(20')", 0))

    lines = [
        f"## 🏥【{p_name}】RDHS 产研过程体检诊断报告",
        f"- **业务归属**：`{b_path}` | **产品属性**：{p_attr} | **当前状态**：{status_str}",
        f"- **核心责任角色**：{roles_str}",
        f"- **综合健康度**：**{rdhs_cur:.0f} 分**（{tier_name}，治理优先级：`{tier_p}`） | **上月基线**：{last_rdhs_str}（环比：{delta_str}）",
        f"- **核心归因判定**：`【{main_tag}】` ── 节拍失衡点：`{step}`",
        f"- **病根事实**：{detail}",
        "",
        "### 五维分项得分与体检",
        "| 评估维度 | 得分 / 满分 | 健康度状态 | 核心过程指标实绩 |",
        "| :--- | :---: | :---: | :--- |",
        f"| **链路闭环** | **{s_chain:.0f}** / 25' | {dim_status(s_chain, 25)} | 有效人数: {metrics.get('有效参与人数')}人, 人均吞吐: {metrics.get('人均需求吞吐量')}, 人均缺陷关闭: {metrics.get('人均缺陷关闭量')} |",
        f"| **交付闭环** | **{s_deliv:.0f}** / 15' | {dim_status(s_deliv, 15)} | 应发布需求: {metrics.get('应发布需求数')}, 有效发布: {metrics.get('有效发布需求数')}, 发布总量: {metrics.get('发布总量')} |",
        f"| **时效节奏** | **{s_time:.0f}** / 20' | {dim_status(s_time, 20)} | 需求在途: {metrics.get('需求在途时长')}天, 需求开发周期: {metrics.get('需求开发周期')}天, 积压率: {float(metrics.get('积压需求占比',0))*100:.1f}% |",
        f"| **颗粒度对齐** | **{s_grain:.0f}** / 20' | {dim_status(s_grain, 20)} | 需求交付周期: {metrics.get('需求交付周期')}天, 需求总量: {metrics.get('需求总量')}个 |",
        f"| **质量敏锐度** | **{s_qual:.0f}** / 20' | {dim_status(s_qual, 20)} | 严重缺陷占比: {float(metrics.get('严重缺陷占比',0))*100:.1f}%, 缺陷关闭周期: {metrics.get('缺陷关闭周期')}天, 线上Bug: {metrics.get('线上缺陷数量')}个 |",
        "",
        "### 当前优先治理动作" if rdhs_cur < 70 else "### 稳定性关注事项",
    ]

    actions = []
    if float(metrics.get("人均需求吞吐量") or 0) == 0:
        actions.append("**立即推进在途需求验收**：清点实际已开发完成但卡在转测/验收节点的需求卡片，在飞书项目中流转闭环，破除人均吞吐为 0。")
    if float(metrics.get("积压需求占比") or 0) > 0.3 or float(metrics.get("需求在途时长") or 0) > 60:
        actions.append("**清理超期积压僵尸需求**：对在途超 60 天以上的不做需求进行取消、归档或缩期结项，消除积压扣分。")
    if s_deliv < 10:
        actions.append("**发版挂载发布计划**：后续版本上线通过飞书项目【发布计划】关联上线需求，直接解锁交付闭环 15 分。")
    if not actions:
        actions.append("**保持当前研发节拍**：监控严重缺陷比例，保持迭代定期发版。")

    lines.extend(f"{index}. {action}" for index, action in enumerate(actions, 1))
    return "\n".join(lines)

def main():
    parser = argparse.ArgumentParser(description="RDHS 产研健康度极速查询与诊断")
    scope = parser.add_mutually_exclusive_group(required=True)
    scope.add_argument("--product", "-p", help="按产品名称精确或模糊查询")
    scope.add_argument("--business-line", "-b", help="按一级或二级业务线名称筛选")
    scope.add_argument("--all", "-a", action="store_true", help="输出消费者 BG 整体健康度")
    parser.add_argument("--compare", "-c", action="store_true", help="对比上月产品 RDHS")
    parser.add_argument("--trend", action="store_true", help="追加一级业务线或消费者 BG 月度趋势")
    parser.add_argument("--cache-ttl", type=int, default=CACHE_TTL, help="缓存过期时间(秒)，默认 0 (实时直连)")
    parser.add_argument("--refresh", "-r", action="store_true", help="强制穿透缓存直连拉取最新数据")
    parser.add_argument("--format", "-f", choices=["markdown", "json"], default="markdown", help="输出格式")
    args = parser.parse_args()

    master = get_product_master(ttl=args.cache_ttl, refresh=args.refresh)
    cur_qt, cur_rows = get_chart_data(CURRENT_CHART_ID, ttl=args.cache_ttl, refresh=args.refresh)
    cur_prods = parse_chart_rows(cur_qt, cur_rows, master)

    last_prods: Dict[str, Dict[str, Any]] = {}
    if args.compare:
        try:
            last_qt, last_rows = get_chart_data(LAST_CHART_ID, ttl=args.cache_ttl, refresh=args.refresh)
            last_prods = parse_chart_rows(last_qt, last_rows, master)
        except Exception as e:
            sys.stderr.write(f"Warning: Failed to fetch baseline chart: {e}\n")

    matched: List[Tuple[str, Optional[Dict[str, Any]], Optional[Dict[str, Any]], Optional[Dict[str, Any]]]] = []
    all_pnames = sorted(set(master) | set(cur_prods))
    if args.product and args.product in all_pnames:
        all_pnames = [args.product]
    for pname in all_pnames:
        minfo = master.get(pname)
        current = cur_prods.get(pname)
        path = minfo.get("business_path", current["business_line_chart"] if current else "") if minfo else (current["business_line_chart"] if current else "")
        if args.product:
            if args.product.lower() in pname.lower():
                matched.append((pname, current, last_prods.get(pname), minfo))
        elif is_eligible_product(minfo) and (args.all or args.business_line.lower() in path.lower()):
            matched.append((pname, current, last_prods.get(pname), minfo))

    if not matched:
        print(f"未找到与 '{args.product or args.business_line or '消费者BG'}' 相关的度量数据。")
        return

    trend_sections: List[Tuple[str, List[Dict[str, Any]]]] = []
    if args.trend and args.all:
        trend_qt, trend_rows = get_chart_data(BG_TREND_CHART_ID, ttl=args.cache_ttl, refresh=args.refresh)
        trend_sections.append(("消费者 BG ", parse_trend_rows(trend_qt, trend_rows)))
    elif args.trend and args.business_line:
        paths = sorted({item[3]["business_path"] for item in matched if item[3]})
        top_lines = sorted({path.split("/")[0] for path in paths})
        secondary_names = {path.split("/", 1)[1] for path in paths if "/" in path}
        resolved_secondary = next(iter(secondary_names)) if len(secondary_names) == 1 else None
        if resolved_secondary and args.business_line.lower() in resolved_secondary.lower():
            trend_qt, trend_rows = get_chart_data(SECONDARY_LINE_TREND_CHART_ID, ttl=args.cache_ttl, refresh=args.refresh)
            trend_sections = [
                (
                    f"【{top_line}/{resolved_secondary}】",
                    parse_trend_rows(trend_qt, trend_rows, top_line, resolved_secondary),
                )
                for top_line in top_lines
            ]
        else:
            trend_qt, trend_rows = get_chart_data(LINE_TREND_CHART_ID, ttl=args.cache_ttl, refresh=args.refresh)
            trend_sections = [
                (f"【{top_line}】", parse_trend_rows(trend_qt, trend_rows, top_line))
                for top_line in top_lines
            ]

    if args.format == "json":
        result = {
            "scope": args.product or args.business_line or "消费者BG",
            "summary": None if args.product else summarize_scope(matched),
            "products": [
                {"product_name": pname, "current": current, "last": last, "master": minfo}
                for pname, current, last, minfo in matched
            ],
            "trends": [
                {"title": title, "judgement": format_trend_judgement(rows), "rows": rows}
                for title, rows in trend_sections
            ],
        }
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return

    if args.product and len(matched) == 1:
        pname, current, last, minfo = matched[0]
        print(format_product_report(pname, current, last, minfo))
    elif args.product:
        print(format_product_candidates(args.product, matched))
    else:
        title = f"【{args.business_line}】" if args.business_line else "消费者 BG"
        print(format_scope_summary(title, matched, args.compare))
        if args.all:
            print("\n\n" + format_business_line_summary(matched))
        print("\n\n" + format_governance_entries(matched))

    if not args.product:
        if trend_sections:
            print("\n\n" + "\n\n".join(format_trend_report(title, rows) for title, rows in trend_sections))
        print("\n\n" + format_full_leaderboard(matched))

if __name__ == "__main__":
    main()
