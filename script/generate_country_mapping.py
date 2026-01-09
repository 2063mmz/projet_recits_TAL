#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
自动生成 country_mapping.json 文件
根据 articles_txt 目录中的文件名和 links.txt 中的信息
"""

import json
import re
from pathlib import Path
from collections import Counter

# 配置路径
PROJECT_ROOT = Path(__file__).parent.parent
ARTICLES_TXT_DIR = PROJECT_ROOT / "corpus" / "articles_txt"
LINKS_FILE = PROJECT_ROOT / "links.txt"
OUTPUT_FILE = PROJECT_ROOT / "corpus" / "country_mapping.json"

# 从文件名前缀到国家的映射（基于 links.txt）
PREFIX_TO_COUNTRY = {
    'china_fmprc': 'China',
    'china_focac': 'China',
    'china_yidaiyilu': 'China',
    'russia_kremlin': 'Russia',
    'russia_government': 'Russia',
    'kazakhstan': 'Kazakhstan',
    'indonesia_president': 'Indonesia',
    'indonesia_mofa': 'Indonesia',
    'egypt': 'Egypt',
    'ethiopia': 'Ethiopia',
    'nigeria': 'Nigeria',
    'mongolia': 'Mongolia',
    'serbia': 'Serbia',
    'uzbekistan': 'Uzbekistan',
    'morocco': 'Morocco',
    'tanzania': 'Tanzania',
    'uganda': 'Uganda',
    'kenya': 'Kenya',
    'south_africa': 'South_Africa'
}


def normalize_country_name(country: str) -> str:
    """标准化国家名称（中文转英文，处理特殊格式）"""
    # 处理 "中国-中非论坛" 这种情况
    if '中国' in country or country == '中国':
        return 'China'
    elif '俄罗斯' in country or country == '俄罗斯':
        return 'Russia'
    elif '哈萨克斯坦' in country:
        return 'Kazakhstan'
    elif '印度尼西亚' in country:
        return 'Indonesia'
    elif '埃及' in country:
        return 'Egypt'
    elif '埃塞俄比亚' in country:
        return 'Ethiopia'
    elif '尼日利亚' in country:
        return 'Nigeria'
    elif '蒙古' in country:
        return 'Mongolia'
    elif '塞尔维亚' in country:
        return 'Serbia'
    elif '乌兹别克斯坦' in country:
        return 'Uzbekistan'
    elif '摩洛哥' in country:
        return 'Morocco'
    elif '坦桑尼亚' in country:
        return 'Tanzania'
    elif '乌干达' in country:
        return 'Uganda'
    elif '肯尼亚' in country:
        return 'Kenya'
    elif '南非' in country or 'South Africa' in country:
        return 'South_Africa'
    
    # 如果已经是英文，直接返回（处理空格和下划线）
    return country.replace(' ', '_').replace('-', '_')


def parse_links_file(links_file: Path) -> dict:
    """从 links.txt 解析文件名前缀到国家的映射"""
    mapping = {}
    
    if not links_file.exists():
        print(f"⚠️  {links_file} 不存在，使用默认映射")
        return {f"{prefix}_links.txt": country for prefix, country in PREFIX_TO_COUNTRY.items()}
    
    with open(links_file, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            # 跳过注释和空行
            if not line or line.startswith('#') or '|' not in line:
                continue
            
            parts = [p.strip() for p in line.split('|')]
            if len(parts) >= 4:
                url = parts[0]
                country_raw = parts[1]
                keyword = parts[2]
                prefix = parts[3]
                
                # 标准化国家名称
                country = normalize_country_name(country_raw)
                
                # 生成文件名：{prefix}_links.txt
                filename = f"{prefix}_links.txt"
                mapping[filename] = country
    
    return mapping


def extract_src_file_from_filename(filename: str) -> str:
    """
    从文件名提取 src_file（文件名前缀）
    
    文件名格式: {src_file}_{hash}_{title}.txt
    例如: china_fmprc_links.txt_1f4fe6cc01f2c5b2__一带一路_日新月异_中希合作只争朝夕_中华人民共和国外交部.txt
    
    返回: src_file (例如: "china_fmprc_links.txt")
    """
    # 使用正则表达式匹配 {prefix}_links.txt 模式
    # 匹配格式: {任意字符}_links.txt，后面跟着下划线和哈希值
    pattern = r'^(.+?_links\.txt)_[a-f0-9]+'
    match = re.match(pattern, filename)
    if match:
        return match.group(1)
    
    # 如果正则匹配失败，使用原来的方法作为后备
    parts = filename.split('_')
    for i in range(len(parts)):
        candidate = '_'.join(parts[:i+1])
        if 'links.txt' in candidate:
            return candidate
    
    return None


def extract_src_files_from_articles_txt(directory: Path) -> set:
    """从 articles_txt 目录中的文件名提取所有唯一的 src_file"""
    if not directory.exists():
        print(f"⚠️  目录 {directory} 不存在")
        return set()
    
    src_files = set()
    
    for txt_file in directory.glob("*.txt"):
        src_file = extract_src_file_from_filename(txt_file.name)
        if src_file:
            src_files.add(src_file)
        else:
            print(f"⚠️  警告: 无法从文件名提取 src_file: {txt_file.name}")
    
    return src_files


def count_documents_by_country(corpus_dir: Path, country_mapping: dict) -> dict:
    """统计每个国家的文档数量"""
    if not corpus_dir.exists():
        return {}
    
    txt_dir = corpus_dir / "articles_txt"
    if not txt_dir.exists():
        return {}
    
    country_counts = Counter()
    unmatched_files = []
    
    for txt_file in txt_dir.glob("*.txt"):
        # 从文件名提取 src_file
        src_file = extract_src_file_from_filename(txt_file.name)
        
        if src_file and src_file in country_mapping:
            country = country_mapping[src_file]
            country_counts[country] += 1
        else:
            unmatched_files.append(txt_file.name)
    
    if unmatched_files:
        print(f"⚠️  警告: {len(unmatched_files)} 个文件无法匹配到国家（前5个示例）:")
        for f in unmatched_files[:5]:
            print(f"     - {f}")
    
    return dict(country_counts)


def generate_country_mapping():
    """生成 country_mapping.json 文件"""
    print("=" * 60)
    print("生成 country_mapping.json")
    print("=" * 60)
    
    # 1. 从 links.txt 解析映射
    print("\n📖 从 links.txt 解析映射...")
    links_mapping = parse_links_file(LINKS_FILE)
    print(f"   从 links.txt 解析到 {len(links_mapping)} 个映射")
    
    # 2. 从 articles_txt 目录提取实际的 src_file
    print("\n📁 从 articles_txt 目录提取 src_file...")
    src_files = extract_src_files_from_articles_txt(ARTICLES_TXT_DIR)
    print(f"   找到 {len(src_files)} 个不同的 src_file")
    for sf in sorted(src_files):
        print(f"     - {sf}")
    
    # 3. 合并映射（优先使用 links.txt 的映射，如果没有则使用默认映射）
    country_mapping = {}
    for src_file in src_files:
        if src_file in links_mapping:
            country_mapping[src_file] = links_mapping[src_file]
        else:
            # 尝试从文件名推断
            prefix = src_file.replace('_links.txt', '')
            if prefix in PREFIX_TO_COUNTRY:
                country_mapping[src_file] = PREFIX_TO_COUNTRY[prefix]
            else:
                print(f"⚠️  警告: 无法确定 {src_file} 的国家，跳过")
    
    print(f"\n✅ 生成 {len(country_mapping)} 个国家映射")
    
    # 4. 统计文档数量
    print("\n📊 统计文档数量...")
    corpus_dir = PROJECT_ROOT / "corpus"
    statistics = count_documents_by_country(corpus_dir, country_mapping)
    
    # 5. 生成完整的 JSON 数据
    output_data = {
        "country_mapping": country_mapping,
        "statistics": statistics,
        "total_sources": len(country_mapping)
    }
    
    # 6. 保存文件
    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
        json.dump(output_data, f, ensure_ascii=False, indent=2)
    
    print(f"\n✅ 已保存到: {OUTPUT_FILE}")
    print(f"\n📋 映射详情:")
    for filename, country in sorted(country_mapping.items()):
        count = statistics.get(country, 0)
        print(f"   {filename:30s} -> {country:15s} ({count} 篇文档)")
    
    print("\n" + "=" * 60)
    print("完成！")
    print("=" * 60)


if __name__ == "__main__":
    generate_country_mapping()
