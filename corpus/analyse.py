#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
多国文本主题建模分析系统
支持中英文混合语料，对语料不足的国家使用统计分析
"""

import os
import re
from collections import Counter, defaultdict
import numpy as np
from pathlib import Path

# 需要安装的库：
# pip install gensim jieba scikit-learn pandas matplotlib seaborn wordcloud

try:
    from gensim import corpora, models
    from gensim.models import LdaModel, CoherenceModel
    import jieba
    import jieba.analyse
    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.decomposition import LatentDirichletAllocation, NMF
    import pandas as pd
    import matplotlib.pyplot as plt
    import seaborn as sns
    from wordcloud import WordCloud
except ImportError as e:
    print(f"请安装必要的库: {e}")
    print("运行: pip install gensim jieba scikit-learn pandas matplotlib seaborn wordcloud")
    exit(1)

# 设置中文字体（根据系统调整）
plt.rcParams['font.sans-serif'] = ['SimHei', 'DejaVu Sans']
plt.rcParams['axes.unicode_minus'] = False


class MultiCountryTopicModeling:
    """多国主题建模分析器"""
    
    def __init__(self, data_dir, output_dir='results', min_docs_for_lda=10):
        """
        初始化
        
        Args:
            data_dir: 数据文件夹路径
            output_dir: 输出结果文件夹
            min_docs_for_lda: 使用LDA的最小文档数阈值
        """
        self.data_dir = Path(data_dir)
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(exist_ok=True)
        self.min_docs_for_lda = min_docs_for_lda
        
        # 英文停用词
        self.english_stopwords = set([
            'the', 'a', 'an', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for',
            'of', 'with', 'by', 'from', 'as', 'is', 'was', 'are', 'been', 'be',
            'have', 'has', 'had', 'do', 'does', 'did', 'will', 'would', 'could',
            'should', 'may', 'might', 'can', 'this', 'that', 'these', 'those',
            'i', 'you', 'he', 'she', 'it', 'we', 'they', 'what', 'which', 'who',
            'when', 'where', 'why', 'how', 'said', 'also', 'more', 'about', 'into',
            'through', 'during', 'before', 'after', 'above', 'below', 'between',
            'under', 'again', 'further', 'then', 'once', 'here', 'there', 'all',
            'both', 'each', 'few', 'other', 'some', 'such', 'only', 'own', 'same',
            'than', 'too', 'very', 'just', 'now'
        ])
        
        # 中文停用词
        self.chinese_stopwords = set([
            '的', '了', '在', '是', '我', '有', '和', '就', '不', '人', '都', '一',
            '一个', '上', '也', '很', '到', '说', '要', '去', '你', '会', '着', '没有',
            '看', '好', '自己', '这', '个', '们', '能', '而', '她', '他', '你们', '中',
            '与', '及', '等', '但', '或', '等等', '为', '向', '之', '被', '从', '以',
            '可以', '将', '已', '对', '已经', '还', '更', '其', '让', '使', '把', '给',
            '并', '这个', '那个', '这些', '那些', '什么', '怎么', '如何', '哪里'
        ])
        
        self.country_docs = defaultdict(list)
        self.country_texts = defaultdict(list)
        
    def parse_file(self, filepath):
        """解析单个文件，去除metadata"""
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                content = f.read()
            
            # 找到 "note:" 行
            lines = content.split('\n')
            metadata_end = 0
            
            for i, line in enumerate(lines):
                if line.strip().startswith('note:'):
                    metadata_end = i + 1
                    break
            
            # 返回正文内容
            text = '\n'.join(lines[metadata_end:]).strip()
            return text
            
        except Exception as e:
            print(f"Error parsing {filepath}: {e}")
            return ""
    
    def is_chinese(self, text):
        """判断文本是否为中文"""
        chinese_chars = len(re.findall(r'[\u4e00-\u9fa5]', text))
        total_chars = len(re.findall(r'\w', text))
        return total_chars > 0 and chinese_chars / total_chars > 0.3
    
    def tokenize_english(self, text):
        """英文分词"""
        # 转小写，去除标点
        text = text.lower()
        text = re.sub(r'[^\w\s]', ' ', text)
        
        # 分词并过滤
        words = text.split()
        words = [w for w in words if len(w) > 2 and w not in self.english_stopwords]
        
        return words
    
    def tokenize_chinese(self, text):
        """中文分词"""
        # 使用jieba分词
        words = jieba.cut(text)
        words = [w.strip() for w in words if len(w.strip()) > 1]
        
        # 过滤停用词和非中文词
        words = [w for w in words if w not in self.chinese_stopwords 
                 and re.search(r'[\u4e00-\u9fa5]', w)]
        
        return words
    
    def load_documents(self):
        """加载所有文档并按国家分组"""
        print("Loading documents...")
        
        for filepath in self.data_dir.glob('*.txt'):
            # 从文件名提取国家
            filename = filepath.name
            country = filename.split('_')[0]
            
            # 解析文件内容
            text = self.parse_file(filepath)
            
            if text:
                self.country_docs[country].append(str(filepath))
                self.country_texts[country].append(text)
        
        print(f"Loaded {len(self.country_docs)} countries")
        for country, docs in self.country_docs.items():
            print(f"  {country}: {len(docs)} documents")
    
    def lda_topic_modeling(self, country, texts):
        """使用LDA进行主题建模（适用于语料充足的国家）"""
        print(f"\n--- LDA Topic Modeling for {country} ---")
        
        # 判断是否为中文
        is_chinese = self.is_chinese(texts[0])
        
        # 分词
        if is_chinese:
            print(f"{country} detected as Chinese")
            tokenized_docs = [self.tokenize_chinese(text) for text in texts]
        else:
            print(f"{country} detected as English")
            tokenized_docs = [self.tokenize_english(text) for text in texts]
        
        # 创建字典和语料库
        dictionary = corpora.Dictionary(tokenized_docs)
        dictionary.filter_extremes(no_below=2, no_above=0.7)
        corpus = [dictionary.doc2bow(doc) for doc in tokenized_docs]
        
        # 确定最佳主题数（简化版，使用固定值或根据文档数调整）
        num_docs = len(texts)
        num_topics = 5  # 固定为5个主题
        
        print(f"Training LDA with {num_topics} topics...")
        
        # 训练LDA模型
        lda_model = LdaModel(
            corpus=corpus,
            id2word=dictionary,
            num_topics=num_topics,
            random_state=42,
            passes=10,
            alpha='auto',
            per_word_topics=True
        )
        
        # 计算一致性分数
        coherence_model = CoherenceModel(
            model=lda_model,
            texts=tokenized_docs,
            dictionary=dictionary,
            coherence='c_v'
        )
        coherence_score = coherence_model.get_coherence()
        
        print(f"Coherence Score: {coherence_score:.4f}")
        
        # 提取主题
        topics = []
        for idx in range(num_topics):
            topic_words = lda_model.show_topic(idx, topn=10)
            topics.append({
                'topic_id': idx,
                'words': [(word, float(prob)) for word, prob in topic_words]
            })
        
        # 保存结果
        self.save_lda_results(country, lda_model, topics, coherence_score, 
                             dictionary, corpus, tokenized_docs, is_chinese)
        
        return {
            'method': 'LDA',
            'num_topics': num_topics,
            'coherence_score': coherence_score,
            'topics': topics
        }
    
    def statistical_analysis(self, country, texts):
        """统计分析方法（适用于语料不足的国家）"""
        print(f"\n--- Statistical Analysis for {country} ---")
        
        # 判断语言
        is_chinese = self.is_chinese(texts[0])
        
        # 合并所有文本
        combined_text = ' '.join(texts)
        
        # 分词
        if is_chinese:
            print(f"{country} detected as Chinese")
            words = self.tokenize_chinese(combined_text)
            tokenized_docs = [self.tokenize_chinese(text) for text in texts]
        else:
            print(f"{country} detected as English")
            words = self.tokenize_english(combined_text)
            tokenized_docs = [self.tokenize_english(text) for text in texts]
        
        # 1. 词频统计 (Term Frequency)
        word_freq = Counter(words)
        top_words = word_freq.most_common(30)
        
        # 2. TF-IDF分析
        if len(texts) > 1:
            tokenized_strings = [' '.join(doc) for doc in tokenized_docs]
            
            vectorizer = TfidfVectorizer(max_features=50)
            tfidf_matrix = vectorizer.fit_transform(tokenized_strings)
            feature_names = vectorizer.get_feature_names_out()
            
            # 计算平均TF-IDF
            avg_tfidf = np.mean(tfidf_matrix.toarray(), axis=0)
            top_tfidf_idx = np.argsort(avg_tfidf)[-20:][::-1]
            top_tfidf_words = [(feature_names[i], avg_tfidf[i]) for i in top_tfidf_idx]
        else:
            top_tfidf_words = []
        
        # 3. 关键词提取
        if is_chinese:
            keywords = jieba.analyse.extract_tags(combined_text, topK=20, withWeight=True)
        else:
            # 简单的bigram提取
            bigrams = [' '.join(words[i:i+2]) for i in range(len(words)-1)]
            bigram_freq = Counter(bigrams)
            keywords = bigram_freq.most_common(20)
        
        # 4. 词共现分析 (Co-occurrence Analysis)
        cooccurrence = self.compute_cooccurrence(tokenized_docs, window_size=5)
        
        # 5. 主题相关词聚类 (PMI-based semantic clustering)
        semantic_clusters = self.extract_semantic_clusters(words, cooccurrence, top_k=5)
        
        # 6. N-gram分析 (Bigrams & Trigrams)
        bigrams = self.extract_ngrams(words, n=2, top_k=15)
        trigrams = self.extract_ngrams(words, n=3, top_k=10)
        
        # 7. 词性标注分析 (对于关键实体提取)
        if is_chinese:
            entities = jieba.analyse.textrank(combined_text, topK=15, withWeight=True)
        else:
            # 简单的专有名词识别（首字母大写的词）
            entities = self.extract_named_entities(texts)
        
        # 8. 文档相似度分析 (如果有多个文档)
        doc_similarity = None
        if len(texts) > 1:
            doc_similarity = self.compute_document_similarity(tokenized_docs)
        
        # 9. 情感倾向词分析
        sentiment_words = self.extract_sentiment_indicators(words, is_chinese)
        
        # 保存结果
        self.save_statistical_results(
            country, top_words, top_tfidf_words, keywords, is_chinese,
            cooccurrence, semantic_clusters, bigrams, trigrams, 
            entities, doc_similarity, sentiment_words
        )
        
        return {
            'method': 'Statistical',
            'num_docs': len(texts),
            'total_words': len(words),
            'unique_words': len(word_freq),
            'top_words': top_words[:20],
            'top_tfidf': top_tfidf_words[:20] if top_tfidf_words else [],
            'keywords': keywords[:20],
            'cooccurrence': list(cooccurrence.items())[:10],
            'semantic_clusters': semantic_clusters,
            'bigrams': bigrams,
            'trigrams': trigrams,
            'entities': entities[:15],
            'sentiment_words': sentiment_words
        }
    
    def compute_cooccurrence(self, tokenized_docs, window_size=5):
        """计算词共现矩阵"""
        cooccur = defaultdict(int)
        
        for doc in tokenized_docs:
            for i, word in enumerate(doc):
                # 在窗口内查找共现词
                start = max(0, i - window_size)
                end = min(len(doc), i + window_size + 1)
                
                for j in range(start, end):
                    if i != j:
                        pair = tuple(sorted([word, doc[j]]))
                        cooccur[pair] += 1
        
        # 返回最高频的共现对
        sorted_cooccur = sorted(cooccur.items(), key=lambda x: x[1], reverse=True)
        return dict(sorted_cooccur[:30])
    
    def extract_semantic_clusters(self, words, cooccurrence, top_k=5):
        """基于PMI提取语义簇"""
        word_freq = Counter(words)
        total_words = len(words)
        
        # 计算PMI (Pointwise Mutual Information)
        pmi_scores = {}
        for (w1, w2), cooccur_count in cooccurrence.items():
            if w1 in word_freq and w2 in word_freq:
                p_w1 = word_freq[w1] / total_words
                p_w2 = word_freq[w2] / total_words
                p_w1_w2 = cooccur_count / total_words
                
                if p_w1_w2 > 0:
                    pmi = np.log2(p_w1_w2 / (p_w1 * p_w2))
                    pmi_scores[(w1, w2)] = pmi
        
        # 找出高PMI的词对，构建簇
        sorted_pmi = sorted(pmi_scores.items(), key=lambda x: x[1], reverse=True)
        
        clusters = []
        used_words = set()
        
        for (w1, w2), score in sorted_pmi[:20]:
            if w1 not in used_words and w2 not in used_words:
                # 找到与这两个词相关的其他词
                cluster = {w1, w2}
                for (wa, wb), _ in sorted_pmi[:50]:
                    if wa in cluster:
                        cluster.add(wb)
                    elif wb in cluster:
                        cluster.add(wa)
                
                if len(cluster) >= 3 and len(clusters) < top_k:
                    clusters.append(list(cluster)[:8])  # 限制簇大小
                    used_words.update(cluster)
        
        return clusters
    
    def extract_ngrams(self, words, n=2, top_k=15):
        """提取N-grams"""
        ngrams = []
        for i in range(len(words) - n + 1):
            ngram = ' '.join(words[i:i+n])
            ngrams.append(ngram)
        
        ngram_freq = Counter(ngrams)
        # 过滤只出现一次的
        filtered = [(ng, count) for ng, count in ngram_freq.items() if count > 1]
        return sorted(filtered, key=lambda x: x[1], reverse=True)[:top_k]
    
    def extract_named_entities(self, texts):
        """简单的命名实体识别（基于大写规则）"""
        entities = []
        
        for text in texts:
            # 查找连续大写的词
            words = re.findall(r'\b[A-Z][a-z]+(?:\s+[A-Z][a-z]+)*\b', text)
            entities.extend(words)
        
        entity_freq = Counter(entities)
        # 过滤常见词
        common_words = {'The', 'A', 'An', 'This', 'That', 'These', 'Those'}
        filtered = [(e, c) for e, c in entity_freq.items() 
                   if e not in common_words and c > 1]
        
        return sorted(filtered, key=lambda x: x[1], reverse=True)
    
    def compute_document_similarity(self, tokenized_docs):
        """计算文档间相似度"""
        from sklearn.metrics.pairwise import cosine_similarity
        
        # 转换为TF-IDF向量
        doc_strings = [' '.join(doc) for doc in tokenized_docs]
        vectorizer = TfidfVectorizer()
        tfidf_matrix = vectorizer.fit_transform(doc_strings)
        
        # 计算余弦相似度
        similarity_matrix = cosine_similarity(tfidf_matrix)
        
        # 返回平均相似度
        n = len(tokenized_docs)
        if n > 1:
            avg_similarity = (similarity_matrix.sum() - n) / (n * (n - 1))
            return {
                'average_similarity': float(avg_similarity),
                'matrix_shape': similarity_matrix.shape
            }
        return None
    
    def extract_sentiment_indicators(self, words, is_chinese):
        """提取情感倾向词"""
        # 简单的情感词典
        if is_chinese:
            positive_words = {'发展', '增长', '提高', '改善', '促进', '加强', '成功', 
                             '繁荣', '进步', '创新', '合作', '共赢', '友好', '稳定'}
            negative_words = {'困难', '挑战', '问题', '下降', '减少', '危机', 
                             '冲突', '威胁', '风险', '障碍', '压力'}
        else:
            positive_words = {'development', 'growth', 'increase', 'improve', 'enhance', 
                             'strengthen', 'success', 'prosperity', 'progress', 'innovation',
                             'cooperation', 'partnership', 'positive', 'stable', 'opportunity'}
            negative_words = {'challenge', 'problem', 'decline', 'decrease', 'crisis', 
                             'conflict', 'threat', 'risk', 'obstacle', 'pressure', 'difficulty',
                             'concern', 'issue', 'negative'}
        
        word_set = set(words)
        
        positive_found = [(w, words.count(w)) for w in positive_words if w in word_set]
        negative_found = [(w, words.count(w)) for w in negative_words if w in word_set]
        
        positive_count = sum(count for _, count in positive_found)
        negative_count = sum(count for _, count in negative_found)
        
        return {
            'positive_words': sorted(positive_found, key=lambda x: x[1], reverse=True)[:10],
            'negative_words': sorted(negative_found, key=lambda x: x[1], reverse=True)[:10],
            'positive_count': positive_count,
            'negative_count': negative_count,
            'sentiment_ratio': positive_count / (negative_count + 1)  # 避免除零
        }
    
    def save_lda_results(self, country, model, topics, coherence_score, 
                        dictionary, corpus, tokenized_docs, is_chinese):
        """保存LDA结果"""
        country_dir = self.output_dir / country
        country_dir.mkdir(exist_ok=True)
        
        # 保存主题
        with open(country_dir / 'lda_topics.txt', 'w', encoding='utf-8') as f:
            f.write(f"Country: {country}\n")
            f.write(f"Method: LDA Topic Modeling\n")
            f.write(f"Coherence Score: {coherence_score:.4f}\n")
            f.write(f"Number of Topics: {len(topics)}\n\n")
            
            for topic in topics:
                f.write(f"Topic {topic['topic_id']}:\n")
                for word, prob in topic['words']:
                    f.write(f"  {word}: {prob:.4f}\n")
                f.write("\n")
        
        # 可视化：词云
        try:
            for topic in topics:
                word_freq = {word: prob for word, prob in topic['words']}
                
                if is_chinese:
                    # 中文词云需要指定字体路径
                    # 常见中文字体路径（根据系统选择）
                    font_paths = [
                        '/System/Library/Fonts/PingFang.ttc',  # macOS
                        '/usr/share/fonts/truetype/droid/DroidSansFallbackFull.ttf',  # Linux
                        '/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc',  # Linux
                        'C:\\Windows\\Fonts\\msyh.ttc',  # Windows 微软雅黑
                        'C:\\Windows\\Fonts\\simhei.ttf',  # Windows 黑体
                        'C:\\Windows\\Fonts\\simsun.ttc',  # Windows 宋体
                    ]
                    
                    font_path = None
                    for path in font_paths:
                        if os.path.exists(path):
                            font_path = path
                            print(f"Using Chinese font: {path}")
                            break
                    
                    if font_path:
                        wordcloud = WordCloud(
                            width=800, height=400,
                            background_color='white',
                            font_path=font_path,
                            max_words=50,
                            relative_scaling=0.5,
                            min_font_size=10
                        ).generate_from_frequencies(word_freq)
                    else:
                        print(f"Warning: No Chinese font found for {country}, skipping wordcloud")
                        continue
                else:
                    wordcloud = WordCloud(
                        width=800, height=400,
                        background_color='white',
                        max_words=50
                    ).generate_from_frequencies(word_freq)
                
                plt.figure(figsize=(10, 5))
                plt.imshow(wordcloud, interpolation='bilinear')
                plt.axis('off')
                plt.title(f'{country} - Topic {topic["topic_id"]}')
                plt.tight_layout()
                plt.savefig(country_dir / f'{topic["topic_id"]}_{country}.png', 
                           dpi=300, bbox_inches='tight')
                plt.close()
        except Exception as e:
            print(f"Warning: Could not generate wordcloud for {country}: {e}")
        
        # 保存模型
        model.save(str(country_dir / 'lda_model'))
        dictionary.save(str(country_dir / 'dictionary'))
    
    def save_statistical_results(self, country, top_words, top_tfidf_words, 
                                 keywords, is_chinese, cooccurrence=None, 
                                 semantic_clusters=None, bigrams=None, trigrams=None,
                                 entities=None, doc_similarity=None, sentiment_words=None):
        """保存统计分析结果"""
        country_dir = self.output_dir / country
        country_dir.mkdir(exist_ok=True)
        
        # 保存详细统计结果
        with open(country_dir / 'statistical_analysis.txt', 'w', encoding='utf-8') as f:
            f.write(f"Country: {country}\n")
            f.write(f"Method: Statistical Analysis (Limited Corpus)\n")
            f.write("=" * 60 + "\n\n")
            
            # 1. 词频统计
            f.write("1. TOP WORDS BY FREQUENCY\n")
            f.write("-" * 40 + "\n")
            for word, freq in top_words:
                f.write(f"  {word}: {freq}\n")
            f.write("\n")
            
            # 2. TF-IDF
            if top_tfidf_words:
                f.write("2. TOP WORDS BY TF-IDF\n")
                f.write("-" * 40 + "\n")
                for word, score in top_tfidf_words:
                    f.write(f"  {word}: {score:.4f}\n")
                f.write("\n")
            
            # 3. 关键词
            f.write("3. KEY PHRASES/KEYWORDS\n")
            f.write("-" * 40 + "\n")
            for item in keywords:
                if isinstance(item, tuple):
                    f.write(f"  {item[0]}: {item[1]:.4f}\n")
                else:
                    f.write(f"  {item}\n")
            f.write("\n")
            
            # 4. 词共现
            if cooccurrence:
                f.write("4. WORD CO-OCCURRENCE (Top pairs)\n")
                f.write("-" * 40 + "\n")
                for (w1, w2), count in list(cooccurrence.items())[:15]:
                    f.write(f"  {w1} <-> {w2}: {count}\n")
                f.write("\n")
            
            # 5. 语义簇
            if semantic_clusters:
                f.write("5. SEMANTIC CLUSTERS (PMI-based)\n")
                f.write("-" * 40 + "\n")
                for i, cluster in enumerate(semantic_clusters):
                    f.write(f"  Cluster {i+1}: {', '.join(cluster)}\n")
                f.write("\n")
            
            # 6. Bigrams
            if bigrams:
                f.write("6. TOP BIGRAMS\n")
                f.write("-" * 40 + "\n")
                for bg, count in bigrams:
                    f.write(f"  {bg}: {count}\n")
                f.write("\n")
            
            # 7. Trigrams
            if trigrams:
                f.write("7. TOP TRIGRAMS\n")
                f.write("-" * 40 + "\n")
                for tg, count in trigrams:
                    f.write(f"  {tg}: {count}\n")
                f.write("\n")
            
            # 8. 命名实体
            if entities:
                f.write("8. NAMED ENTITIES / KEY TERMS\n")
                f.write("-" * 40 + "\n")
                for entity, count in entities:
                    f.write(f"  {entity}: {count}\n")
                f.write("\n")
            
            # 9. 文档相似度
            if doc_similarity:
                f.write("9. DOCUMENT SIMILARITY\n")
                f.write("-" * 40 + "\n")
                f.write(f"  Average Similarity: {doc_similarity['average_similarity']:.4f}\n")
                f.write(f"  Matrix Shape: {doc_similarity['matrix_shape']}\n")
                f.write("\n")
            
            # 10. 情感倾向
            if sentiment_words:
                f.write("10. SENTIMENT INDICATORS\n")
                f.write("-" * 40 + "\n")
                f.write(f"  Sentiment Ratio: {sentiment_words['sentiment_ratio']:.2f}\n")
                f.write(f"  (Positive: {sentiment_words['positive_count']}, "
                       f"Negative: {sentiment_words['negative_count']})\n\n")
                
                f.write("  Positive Words:\n")
                for word, count in sentiment_words['positive_words']:
                    f.write(f"    {word}: {count}\n")
                
                f.write("\n  Negative Words:\n")
                for word, count in sentiment_words['negative_words']:
                    f.write(f"    {word}: {count}\n")
                f.write("\n")
        
        # 可视化：词频柱状图
        try:
            plt.figure(figsize=(12, 6))
            words, freqs = zip(*top_words[:15])
            plt.barh(range(len(words)), freqs)
            plt.yticks(range(len(words)), words)
            plt.xlabel('Frequency')
            plt.title(f'{country} - Top 15 Words by Frequency')
            plt.tight_layout()
            plt.savefig(country_dir / 'word_frequency.png', dpi=300, bbox_inches='tight')
            plt.close()
        except Exception as e:
            print(f"Warning: Could not generate frequency chart for {country}: {e}")
        
        # 可视化：共现网络图
        if cooccurrence:
            try:
                import networkx as nx
                
                G = nx.Graph()
                top_cooccur = list(cooccurrence.items())[:20]
                
                for (w1, w2), weight in top_cooccur:
                    G.add_edge(w1, w2, weight=weight)
                
                plt.figure(figsize=(14, 10))
                pos = nx.spring_layout(G, k=2, iterations=50)
                
                # 绘制边，粗细代表共现频率
                edges = G.edges()
                weights = [G[u][v]['weight'] for u, v in edges]
                max_weight = max(weights) if weights else 1
                
                nx.draw_networkx_edges(
                    G, pos, 
                    width=[w/max_weight * 5 for w in weights],
                    alpha=0.6
                )
                
                # 绘制节点
                nx.draw_networkx_nodes(
                    G, pos,
                    node_size=1000,
                    node_color='lightblue',
                    alpha=0.9
                )
                
                # 绘制标签
                nx.draw_networkx_labels(
                    G, pos,
                    font_size=10,
                    font_weight='bold'
                )
                
                plt.title(f'{country} - Word Co-occurrence Network')
                plt.axis('off')
                plt.tight_layout()
                plt.savefig(country_dir / 'cooccurrence_network.png', 
                           dpi=300, bbox_inches='tight')
                plt.close()
            except Exception as e:
                print(f"Warning: Could not generate network graph for {country}: {e}")
        
        # 可视化：情感对比
        if sentiment_words:
            try:
                fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(14, 5))
                
                # 正面词
                if sentiment_words['positive_words']:
                    pos_words, pos_counts = zip(*sentiment_words['positive_words'][:8])
                    ax1.barh(range(len(pos_words)), pos_counts, color='green', alpha=0.7)
                    ax1.set_yticks(range(len(pos_words)))
                    ax1.set_yticklabels(pos_words)
                    ax1.set_xlabel('Frequency')
                    ax1.set_title('Positive Sentiment Words')
                
                # 负面词
                if sentiment_words['negative_words']:
                    neg_words, neg_counts = zip(*sentiment_words['negative_words'][:8])
                    ax2.barh(range(len(neg_words)), neg_counts, color='red', alpha=0.7)
                    ax2.set_yticks(range(len(neg_words)))
                    ax2.set_yticklabels(neg_words)
                    ax2.set_xlabel('Frequency')
                    ax2.set_title('Negative Sentiment Words')
                
                plt.suptitle(f'{country} - Sentiment Analysis')
                plt.tight_layout()
                plt.savefig(country_dir / 'sentiment_analysis.png', 
                           dpi=300, bbox_inches='tight')
                plt.close()
            except Exception as e:
                print(f"Warning: Could not generate sentiment chart for {country}: {e}")
    
    def analyze_all_countries(self):
        """分析所有国家"""
        self.load_documents()
        
        results = {}
        
        for country, texts in self.country_texts.items():
            print(f"\n{'='*60}")
            print(f"Processing: {country} ({len(texts)} documents)")
            print(f"{'='*60}")
            
            if len(texts) >= self.min_docs_for_lda:
                # 语料充足，使用LDA
                results[country] = self.lda_topic_modeling(country, texts)
            else:
                # 语料不足，使用统计分析
                results[country] = self.statistical_analysis(country, texts)
        
        # 保存总结报告
        self.save_summary_report(results)
        
        print(f"\n{'='*60}")
        print("Analysis complete! Results saved to:", self.output_dir)
        print(f"{'='*60}")
        
        return results
    
    def save_summary_report(self, results):
        """保存总结报告"""
        with open(self.output_dir / 'summary_report.txt', 'w', encoding='utf-8') as f:
            f.write("Multi-Country Topic Modeling Analysis Summary\n")
            f.write("=" * 60 + "\n\n")
            
            for country, result in results.items():
                f.write(f"Country: {country}\n")
                f.write(f"Method: {result['method']}\n")
                
                if result['method'] == 'LDA':
                    f.write(f"Number of Topics: {result['num_topics']}\n")
                    f.write(f"Coherence Score: {result['coherence_score']:.4f}\n")
                else:
                    f.write(f"Number of Documents: {result['num_docs']}\n")
                    f.write(f"Total Words: {result['total_words']}\n")
                    f.write(f"Unique Words: {result['unique_words']}\n")
                
                f.write("\n" + "-" * 60 + "\n\n")


def main():
    """主函数"""
    # 配置参数
    DATA_DIR = './articles_txt'  # 修改为你的数据文件夹路径
    OUTPUT_DIR = './results'
    MIN_DOCS_FOR_LDA = 10  # 使用LDA的最小文档数
    
    # 创建分析器
    analyzer = MultiCountryTopicModeling(
        data_dir=DATA_DIR,
        output_dir=OUTPUT_DIR,
        min_docs_for_lda=MIN_DOCS_FOR_LDA
    )
    
    # 执行分析
    results = analyzer.analyze_all_countries()
    
    print("\nDone!")


if __name__ == '__main__':
    main()
