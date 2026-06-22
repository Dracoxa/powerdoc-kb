from __future__ import annotations

import base64
import io
import json
import math
import re
import time
import zipfile
from collections import Counter
from dataclasses import dataclass
from datetime import datetime
from html import escape
from pathlib import Path
from typing import Any
from xml.etree import ElementTree

import streamlit as st


APP_TITLE = "PowerDoc-KB"
SCHEMA_VERSION = "0.1.0"
ASSET_DIR = Path(__file__).resolve().parent / "assets"
ORBIT_LOOP_PATH = ASSET_DIR / "orbit-view-loop.webp"
ORBIT_VIDEO_PATH = ASSET_DIR / "orbit-background-2x-crossfade.mp4"

SYSTEM_SECTION_RULES = [
    ("mission_function", r"(任务和功能|任务需求|功能定义|功能分类|功能描述)"),
    ("orbit_environment", r"(轨道|环境|入轨高度|运行轨道|轨道周期|光照|阴影|地影|受晒因子)"),
    ("electrical_indicators", r"(电气技术指标|输出功率|母线电压|母线品质|火工品母线|抗扰|纹波|阶跃负载)"),
    ("topology_scheme", r"(拓扑方案|拓扑架构|光伏电源系统|功率通道|母线全调节|S3R|分流调节|放电调节)"),
    ("solar_array", r"(太阳电池翼|太阳电池阵|太阳翼|对日定向|展开|收拢|阵面面积|三结砷化镓)"),
    ("battery_energy_storage", r"(蓄电池|储能电池|锂离子|DOD|放电深度|循环寿命|深充放|恒流|恒压)"),
    ("control_equipment", r"(控制设备|电源管理器|分流调节器|充放电调节器|母线滤波器|驱动控制器|配电系统)"),
    ("reliability_maintenance", r"(可靠性|安全性|维修性|可测试性|在轨维修|寿命|故障|FMEA)"),
    ("mechanical_constraints", r"(重量|基频|共振|剩磁矩|磁干扰|外形尺寸|姿态控制|对接)"),
    ("document_deliverables", r"(研试文件|设计文件|设计报告|任务书|说明书|分析报告|文件名称)"),
]

SYSTEM_SECTION_LABELS = {
    "mission_function": "任务与功能",
    "orbit_environment": "轨道与环境边界",
    "electrical_indicators": "主要电气指标",
    "topology_scheme": "电源系统拓扑方案",
    "solar_array": "太阳电池翼与发电单元",
    "battery_energy_storage": "蓄电池与储能单元",
    "control_equipment": "控制设备与功率调节",
    "reliability_maintenance": "可靠性、安全性与在轨维修",
    "mechanical_constraints": "机械、磁与重量约束",
    "document_deliverables": "研试文件与设计交付物",
    "unclassified": "未归类条目",
}

TOPOLOGY_FEATURES = {
    "power_source": (r"(光伏电源系统|太阳电池翼|太阳电池阵|太阳翼)", "光伏电源系统 / 太阳电池翼发电"),
    "distribution_architecture": (r"(多功率通道|两个功率通道|功率通道相对独立|独立母线)", "多功率通道、通道相对独立"),
    "primary_bus": (r"(一次母线全调节|母线全调节|全调节方式|母线电压稳定)", "一次母线全调节"),
    "sunlight_control": (r"(S3R|顺序开关分流调节|分流调节)", "光照区 S3R 分流调节"),
    "eclipse_control": (r"(放电调节采用升压|升压控制调节|阴影区)", "阴影区储能电池升压放电调节"),
    "battery_charging": (r"(恒流转恒压|恒流|恒压充电)", "锂离子蓄电池恒流转恒压充电"),
    "solar_tracking": (r"(双自由度对日定向|对日定向系统|实时跟踪太阳)", "双自由度对日定向"),
}

TOPOLOGY_PATTERNS = {
    "buck_converter": r"\b(buck|step[-\s]?down|降压)\b",
    "boost_converter": r"\b(boost|step[-\s]?up|升压)\b",
    "buck_boost_converter": r"\b(buck[-\s]?boost|升降压)\b",
    "flyback_converter": r"\b(flyback|反激)\b",
    "forward_converter": r"\b(forward converter|正激)\b",
    "half_bridge": r"\b(half[-\s]?bridge|半桥)\b",
    "full_bridge": r"\b(full[-\s]?bridge|全桥)\b",
    "llc_resonant": r"\b(LLC|resonant converter|谐振)\b",
    "pfc": r"\b(PFC|power factor correction|功率因数校正)\b",
    "ldo": r"\b(LDO|low dropout|低压差)\b",
    "photovoltaic_power_system": r"(光伏电源系统|太阳电池翼|太阳电池阵|太阳翼)",
    "regulated_primary_bus": r"(一次母线全调节|母线全调节|全调节方式|母线电压稳定)",
    "s3r_shunt_regulator": r"(S3R|Sequential Switching Shunt Regulator|顺序开关分流调节|分流调节)",
    "boost_discharge_regulator": r"(放电调节采用升压|升压控制调节|放电调节)",
    "cc_cv_charging": r"(恒流转恒压|恒压充电|充电控制模式)",
    "multi_channel_power": r"(多功率通道|功率通道|多机组配置|独立母线)",
    "dual_axis_solar_tracking": r"(双自由度对日定向|对日定向系统|太阳翼实时跟踪)",
}

COMPONENT_PATTERNS = {
    "controller": r"\b(controller|PWM controller|控制器|控制芯片)\b",
    "mosfet": r"\b(MOSFET|FET|switching transistor|开关管)\b",
    "diode": r"\b(diode|Schottky|二极管|肖特基)\b",
    "inductor": r"\b(inductor|choke|电感)\b",
    "transformer": r"\b(transformer|变压器)\b",
    "input_capacitor": r"\b(input capacitor|Cin|输入电容)\b",
    "output_capacitor": r"\b(output capacitor|Cout|输出电容)\b",
    "current_sense": r"\b(current sense|sense resistor|电流检测|采样电阻)\b",
    "gate_driver": r"\b(gate driver|driver|栅极驱动|驱动器)\b",
    "snubber": r"\b(snubber|RC clamp|RCD clamp|吸收|钳位)\b",
    "solar_array": r"(太阳电池翼|太阳电池阵|太阳翼|太阳电池片)",
    "battery_pack": r"(蓄电池组|储能电池|锂离子蓄电池|电池组)",
    "shunt_regulator": r"(分流调节器|分流调节|S3R)",
    "charge_discharge_regulator": r"(充放电调节器|充电调节|放电调节)",
    "bus_filter": r"(母线滤波器|滤波器)",
    "power_management_unit": r"(电源管理器|配电系统|功率调配)",
    "solar_drive_controller": r"(驱动控制器|驱动机构|对日定向装置)",
    "pyro_bus": r"(火工品母线|火工品)",
}

RULE_CATEGORIES = {
    "layout": r"\b(layout|PCB|placement|place|route|trace|loop|ground|return path|布局|走线|接地|回路)\b",
    "emi": r"\b(EMI|EMC|noise|radiated|conducted|filter|shield|噪声|滤波|电磁)\b",
    "thermal": r"\b(thermal|temperature|heat|junction|derating|散热|温升|结温|降额)\b",
    "protection": r"\b(OCP|OVP|UVLO|short circuit|soft[-\s]?start|current limit|保护|限流|短路|软启动)\b",
    "component_selection": r"\b(select|selection|choose|rating|saturation|ESR|ripple current|选型|额定|饱和|纹波电流)\b",
    "troubleshooting": r"\b(failure|unstable|oscillation|ringing|overshoot|debug|troubleshoot|振荡|过冲|调试|故障)\b",
    "system_topology": r"(拓扑|架构|功率通道|机组|独立母线|配电系统|全调节|分流调节|放电调节)",
    "bus_regulation": r"(母线电压|一次母线|火工品母线|电压控制|稳定在|电压扰动|恢复时间)",
    "power_capacity": r"(输出功率|功耗|供电需求|发电功率|功率密度|比能量|能量平衡)",
    "orbit_environment": r"(轨道|入轨高度|运行轨道|轨道周期|光照|阴影|地影|受晒因子|太阳高度角)",
    "solar_array": r"(太阳电池翼|太阳电池阵|太阳翼|对日定向|展开|收拢|阵面面积|三结砷化镓)",
    "energy_storage": r"(蓄电池|储能电池|DOD|放电深度|循环寿命|深充放|恒流|恒压)",
    "power_quality": r"(母线品质|纹波|峰峰值|阶跃负载|抗扰|浪涌|跃变)",
    "reliability_maintenance": r"(可靠性|安全性|寿命|长寿命|在轨维修|故障|FMEA|可维修性|可测试性)",
    "mechanical_constraint": r"(基频|共振|姿态控制|对接|剩磁矩|磁干扰|外形尺寸|重量)",
    "document_requirement": r"(研试文件|设计文件|设计报告|任务书|技术说明书|使用说明书|分析报告)",
}

PARAM_ALIASES = {
    "input_voltage": ["vin", "v_in", "input voltage", "输入电压"],
    "output_voltage": ["vout", "v_out", "output voltage", "输出电压"],
    "output_current": ["iout", "i_out", "load current", "output current", "输出电流"],
    "switching_frequency": ["fsw", "f_sw", "switching frequency", "开关频率"],
    "efficiency": ["efficiency", "效率"],
    "output_ripple": ["ripple voltage", "output ripple", "纹波"],
    "inductance": ["inductance", "inductor value", "电感量"],
    "capacitance": ["capacitance", "capacitor value", "电容量"],
    "power": ["power", "output power", "功率", "输出功率", "功耗"],
    "bus_voltage": ["母线电压", "一次母线", "火工品母线"],
    "orbit_period": ["轨道周期", "周期"],
    "orbit_altitude": ["入轨高度", "运行轨道高度", "轨道高度"],
    "sunlight_duration": ["阳照区", "光照时间", "最短阳照区"],
    "eclipse_duration": ["阴影区", "最长阴影区"],
    "depth_of_discharge": ["DOD", "放电深度"],
    "ripple_voltage": ["纹波", "峰峰值", "p-p"],
    "recovery_time": ["恢复时间"],
    "surge_current": ["浪涌电流", "脉冲电流"],
    "cycle_life": ["循环寿命", "寿命"],
    "frequency": ["基频"],
    "area": ["阵面面积"],
    "efficiency": ["efficiency", "效率", "发电效率"],
}

UNIT_PATTERN = r"(V/ms|A/s|mV|V|A|W|kW|mW|Hz|kHz|MHz|uH|µH|mH|nF|uF|µF|mF|pF|mΩ|mohm|ohm|Ω|%|°C|C|km|m2|m²|s|ms|min|周次|次|年|Am²)"
VALUE_PATTERN = r"(?:[≥≤<>±]\s*)?[-+]?\d+(?:\.\d+)?(?:\s?(?:-|~|～|至|to)\s?(?:[≥≤<>±]\s*)?[-+]?\d+(?:\.\d+)?)?"


@dataclass
class ParsedDocument:
    name: str
    file_type: str
    text: str
    pages: list[str]


def normalize_space(text: str) -> str:
    text = text.replace("\x00", " ")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def read_pdf(data: bytes) -> tuple[str, list[str]]:
    from pypdf import PdfReader

    reader = PdfReader(io.BytesIO(data))
    pages: list[str] = []
    for page in reader.pages:
        pages.append(normalize_space(page.extract_text() or ""))
    return "\n\n".join(pages), pages


def read_docx(data: bytes) -> tuple[str, list[str]]:
    try:
        from docx import Document

        doc = Document(io.BytesIO(data))
        chunks = [paragraph.text for paragraph in doc.paragraphs if paragraph.text.strip()]
        for table in doc.tables:
            for row in table.rows:
                cells = [normalize_space(cell.text.replace("\n", " ")) for cell in row.cells if cell.text.strip()]
                if cells:
                    chunks.append(" | ".join(cells))
        text = normalize_space("\n".join(chunks))
        return text, [text]
    except Exception:
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            xml = archive.read("word/document.xml")
        root = ElementTree.fromstring(xml)
        namespace = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
        chunks = [node.text for node in root.findall(".//w:t", namespace) if node.text]
        text = normalize_space(" ".join(chunks))
        return text, [text]


def read_plain(data: bytes) -> tuple[str, list[str]]:
    for encoding in ("utf-8", "utf-16", "gb18030", "latin-1"):
        try:
            text = data.decode(encoding)
            return normalize_space(text), [normalize_space(text)]
        except UnicodeDecodeError:
            continue
    text = data.decode("utf-8", errors="ignore")
    return normalize_space(text), [normalize_space(text)]


def parse_upload(uploaded_file: Any) -> ParsedDocument:
    data = uploaded_file.getvalue()
    suffix = Path(uploaded_file.name).suffix.lower()
    if suffix == ".pdf":
        text, pages = read_pdf(data)
        file_type = "pdf"
    elif suffix == ".docx":
        text, pages = read_docx(data)
        file_type = "docx"
    else:
        text, pages = read_plain(data)
        file_type = suffix.lstrip(".") or "text"
    return ParsedDocument(
        name=uploaded_file.name,
        file_type=file_type,
        text=normalize_space(text),
        pages=[normalize_space(page) for page in pages],
    )


def split_sentences(text: str) -> list[str]:
    raw = re.split(r"(?<=[。！？.!?])\s+|\n+", text)
    return [item.strip(" -•\t") for item in raw if len(item.strip()) > 12]


def split_table_rows(text: str) -> list[list[str]]:
    rows: list[list[str]] = []
    for line in text.splitlines():
        if "|" not in line:
            continue
        cells = [normalize_space(cell) for cell in line.split("|")]
        cells = [cell for cell in cells if cell and cell not in {"-", "—"}]
        if len(cells) >= 2:
            rows.append(cells)
    return rows


def is_header_row(cells: list[str]) -> bool:
    joined = "".join(cells)
    header_tokens = {
        "功能分类功能描述关键配置/要求",
        "参数项指标数值/描述备注",
        "指标类别具体参数要求工况/约束条件",
        "特性维度指标要求设计意义",
        "序号类别文件名称文件类型",
        "序号类别项目类别备注",
        "项目指标详情",
    }
    return joined in header_tokens or all(not re.search(r"\d|≥|≤|V|W|Hz|DOD|FMEA", cell, flags=re.IGNORECASE) for cell in cells[1:])


def document_blocks(text: str) -> list[str]:
    blocks = []
    for line in text.splitlines():
        item = normalize_space(line)
        if len(item) >= 2:
            blocks.append(item)
    if blocks:
        return blocks
    return split_sentences(text)


def classify_system_section(text: str) -> str:
    for section, pattern in SYSTEM_SECTION_RULES:
        if re.search(pattern, text, flags=re.IGNORECASE):
            return section
    return "unclassified"


def parameter_name_from_label(label: str) -> str:
    label_norm = label.lower()
    for canonical, aliases in PARAM_ALIASES.items():
        if any(alias.lower() in label_norm for alias in aliases):
            return canonical
    cleaned = re.sub(r"[^\w\u4e00-\u9fff]+", "_", label.strip().lower()).strip("_")
    return cleaned[:48] or "parameter"


def source_for_text(pages: list[str], needle: str) -> dict[str, Any]:
    needle_norm = normalize_space(needle)
    for index, page in enumerate(pages, start=1):
        if needle_norm[:80] and needle_norm[:80] in normalize_space(page):
            return {"page": index, "snippet": needle_norm[:420]}
    return {"page": None, "snippet": needle_norm[:420]}


def confidence_from_hits(*hits: bool) -> float:
    base = 0.52 + sum(0.11 for hit in hits if hit)
    return round(min(base, 0.93), 2)


def clean_heading(text: str) -> str:
    text = normalize_space(text)
    text = re.sub(r"^[一二三四五六七八九十]+[、.．]\s*", "", text)
    text = re.sub(r"^\d+[、.．]\s*", "", text)
    return text


def make_source(doc: ParsedDocument, text: str) -> dict[str, Any]:
    return source_for_text(doc.pages, text)


def row_to_metric(cells: list[str], doc: ParsedDocument) -> dict[str, Any] | None:
    if is_header_row(cells):
        return None
    label = clean_heading(cells[0])
    value = "；".join(cells[1:]).strip()
    if not label or not value:
        return None
    section = classify_system_section(" | ".join(cells))
    units = sorted(set(re.findall(UNIT_PATTERN, value, flags=re.IGNORECASE)))
    numeric_values = re.findall(rf"{VALUE_PATTERN}\s*(?:{UNIT_PATTERN})?", value, flags=re.IGNORECASE)
    return {
        "name": label,
        "section": section,
        "value": value,
        "units": units[:6],
        "has_numeric_value": bool(numeric_values),
        "source": make_source(doc, " | ".join(cells)),
    }


def extract_system_sections(doc: ParsedDocument) -> dict[str, list[dict[str, Any]]]:
    sections: dict[str, list[dict[str, Any]]] = {key: [] for key, _ in SYSTEM_SECTION_RULES}
    sections["unclassified"] = []
    seen: set[str] = set()
    for cells in split_table_rows(doc.text):
        if is_header_row(cells):
            continue
        row_text = " | ".join(cells)
        section = classify_system_section(row_text)
        key = re.sub(r"\W+", "", row_text.lower())[:140]
        if key in seen:
            continue
        seen.add(key)
        sections.setdefault(section, []).append(
            {
                "kind": "table_row",
                "title": clean_heading(cells[0]),
                "content": "；".join(cells[1:]) if len(cells) > 1 else row_text,
                "cells": cells,
                "source": make_source(doc, row_text),
            }
        )
    for block in document_blocks(doc.text):
        if "|" in block or len(block) < 18:
            continue
        section = classify_system_section(block)
        if section == "unclassified":
            continue
        key = re.sub(r"\W+", "", block.lower())[:140]
        if key in seen:
            continue
        seen.add(key)
        sections.setdefault(section, []).append(
            {
                "kind": "paragraph",
                "title": clean_heading(block[:34]),
                "content": block,
                "cells": [],
                "source": make_source(doc, block),
            }
        )
    return {section: items for section, items in sections.items() if items}


def extract_structured_metrics(doc: ParsedDocument) -> list[dict[str, Any]]:
    metrics: list[dict[str, Any]] = []
    seen: set[str] = set()
    for cells in split_table_rows(doc.text):
        metric = row_to_metric(cells, doc)
        if not metric:
            continue
        if not metric["has_numeric_value"] and metric["section"] not in {"document_deliverables", "mission_function"}:
            continue
        key = f"{metric['section']}::{metric['name']}::{metric['value']}"
        if key in seen:
            continue
        seen.add(key)
        metrics.append(metric)
    return metrics[:120]


def extract_topology_scheme(doc: ParsedDocument) -> dict[str, Any]:
    features = []
    for feature_id, (pattern, label) in TOPOLOGY_FEATURES.items():
        match = re.search(pattern, doc.text, flags=re.IGNORECASE)
        if not match:
            continue
        start = max(0, match.start() - 140)
        end = min(len(doc.text), match.end() + 180)
        snippet = normalize_space(doc.text[start:end])
        features.append(
            {
                "id": feature_id,
                "label": label,
                "evidence": snippet,
                "source": make_source(doc, snippet),
            }
        )
    return {
        "architecture": " / ".join(feature["label"] for feature in features[:4]) or "未识别",
        "features": features,
        "confidence": confidence_from_hits(bool(features), len(features) >= 3, len(features) >= 5),
    }


def extract_design_constraints(doc: ParsedDocument, metrics: list[dict[str, Any]]) -> list[dict[str, Any]]:
    constraints = []
    for metric in metrics:
        text = f"{metric['name']} {metric['value']}"
        if not re.search(r"(≥|≤|不小于|不大于|范围|约束|要求|稳定|恢复|寿命|满足|支持|保障)", text):
            continue
        constraints.append(
            {
                "category": metric["section"],
                "name": metric["name"],
                "requirement": metric["value"],
                "rationale": infer_constraint_rationale(metric["section"], text),
                "source": metric["source"],
            }
        )
    return constraints[:80]


def infer_constraint_rationale(section: str, text: str) -> str:
    if section == "orbit_environment":
        return "作为发电、储能容量和热/光照边界的输入条件。"
    if section == "electrical_indicators":
        return "约束母线供电能力、电能质量和瞬态响应。"
    if section == "solar_array":
        return "约束太阳翼发电能力、展开机构和姿态跟踪能力。"
    if section == "battery_energy_storage":
        return "约束储能容量、放电深度和寿命裕度。"
    if section == "reliability_maintenance":
        return "约束长寿命任务、故障处理和在轨维护能力。"
    if section == "mechanical_constraints":
        return "约束结构动力学、磁特性和系统重量。"
    if "母线" in text:
        return "约束一次母线和特殊负载母线的稳定供电。"
    return "从原文指标表抽取的设计边界。"


def extract_deliverables(doc: ParsedDocument) -> list[dict[str, Any]]:
    deliverables = []
    for cells in split_table_rows(doc.text):
        row_text = " | ".join(cells)
        if not re.search(RULE_CATEGORIES["document_requirement"], row_text):
            continue
        file_name = cells[1] if len(cells) > 1 else cells[0]
        deliverables.append(
            {
                "category": cells[0],
                "name": file_name,
                "type": cells[2] if len(cells) > 2 else "文件",
                "source": make_source(doc, row_text),
            }
        )
    return deliverables[:80]


def build_power_system_model(doc: ParsedDocument) -> dict[str, Any]:
    sections = extract_system_sections(doc)
    metrics = extract_structured_metrics(doc)
    topology = extract_topology_scheme(doc)
    constraints = extract_design_constraints(doc, metrics)
    deliverables = extract_deliverables(doc)
    section_summary = []
    for section, items in sections.items():
        section_summary.append(
            {
                "id": section,
                "label": SYSTEM_SECTION_LABELS.get(section, section),
                "items": len(items),
                "preview": [item["content"][:120] for item in items[:3]],
            }
        )
    return {
        "schema": "aerospace_power_system.v1",
        "extraction_mode": "schema_driven_rule_v2",
        "sections": sections,
        "section_summary": section_summary,
        "topology_scheme": topology,
        "metrics": metrics,
        "constraints": constraints,
        "deliverables": deliverables,
    }


def extract_topologies(doc: ParsedDocument) -> list[dict[str, Any]]:
    results = []
    for name, pattern in TOPOLOGY_PATTERNS.items():
        matches = list(re.finditer(pattern, doc.text, flags=re.IGNORECASE))
        if matches:
            first = matches[0]
            start = max(0, first.start() - 180)
            end = min(len(doc.text), first.end() + 240)
            snippet = normalize_space(doc.text[start:end])
            source = source_for_text(doc.pages, snippet)
            results.append(
                {
                    "id": name,
                    "label": name.replace("_", " ").title(),
                    "mentions": len(matches),
                    "confidence": confidence_from_hits(len(matches) > 2, True),
                    "source": source,
                }
            )
    return sorted(results, key=lambda item: item["mentions"], reverse=True)


def extract_parameters(doc: ParsedDocument) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str]] = set()
    text = doc.text
    for cells in split_table_rows(text):
        label = cells[0]
        value_text = " ".join(cells[1:])
        if not re.search(r"\d", value_text):
            continue
        for match in re.finditer(rf"(?P<value>{VALUE_PATTERN})\s*(?P<unit>{UNIT_PATTERN})", value_text, flags=re.IGNORECASE):
            canonical = parameter_name_from_label(label)
            value = re.sub(r"\s+", "", match.group("value"))
            unit = match.group("unit")
            key = (canonical, value, unit)
            if key in seen:
                continue
            seen.add(key)
            row_text = " | ".join(cells)
            results.append(
                {
                    "name": canonical,
                    "raw_label": label,
                    "value": value,
                    "unit": unit,
                    "confidence": confidence_from_hits(True, "|" in row_text),
                    "source": source_for_text(doc.pages, row_text),
                }
            )
    for canonical, aliases in PARAM_ALIASES.items():
        alias_pattern = "|".join(re.escape(alias) for alias in aliases)
        patterns = [
            rf"(?P<label>{alias_pattern})\s*[:=]?\s*(?P<value>{VALUE_PATTERN})\s*(?P<unit>{UNIT_PATTERN})",
            rf"(?P<value>{VALUE_PATTERN})\s*(?P<unit>{UNIT_PATTERN})\s+(?P<label>{alias_pattern})",
        ]
        for pattern in patterns:
            for match in re.finditer(pattern, text, flags=re.IGNORECASE):
                label = match.group("label")
                value = re.sub(r"\s+", "", match.group("value"))
                unit = match.group("unit")
                key = (canonical, value, unit)
                if key in seen:
                    continue
                seen.add(key)
                start = max(0, match.start() - 150)
                end = min(len(text), match.end() + 180)
                snippet = normalize_space(text[start:end])
                results.append(
                    {
                        "name": canonical,
                        "raw_label": label,
                        "value": value,
                        "unit": unit,
                        "confidence": confidence_from_hits(True, len(value) > 0),
                        "source": source_for_text(doc.pages, snippet),
                    }
                )
    return results[:80]


def extract_formulas(doc: ParsedDocument) -> list[dict[str, Any]]:
    formulas = []
    formula_pattern = re.compile(
        r"(?P<expr>[A-Za-zΔ∆ηµμ][A-Za-z0-9_Δ∆ηµμ/().\s-]{0,30}\s*=\s*[^。\n;]{4,120})"
    )
    for match in formula_pattern.finditer(doc.text):
        expr = normalize_space(match.group("expr"))
        if len(expr) < 8 or len(re.findall(r"[A-Za-z]", expr)) < 2:
            continue
        variables = sorted(set(re.findall(r"\b[A-Za-z][A-Za-z0-9_]{0,8}\b|[Δ∆][A-Za-z0-9_]+", expr)))
        snippet = normalize_space(doc.text[max(0, match.start() - 160) : min(len(doc.text), match.end() + 180)])
        formulas.append(
            {
                "name": variables[0].lower() if variables else "formula",
                "expression": expr,
                "variables": variables[:12],
                "confidence": confidence_from_hits("=" in expr, any(op in expr for op in ["/", "*", "+", "-"])),
                "source": source_for_text(doc.pages, snippet),
            }
        )
    unique = []
    seen = set()
    for formula in formulas:
        key = formula["expression"].lower()
        if key not in seen:
            seen.add(key)
            unique.append(formula)
    return unique[:60]


def extract_components(doc: ParsedDocument) -> list[dict[str, Any]]:
    components = []
    for component, pattern in COMPONENT_PATTERNS.items():
        matches = list(re.finditer(pattern, doc.text, flags=re.IGNORECASE))
        if not matches:
            continue
        nearby_rules = []
        for sentence in split_sentences(doc.text):
            if re.search(pattern, sentence, flags=re.IGNORECASE) and re.search(
                RULE_CATEGORIES["component_selection"], sentence, flags=re.IGNORECASE
            ):
                nearby_rules.append(sentence[:260])
        first = matches[0]
        snippet = normalize_space(doc.text[max(0, first.start() - 180) : min(len(doc.text), first.end() + 220)])
        components.append(
            {
                "type": component,
                "mentions": len(matches),
                "selection_notes": nearby_rules[:4],
                "confidence": confidence_from_hits(len(matches) > 1, bool(nearby_rules)),
                "source": source_for_text(doc.pages, snippet),
            }
        )
    return sorted(components, key=lambda item: item["mentions"], reverse=True)


def extract_rules(doc: ParsedDocument) -> list[dict[str, Any]]:
    rules = []
    imperative = re.compile(
        r"\b(should|must|keep|place|connect|route|avoid|ensure|use|select|choose|recommend|注意|必须|应|应该|避免|保持|放置|选择|采用|配置|实现|维持|保障|支持|满足|需|要求)\b",
        re.IGNORECASE,
    )
    for cells in split_table_rows(doc.text):
        row_text = " | ".join(cells)
        matched_categories = [
            category
            for category, pattern in RULE_CATEGORIES.items()
            if re.search(pattern, row_text, flags=re.IGNORECASE)
        ]
        if not matched_categories:
            continue
        severity = (
            "high"
            if any(category in matched_categories for category in ["bus_regulation", "power_quality", "protection", "reliability_maintenance"])
            else "medium"
        )
        rules.append(
            {
                "category": matched_categories[0],
                "rule": row_text[:420],
                "severity": severity,
                "confidence": confidence_from_hits(True, len(cells) > 2),
                "source": source_for_text(doc.pages, row_text),
            }
        )
    for sentence in split_sentences(doc.text):
        matched_categories = [
            category
            for category, pattern in RULE_CATEGORIES.items()
            if re.search(pattern, sentence, flags=re.IGNORECASE)
        ]
        if not matched_categories:
            continue
        has_action = bool(imperative.search(sentence))
        if not has_action and len(sentence) > 180:
            continue
        severity = (
            "high"
            if any(category in matched_categories for category in ["layout", "emi", "protection", "bus_regulation", "power_quality", "reliability_maintenance"])
            else "medium"
        )
        rules.append(
            {
                "category": matched_categories[0],
                "rule": sentence[:420],
                "severity": severity,
                "confidence": confidence_from_hits(has_action, len(matched_categories) > 1),
                "source": source_for_text(doc.pages, sentence),
            }
        )
    unique = []
    seen = set()
    for rule in rules:
        key = re.sub(r"\W+", "", rule["rule"].lower())[:120]
        if key and key not in seen:
            seen.add(key)
            unique.append(rule)
    return unique[:120]


def build_summary(doc: ParsedDocument, topologies: list[dict[str, Any]], rules: list[dict[str, Any]]) -> dict[str, Any]:
    words = re.findall(r"[A-Za-z][A-Za-z0-9_-]+|[\u4e00-\u9fff]{2,}", doc.text)
    counter = Counter(word.lower() for word in words if len(word) > 2)
    top_keywords = [word for word, _ in counter.most_common(16)]
    dominant_rules = Counter(rule["category"] for rule in rules).most_common(4)
    return {
        "primary_topology": topologies[0]["id"] if topologies else None,
        "estimated_tokens": math.ceil(len(doc.text) / 4),
        "character_count": len(doc.text),
        "keyword_cloud": top_keywords,
        "dominant_rule_categories": [{"category": category, "count": count} for category, count in dominant_rules],
    }


def extract_knowledge(doc: ParsedDocument) -> dict[str, Any]:
    topologies = extract_topologies(doc)
    parameters = extract_parameters(doc)
    formulas = extract_formulas(doc)
    components = extract_components(doc)
    rules = extract_rules(doc)
    power_system = build_power_system_model(doc)
    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "document": {
            "title": Path(doc.name).stem,
            "filename": doc.name,
            "type": doc.file_type,
            "pages": len(doc.pages),
        },
        "summary": build_summary(doc, topologies, rules),
        "topologies": topologies,
        "parameters": parameters,
        "formulas": formulas,
        "components": components,
        "design_rules": rules,
        "power_system": power_system,
    }


def page_signal_counts(payload: dict[str, Any], page_count: int) -> list[dict[str, int]]:
    rows = [{"page": index, "parameters": 0, "formulas": 0, "rules": 0, "components": 0} for index in range(1, page_count + 1)]
    buckets = [
        ("parameters", payload["parameters"]),
        ("formulas", payload["formulas"]),
        ("rules", payload["design_rules"]),
        ("components", payload["components"]),
    ]
    for key, items in buckets:
        for item in items:
            page = item.get("source", {}).get("page")
            if isinstance(page, int) and 1 <= page <= page_count:
                rows[page - 1][key] += 1
    return rows


def asset_data_url(path: Path, mime_type: str) -> str:
    if not path.exists():
        return ""
    encoded = base64.b64encode(path.read_bytes()).decode("ascii")
    return f"data:{mime_type};base64,{encoded}"


def render_metric(label: str, value: Any) -> None:
    st.markdown(
        f"""
        <div class="metric-tile">
          <span>{escape(str(label))}</span>
          <strong>{escape(str(value))}</strong>
        </div>
        """,
        unsafe_allow_html=True,
    )


def section_label(title: str, caption: str | None = None) -> None:
    caption_html = f"<p>{escape(caption)}</p>" if caption else ""
    st.markdown(
        f"""
        <div class="section-label">
          <h2>{escape(title)}</h2>
          {caption_html}
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_empty_state() -> None:
    st.markdown(
        """
        <div class="empty-workbench">
          <div>
            <span class="system-kicker">Ready for extraction</span>
            <h2>Drop in an aerospace power document.</h2>
            <p>PowerDoc-KB will turn system-level design text into topology, metrics, constraints, deliverables, and traceable JSON.</p>
          </div>
          <div class="empty-grid">
            <div><strong>1</strong><span>Upload PDF or DOCX</span></div>
            <div><strong>2</strong><span>Build aerospace power schema</span></div>
            <div><strong>3</strong><span>Review system sections</span></div>
            <div><strong>4</strong><span>Export knowledge JSON</span></div>
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_source(source: dict[str, Any]) -> str:
    page = source.get("page")
    page_text = f"Page {page}" if page else "Source"
    snippet = escape(source.get("snippet") or "")
    return f"<details><summary>{page_text}</summary><p>{snippet}</p></details>"


def card(title: str, body: str, meta: str = "") -> None:
    st.markdown(
        f"""
        <div class="kb-card">
          <div class="kb-card-title">{escape(title)}</div>
          <div class="kb-card-body">{body}</div>
          <div class="kb-card-meta">{meta}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def code_panel(text: str, max_height: int = 560) -> None:
    st.markdown(
        f"""
        <div class="code-panel" style="max-height:{max_height}px;"><pre><code>{escape(text)}</code></pre></div>
        """,
        unsafe_allow_html=True,
    )


def render_dark_table(headers: list[str], rows: list[list[Any]]) -> None:
    head_html = "".join(f"<th>{escape(header)}</th>" for header in headers)
    body_html = "".join(
        "<tr>" + "".join(f"<td>{escape('' if value is None else str(value))}</td>" for value in row) + "</tr>"
        for row in rows
    )
    st.markdown(
        f"""
        <div class="table-shell">
          <table class="dark-table">
            <thead><tr>{head_html}</tr></thead>
            <tbody>{body_html}</tbody>
          </table>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_parse_visualization(payload: dict[str, Any], doc: ParsedDocument) -> None:
    section_label("解析流水线", "从文件解析到 JSON 生成的处理链路，节点数量会随文档内容变化。")
    total_items = (
        len(payload["parameters"])
        + len(payload["formulas"])
        + len(payload["components"])
        + len(payload["design_rules"])
        + len(payload["topologies"])
    )
    pipeline = [
        ("01", "Document ingest", f"{payload['document']['pages']} pages"),
        ("02", "Text segmentation", f"{len(split_sentences(doc.text))} segments"),
        ("03", "Signal extraction", f"{total_items} items"),
        ("04", "Source binding", "page snippets"),
        ("05", "JSON assembly", payload["schema_version"]),
    ]
    st.markdown('<div class="flow-lane-wrap">', unsafe_allow_html=True)
    for column, (index, title, detail) in zip(st.columns(len(pipeline)), pipeline):
        with column:
            st.markdown(
                f"""
                <div class="flow-step">
                  <span>{escape(index)}</span>
                  <strong>{escape(title)}</strong>
                  <small>{escape(detail)}</small>
                </div>
                """,
                unsafe_allow_html=True,
            )
    st.markdown("</div>", unsafe_allow_html=True)

    section_label("文档页热力图", "颜色越深代表该页被抽取到的参数、公式、器件或规则越多。")
    page_rows = page_signal_counts(payload, max(len(doc.pages), 1))
    max_signal = max([sum(row[key] for key in ["parameters", "formulas", "rules", "components"]) for row in page_rows] + [1])
    heat_html = ""
    for row in page_rows[:80]:
        signal = sum(row[key] for key in ["parameters", "formulas", "rules", "components"])
        level = signal / max_signal
        heat_html += (
            f'<div class="page-cell" style="--level:{level:.2f}" '
            f'title="Page {row["page"]}: {signal} extracted signals">'
            f'<span>{row["page"]}</span><strong>{signal}</strong></div>'
        )
    st.markdown(f'<div class="page-heatmap">{heat_html}</div>', unsafe_allow_html=True)

    left, right = st.columns([1, 1])
    with left:
        section_label("规则分类分布")
        category_counts = Counter(rule["category"] for rule in payload["design_rules"])
        max_count = max(category_counts.values(), default=1)
        bars = ""
        for category, count in category_counts.most_common():
            width = max(8, round(count / max_count * 100))
            bars += (
                f'<div class="signal-bar"><div><span>{escape(category)}</span><strong>{count}</strong></div>'
                f'<i style="width:{width}%"></i></div>'
            )
        if not bars:
            bars = '<div class="empty-note">No rule categories detected.</div>'
        st.markdown(f'<div class="bar-panel">{bars}</div>', unsafe_allow_html=True)
    with right:
        section_label("知识节点网络")
        nodes = [
            ("Topologies", len(payload["topologies"])),
            ("Parameters", len(payload["parameters"])),
            ("Formulas", len(payload["formulas"])),
            ("Components", len(payload["components"])),
            ("Design Rules", len(payload["design_rules"])),
            ("JSON", total_items),
        ]
        max_node = max([value for _, value in nodes] + [1])
        node_html = ""
        for label, value in nodes:
            scale = 0.72 + (value / max_node) * 0.38
            node_html += (
                f'<div class="knowledge-node" style="--scale:{scale:.2f}">'
                f'<strong>{value}</strong><span>{escape(label)}</span></div>'
            )
        st.markdown(f'<div class="node-map">{node_html}</div>', unsafe_allow_html=True)


def inject_css() -> None:
    css = """
        <style>
          :root {
            --pd-bg: #030814;
            --pd-surface: rgba(7, 18, 34, .82);
            --pd-surface-muted: rgba(13, 34, 58, .72);
            --pd-ink: #ecf8ff;
            --pd-muted: #8ea8ba;
            --pd-line: rgba(119, 217, 255, .22);
            --pd-accent: #2ee6ff;
            --pd-accent-dark: #7df3ff;
            --pd-green: #ffb84d;
            --pd-radius: 8px;
          }
          .stApp {
            background:
              radial-gradient(circle at 18% 18%, rgba(46, 230, 255, .18), transparent 30%),
              radial-gradient(circle at 78% 10%, rgba(255, 184, 77, .12), transparent 26%),
              radial-gradient(circle at 64% 74%, rgba(62, 92, 255, .12), transparent 32%),
              linear-gradient(180deg, #06101f 0%, #030814 52%, #01040b 100%);
            color: var(--pd-ink);
            font-family: ui-sans-serif, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
          }
          .stApp::before {
            content: "";
            position: fixed;
            inset: 0;
            z-index: 0;
            pointer-events: none;
            background:
              radial-gradient(circle, rgba(255,255,255,.72) 0 1px, transparent 1.6px) 0 0 / 96px 96px,
              radial-gradient(circle, rgba(125,243,255,.45) 0 1px, transparent 1.8px) 38px 24px / 142px 142px;
            opacity: .24;
            animation: star-drift 42s linear infinite;
          }
          .stApp::after {
            content: "";
            position: fixed;
            inset: auto -18% -28% -18%;
            height: 46vh;
            z-index: 0;
            pointer-events: none;
            background: radial-gradient(ellipse at center, rgba(46, 230, 255, .20), transparent 62%);
            filter: blur(34px);
          }
          .block-container {
            position: relative;
            z-index: 1;
            max-width: 1500px;
            padding-top: 22px;
            padding-bottom: 48px;
          }
          [data-testid="stHeader"] {
            background: rgba(3, 8, 20, .72);
            backdrop-filter: blur(12px);
          }
          h1, h2, h3 {
            letter-spacing: 0;
          }
          [data-testid="stSidebar"] {
            background:
              linear-gradient(180deg, rgba(7, 18, 34, .98), rgba(3, 8, 20, .98)),
              radial-gradient(circle at 30% 0%, rgba(46, 230, 255, .14), transparent 34%);
            border-right: 1px solid rgba(125,243,255,.16);
          }
          [data-testid="stSidebar"] * {
            color: rgba(255,255,255,.88);
          }
          [data-testid="stSidebar"] h2,
          [data-testid="stSidebar"] h3 {
            color: #ffffff;
            font-size: 16px;
          }
          [data-testid="stSidebar"] p,
          [data-testid="stSidebar"] label {
            color: rgba(255,255,255,.72);
          }
          [data-testid="stSidebar"] [data-testid="stFileUploaderDropzone"] {
            background: rgba(8, 24, 43, .74);
            border: 1px solid rgba(125,243,255,.22);
            border-radius: var(--pd-radius);
          }
          [data-testid="stSidebar"] [data-testid="stFileUploaderDropzone"] button {
            background: rgba(226, 249, 255, .10) !important;
            border: 1px solid rgba(226, 249, 255, .20) !important;
            color: #eefcff !important;
            box-shadow: none !important;
          }
          [data-testid="stSidebar"] button {
            border-radius: var(--pd-radius);
          }
          [data-testid="stSidebar"] div[data-baseweb="select"] > div {
            background: rgba(8, 24, 43, .82) !important;
            border: 1px solid rgba(125, 243, 255, .22) !important;
            box-shadow: none !important;
          }
          [data-testid="stSidebar"] span[data-baseweb="tag"] {
            background: rgba(46, 230, 255, .16) !important;
            border: 1px solid rgba(125, 243, 255, .28) !important;
            border-radius: 8px !important;
          }
          [data-testid="stSidebar"] span[data-baseweb="tag"] span {
            color: #e8fbff !important;
          }
          .hero-band {
            position: relative;
            overflow: hidden;
            background:
              radial-gradient(circle at 14% 18%, rgba(46, 230, 255, .16), transparent 30%),
              radial-gradient(circle at 82% 22%, rgba(255, 184, 77, .10), transparent 26%),
              linear-gradient(135deg, rgba(4, 12, 25, .98), rgba(2, 7, 16, .94));
            background-size: cover;
            background-position: center;
            color: #ffffff;
            min-height: auto;
            padding: clamp(28px, 4vw, 56px);
            border-radius: 24px;
            margin: 0 0 28px;
            border: 1px solid rgba(226, 249, 255, .14);
            box-shadow:
              0 38px 110px rgba(0, 0, 0, .42),
              0 0 0 1px rgba(255,255,255,.04),
              inset 0 1px 0 rgba(255,255,255,.12);
            transform: translateY(0);
          }
          .hero-band::before {
            content: "";
            position: absolute;
            width: 58vw;
            height: 58vw;
            left: -26vw;
            bottom: -42vw;
            border: 1px solid rgba(125,243,255,.34);
            border-radius: 50%;
            box-shadow:
              0 0 24px rgba(46, 230, 255, .20),
              inset 0 0 42px rgba(46, 230, 255, .10);
            opacity: .34;
          }
          .hero-band::after {
            content: "";
            position: absolute;
            inset: 0;
            background:
              linear-gradient(90deg, rgba(125,243,255,.08) 1px, transparent 1px),
              linear-gradient(180deg, rgba(125,243,255,.06) 1px, transparent 1px);
            background-size: 52px 52px;
            opacity: .14;
            pointer-events: none;
          }
          .hero-content {
            position: relative;
            z-index: 1;
            display: grid;
            grid-template-columns: minmax(340px, 520px) minmax(580px, 1fr);
            gap: clamp(30px, 5vw, 72px);
            align-items: center;
            min-height: auto;
          }
          .hero-copy {
            align-self: center;
            max-width: 520px;
            padding: 0;
          }
          .system-kicker {
            display: inline-flex;
            color: rgba(198, 240, 255, .72);
            font-size: 12px;
            font-weight: 720;
            letter-spacing: .10em;
            text-transform: uppercase;
            margin-bottom: 16px;
          }
          .hero-band h1 {
            max-width: 560px;
            margin: 0 0 18px;
            font-family: -apple-system, BlinkMacSystemFont, "SF Pro Display", "Avenir Next", "Segoe UI", sans-serif;
            font-size: clamp(48px, 5.6vw, 86px);
            line-height: .94;
            font-weight: 780;
            letter-spacing: -.055em;
            color: #f2fbff;
            text-shadow: 0 14px 42px rgba(46, 230, 255, .14);
          }
          .hero-band p {
            max-width: 500px;
            margin: 0;
            color: rgba(220, 237, 246, .78);
            line-height: 1.68;
            font-size: 16px;
          }
          .mission-chips {
            display: flex;
            flex-wrap: wrap;
            gap: 8px;
            margin-top: 20px;
          }
          .mission-chips span {
            display: inline-flex;
            min-height: 32px;
            align-items: center;
            padding: 6px 11px;
            border-radius: 999px;
            border: 1px solid rgba(125, 243, 255, .26);
            background: rgba(226, 249, 255, .06);
            color: rgba(226, 249, 255, .84);
            font-size: 12px;
            font-weight: 760;
          }
          .hero-status {
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 10px;
            margin-top: 26px;
          }
          .hero-status div {
            display: grid;
            gap: 7px;
            padding: 14px;
            border: 1px solid rgba(226,249,255,.14);
            border-radius: 14px;
            background: rgba(226,249,255,.055);
            font-size: 13px;
          }
          .hero-status div:last-child {
            border-bottom: 1px solid rgba(226,249,255,.14);
          }
          .hero-status span {
            color: rgba(191, 230, 244, .64);
          }
          .hero-status strong {
            color: #ffffff;
            font-weight: 700;
          }
          .video-stage {
            position: relative;
            aspect-ratio: 16 / 9;
            width: 100%;
            max-height: 560px;
            border-radius: 24px;
            border: 1px solid rgba(226, 249, 255, .16);
            background: rgba(4, 14, 29, .46);
            box-shadow:
              0 34px 90px rgba(0,0,0,.34),
              0 0 48px rgba(46,230,255,.08),
              inset 0 1px 0 rgba(255,255,255,.12);
            overflow: hidden;
            transform: none;
          }
          .video-stage::before {
            content: "";
            position: absolute;
            inset: 10px;
            border: 1px solid rgba(255, 255, 255, .10);
            border-radius: 18px;
            pointer-events: none;
            z-index: 2;
          }
          .video-stage::after {
            content: "";
            position: absolute;
            inset: 0;
            z-index: 3;
            pointer-events: none;
            box-shadow: inset 0 -70px 90px rgba(0,0,0,.16);
          }
          .hero-video {
            position: absolute;
            inset: 0;
            width: 100%;
            height: 100%;
            object-fit: contain;
            object-position: center;
            z-index: 1;
            opacity: 1;
            filter: brightness(1.18) contrast(1.04) saturate(1.03);
          }
          .video-glass-line {
            position: absolute;
            inset: 0;
            z-index: 2;
            pointer-events: none;
            background:
              linear-gradient(90deg, rgba(125,243,255,.09) 1px, transparent 1px),
              linear-gradient(180deg, rgba(125,243,255,.07) 1px, transparent 1px);
            background-size: 54px 54px;
            opacity: .08;
          }
          .metric-tile {
            min-height: 94px;
            border: 1px solid var(--pd-line);
            background: var(--pd-surface);
            border-radius: var(--pd-radius);
            padding: 16px 17px;
            display: flex;
            flex-direction: column;
            justify-content: space-between;
            box-shadow: 0 18px 42px rgba(0, 0, 0, .20), inset 0 1px 0 rgba(255,255,255,.08);
          }
          .metric-tile span {
            color: var(--pd-muted);
            font-size: 13px;
            font-weight: 650;
          }
          .metric-tile strong {
            color: var(--pd-ink);
            font-size: 24px;
            line-height: 1.1;
          }
          .kb-card {
            border: 1px solid var(--pd-line);
            background: var(--pd-surface);
            border-radius: var(--pd-radius);
            padding: 15px 16px;
            margin-bottom: 10px;
            box-shadow: 0 16px 38px rgba(0, 0, 0, .18), inset 0 1px 0 rgba(255,255,255,.07);
          }
          .kb-card-title {
            font-weight: 700;
            color: var(--pd-ink);
            margin-bottom: 7px;
          }
          .kb-card-body {
            color: #c8dbe8;
            line-height: 1.65;
            font-size: 14px;
          }
          .kb-card-meta {
            margin-top: 10px;
            color: var(--pd-muted);
            font-size: 12px;
          }
          .section-label {
            display: flex;
            justify-content: space-between;
            align-items: end;
            gap: 20px;
            margin: 18px 0 12px;
          }
          .section-label h2 {
            margin: 0;
            font-size: 20px;
            line-height: 1.15;
            color: var(--pd-ink);
          }
          .section-label p {
            max-width: 58ch;
            margin: 0;
            color: var(--pd-muted);
            font-size: 13px;
            line-height: 1.55;
          }
          details {
            margin-top: 9px;
            border-top: 1px solid rgba(125,243,255,.14);
            padding-top: 7px;
          }
          summary {
            cursor: pointer;
            color: var(--pd-accent-dark);
            font-weight: 650;
          }
          details p {
            color: #9fb7c7;
            margin-bottom: 0;
          }
          .tag-row {
            display: flex;
            flex-wrap: wrap;
            gap: 8px;
          }
          .tag {
            display: inline-flex;
            align-items: center;
            min-height: 28px;
            padding: 4px 10px;
            border-radius: 999px;
            background: rgba(46, 230, 255, .10);
            color: #d9f8ff;
            font-size: 13px;
            border: 1px solid rgba(125,243,255,.26);
          }
          .json-box pre {
            max-height: 680px;
          }
          .flow-lane-wrap {
            margin-bottom: 18px;
          }
          .flow-step {
            position: relative;
            min-height: 148px;
            border: 1px solid var(--pd-line);
            background: var(--pd-surface);
            border-radius: var(--pd-radius);
            padding: 14px;
            overflow: hidden;
          }
          .flow-step::before {
            content: "";
            position: absolute;
            inset: 0;
            background: linear-gradient(110deg, transparent 0%, rgba(46, 230, 255, .18) 46%, transparent 78%);
            transform: translateX(-100%);
            animation: pd-scan 2.8s ease-in-out infinite;
          }
          .flow-step span,
          .flow-step strong,
          .flow-step small {
            position: relative;
            z-index: 1;
          }
          .flow-step span {
            display: inline-flex;
            color: var(--pd-accent-dark);
            font-size: 12px;
            font-weight: 800;
            margin-bottom: 22px;
          }
          .flow-step strong {
            display: block;
            color: var(--pd-ink);
            font-size: 15px;
            line-height: 1.25;
            margin-bottom: 8px;
          }
          .flow-step small {
            color: var(--pd-muted);
            font-size: 12px;
          }
          .table-shell {
            width: 100%;
            overflow-x: auto;
            border: 1px solid rgba(226,249,255,.14);
            border-radius: 14px;
            background: rgba(5, 14, 28, .88);
            box-shadow: 0 20px 50px rgba(0,0,0,.22), inset 0 1px 0 rgba(255,255,255,.06);
          }
          .dark-table {
            width: 100%;
            min-width: 760px;
            border-collapse: collapse;
            color: #dff8ff;
            font-size: 13px;
          }
          .dark-table th {
            position: sticky;
            top: 0;
            background: rgba(12, 30, 52, .96);
            color: rgba(198, 240, 255, .72);
            text-align: left;
            font-weight: 760;
            padding: 12px 14px;
            border-bottom: 1px solid rgba(226,249,255,.12);
          }
          .dark-table td {
            padding: 12px 14px;
            border-bottom: 1px solid rgba(226,249,255,.08);
            color: rgba(226, 249, 255, .86);
            white-space: nowrap;
          }
          .dark-table tr:last-child td {
            border-bottom: 0;
          }
          .code-panel {
            overflow: auto;
            margin: 0;
            padding: 18px 20px;
            border: 1px solid rgba(226,249,255,.14);
            border-radius: 14px;
            background: rgba(5, 14, 28, .92);
            color: #dff8ff;
            box-shadow: 0 20px 50px rgba(0,0,0,.22), inset 0 1px 0 rgba(255,255,255,.06);
          }
          .code-panel pre {
            margin: 0;
            background: transparent !important;
          }
          .code-panel code {
            color: #dff8ff;
            font-family: "SF Mono", "Menlo", "Consolas", monospace;
            font-size: 13px;
            line-height: 1.62;
            white-space: pre;
          }
          .page-heatmap {
            display: grid;
            grid-template-columns: repeat(auto-fill, minmax(58px, 1fr));
            gap: 7px;
            margin-bottom: 18px;
          }
          .page-cell {
            min-height: 58px;
            border: 1px solid rgba(125, 243, 255, calc(.16 + var(--level) * .42));
            background:
              linear-gradient(180deg, rgba(46, 230, 255, calc(.08 + var(--level) * .44)), rgba(255, 184, 77, calc(.04 + var(--level) * .18))),
              var(--pd-surface);
            border-radius: var(--pd-radius);
            padding: 8px;
            display: flex;
            flex-direction: column;
            justify-content: space-between;
          }
          .page-cell span {
            color: var(--pd-muted);
            font-size: 11px;
            font-weight: 700;
          }
          .page-cell strong {
            color: var(--pd-ink);
            font-size: 18px;
            line-height: 1;
          }
          .bar-panel {
            border: 1px solid var(--pd-line);
            background: var(--pd-surface);
            border-radius: var(--pd-radius);
            padding: 14px;
            min-height: 268px;
          }
          .signal-bar {
            margin-bottom: 13px;
          }
          .signal-bar div {
            display: flex;
            justify-content: space-between;
            gap: 16px;
            color: var(--pd-muted);
            font-size: 13px;
            margin-bottom: 7px;
          }
          .signal-bar strong {
            color: var(--pd-ink);
          }
          .signal-bar i {
            display: block;
            height: 10px;
            border-radius: 999px;
            background: linear-gradient(90deg, var(--pd-accent), var(--pd-green));
            box-shadow: inset 0 0 0 1px rgba(255,255,255,.25);
            animation: pd-grow .75s ease-out both;
          }
          .node-map {
            position: relative;
            min-height: 268px;
            border: 1px solid var(--pd-line);
            background:
              linear-gradient(90deg, rgba(125, 243, 255, .08) 1px, transparent 1px),
              linear-gradient(180deg, rgba(125, 243, 255, .06) 1px, transparent 1px),
              var(--pd-surface);
            background-size: 34px 34px;
            border-radius: var(--pd-radius);
            padding: 14px;
            display: grid;
            grid-template-columns: repeat(3, 1fr);
            gap: 12px;
            align-items: center;
          }
          .node-map::before,
          .node-map::after {
            content: "";
            position: absolute;
            left: 11%;
            right: 11%;
            top: 50%;
            height: 1px;
            background: rgba(46, 230, 255, .28);
          }
          .node-map::after {
            top: 26%;
            transform: rotate(18deg);
            transform-origin: center;
          }
          .knowledge-node {
            position: relative;
            z-index: 1;
            min-height: 78px;
            border: 1px solid rgba(125, 243, 255, .30);
            background: rgba(6, 20, 38, .92);
            border-radius: var(--pd-radius);
            padding: 12px;
            transform: scale(var(--scale));
            transform-origin: center;
            box-shadow: 0 16px 34px rgba(0, 0, 0, .24), 0 0 22px rgba(46, 230, 255, .08);
          }
          .knowledge-node strong {
            display: block;
            color: var(--pd-accent-dark);
            font-size: 22px;
            line-height: 1;
            margin-bottom: 8px;
          }
          .knowledge-node span {
            color: var(--pd-ink);
            font-size: 12px;
            font-weight: 700;
          }
          .empty-note {
            color: var(--pd-muted);
            font-size: 13px;
            padding: 10px;
          }
          @keyframes pd-scan {
            0% { transform: translateX(-100%); }
            48%, 100% { transform: translateX(120%); }
          }
          @keyframes pd-grow {
            from { transform: scaleX(.18); transform-origin: left; }
            to { transform: scaleX(1); transform-origin: left; }
          }
          @keyframes star-drift {
            from { transform: translate3d(0, 0, 0); }
            to { transform: translate3d(-96px, 96px, 0); }
          }
          @keyframes orbital-scan {
            0%, 100% { background-position: 0 0, 0 0, -80% 0; }
            50% { background-position: 0 0, 0 0, 120% 0; }
          }
          @keyframes orbit-pulse {
            0%, 100% { opacity: .42; transform: scale(.98); }
            50% { opacity: .78; transform: scale(1.02); }
          }
          @media (prefers-reduced-motion: reduce) {
            .flow-step::before,
            .signal-bar i,
            .stApp::before,
            .hero-band::before,
            .hero-band::after {
              animation: none;
            }
          }
          .empty-workbench {
            display: grid;
            grid-template-columns: minmax(0, 1fr) minmax(280px, 420px);
            gap: 22px;
            align-items: stretch;
            border: 1px solid var(--pd-line);
            background:
              linear-gradient(135deg, rgba(7, 18, 34, .88), rgba(5, 12, 24, .78)),
              radial-gradient(circle at 100% 0%, rgba(46, 230, 255, .12), transparent 32%);
            border-radius: var(--pd-radius);
            padding: 22px;
            margin-top: -10px;
            box-shadow: 0 24px 70px rgba(0,0,0,.26), inset 0 1px 0 rgba(255,255,255,.08);
          }
          .empty-workbench .system-kicker {
            color: var(--pd-accent-dark);
            margin-bottom: 10px;
          }
          .empty-workbench h2 {
            margin: 0 0 10px;
            font-size: clamp(26px, 4vw, 42px);
            line-height: 1.02;
          }
          .empty-workbench p {
            margin: 0;
            max-width: 58ch;
            color: var(--pd-muted);
            line-height: 1.65;
          }
          .empty-grid {
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 8px;
          }
          .empty-grid div {
            border: 1px solid var(--pd-line);
            background: var(--pd-surface-muted);
            border-radius: var(--pd-radius);
            padding: 13px;
            min-height: 104px;
          }
          .empty-grid strong {
            display: block;
            color: var(--pd-accent-dark);
            font-size: 24px;
            margin-bottom: 12px;
          }
          .empty-grid span {
            color: var(--pd-ink);
            font-size: 13px;
            line-height: 1.35;
          }
          div[data-testid="stAlert"] {
            border-radius: var(--pd-radius);
            border-color: var(--pd-line);
            background: rgba(7, 18, 34, .82);
          }
          div[data-testid="stTabs"] button {
            border-radius: var(--pd-radius) var(--pd-radius) 0 0;
          }
          .stDownloadButton button,
          .stButton button {
            border-radius: var(--pd-radius);
            min-height: 40px;
            font-weight: 700;
          }
          div[data-testid="stCodeBlock"] pre {
            background: rgba(5, 14, 28, .92) !important;
            border: 1px solid rgba(226,249,255,.14);
            border-radius: 14px;
          }
          div[data-testid="stCodeBlock"] code {
            color: #dff8ff !important;
          }
          @media (max-width: 860px) {
            .hero-content,
            .empty-workbench {
              grid-template-columns: 1fr;
            }
            .hero-band {
              min-height: auto;
              transform: none;
            }
            .hero-content {
              min-height: auto;
            }
            .hero-status {
              grid-column: 1;
            }
            .hero-band h1 {
              font-size: clamp(44px, 12vw, 72px);
            }
            .hero-band p {
              font-size: 15px;
            }
            .mission-chips {
              margin-top: 16px;
            }
            .empty-workbench {
              margin-top: -8px;
            }
            .flow-lane,
            .node-map {
              grid-template-columns: 1fr;
            }
            .section-label {
              display: block;
            }
            .section-label p {
              margin-top: 6px;
            }
          }
        </style>
        """
    st.markdown(
        css.replace("__ORBIT_LOOP__", asset_data_url(ORBIT_LOOP_PATH, "image/webp")),
        unsafe_allow_html=True,
    )


def render_overview(payload: dict[str, Any]) -> None:
    summary = payload["summary"]
    power_system = payload.get("power_system", {})
    cols = st.columns(4)
    with cols[0]:
        render_metric("系统模型", power_system.get("schema", "未生成"))
    with cols[1]:
        render_metric("结构化指标", len(power_system.get("metrics", [])))
    with cols[2]:
        render_metric("设计约束", len(power_system.get("constraints", [])))
    with cols[3]:
        render_metric("交付文件", len(power_system.get("deliverables", [])))

    topology = power_system.get("topology_scheme", {})
    section_label("系统拓扑方案", "按航天电源系统语义抽取的架构，不再只是关键词命中。")
    card(
        "Architecture",
        f"{escape(topology.get('architecture', '未识别'))}<br>置信度：{topology.get('confidence', 0)}",
    )
    feature_rows = [
        [item["id"], item["label"], item["source"].get("page"), item["evidence"][:120]]
        for item in topology.get("features", [])
    ]
    if feature_rows:
        render_dark_table(["feature", "label", "page", "evidence"], feature_rows)

    section_label("系统分区", "仿照样例把原文组织成任务、轨道、电气指标、拓扑、太阳翼、蓄电池、控制设备、可靠性等模块。")
    summary_rows = [
        [item["label"], item["items"], " / ".join(item["preview"])]
        for item in power_system.get("section_summary", [])
    ]
    if summary_rows:
        render_dark_table(["section", "items", "preview"], summary_rows)

    section_label("关键词", "从文档正文中提取的高频技术词，用来快速判断文档主题。")
    tags = "".join(f'<span class="tag">{escape(keyword)}</span>' for keyword in summary["keyword_cloud"])
    st.markdown(f'<div class="tag-row">{tags}</div>', unsafe_allow_html=True)

    section_label("识别到的拓扑", "按出现次数排序，并保留可追溯的原文片段。")
    if not payload["topologies"]:
        st.info("暂未识别到明确拓扑，可以上传 datasheet、application note 或设计指南类文档再试。")
    for item in payload["topologies"]:
        card(
            item["label"],
            f"出现次数：{item['mentions']}<br>置信度：{item['confidence']}",
            render_source(item["source"]),
        )


def render_system_model(power_system: dict[str, Any]) -> None:
    section_label("航天电源系统模型", "这是面向知识库入库的主结果：系统级结构、指标、约束和交付物。")
    top_cols = st.columns(4)
    with top_cols[0]:
        render_metric("Schema", power_system.get("schema", "n/a"))
    with top_cols[1]:
        render_metric("Sections", len(power_system.get("sections", {})))
    with top_cols[2]:
        render_metric("Metrics", len(power_system.get("metrics", [])))
    with top_cols[3]:
        render_metric("Constraints", len(power_system.get("constraints", [])))

    topology = power_system.get("topology_scheme", {})
    section_label("拓扑方案", "系统级供电架构、调节方式和关键功能链路。")
    card("拓扑摘要", escape(topology.get("architecture", "未识别")))
    for feature in topology.get("features", []):
        card(feature["label"], escape(feature["evidence"]), render_source(feature["source"]))

    section_label("结构化指标", "从表格和段落中归并出的设计指标，保留原文依据。")
    metric_rows = [
        [
            SYSTEM_SECTION_LABELS.get(item["section"], item["section"]),
            item["name"],
            item["value"],
            ", ".join(item["units"]),
            item["source"].get("page"),
        ]
        for item in power_system.get("metrics", [])
    ]
    if metric_rows:
        render_dark_table(["section", "name", "value", "unit", "page"], metric_rows)
    else:
        st.info("没有识别到结构化指标。")

    section_label("设计约束", "把指标中带有范围、上下限、稳定性、寿命、恢复时间等语义的条目提炼为约束。")
    for item in power_system.get("constraints", [])[:50]:
        body = f"<strong>{escape(item['requirement'])}</strong><br>{escape(item['rationale'])}"
        card(f"{SYSTEM_SECTION_LABELS.get(item['category'], item['category'])} / {item['name']}", body, render_source(item["source"]))

    deliverables = power_system.get("deliverables", [])
    if deliverables:
        section_label("研试文件与交付物", "适合直接进入知识库的文档清单。")
        render_dark_table(
            ["category", "name", "type", "page"],
            [[item["category"], item["name"], item["type"], item["source"].get("page")] for item in deliverables],
        )


def render_section_browser(power_system: dict[str, Any]) -> None:
    sections = power_system.get("sections", {})
    if not sections:
        st.info("没有可浏览的系统分区。")
        return
    labels = {SYSTEM_SECTION_LABELS.get(section, section): section for section in sections}
    selected_label = st.segmented_control("系统分区", list(labels), default=list(labels)[0])
    section = labels[selected_label]
    for item in sections.get(section, []):
        title = item.get("title") or selected_label
        body = escape(item.get("content") or "")
        card(title, body, render_source(item["source"]))


def render_parameters(parameters: list[dict[str, Any]]) -> None:
    if not parameters:
        st.info("没有抽取到标准参数。")
        return
    section_label("参数表", "抽取 Vin、Vout、Iout、fsw、效率、纹波等工程参数。")
    render_dark_table(
        ["name", "raw", "value", "unit", "page", "confidence"],
        [
            [
                item["name"],
                item["raw_label"],
                item["value"],
                item["unit"],
                item["source"].get("page"),
                item["confidence"],
            ]
            for item in parameters
        ],
    )
    section_label("参数溯源", "前 12 条参数以卡片形式展示，方便快速回看上下文。")
    for item in parameters[:12]:
        body = f"<strong>{escape(item['value'])} {escape(item['unit'])}</strong><br>原始标签：{escape(item['raw_label'])}"
        card(item["name"], body, render_source(item["source"]))


def render_formulas(formulas: list[dict[str, Any]]) -> None:
    if not formulas:
        st.info("没有抽取到公式。")
        return
    section_label("公式", "保留表达式、变量列表和原文位置，后续可以接入公式校验。")
    for item in formulas:
        variables = ", ".join(item["variables"]) if item["variables"] else "未识别"
        body = f"<code>{escape(item['expression'])}</code><br>变量：{escape(variables)}<br>置信度：{item['confidence']}"
        card(item["name"], body, render_source(item["source"]))


def render_components(components: list[dict[str, Any]]) -> None:
    if not components:
        st.info("没有抽取到器件信息。")
        return
    section_label("器件", "统计控制器、MOSFET、电感、电容、驱动器、吸收电路等器件线索。")
    for item in components:
        notes = "<br>".join(escape(note) for note in item["selection_notes"]) or "暂无明确选型句子"
        body = f"出现次数：{item['mentions']}<br>选型线索：<br>{notes}"
        card(item["type"], body, render_source(item["source"]))


def render_rules(rules: list[dict[str, Any]], category: str | None = None) -> None:
    filtered = [rule for rule in rules if category is None or rule["category"] == category]
    if not filtered:
        st.info("这个分类下暂时没有抽取结果。")
        return
    section_label("设计规则", "规则按 layout、EMI、thermal、protection、selection 和 troubleshooting 分类。")
    for rule in filtered:
        body = escape(rule["rule"])
        meta = f"category={rule['category']} / severity={rule['severity']} / confidence={rule['confidence']}"
        card(rule["category"], body, meta + render_source(rule["source"]))


def main() -> None:
    st.set_page_config(page_title=APP_TITLE, page_icon="PD", layout="wide")
    inject_css()
    hero_video_src = asset_data_url(ORBIT_VIDEO_PATH, "video/mp4")
    st.markdown(
        f"""
        <div class="hero-band">
          <div class="hero-content">
            <div class="hero-copy">
              <span class="system-kicker">Satellite power knowledge system</span>
              <h1>PowerDoc-KB</h1>
              <p>面向卫星空间电源设计，把 PDF 和 Word 文档解析成参数、公式、器件规则、轨道级可靠性约束和可下载 JSON。</p>
              <div class="mission-chips">
                <span>Orbit power docs</span>
                <span>Reliability rules</span>
                <span>Traceable extraction</span>
              </div>
              <div class="hero-status">
                <div><span>Input</span><strong>PDF / DOCX / TXT</strong></div>
                <div><span>Output</span><strong>Traceable JSON</strong></div>
              </div>
            </div>
            <div class="video-stage">
              <video class="hero-video" autoplay muted loop playsinline preload="auto" src="{hero_video_src}"></video>
              <div class="video-glass-line"></div>
            </div>
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    with st.sidebar:
        st.header("PowerDoc-KB")
        st.caption("电源设计文档结构化工具")
        st.divider()
        st.header("文档输入")
        uploaded_file = st.file_uploader(
            "上传电源设计文档",
            type=["pdf", "docx", "txt", "md"],
            help="第一版本地解析，不会上传到外部服务。",
        )
        st.caption("建议优先尝试 datasheet、application note、design guide。")
        st.divider()
        st.header("抽取范围")
        enabled_views = st.multiselect(
            "显示模块",
            ["System Model", "Section Browser", "Visual Parse", "Overview", "Parameters", "Formulas", "Components", "Design Rules", "JSON"],
            default=["System Model", "Section Browser", "Visual Parse", "Overview", "JSON"],
        )

    if not uploaded_file:
        render_empty_state()
        demo = {
            "schema": "aerospace_power_system.v1",
            "output": ["topology_scheme", "metrics", "constraints", "deliverables", "source_trace"],
            "extractor": "schema_driven_rule_v2",
        }
        section_label("JSON 输出预览")
        code_panel(json.dumps(demo, ensure_ascii=False, indent=2), max_height=360)
        return

    try:
        with st.status("正在解析文档", expanded=True) as status:
            st.write("读取文件结构")
            doc = parse_upload(uploaded_file)
            time.sleep(0.12)
            st.write("切分页码和文本段落")
            time.sleep(0.12)
            st.write("抽取参数、公式、器件和设计规则")
            payload = extract_knowledge(doc)
            time.sleep(0.12)
            st.write("绑定原文页码并生成 JSON")
            status.update(label="解析完成", state="complete", expanded=False)
    except Exception as exc:
        st.error(f"解析失败：{exc}")
        st.stop()

    st.caption(f"已解析：{payload['document']['filename']} / {payload['document']['pages']} 页或段 / {payload['summary']['character_count']} 字符")

    tabs = st.tabs(enabled_views)
    for tab, view in zip(tabs, enabled_views):
        with tab:
            if view == "System Model":
                render_system_model(payload["power_system"])
            elif view == "Section Browser":
                render_section_browser(payload["power_system"])
            elif view == "Visual Parse":
                render_parse_visualization(payload, doc)
            elif view == "Overview":
                render_overview(payload)
            elif view == "Parameters":
                render_parameters(payload["parameters"])
            elif view == "Formulas":
                render_formulas(payload["formulas"])
            elif view == "Components":
                render_components(payload["components"])
            elif view == "Design Rules":
                categories = ["all"] + sorted({rule["category"] for rule in payload["design_rules"]})
                selected = st.segmented_control("规则分类", categories, default="all")
                render_rules(payload["design_rules"], None if selected == "all" else selected)
            elif view == "JSON":
                json_text = json.dumps(payload, ensure_ascii=False, indent=2)
                st.download_button(
                    "下载 JSON",
                    data=json_text,
                    file_name=f"{Path(uploaded_file.name).stem}.powerdoc.json",
                    mime="application/json",
                    type="primary",
                )
                code_panel(json_text, max_height=720)


if __name__ == "__main__":
    main()
