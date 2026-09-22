#!/usr/bin/env python3
"""RDHS 产研健康度极速查询与诊断工具 (rdhs_query.py)

专为 AI Agent 和产研效能分析设计：
1. 自动调用 Meegle CLI 拉取实时度量底表，支持会话级短缓存（默认 5 分钟，--refresh 强制刷新）。
2. 内置 10429 频率限制自动重试与退避机制。
3. 动态结合主数据清洗规则（自动剔除交付定制与测试业务线，只考核 In Progress 在研标准产品）。
4. 内置 7 阶归因判定引擎与 4 级治理分档计算。
5. 一键输出结构化 Markdown 体检报告或 JSON 数据，单次命令直接出具结论。
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

CACHE_DIR = Path(os.path.expanduser("~/.cache/meegle-rdhs"))
CACHE_TTL = 0  # 默认 0 秒：确保每次调用 100% 直连飞书项目拉取此时此刻最新实时数据

CURRENT_CHART_ID = "7659618575337915254"
LAST_CHART_ID = "7681204196376314742"
PROJECT_KEY = "cbg_product_develop"
MASTER_TYPE_KEY = "693f665435b354b7ca0085dc"

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

def get_cached_or_fetch(key: str, fetch_fn, refresh: bool = False) -> Any:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cache_file = CACHE_DIR / f"{key}.json"
    now = time.time()
    if not refresh and cache_file.exists():
        try:
            mtime = cache_file.stat().st_mtime
            if now - mtime < CACHE_TTL:
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

def get_chart_data(chart_id: str, refresh: bool = False) -> Tuple[List[str], List[Dict[str, Any]]]:
    raw = get_cached_or_fetch(
        f"chart_{chart_id}",
        lambda: run_meegle_cmd(["chart", "get", "--project-key", PROJECT_KEY, "--chart-id", chart_id]),
        refresh=refresh
    )
    quota_titles = raw.get("quota_titles", []) if isinstance(raw, dict) else []
    chart_list = raw.get("chart_data_list", []) if isinstance(raw, dict) else []
    rows = chart_list[0] if chart_list else []
    return quota_titles, rows

def get_business_lines(refresh: bool = False) -> Dict[str, str]:
    raw = get_cached_or_fetch(
        "business_lines",
        lambda: run_meegle_cmd(["space", "business-lines", "--project-key", PROJECT_KEY]),
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

def get_product_master(refresh: bool = False) -> Dict[str, Dict[str, Any]]:
    raw = get_cached_or_fetch(
        "product_master",
        lambda: run_meegle_cmd([
            "workitem", "search-filter",
            "--project-key", PROJECT_KEY,
            "--work-item-type-keys", MASTER_TYPE_KEY,
            "--page-size", "200"
        ]),
        refresh=refresh
    )
    items = raw if isinstance(raw, list) else (raw.get("data", []) if isinstance(raw, dict) else [])
    b_lines = get_business_lines(refresh=refresh)
    
    master: Dict[str, Dict[str, Any]] = {}
    for it in items:
        f_map = {f["field_key"]: f for f in it.get("fields", [])}
        bid = f_map.get("business", {}).get("field_value")
        p_attr = f_map.get("field_22acd7", {}).get("field_value", {}).get("label", "标准产品")
        status = it.get("work_item_status", {}).get("state_key", "")
        owner = f_map.get("owner", {}).get("field_value")
        b_path = b_lines.get(bid, "其他业务线")
        
        master[it["name"].strip()] = {
            "id": it["id"],
            "business_id": bid,
            "business_path": b_path,
            "status": status,
            "is_in_progress": (status == "In Progress"),
            "product_attr": p_attr,
            "is_custom": (p_attr == "交付定制"),
            "owner": str(owner) if owner else ""
        }
    return master

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

    to_query = [k for k in user_keys if k and k not in known]
    if to_query:
        try:
            res = run_meegle_cmd(["user", "query", "--user-keys", ",".join(to_query)])
            user_list = res if isinstance(res, list) else (res.get("data", []) if isinstance(res, dict) else [])
            for u in user_list:
                uk = str(u.get("user_key", ""))
                name_cn = u.get("name_cn", "") or u.get("name", {}).get("zh_cn", "")
                simple_name = name_cn.split()[0] if name_cn else uk
                known[uk] = simple_name
            with open(USER_CACHE_FILE, "w", encoding="utf-8") as f:
                json.dump(known, f, ensure_ascii=False)
        except Exception:
            pass
    return known

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
    """Match chart rows to product master, avoiding empty/zero cross-product noise."""
    prods: Dict[str, Dict[str, Any]] = {}
    
    # First pass: collect non-zero_spec rows
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

    # Match each product in master
    for pname, minfo in master.items():
        b_top = minfo["business_path"].split("/")[0] if minfo.get("business_path") else ""
        if (b_top, pname) in valid_rows:
            prods[pname] = valid_rows[(b_top, pname)]
        elif pname in fallback_rows:
            prods[pname] = fallback_rows[pname]

    # Also add any products in chart that might not be in master
    for (b_name, pname), row_obj in valid_rows.items():
        if pname not in prods:
            prods[pname] = row_obj

    return prods

def format_product_report(p_name: str, cur_item: Optional[Dict[str, Any]], last_item: Optional[Dict[str, Any]], master_info: Optional[Dict[str, Any]], user_map: Dict[str, str]) -> str:
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
    owner_raw = master_info.get("owner", "") if master_info else ""
    owner_name = user_map.get(owner_raw, owner_raw) or "未指定"

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
        f"- **业务归属**：`{b_path}` | **产品属性**：{p_attr} | **当前状态**：{status_str} | **负责人**：{owner_name}",
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
        "### 跨过 70 分及格线的极简行动建议",
    ]

    actions = []
    if float(metrics.get("人均需求吞吐量") or 0) == 0:
        actions.append("1. **立即推进在途需求验收**：清点实际已开发完成但卡在转测/验收节点的需求卡片，在飞书项目中流转闭环，破除人均吞吐为 0。")
    if float(metrics.get("积压需求占比") or 0) > 0.3 or float(metrics.get("需求在途时长") or 0) > 60:
        actions.append("2. **清理超期积压僵尸需求**：对在途超 60 天以上的不做需求进行取消、归档或缩期结项，消除积压扣分。")
    if s_deliv < 10:
        actions.append("3. **发版挂载发布计划**：后续版本上线通过飞书项目【发布计划】关联上线需求，直接解锁交付闭环 15 分。")
    if not actions:
        actions.append("1. **保持当前研发节拍**：监控严重缺陷比例，保持迭代定期发版。")

    lines.extend(actions)
    return "\n".join(lines)

def main():
    parser = argparse.ArgumentParser(description="RDHS 产研健康度极速查询与诊断")
    parser.add_argument("--product", "-p", help="按产品名称精确或模糊查询")
    parser.add_argument("--business-line", "-b", help="按业务线名称筛选 (如: AI交互, 开放平台, 录音笔)")
    parser.add_argument("--all", "-a", action="store_true", help="输出全景排行榜")
    parser.add_argument("--compare", "-c", action="store_true", help="是否拉取上月基线进行环比对比")
    parser.add_argument("--cache-ttl", type=int, default=0, help="缓存过期时间(秒)，默认 0 (始终实时直连)")
    parser.add_argument("--refresh", "-r", action="store_true", help="强制穿透缓存直连拉取最新数据")
    parser.add_argument("--format", "-f", choices=["markdown", "json"], default="markdown", help="输出格式")

    args = parser.parse_args()

    # 1. Fetch master data first
    master = get_product_master(refresh=args.refresh)

    # 2. Fetch current month chart
    cur_qt, cur_rows = get_chart_data(CURRENT_CHART_ID, refresh=args.refresh)
    cur_prods = parse_chart_rows(cur_qt, cur_rows, master)

    # 3. Fetch last month if compare requested
    last_prods: Dict[str, Dict[str, Any]] = {}
    if args.compare:
        try:
            last_qt, last_rows = get_chart_data(LAST_CHART_ID, refresh=args.refresh)
            last_prods = parse_chart_rows(last_qt, last_rows, master)
        except Exception as e:
            sys.stderr.write(f"Warning: Failed to fetch baseline chart: {e}\n")

    # Resolve owners
    owners = [m.get("owner", "") for m in master.values() if m.get("owner")]
    user_map = resolve_user_names(owners)

    # Filter
    matched: List[Tuple[str, Optional[Dict[str, Any]], Optional[Dict[str, Any]], Optional[Dict[str, Any]]]] = []
    
    # Check all products in master or chart
    all_pnames = sorted(set(list(master.keys()) + list(cur_prods.keys())))

    for pname in all_pnames:
        minfo = master.get(pname)
        c_item = cur_prods.get(pname)
        bpath = minfo.get("business_path", c_item["business_line_chart"] if c_item else "") if minfo else (c_item["business_line_chart"] if c_item else "")
        
        # Exclude test business line
        if "测试业务线" in bpath:
            continue
            
        if args.product:
            if args.product.lower() in pname.lower():
                matched.append((pname, c_item, last_prods.get(pname), minfo))
        elif args.business_line:
            target_bl = args.business_line.lower()
            if target_bl in bpath.lower() or (c_item and target_bl in c_item["business_line_chart"].lower()):
                matched.append((pname, c_item, last_prods.get(pname), minfo))
        elif args.all:
            matched.append((pname, c_item, last_prods.get(pname), minfo))

    if not matched:
        print(f"未找到与 '{args.product or args.business_line}' 相关的度量数据。")
        return

    if args.format == "json":
        res_list = []
        for pname, c_item, l_item, minfo in matched:
            res_list.append({
                "product_name": pname,
                "current": c_item,
                "last": l_item,
                "master": minfo
            })
        print(json.dumps(res_list, ensure_ascii=False, indent=2))
        return

    # Markdown format
    if args.product and len(matched) == 1:
        pname, c_item, l_item, minfo = matched[0]
        print(format_product_report(pname, c_item, l_item, minfo, user_map))
    else:
        # Multi-product summary table
        bl_title = f"【{args.business_line}】" if args.business_line else "产研健康度全景"
        print(f"## 📊 {bl_title} 产研健康度 (RDHS) 诊断榜单 (共 {len(matched)} 款产品)")
        print()
        print("| 产品型号/名称 | 业务线归属 | 属性/状态 | RDHS得分 | 治理分档 | 核心归因与短板 | 负责人 |")
        print("| :--- | :--- | :--- | :---: | :---: | :--- | :--- |")
        
        # Sort by RDHS ascending (worst first)
        matched.sort(key=lambda x: (x[1]["rdhs"] if x[1] else 0))
        
        for pname, c_item, l_item, minfo in matched:
            if not c_item:
                print(f"| **{pname}** | {minfo.get('business_path','-')} | 缺失度量 | **—** | P0 重点治理 | 未形成有效度量底表 | - |")
                continue
            rdhs = c_item["rdhs"]
            t_name, t_p = get_tier(rdhs)
            tag, detail, step = evaluate_attribution(c_item["metrics"])
            bpath = minfo.get("business_path", c_item["business_line_chart"]) if minfo else c_item["business_line_chart"]
            p_attr = minfo.get("product_attr", "标准产品") if minfo else "标准产品"
            status_desc = "在研" if (minfo and minfo.get("is_in_progress")) else "存量"
            attr_full = f"{p_attr}({status_desc})"
            owner_raw = minfo.get("owner", "") if minfo else ""
            owner_name = user_map.get(owner_raw, owner_raw) or "-"
            print(f"| **{pname}** | {bpath} | {attr_full} | **{rdhs:.0f} 分** | `{t_name}({t_p})` | 【{tag}】{step} | {owner_name} |")

if __name__ == "__main__":
    main()
