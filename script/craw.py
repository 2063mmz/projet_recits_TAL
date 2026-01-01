from playwright.sync_api import sync_playwright
from bs4 import BeautifulSoup
import time
import os
import re

def clean_filename(text):
    """清理文件名，去除非法字符"""
    # 移除或替换文件名中的非法字符
    text = re.sub(r'[\\/*?:"<>|]', '', text)
    # 限制长度
    if len(text) > 100:
        text = text[:100]
    return text.strip()

def extract_links_with_keyword(page, keyword="联合"):
    """从列表页提取包含关键词的链接"""
    try:
        # 获取页面所有链接
        links = []
        elements = page.locator('a[href]').all()
        
        for elem in elements:
            try:
                text = elem.text_content().strip()
                href = elem.get_attribute('href')
                
                # 只选择包含关键词的链接
                if keyword in text and href:
                    # 构建完整URL
                    if href.startswith('/'):
                        full_url = 'https://www.yidaiyilu.gov.cn' + href
                    elif not href.startswith('http'):
                        full_url = 'https://www.yidaiyilu.gov.cn/' + href
                    else:
                        full_url = href
                    
                    links.append({
                        'title': text,
                        'url': full_url
                    })
                    print(f"   找到: {text}")
            except:
                continue
        
        return links
    except Exception as e:
        print(f"❌ 提取链接失败: {e}")
        return []

def parse_article_content(html):
    """解析文章页面内容"""
    soup = BeautifulSoup(html, 'html.parser')
    
    # 提取标题
    title = ""
    title_candidates = [
        soup.find('h1'),
        soup.find('h2'),
        soup.find('div', class_='article-title'),
        soup.find('title')
    ]
    
    for candidate in title_candidates:
        if candidate:
            title = candidate.get_text().strip()
            if title and len(title) > 5:
                break
    
    # 移除不需要的元素
    unwanted_tags = ['script', 'style', 'nav', 'footer', 'header', 'iframe', 'noscript']
    for tag in unwanted_tags:
        for element in soup.find_all(tag):
            element.decompose()
    
    # 查找主要内容区域
    main_content = (
        soup.find('article') or 
        soup.find('main') or
        soup.find('div', class_=re.compile(r'content|article|main', re.I)) or
        soup.find('body')
    )
    
    if not main_content:
        return {'title': title, 'content': '未能提取到内容'}
    
    # 提取段落
    paragraphs = main_content.find_all(['p', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6'])
    
    # 收集文本并去重
    seen_texts = set()
    content_lines = []
    
    # 导航关键词
    navigation_keywords = [
        '首页', '资讯', '政策', '项目', '数据', '服务',
        '简体版', '繁體版', 'English', 'Français',
        '无障碍', '友情链接', '关于我们', '官网动态',
        '导航', '语言', '网站导航'
    ]
    
    for para in paragraphs:
        text = para.get_text().strip()
        
        # 过滤条件
        if not text or len(text) < 15:
            continue
        if text in seen_texts:
            continue
        
        # 过滤导航文本
        if len(text) < 50 and any(keyword in text for keyword in navigation_keywords):
            continue
        
        seen_texts.add(text)
        content_lines.append(text)
    
    text_content = '\n\n'.join(content_lines)
    
    return {
        'title': title,
        'content': text_content
    }

def save_article(data, output_dir='articles'):
    """保存文章到txt文件"""
    try:
        # 创建输出目录
        if not os.path.exists(output_dir):
            os.makedirs(output_dir)
        
        # 生成文件名
        filename = clean_filename(data['title'])
        if not filename:
            filename = f"article_{int(time.time())}"
        
        filepath = os.path.join(output_dir, f"{filename}.txt")
        
        # 保存文件
        with open(filepath, 'w', encoding='utf-8') as file:
            file.write(f"标题: {data['title']}\n\n")
            file.write("=" * 80 + "\n\n")
            file.write(data['content'])
        
        print(f"   ✅ 已保存: {filepath}")
        return True
    except Exception as e:
        print(f"   ❌ 保存失败: {e}")
        return False

def check_next_page(page):
    """检查是否有下一页"""
    try:
        # 查找下一页按钮
        next_button = page.locator('a:has-text("下一页"), a:has-text(">"), .next-page').first
        if next_button.is_visible():
            return True
        
        # 检查分页数字
        current_page_elem = page.locator('.current, .active, [class*="current"], [class*="active"]').first
        if current_page_elem.count() > 0:
            return True
        
        return False
    except:
        return False

def go_to_next_page(page):
    """翻到下一页"""
    try:
        # 尝试点击下一页按钮
        next_selectors = [
            'a:has-text("下一页")',
            'a:has-text(">")',
            '.next-page',
            'a[rel="next"]'
        ]
        
        for selector in next_selectors:
            try:
                next_button = page.locator(selector).first
                if next_button.is_visible():
                    next_button.click()
                    time.sleep(2)
                    return True
            except:
                continue
        
        # 如果按钮点击失败，尝试通过URL翻页
        current_url = page.url
        if 'page=' in current_url:
            match = re.search(r'page=(\d+)', current_url)
            if match:
                current_page = int(match.group(1))
                next_page = current_page + 1
                next_url = re.sub(r'page=\d+', f'page={next_page}', current_url)
                page.goto(next_url)
                time.sleep(2)
                return True
        
        return False
    except Exception as e:
        print(f"   ⚠️ 翻页失败: {e}")
        return False

def crawl_list_page(page, keyword="联合", output_dir='articles'):
    """爬取列表页中包含关键词的文章"""
    try:
        # 等待页面加载
        page.wait_for_load_state('networkidle')
        time.sleep(2)
        
        print(f"\n📋 当前页面: {page.url}")
        
        # 提取包含关键词的链接
        print(f"🔍 搜索包含'{keyword}'的链接...")
        links = extract_links_with_keyword(page, keyword)
        
        if not links:
            print(f"   ⚠️ 未找到包含'{keyword}'的链接")
            return 0
        
        print(f"   找到 {len(links)} 个包含'{keyword}'的链接\n")
        
        # 访问每个链接并保存内容
        success_count = 0
        for i, link_info in enumerate(links, 1):
            print(f"📄 [{i}/{len(links)}] 正在处理: {link_info['title']}")
            
            try:
                # 访问详情页
                page.goto(link_info['url'])
                page.wait_for_load_state('networkidle')
                time.sleep(1)
                
                # 获取并解析内容
                html = page.content()
                data = parse_article_content(html)
                
                # 保存文章
                if save_article(data, output_dir):
                    success_count += 1
                
                # 返回列表页
                page.go_back()
                page.wait_for_load_state('networkidle')
                time.sleep(1)
                
            except Exception as e:
                print(f"   ❌ 处理失败: {e}")
                # 尝试返回列表页
                try:
                    page.go_back()
                except:
                    pass
        
        return success_count
    except Exception as e:
        print(f"❌ 爬取列表页失败: {e}")
        return 0

def main():
    """主函数"""
    base_url = 'https://www.yidaiyilu.gov.cn/list/w/sdbwj?page=1'
    keyword = "联合"
    output_dir = 'articles'
    
    print("=" * 80)
    print("🚀 一带一路网站文章爬虫")
    print("=" * 80)
    print(f"关键词: {keyword}")
    print(f"输出目录: {output_dir}")
    print(f"起始页: {base_url}\n")
    
    try:
        with sync_playwright() as p:
            print("🌐 启动浏览器...")
            browser = p.firefox.launch(headless=False)
            page = browser.new_page()
            
            # 访问起始页
            print(f"📡 访问起始页面...")
            page.goto(base_url)
            
            total_articles = 0
            page_num = 1
            
            # 循环处理每一页
            while True:
                print(f"\n{'='*80}")
                print(f"📖 第 {page_num} 页")
                print(f"{'='*80}")
                
                # 爬取当前页
                count = crawl_list_page(page, keyword, output_dir)
                total_articles += count
                
                print(f"\n✅ 第 {page_num} 页完成，成功保存 {count} 篇文章")
                
                # 检查是否有下一页
                print("\n🔄 检查下一页...")
                if not go_to_next_page(page):
                    print("📌 已到达最后一页")
                    break
                
                page_num += 1
                time.sleep(2)
            
            browser.close()
            
            print(f"\n{'='*80}")
            print(f"✅ 爬取完成！")
            print(f"   总页数: {page_num}")
            print(f"   成功保存: {total_articles} 篇文章")
            print(f"   保存位置: {output_dir}/")
            print(f"{'='*80}")
            
    except Exception as e:
        print(f"\n❌ 程序异常: {e}")
        import traceback
        traceback.print_exc()

if __name__ == '__main__':
    main()
