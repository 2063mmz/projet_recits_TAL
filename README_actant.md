# 行动元分析 (Actant Analysis)

基于叙事学理论（Greimas的六元模型）分析文本中的行动者、行动和关系。

## 安装依赖

```bash
pip install -r requirements_actant.txt
```

### 可选：安装spaCy（用于更好的实体识别）

```bash
pip install spacy
python -m spacy download en_core_web_sm
python -m spacy download zh_core_web_sm
```

如果不安装spaCy，脚本会使用基于规则的方法提取实体。

## 使用方法

```bash
python script/actant_analysis.py
```

## 输出文件

所有结果都是HTML可视化文件：

1. **actant_network.html** - 行动元网络图（交互式）
2. **entity_frequency_*.html** - 各类实体频率图
3. **action_distribution.html** - 行动类型分布饼图
4. **country_actant_heatmap.html** - 各国行动元分布热力图
5. **action_entity_cooccurrence.html** - 行动-实体共现矩阵
6. **actant_analysis_results.html** - 完整的分析结果报告

## 行动元类型

基于Greimas的六元模型：

- **Subject (主体)**: 主要行动者
- **Object (客体)**: 目标/对象
- **Sender (发送者)**: 动机来源
- **Receiver (接收者)**: 受益者
- **Helper (辅助者)**: 帮助者
- **Opponent (反对者)**: 阻碍者

## 分析内容

1. **实体提取**: 识别国家、组织、人物、项目等
2. **行动提取**: 识别合作、建设、贸易、投资等行动
3. **关系分析**: 分析行动者与行动之间的关系
4. **网络可视化**: 展示行动元之间的网络关系
5. **统计分析**: 按国家、类型等维度统计
