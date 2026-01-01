"""
使用Google Dork搜索一带一路相关内容
通过Google搜索各个网站，而不是直接访问
"""
from playwright.sync_api import sync_playwright
from bs4 import BeautifulSoup
import time
import os
import re
from urllib.parse import quote

def read_target_websites(file_path='links.txt'):
    """读取目标网站列表"""
    websites = []
    with open(file_path, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            # 跳过空行、注释和标题行
            if not line or line.startswith('#') or line.startswith('=') or '|' not in line:
                continue
            
            try:
                parts = [p.strip() for p in line.split('|')]
                if len(parts) >= 4:
                    url, country, keyword, file_prefix = parts[0], parts[1], parts[2], parts[3]
                    websites.append({
                        'url': url,
                        'country': country,
                        'keyword': keyword,
                        'file_prefix': file_prefix
                    })
            except Exception as e:
                print(f"⚠️ 跳过无效行: {line}")
    
    return websites

def build_google_query(keyword, site_url):
    """构建Google搜索查询"""
    # 清理URL，移除协议前缀
    clean_url = site_url.replace('https://', '').replace('http://', '').rstrip('/')
    
    # 构建查询
    query = f"{keyword} site:{clean_url}"
    return query

def extract_results_from_page(page):
    """从当前页面提取Google搜索结果"""
    results = []
    html = page.content()
    soup = BeautifulSoup(html, 'html.parser')
    
    # 尝试多种选择器来找到搜索结果
    # Google搜索结果的结构可能变化，所以使用多种方法
    
    # 方法1: 查找所有包含链接和标题的div
    search_divs = soup.find_all('div', class_='g')
    
    # 方法2: 如果方法1没有结果，尝试查找所有主要搜索结果
    if not search_divs:
        search_divs = soup.find_all('div', attrs={'data-sokoban-container': True})
    
    # 方法3: 查找所有包含h3标题的父div
    if not search_divs:
        h3_tags = soup.find_all('h3')
        search_divs = [h3.find_parent('div') for h3 in h3_tags if h3.find_parent('div')]
    
    print(f"      找到 {len(search_divs)} 个候选结果")
    
    for div in search_divs:
        try:
            # 查找链接
            a_tag = div.find('a', href=True)
            if not a_tag:
                continue
            
            url = a_tag.get('href', '')
            
            # 跳过Google内部链接和无效链接
            if not url or url.startswith('/search') or 'google.com/search' in url:
                continue
            
            # 如果链接是相对路径，跳过
            if not url.startswith('http'):
                continue
            
            # 查找标题（h3标签）
            h3_tag = div.find('h3')
            title = h3_tag.get_text(strip=True) if h3_tag else 'No Title'
            
            # 跳过没有标题的结果
            if not title or title == 'No Title':
                continue
            
            # 查找描述（多种可能的class）
            description = ''
            desc_classes = ['VwiC3b', 'IsZvec', 'lEBKkf']
            for desc_class in desc_classes:
                desc_tag = div.find('div', class_=desc_class)
                if desc_tag:
                    description = desc_tag.get_text(strip=True)
                    break
            
            # 如果还没找到描述，尝试查找span
            if not description:
                desc_span = div.find('span', class_='aCOpRe')
                if desc_span:
                    description = desc_span.get_text(strip=True)
            
            # 提取日期
            date = ''
            date_match = re.search(r'(20[0-2]\d[-/年]\d{1,2}[-/月]\d{1,2}[日]?)', 
                                   title + description + url)
            if date_match:
                date = date_match.group(0)
            
            # 判断文件类型
            file_type = 'HTML'
            url_lower = url.lower()
            if url_lower.endswith('.pdf') or '[PDF]' in title:
                file_type = 'PDF'
            elif url_lower.endswith(('.doc', '.docx')):
                file_type = 'DOC'
            
            results.append({
                'title': title[:200],
                'url': url,
                'description': description[:300],
                'type': file_type,
                'date': date
            })
            
        except Exception as e:
            continue
    
    return results

def google_search_with_pagination(page, query, max_pages=10, is_first_search=False):
    """在Google上搜索并自动翻页提取结果"""
    print(f"   🔍 搜索查询: {query}")
    print(f"   📄 最多翻页: {max_pages} 页")
    
    # 构建Google搜索URL
    encoded_query = quote(query)
    google_url = f"https://www.google.com/search?q={encoded_query}&num=100"
    
    all_results = []
    seen_urls = set()
    
    try:
        # 第一次访问
        print(f"   📡 访问Google...")
        page.goto(google_url, wait_until='domcontentloaded', timeout=30000)
        
        # 接受cookies（如果有弹窗）
        try:
            accept_buttons = page.locator('button:has-text("Accept all"), button:has-text("Accept"), button:has-text("全部接受"), button:has-text("同意"), button:has-text("接受")')
            if accept_buttons.count() > 0:
                print(f"   🍪 接受cookies...")
                accept_buttons.first.click(timeout=3000)
                time.sleep(2)
        except:
            pass
        
        # 只在第一次搜索时等待更长时间，让用户有时间完成人机验证
        if is_first_search:
            print(f"   ⏳ 等待15秒（请在此期间完成人机验证）...")
            time.sleep(15)
        else:
            time.sleep(3)
        
        # 开始翻页
        current_page = 1
        
        while current_page <= max_pages:
            print(f"\n   📄 第 {current_page}/{max_pages} 页")
            
            # 等待页面加载
            time.sleep(2)
            
            # 提取当前页结果
            page_results = extract_results_from_page(page)
            
            # 去重并添加结果
            new_count = 0
            for result in page_results:
                if result['url'] not in seen_urls:
                    seen_urls.add(result['url'])
                    all_results.append(result)
                    new_count += 1
            
            print(f"      ✅ 本页新增 {new_count} 个结果（总计: {len(all_results)}）")
            
            # 如果本页没有新结果，可能是到底了
            if new_count == 0 and current_page > 1:
                print(f"      ⚠️ 本页无新结果，停止翻页")
                break
            
            # 查找"下一页"按钮
            if current_page < max_pages:
                try:
                    # 多种"下一页"按钮的选择器
                    next_selectors = [
                        'a#pnnext',
                        'a[aria-label="Next page"]',
                        'a[aria-label="下一页"]',
                        'a:has-text("Next")',
                        'a:has-text("下一页")',
                        'span:has-text("Next")',
                    ]
                    
                    next_button = None
                    for selector in next_selectors:
                        try:
                            btn = page.locator(selector).first
                            if btn.count() > 0 and btn.is_visible(timeout=2000):
                                next_button = btn
                                break
                        except:
                            continue
                    
                    if next_button:
                        print(f"      🔄 点击下一页...")
                        next_button.click()
                        current_page += 1
                        time.sleep(3)  # 等待新页面加载
                    else:
                        print(f"      ℹ️ 没有找到下一页按钮")
                        break
                        
                except Exception as e:
                    print(f"      ⚠️ 翻页失败: {e}")
                    break
            else:
                current_page += 1
        
        print(f"\n   ✅ 搜索完成，共 {current_page-1} 页，{len(all_results)} 个结果")
        return all_results
        
    except Exception as e:
        print(f"   ❌ Google搜索失败: {e}")
        import traceback
        traceback.print_exc()
        return all_results  # 返回已经收集到的结果

def crawl_with_google_dork(page, website_info, output_dir='google_dork_results', max_pages=10, is_first_search=False):
    """使用Google Dork爬取单个网站"""
    url = website_info['url']
    country = website_info['country']
    keyword = website_info['keyword']
    file_prefix = website_info['file_prefix']
    
    print(f"\n{'='*80}")
    print(f"🌐 正在搜索: {country}")
    print(f"🔗 目标网站: {url}")
    print(f"🔍 关键词: {keyword}")
    print(f"{'='*80}")
    
    # 构建Google查询
    query = build_google_query(keyword, url)
    
    # 执行搜索（带翻页）
    results = google_search_with_pagination(page, query, max_pages, is_first_search)
    
    print(f"\n   ✅ 总计找到 {len(results)} 个结果")
    
    # 保存结果
    if results:
        output_file = os.path.join(output_dir, f"{file_prefix}_links.txt")
        with open(output_file, 'w', encoding='utf-8') as f:
            f.write(f"{'='*80}\n")
            f.write(f"{country} - 一带一路相关链接 (Google搜索结果)\n")
            f.write(f"目标网站: {url}\n")
            f.write(f"搜索查询: {query}\n")
            f.write(f"爬取时间: {time.strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write(f"{'='*80}\n\n")
            
            for i, link in enumerate(results, 1):
                f.write(f"{i}. {link['title']}\n")
                f.write(f"   URL: {link['url']}\n")
                f.write(f"   类型: {link['type']}")
                if link['date']:
                    f.write(f" | 日期: {link['date']}")
                f.write(f"\n")
                if link['description']:
                    f.write(f"   描述: {link['description']}\n")
                f.write(f"\n")
        
        print(f"   💾 已保存到: {output_file}")
    
    return len(results)

def generate_summary(output_dir='google_dork_results'):
    """生成汇总报告"""
    print(f"\n{'='*80}")
    print("📊 生成汇总报告...")
    print(f"{'='*80}")
    
    summary_file = os.path.join(output_dir, 'summary_report.txt')
    
    # 统计所有文件
    link_files = [f for f in os.listdir(output_dir) if f.endswith('_links.txt')]
    
    total_links = 0
    results = []
    
    for file_name in sorted(link_files):
        file_path = os.path.join(output_dir, file_name)
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
            # 统计链接数量
            count = content.count('URL:')
            total_links += count
            
            # 提取国家名
            country_match = re.search(r'^(.+?) - 一带一路相关链接', content, re.MULTILINE)
            country = country_match.group(1) if country_match else file_name
            
            results.append({
                'file': file_name,
                'country': country,
                'count': count
            })
    
    # 写入汇总报告
    with open(summary_file, 'w', encoding='utf-8') as f:
        f.write(f"{'='*80}\n")
        f.write("一带一路多国网站爬取 - Google Dork 汇总报告\n")
        f.write(f"生成时间: {time.strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write(f"{'='*80}\n\n")
        
        f.write(f"总网站数: {len(link_files)}\n")
        f.write(f"总链接数: {total_links}\n\n")
        
        f.write(f"{'='*80}\n")
        f.write("各网站详细统计:\n")
        f.write(f"{'='*80}\n\n")
        
        for i, result in enumerate(results, 1):
            f.write(f"{i}. {result['country']}\n")
            f.write(f"   文件: {result['file']}\n")
            f.write(f"   链接数: {result['count']}\n\n")
        
        f.write(f"{'='*80}\n")
        f.write("完成！\n")
        f.write(f"{'='*80}\n")
    
    print(f"✅ 汇总报告已保存: {summary_file}")
    print(f"\n📊 统计结果:")
    print(f"   总网站数: {len(link_files)}")
    print(f"   总链接数: {total_links}")

def main():
    """主函数"""
    print("="*80)
    print("🚀 一带一路多国网站链接爬取工具 (Google Dork方法)")
    print("="*80)
    
    # 创建输出目录
    output_dir = 'google_dork_results'
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)
        print(f"📁 创建输出目录: {output_dir}")
    
    # 读取目标网站
    print("\n📖 读取目标网站列表...")
    websites = read_target_websites('links.txt')[13:]
    print(f"✅ 找到 {len(websites)} 个目标网站\n")
    
    # 开始爬取
    try:
        with sync_playwright() as p:
            print("🌐 启动浏览器...")
            browser = p.firefox.launch(headless=False)
            page = browser.new_page()
            
            success_count = 0
            total_links = 0
            
            for i, website in enumerate(websites, 1):
                print(f"\n进度: [{i}/{len(websites)}]")
                # 只有第一个网站需要等待15秒完成人机验证
                is_first = (i == 1)
                links_count = crawl_with_google_dork(page, website, output_dir, max_pages=10, is_first_search=is_first)
                if links_count > 0:
                    success_count += 1
                    total_links += links_count
                
                # 每个搜索之间需要延迟，避免被Google限制
                if i < len(websites):
                    delay = 10  # Google搜索需要更长的延迟
                    print(f"\n   ⏳ 等待 {delay} 秒后搜索下一个网站...")
                    time.sleep(delay)
            
            browser.close()
            
            # 生成汇总报告
            print(f"\n{'='*80}")
            print("📊 爬取完成！")
            print(f"{'='*80}")
            print(f"成功搜索: {success_count}/{len(websites)} 个网站")
            print(f"总链接数: {total_links}")
            print(f"{'='*80}")
            
            generate_summary(output_dir)
            
    except Exception as e:
        print(f"\n❌ 程序异常: {e}")
        import traceback
        traceback.print_exc()

if __name__ == '__main__':
    main()

