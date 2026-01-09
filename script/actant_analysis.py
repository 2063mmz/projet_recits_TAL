#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
行动元分析 (Actant Analysis)
基于叙事学理论，分析文本中的行动者、行动和关系
"""

import json
import re
from pathlib import Path
from typing import List, Dict, Tuple, Set
from collections import defaultdict, Counter
import pandas as pd
import numpy as np

import plotly.express as px

# 尝试导入spaCy（用于NER和依存句法分析）
try:
    import spacy
    SPACY_AVAILABLE = True
    try:
        nlp_en = spacy.load("en_core_web_sm")
    except:
        nlp_en = None
        print("⚠️  英文spaCy模型未安装，运行: python -m spacy download en_core_web_sm")
    try:
        nlp_zh = spacy.load("zh_core_web_sm")
    except:
        nlp_zh = None
        print("⚠️  中文spaCy模型未安装，运行: python -m spacy download zh_core_web_sm")
except ImportError:
    SPACY_AVAILABLE = False
    print("⚠️  spaCy未安装，将使用基于规则的方法")

# 配置路径
CORPUS_DIR = Path(__file__).parent.parent / "corpus"
ARTICLES_TXT_DIR = CORPUS_DIR / "articles_txt"
OUTPUT_DIR = Path(__file__).parent.parent / "actant_results"
OUTPUT_DIR.mkdir(exist_ok=True)

# 国家映射文件
COUNTRY_MAPPING_FILE = CORPUS_DIR / "country_mapping.json"

# 行动元类型（基于Greimas的六元模型）
ACTANT_TYPES = {
    'Subject': '主体（行动者）',
    'Object': '客体（目标/对象）',
    'Sender': '发送者（动机来源）',
    'Receiver': '接收者（受益者）',
    'Helper': '辅助者（帮助者）',
    'Opponent': '反对者（阻碍者）'
}

# 常见行动动词（中英文）
ACTION_VERBS = {
    'en': {
        'cooperation': ['cooperate', 'collaborate', 'partnership', 'joint', 'together'],
        'construction': ['build', 'construct', 'develop', 'establish', 'create'],
        'trade': ['trade', 'export', 'import', 'commerce', 'business'],
        'investment': ['invest', 'fund', 'finance', 'capital'],
        'communication': ['communicate', 'exchange', 'dialogue', 'discuss'],
        'support': ['support', 'assist', 'help', 'aid', 'promote'],
        'oppose': ['oppose', 'resist', 'challenge', 'conflict']
    },
    'zh': {
        'cooperation': ['合作', '协作', '伙伴', '共同', '联合'],
        'construction': ['建设', '构建', '发展', '建立', '创建'],
        'trade': ['贸易', '出口', '进口', '商业', '经贸'],
        'investment': ['投资', '资金', '融资', '资本'],
        'communication': ['沟通', '交流', '对话', '讨论'],
        'support': ['支持', '援助', '帮助', '促进'],
        'oppose': ['反对', '抵制', '冲突', '挑战']
    }
}


def clean_text(text: str) -> str:
    """清理文本"""
    if not text:
        return ""
    # 移除HTML标签
    text = re.sub(r'<[^>]+>', '', text)
    # 移除URL
    text = re.sub(r'http[s]?://[^\s]+', '', text)
    # 移除过多的空白
    text = re.sub(r'\s+', ' ', text)
    return text.strip()


def detect_language(text: str) -> str:
    """检测文本语言"""
    chinese_chars = sum(1 for c in text if '\u4e00' <= c <= '\u9fff')
    total_chars = len([c for c in text if c.isalnum() or '\u4e00' <= c <= '\u9fff'])
    if total_chars == 0:
        return "unknown"
    chinese_ratio = chinese_chars / total_chars if total_chars > 0 else 0
    return "zh" if chinese_ratio > 0.3 else "en"


def extract_entities_rule_based(text: str, lang: str) -> Dict[str, List[str]]:
    """
    基于规则提取实体（当spaCy不可用时使用）
    优化版本：避免提取不完整的实体
    """
    entities = {
        'countries': [],
        'organizations': [],
        'persons': [],
        'projects': []
    }
    
    # 完整的国家名称列表（中英文）
    countries = {
        'China', 'Chinese', '中国', '中华人民共和国',
        'Russia', 'Russian', '俄罗斯',
        'Kazakhstan', '哈萨克斯坦',
        'Indonesia', '印度尼西亚',
        'Egypt', '埃及',
        'Ethiopia', '埃塞俄比亚',
        'Nigeria', '尼日利亚',
        'Mongolia', '蒙古',
        'Serbia', '塞尔维亚',
        'Uzbekistan', '乌兹别克斯坦',
        'Morocco', '摩洛哥',
        'Tanzania', '坦桑尼亚',
        'Uganda', '乌干达',
        'South Africa', '南非',
        'Kenya', '肯尼亚',
        'Nepal', '尼泊尔',
        'Greece', '希腊',
        'Pakistan', '巴基斯坦',
        'Bangladesh', '孟加拉国',
        'Myanmar', '缅甸',
        'Laos', '老挝',
        'Cambodia', '柬埔寨',
        'Thailand', '泰国',
        'Malaysia', '马来西亚',
        'Singapore', '新加坡',
        'Philippines', '菲律宾',
        'Vietnam', '越南'
    }
    
    # 常见人名（特别是中文人名）
    common_persons_zh = {
        '习近平', '李克强', '王毅', '张骞', '郑和', '马可·波罗',
        '于红', '马哈拉', '马哈特', '巴拉吉'
    }
    
    # 需要过滤的不完整实体（单字、不完整缩写等）
    invalid_entities = {
        '中', '华', '国', '阿', '尼', '俄', '印', '埃', '蒙', '塞', '乌', '摩', '坦', '乌干', '南非',
        '中阿', '中尼', '中俄', '中印', '中埃', '中蒙', '中塞', '中乌', '中摩', '中坦',
        '华', '国', '家', '人', '民', '政', '府', '部', '长', '大', '使', '主', '席'
    }
    
    # 提取国家（使用完整匹配，避免部分匹配）
    for country in countries:
        # 使用单词边界或中文边界来匹配
        if lang == 'zh':
            # 中文：确保是国家名称的完整出现
            pattern = re.escape(country)
            if re.search(pattern, text):
                entities['countries'].append(country)
        else:
            # 英文：使用单词边界
            pattern = r'\b' + re.escape(country) + r'\b'
            if re.search(pattern, text, re.IGNORECASE):
                entities['countries'].append(country)
    
    # 提取人名（中文）
    if lang == 'zh':
        # 先提取已知的常见人名
        for person in common_persons_zh:
            if person in text:
                entities['persons'].append(person)
        
        # 中文人名模式：常见姓氏 + 1-2个汉字（更通用的模式）
        # 常见姓氏列表（前50个常见姓氏）
        common_surnames = ['王', '李', '张', '刘', '陈', '杨', '赵', '黄', '周', '吴', 
                          '徐', '孙', '胡', '朱', '高', '林', '何', '郭', '马', '罗',
                          '梁', '宋', '郑', '谢', '韩', '唐', '冯', '于', '董', '萧',
                          '程', '曹', '袁', '邓', '许', '傅', '沈', '曾', '彭', '吕',
                          '苏', '卢', '蒋', '蔡', '贾', '丁', '魏', '薛', '叶', '阎',
                          '余', '潘', '杜', '戴', '夏', '锺', '汪', '田', '任', '姜',
                          '范', '方', '石', '姚', '谭', '廖', '邹', '熊', '金', '陆',
                          '郝', '孔', '白', '崔', '康', '毛', '邱', '秦', '江', '史',
                          '顾', '侯', '邵', '孟', '龙', '万', '段', '雷', '钱', '汤',
                          '尹', '黎', '易', '常', '武', '乔', '贺', '赖', '龚', '文',
                          '习', '于', '马', '巴']
        
        # 构建人名模式：姓氏 + 1-2个汉字，前后有边界
        surname_pattern = '|'.join(re.escape(s) for s in common_surnames)
        chinese_name_pattern = rf'(?:{surname_pattern})[\u4e00-\u9fff]{{1,2}}(?![^\u4e00-\u9fff\s])'
        name_matches = re.findall(chinese_name_pattern, text)
        # 过滤：只保留2-4个字符的人名
        name_matches = [m for m in name_matches if 2 <= len(m) <= 4]
        entities['persons'].extend(name_matches)
    
    # 组织名称模式（改进版，避免匹配不完整的实体）
    org_patterns = {
        'en': [
            r'\b[A-Z][a-z]+ (?:Ministry|Department|Organization|Institution|Bank|Fund|Committee|Embassy)\b',
            r'\b(?:UN|UNESCO|WTO|IMF|World Bank|AIIB|BRICS|ASEAN)\b',
            r'\bBelt and Road\b',
            r'\bOne Belt One Road\b'
        ],
        'zh': [
            # 完整的组织名称，至少3个字符
            r'[^。，；：！？\s]{3,15}(?:部|委员会|组织|机构|银行|基金|论坛|使馆|大使馆)',
            r'一带一路',
            r'丝绸之路',
            # 改进：确保是完整的合作/论坛名称，避免"中阿"、"中尼"等
            r'(?:中国|中华人民共和国)[^。，；：！？\s]{2,10}(?:合作|论坛|峰会|组织|机构)',
            r'[^。，；：！？\s]{3,12}(?:国际合作|高峰论坛|合作论坛)'
        ]
    }
    
    # 项目名称模式
    project_patterns = {
        'en': [
            r'\b[A-Z][a-z]+ (?:Project|Initiative|Program|Plan|Agreement|Corridor|Belt|Road)\b',
            r'\b(?:Economic|Trade|Infrastructure) (?:Corridor|Zone|Belt)\b'
        ],
        'zh': [
            # 至少3个字符的项目名称
            r'[^。，；：！？\s]{3,20}(?:项目|倡议|计划|协议|走廊|经济带|铁路|港口)',
            r'[^。，；：！？\s]{3,15}(?:合作项目|合作计划|合作协议)'
        ]
    }
    
    # 提取组织
    for pattern in org_patterns.get(lang, []):
        matches = re.findall(pattern, text, re.IGNORECASE)
        entities['organizations'].extend(matches)
    
    # 提取项目
    for pattern in project_patterns.get(lang, []):
        matches = re.findall(pattern, text, re.IGNORECASE)
        entities['projects'].extend(matches)
    
    # 后处理：过滤不合理的实体
    for key in entities:
        filtered = []
        for entity in entities[key]:
            entity = entity.strip()
            # 过滤条件：
            # 1. 长度至少2个字符（中文）或3个字符（英文）
            min_len = 2 if lang == 'zh' else 3
            if len(entity) < min_len:
                continue
            # 2. 不在无效实体列表中
            if entity in invalid_entities:
                continue
            # 3. 不包含纯数字
            if entity.isdigit():
                continue
            # 4. 不包含特殊字符（除了常见标点）
            if re.match(r'^[^\w\u4e00-\u9fff]+$', entity):
                continue
            filtered.append(entity)
        
        # 去重并排序
        entities[key] = sorted(list(set(filtered)))
    
    return entities


def extract_entities_spacy(text: str, lang: str) -> Dict[str, List[str]]:
    """使用spaCy提取实体（带后处理过滤）"""
    if lang == 'zh' and nlp_zh:
        doc = nlp_zh(text[:1000000])  # 限制长度
    elif lang == 'en' and nlp_en:
        doc = nlp_en(text[:1000000])
    else:
        return extract_entities_rule_based(text, lang)
    
    entities = {
        'countries': [],
        'organizations': [],
        'persons': [],
        'projects': []
    }
    
    # 需要过滤的不完整实体
    invalid_entities = {
        '中', '华', '国', '阿', '尼', '俄', '印', '埃', '蒙', '塞', '乌', '摩', '坦',
        '中阿', '中尼', '中俄', '中印', '中埃', '中蒙', '中塞', '中乌', '中摩', '中坦',
        '华', '国', '家', '人', '民', '政', '府', '部', '长', '大', '使', '主', '席'
    }
    
    for ent in doc.ents:
        ent_text = ent.text.strip()
        
        # 过滤不合理的实体
        if len(ent_text) < 2:  # 至少2个字符
            continue
        if ent_text in invalid_entities:
            continue
        if ent_text.isdigit():
            continue
        
        if ent.label_ in ['GPE', 'LOC']:  # 地理政治实体/位置
            entities['countries'].append(ent_text)
        elif ent.label_ == 'ORG':  # 组织
            entities['organizations'].append(ent_text)
        elif ent.label_ == 'PERSON':  # 人物
            entities['persons'].append(ent_text)
    
    # 去重并排序
    for key in entities:
        entities[key] = sorted(list(set(entities[key])))
    
    return entities


def extract_actions(text: str, lang: str) -> List[Dict]:
    """提取行动"""
    actions = []
    verbs = ACTION_VERBS.get(lang, ACTION_VERBS['en'])
    
    # 简化的行动提取：查找包含行动动词的句子
    sentences = re.split(r'[。！？.!?]', text)
    
    for sentence in sentences:
        sentence = sentence.strip()
        if len(sentence) < 10:
            continue
        
        for action_type, action_words in verbs.items():
            for word in action_words:
                if word.lower() in sentence.lower():
                    actions.append({
                        'type': action_type,
                        'sentence': sentence[:200],  # 限制长度
                        'keyword': word
                    })
                    break
    
    return actions


def extract_actant_relations(text: str, entities: Dict, actions: List[Dict], lang: str) -> List[Dict]:
    """提取行动元关系"""
    relations = []
    
    # 简化的关系提取：在同一句子中出现的实体和行动
    sentences = re.split(r'[。！？.!?]', text)
    
    for sentence in sentences:
        sentence = sentence.strip()
        if len(sentence) < 10:
            continue
        
        # 检查句子中是否包含实体和行动
        sentence_entities = []
        for entity_type, entity_list in entities.items():
            for entity in entity_list:
                if entity in sentence:
                    sentence_entities.append((entity_type, entity))
        
        sentence_actions = [a for a in actions if a['keyword'] in sentence.lower()]
        
        # 如果句子中有实体和行动，创建关系
        if sentence_entities and sentence_actions:
            for entity_type, entity in sentence_entities:
                for action in sentence_actions:
                    relations.append({
                        'actant': entity,
                        'actant_type': entity_type,
                        'action': action['type'],
                        'sentence': sentence[:200]
                    })
    
    return relations


def load_country_mapping() -> Dict[str, str]:
    """加载国家映射文件"""
    try:
        with open(COUNTRY_MAPPING_FILE, 'r', encoding='utf-8') as f:
            data = json.load(f)
        return data.get("country_mapping", {})
    except:
        return {}


def get_country_from_filename(filename: str, country_mapping: Dict[str, str]) -> str:
    """从文件名提取国家信息"""
    # 文件名格式: {src_file}_{hash}_{title}.txt
    # 例如: china_fmprc_links.txt_1f4fe6cc01f2c5b2__一带一路_日新月异_中希合作只争朝夕_中华人民共和国外交部.txt
    
    # 查找匹配的src_file
    for src_file, country in country_mapping.items():
        if filename.startswith(src_file):
            return country
    
    # 如果找不到，尝试从文件名推断
    filename_lower = filename.lower()
    if 'china' in filename_lower:
        return 'China'
    elif 'russia' in filename_lower:
        return 'Russia'
    elif 'kazakhstan' in filename_lower:
        return 'Kazakhstan'
    elif 'indonesia' in filename_lower:
        return 'Indonesia'
    elif 'egypt' in filename_lower:
        return 'Egypt'
    elif 'ethiopia' in filename_lower:
        return 'Ethiopia'
    elif 'nigeria' in filename_lower:
        return 'Nigeria'
    elif 'mongolia' in filename_lower:
        return 'Mongolia'
    elif 'serbia' in filename_lower:
        return 'Serbia'
    elif 'uzbekistan' in filename_lower:
        return 'Uzbekistan'
    elif 'morocco' in filename_lower:
        return 'Morocco'
    elif 'tanzania' in filename_lower:
        return 'Tanzania'
    elif 'uganda' in filename_lower:
        return 'Uganda'
    elif 'south_africa' in filename_lower or 'southafrica' in filename_lower:
        return 'South_Africa'
    elif 'kenya' in filename_lower:
        return 'Kenya'
    
    return 'Unknown'


def load_documents_from_txt_dir(txt_dir: Path) -> Tuple[List[str], List[Dict]]:
    """
    从 articles_txt 目录加载所有 txt 文件
    跳过前8行元数据，从第9行开始提取文本内容
    """
    texts = []
    metadata = []
    
    print(f"📖 正在从目录加载文档: {txt_dir}")
    
    # 加载国家映射
    country_mapping = load_country_mapping()
    
    # 获取所有txt文件
    txt_files = list(txt_dir.glob("*.txt"))
    print(f"   找到 {len(txt_files)} 个txt文件")
    
    skipped_count = 0
    
    for txt_file in txt_files:
        try:
            with open(txt_file, 'r', encoding='utf-8') as f:
                lines = f.readlines()
            
            # 跳过前8行元数据，从第9行开始（索引8）
            if len(lines) < 9:
                skipped_count += 1
                continue
            
            # 提取元数据（前8行）
            meta_dict = {}
            for i in range(min(8, len(lines))):
                line = lines[i].strip()
                if ':' in line:
                    key, value = line.split(':', 1)
                    meta_dict[key.strip()] = value.strip()
            
            # 从第9行开始提取文本（跳过空行）
            text_lines = []
            start_idx = 8  # 第9行（索引8）
            
            # 跳过可能的空行
            while start_idx < len(lines) and not lines[start_idx].strip():
                start_idx += 1
            
            # 提取文本内容
            for i in range(start_idx, len(lines)):
                line = lines[i].strip()
                if line:
                    text_lines.append(line)
            
            text = '\n'.join(text_lines)
            
            # 清理文本
            text = clean_text(text)
            
            # 只处理有有效文本的文档
            if text and len(text) > 100:  # 至少100个字符
                # 从文件名提取国家
                country = get_country_from_filename(txt_file.name, country_mapping)
                
                texts.append(text)
                metadata.append({
                    'index': len(texts) - 1,
                    'src_file': txt_file.name,
                    'country': country,
                    'title': meta_dict.get('title', txt_file.stem),
                    'date': meta_dict.get('date', ''),
                    'url': meta_dict.get('final_url', meta_dict.get('seed_url', ''))
                })
            else:
                skipped_count += 1
        except Exception as e:
            print(f"⚠️  处理文件 {txt_file.name} 时出错: {e}")
            skipped_count += 1
            continue
    
    print(f"✅ 成功加载 {len(texts)} 个文档")
    if skipped_count > 0:
        print(f"⚠️  跳过了 {skipped_count} 个无效或低质量文档")
    return texts, metadata


def analyze_actants(texts: List[str], metadata: List[Dict], output_dir: Path):
    """分析行动元"""
    print("\n🔍 正在分析行动元...")
    
    all_entities = defaultdict(list)
    all_actions = []
    all_relations = []
    
    for i, (text, meta) in enumerate(zip(texts, metadata)):
        if i % 50 == 0:
            print(f"   处理进度: {i}/{len(texts)}")
        
        lang = detect_language(text)
        
        # 提取实体
        if SPACY_AVAILABLE:
            entities = extract_entities_spacy(text, lang)
        else:
            entities = extract_entities_rule_based(text, lang)
        
        # 提取行动
        actions = extract_actions(text, lang)
        
        # 提取关系
        relations = extract_actant_relations(text, entities, actions, lang)
        
        # 添加元数据
        for entity_type, entity_list in entities.items():
            for entity in entity_list:
                all_entities[entity_type].append({
                    'entity': entity,
                    'country': meta.get('country', ''),
                    'title': meta.get('title', ''),
                    'date': meta.get('date', '')
                })
        
        for action in actions:
            action['country'] = meta.get('country', '')
            action['title'] = meta.get('title', '')
            all_actions.append(action)
        
        for relation in relations:
            relation['country'] = meta.get('country', '')
            relation['title'] = meta.get('title', '')
            all_relations.append(relation)
    
    print(f"✅ 提取完成:")
    print(f"   实体: {sum(len(v) for v in all_entities.values())} 个")
    print(f"   行动: {len(all_actions)} 个")
    print(f"   关系: {len(all_relations)} 个")
    
    return all_entities, all_actions, all_relations




def visualize_actant_statistics(entities: Dict, actions: List[Dict], relations: List[Dict], 
                                metadata: List[Dict], output_dir: Path):
    """可视化行动元统计（只保留核心统计）"""
    print("\n📊 正在生成统计图表...")
    
    # 1. 核心实体频率统计（只保留最重要的类型）
    important_types = ['countries', 'organizations', 'persons']
    
    for entity_type in important_types:
        if entity_type not in entities or len(entities[entity_type]) == 0:
            continue
        
        entity_counts = Counter([e['entity'] for e in entities[entity_type]])
        top_entities = entity_counts.most_common(20)
        
        if len(top_entities) == 0:
            continue
        
        df = pd.DataFrame(top_entities, columns=['Entity', 'Count'])
        
        fig = px.bar(
            df,
            x='Count',
            y='Entity',
            orientation='h',
            title=f"{ACTANT_TYPES.get(entity_type, entity_type)} - Top 20",
            labels={'Count': '出现次数', 'Entity': '实体'}
        )
        fig.update_layout(
            height=600, 
            yaxis={'categoryorder': 'total ascending'},
            xaxis_title='出现次数',
            yaxis_title='实体'
        )
        fig_file = output_dir / f"entity_frequency_{entity_type}.html"
        fig.write_html(str(fig_file))
        print(f"✅ {entity_type}频率图已保存")
    
    # 2. 行动类型分布（简化版，使用条形图）
    action_counts = Counter([a['type'] for a in actions])
    if len(action_counts) > 0:
        df = pd.DataFrame(list(action_counts.items()), columns=['Action', 'Count'])
        df = df.sort_values('Count', ascending=True)
        
        fig = px.bar(
            df,
            x='Count',
            y='Action',
            orientation='h',
            title="行动类型分布",
            labels={'Count': '出现次数', 'Action': '行动类型'}
        )
        fig.update_layout(
            height=400,
            yaxis={'categoryorder': 'total ascending'}
        )
        fig_file = output_dir / "action_distribution.html"
        fig.write_html(str(fig_file))
        print(f"✅ 行动类型分布图已保存")


def save_actant_results(entities: Dict, actions: List[Dict], relations: List[Dict], 
                       output_dir: Path):
    """保存行动元分析结果（HTML格式）"""
    print("\n💾 正在保存结果...")
    
    html_content = """
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <title>行动元分析结果</title>
    <style>
        body { font-family: Arial, sans-serif; margin: 20px; background-color: #f5f5f5; }
        .section { background: white; margin: 20px 0; padding: 20px; border-radius: 8px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }
        h1 { color: #2c3e50; }
        h2 { color: #34495e; border-bottom: 2px solid #3498db; padding-bottom: 10px; }
        table { width: 100%; border-collapse: collapse; margin: 15px 0; }
        th, td { padding: 10px; text-align: left; border-bottom: 1px solid #ddd; }
        th { background-color: #3498db; color: white; }
        tr:hover { background-color: #f5f5f5; }
        .entity-type { color: #e74c3c; font-weight: bold; }
        .count { color: #27ae60; font-weight: bold; }
    </style>
</head>
<body>
    <h1>行动元分析结果</h1>
"""
    
    # 实体统计
    html_content += """
    <div class="section">
        <h2>实体统计</h2>
"""
    
    for entity_type, entity_list in entities.items():
        entity_counts = Counter([e['entity'] for e in entity_list])
        top_entities = entity_counts.most_common(20)
        
        html_content += f"""
        <h3>{ACTANT_TYPES.get(entity_type, entity_type)}</h3>
        <table>
            <tr><th>排名</th><th>实体</th><th>出现次数</th></tr>
"""
        for rank, (entity, count) in enumerate(top_entities, 1):
            html_content += f"<tr><td>{rank}</td><td>{entity}</td><td class='count'>{count}</td></tr>\n"
        
        html_content += "</table>\n"
    
    html_content += "</div>\n"
    
    # 行动统计
    html_content += """
    <div class="section">
        <h2>行动类型统计</h2>
        <table>
            <tr><th>行动类型</th><th>出现次数</th></tr>
"""
    action_counts = Counter([a['type'] for a in actions])
    for action_type, count in action_counts.most_common():
        html_content += f"<tr><td>{action_type}</td><td class='count'>{count}</td></tr>\n"
    html_content += "</table>\n</div>\n"
    
    # 关系示例
    html_content += """
    <div class="section">
        <h2>行动元关系示例</h2>
        <table>
            <tr><th>行动者</th><th>行动</th><th>国家</th><th>上下文</th></tr>
"""
    for relation in relations[:50]:  # 只显示前50个
        html_content += f"""
        <tr>
            <td>{relation['actant']}</td>
            <td>{relation['action']}</td>
            <td>{relation.get('country', 'Unknown')}</td>
            <td>{relation['sentence'][:100]}...</td>
        </tr>
"""
    html_content += "</table>\n</div>\n"
    
    html_content += """
</body>
</html>
"""
    
    result_file = output_dir / "actant_analysis_results.html"
    with open(result_file, 'w', encoding='utf-8') as f:
        f.write(html_content)
    print(f"✅ 分析结果已保存到: {result_file}")


def main():
    """主函数"""
    print("="*80)
    print("🚀 行动元分析 (Actant Analysis)")
    print("="*80)
    
    # 1. 加载文档（从articles_txt目录）
    texts, metadata = load_documents_from_txt_dir(ARTICLES_TXT_DIR)
    
    if not texts:
        print("❌ 没有找到有效文档，退出")
        return
    
    # 2. 分析行动元
    entities, actions, relations = analyze_actants(texts, metadata, OUTPUT_DIR)
    
    # 3. 可视化
    visualize_actant_statistics(entities, actions, relations, metadata, OUTPUT_DIR)
    
    # 4. 保存结果
    save_actant_results(entities, actions, relations, OUTPUT_DIR)
    
    print("\n" + "="*80)
    print("✅ 分析完成！")
    print(f"📁 结果保存在: {OUTPUT_DIR}")
    print("="*80)


if __name__ == "__main__":
    main()
