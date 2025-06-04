import streamlit as st
import requests
from bs4 import BeautifulSoup
import urllib.parse
import time
import random
import html
import re
import pandas as pd

# Set page title and layout
st.set_page_config(page_title="とらばーゆ 求人情報検索", layout="wide")
st.title("とらばーゆ 求人情報スクレイピングツール")

# Show debug checkbox
debug_mode = st.sidebar.checkbox("デバッグモード")
show_html = st.sidebar.checkbox("HTML表示") if debug_mode else False
direct_listing = st.sidebar.checkbox("一覧ページURLを直接使用") if debug_mode else False

# User input
search_keyword = st.text_input("職種名や施設名を入力してください（例：看護師 渋谷メディカルクリニック）")

# 取得件数の設定
max_jobs = st.sidebar.slider("取得する求人数", min_value=1, max_value=30, value=10)

# Common headers to mimic a browser
def get_headers():
    return {
        'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8',
        'Accept-Language': 'ja,en-US;q=0.9,en;q=0.8',
        'Referer': 'https://toranet.jp/',
        'Connection': 'keep-alive',
        'Upgrade-Insecure-Requests': '1',
        'Cache-Control': 'max-age=0',
    }

# Function to validate URL - ensure we only process relevant URLs
def is_valid_job_url(url):
    if not url:
        return False
    
    # Skip favorite_jobs and other irrelevant paths
    invalid_paths = ['favorite_jobs', 'login', 'register', 'contact', 'about']
    for path in invalid_paths:
        if path in url:
            return False
    
    # Only allow toranet.jp URLs or URLs that contain job-related terms
    valid = (
        ('toranet.jp' in url and ('job' in url or 'kyujin' in url or 'prefectures' in url)) or
        ('job_detail' in url)
    )
    
    if debug_mode and not valid:
        st.warning(f"無効なURLをスキップしました: {url}")
        
    return valid

# Function to extract phone number from text
def extract_phone_number(text):
    if not text:
        return None
    
    # 電話番号のパターン（市外局番-市内局番-番号）
    patterns = [
        r'0\d{1,4}[-(]?\d{1,4}[)-]?\d{3,4}',  # 03-1234-5678 or 03(1234)5678
        r'電話番号.{1,5}(0\d{1,4}[-(]?\d{1,4}[)-]?\d{3,4})',  # 「電話番号：03-1234-5678」のようなパターン
        r'TEL.{1,5}(0\d{1,4}[-(]?\d{1,4}[)-]?\d{3,4})',  # 「TEL：03-1234-5678」のようなパターン
        r'Tel.{1,5}(0\d{1,4}[-(]?\d{1,4}[)-]?\d{3,4})',  # 「Tel：03-1234-5678」のようなパターン
        r'電話.{1,5}(0\d{1,4}[-(]?\d{1,4}[)-]?\d{3,4})'   # 「電話：03-1234-5678」のようなパターン
    ]
    
    for pattern in patterns:
        matches = re.search(pattern, text, re.IGNORECASE)
        if matches:
            # グループがキャプチャされている場合はそのグループを、されていない場合は全体を返す
            return matches.group(1) if len(matches.groups()) > 0 else matches.group(0)
    
    return None

# Function to make requests with retry logic
def make_request(url, max_retries=3):
    # Validate URL before sending request
    if not is_valid_job_url(url):
        return None, f"無効なURL: {url}"
    
    for attempt in range(max_retries):
        try:
            # Add a random delay between requests
            if attempt > 0:
                time.sleep(random.uniform(2, 5))
            
            if debug_mode:
                st.info(f"リクエスト送信中: {url}")
            response = requests.get(url, headers=get_headers(), timeout=15)
            if debug_mode:
                st.success(f"ステータスコード: {response.status_code}")
            response.raise_for_status()
            return response, None
        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 503 and attempt < max_retries - 1:
                st.warning(f"サーバーが一時的に利用できません。再試行中... ({attempt+1}/{max_retries})")
                continue
            return None, f"HTTPエラー: {e.response.status_code} - {e}"
        except requests.exceptions.RequestException as e:
            return None, f"リクエストエラー: {str(e)}"
    
    return None, "最大再試行回数に達しました。後でもう一度お試しください。"

# Function to display HTML response
def display_html_response(response, title):
    if show_html and response:
        with st.expander(f"{title} - HTML表示"):
            st.code(html.escape(response.text[:10000]) + "\n...(省略)..." if len(response.text) > 10000 else html.escape(response.text), language="html")

# Function to find all potential job detail links
def find_all_job_links(soup, search_url):
    all_links = []
    
    # Get all links from the page
    for a_tag in soup.find_all('a', href=True):
        href = a_tag.get('href')
        
        # Skip empty links
        if not href:
            continue
            
        # Ensure absolute URL
        if not href.startswith('http'):
            if href.startswith('/'):
                href = f"https://toranet.jp{href}"
            else:
                href = f"https://toranet.jp/{href}"
        
        # Only include valid job URLs
        if is_valid_job_url(href):
            text = a_tag.get_text().strip()
            all_links.append({
                'href': href,
                'text': text,
                'classes': a_tag.get('class', []),
                'id': a_tag.get('id', ''),
                'contains_detail_text': '詳細' in text or 'detail' in href.lower() or '求人' in text
            })
    
    if debug_mode:
        st.write(f"ページから取得したリンク数: {len(all_links)}")
        
        # Show potential job links in debug mode
        with st.expander("潜在的な求人リンク"):
            for i, link in enumerate(all_links[:20]):  # Show first 20 only
                st.write(f"{i+1}. [{link['text']}]({link['href']}) - クラス: {link['classes']}")
    
    # First try links with detail-related text
    detail_links = [link for link in all_links if link['contains_detail_text']]
    
    # Next try to find links that look like job detail URLs
    pattern_links = [link for link in all_links if re.search(r'job.*detail|kyujin|recruit', link['href'])]
    
    # Combine and remove duplicates (keeping the original order)
    combined_links = []
    seen_urls = set()
    
    for link in detail_links + pattern_links:
        if link['href'] not in seen_urls:
            combined_links.append(link)
            seen_urls.add(link['href'])
    
    # As a last resort, add other valid links
    for link in all_links:
        if link['href'] not in seen_urls and search_url not in link['href'] and 'toranet.jp' in link['href']:
            combined_links.append(link)
            seen_urls.add(link['href'])
    
    # Extract just the URLs
    result_urls = [link['href'] for link in combined_links]
    
    if debug_mode:
        st.write(f"取得した求人リンク数: {len(result_urls)}")
    
    return result_urls[:max_jobs]  # Return only up to max_jobs links

# Function to scrape job listings
def get_job_listings(keyword):
    # Create search URL
    encoded_keyword = urllib.parse.quote(keyword)
    search_url = f"https://toranet.jp/prefectures/tokyo/job_search/kw/{encoded_keyword}"
    
    # If direct_listing is checked, use the search URL directly
    if direct_listing:
        st.info("一覧ページを直接詳細ページとして使用します")
        return [search_url], None, search_url
    
    response, error = make_request(search_url)
    if error:
        return None, error, search_url
    
    # Display HTML for debugging
    display_html_response(response, "検索結果ページ")
    
    try:
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # Advanced link finding approach - get multiple links
        job_links = find_all_job_links(soup, search_url)
        
        if not job_links:
            # If we couldn't find any suitable links, check if the search page itself has job details
            if any(tag.name in ['h1', 'h2'] and ('求人情報' in tag.text or '仕事内容' in tag.text) for tag in soup.find_all(['h1', 'h2'])):
                if debug_mode:
                    st.success("検索ページ自体が求人詳細ページのようです。直接使用します。")
                return [search_url], None, search_url
            
            return None, "求人リンクが見つかりませんでした。サイト構造が変更された可能性があります。", search_url
        
        return job_links, None, search_url
    except Exception as e:
        st.error(f"解析エラー: {str(e)}")
        import traceback
        if debug_mode:
            st.code(traceback.format_exc(), language="python")
        return None, f"パース中にエラーが発生しました: {str(e)}", search_url

# Function to scrape job details
def get_job_details(detail_url):
    # Validate URL before processing
    if not is_valid_job_url(detail_url):
        return None, f"無効な詳細ページURL: {detail_url}"
    
    # Add a slight delay before making the next request
    time.sleep(random.uniform(0.5, 2))
    
    response, error = make_request(detail_url)
    if error:
        return None, error
    
    # Display HTML for debugging
    display_html_response(response, "詳細ページ")
    
    try:
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # Debug - output all div classes to help identify correct selectors
        if debug_mode and show_html:
            with st.expander("ページ内のdiv要素のクラス一覧"):
                divs = soup.find_all('div', class_=True)
                for i, div in enumerate(divs[:30]):  # Limit to first 30 to avoid clutter
                    st.write(f"{i+1}. Class: {div.get('class')} - テキスト: {div.text[:50]}")
            
            # Also show all headings
            with st.expander("ページ内の見出し要素"):
                headings = soup.find_all(['h1', 'h2', 'h3', 'h4', 'h5', 'h6'])
                for i, h in enumerate(headings):
                    st.write(f"{i+1}. {h.name}: {h.text.strip()}")
        
        # Extract facility name - try multiple selectors
        facility_name = "情報なし"
        facility_name_selectors = [
            'div.corpNameWrap > span', 
            'div.corpName', 
            'h1.company-name',
            'div.company-name',
            'h1', # Try any h1 tag
            'h2', # Try any h2 tag
            'div.corpInfo', # Try corporation info div
            'span.name', # Try name span
            '.corp-name', # Try corp-name class
            '.company' # Try company class
        ]
        
        for selector in facility_name_selectors:
            facility_name_element = soup.select_one(selector)
            if facility_name_element:
                facility_name = facility_name_element.text.strip()
                if debug_mode and show_html:
                    st.success(f"施設名が見つかりました（セレクタ: {selector}）")
                break
        
        # Fallback: Try to find text that looks like a company name
        if facility_name == "情報なし":
            # Look for text that might be a company name (often near the top of the page)
            top_elements = soup.find_all(['div', 'span', 'p'], limit=20)
            for elem in top_elements:
                text = elem.text.strip()
                # Company names typically aren't very long and don't contain certain patterns
                if 5 < len(text) < 50 and ('株式会社' in text or '有限会社' in text or '病院' in text or 'クリニック' in text):
                    facility_name = text
                    if debug_mode and show_html:
                        st.success(f"テキストパターンから施設名を検出: {text}")
                    break
        
        # Extract phone number
        phone_number = "情報なし"
        
        # Try to find phone number in specific elements first
        phone_selectors = [
            'div.tel', 
            'div.phone',
            'span.tel',
            'span.phone',
            'p.tel',
            'a[href^="tel:"]',
            'div.contact'
        ]
        
        for selector in phone_selectors:
            phone_elements = soup.select(selector)
            for element in phone_elements:
                element_text = element.text.strip()
                extracted_number = extract_phone_number(element_text)
                if extracted_number:
                    phone_number = extracted_number
                    if debug_mode and show_html:
                        st.success(f"電話番号が見つかりました（セレクタ: {selector}）: {phone_number}")
                    break
            if phone_number != "情報なし":
                break
        
        # If not found, search in the entire page text
        if phone_number == "情報なし":
            # Look for phone number in the entire page
            page_text = soup.get_text()
            extracted_number = extract_phone_number(page_text)
            if extracted_number:
                phone_number = extracted_number
                if debug_mode and show_html:
                    st.success(f"ページ全体から電話番号を検出: {phone_number}")
        
        # Extract website URL - try multiple selectors
        website_url = "情報なし"
        website_selectors = [
            'div.corpLink a', 
            'a.company-url', 
            'a[href*="http"]',
            'a[target="_blank"]' # Links that open in new window are often external website links
        ]
        
        for selector in website_selectors:
            elements = soup.select(selector)
            for element in elements:
                href = element.get('href', '')
                # Skip links to toranet.jp and very short URLs
                if href and len(href) > 10 and 'toranet.jp' not in href and href.startswith('http'):
                    website_url = href
                    if debug_mode and show_html:
                        st.success(f"WebサイトURLが見つかりました（セレクタ: {selector}）")
                    break
            if website_url != "情報なし":
                break
        
        # Extract job description - try multiple selectors
        job_description = "情報なし"
        description_selectors = [
            'div.jobDtlText.jobIntro', 
            'div.job-description', 
            'div.description',
            'div[class*="job"][class*="description"]',
            'div[class*="description"]',
            'div.jobDetail',
            'div.jobContent',
            'div.kyujin-detail',
            'section.detail',
            'div.detail-content',
            'div.job-content'
        ]
        
        for selector in description_selectors:
            job_description_elements = soup.select(selector)
            if job_description_elements:
                # Combine all matching elements
                combined_text = "\n\n".join([elem.text.strip() for elem in job_description_elements])
                if combined_text:
                    job_description = combined_text
                    if debug_mode and show_html:
                        st.success(f"業務内容が見つかりました（セレクタ: {selector}）")
                    break
        
        # Enhanced fallback mechanism for job description
        if job_description == "情報なし":
            # Try to find sections with job-related keywords
            keywords = ['仕事内容', '業務内容', '職務内容', 'お仕事', '職種']
            
            # First look for headings with these keywords
            for keyword in keywords:
                elements = soup.find_all(string=re.compile(keyword))
                if elements:
                    # For each element containing the keyword, look for nearby content
                    for element in elements:
                        parent = element.parent
                        # Try to get content from the next sibling or parent's next sibling
                        content = None
                        if parent.next_sibling:
                            content = parent.next_sibling
                        elif parent.parent and parent.parent.next_sibling:
                            content = parent.parent.next_sibling
                        
                        if content and hasattr(content, 'text'):
                            job_description = content.text.strip()
                            if debug_mode and show_html:
                                st.success(f"キーワード '{keyword}' から業務内容を検出")
                            break
                
                if job_description != "情報なし":
                    break
            
            # If still not found, try to look for any substantial text blocks
            if job_description == "情報なし":
                main_content_divs = soup.select('div.main-content, div.content, div.detail, div.job, article, section')
                for div in main_content_divs:
                    paragraphs = div.find_all(['p', 'div'], class_=lambda c: c and ('text' in c or 'content' in c))
                    if paragraphs:
                        job_description = "\n\n".join([p.text.strip() for p in paragraphs])
                        if debug_mode and show_html:
                            st.success("フォールバック方法で業務内容のテキストを抽出しました")
                        break
        
        # Get a shorter version of the job description for the table
        short_description = job_description[:100] + "..." if len(job_description) > 100 else job_description
        
        # Debug information - only show for HTML debug mode
        if debug_mode and show_html:
            st.info("### デバッグ情報 (開発者向け) ###")
            st.info(f"施設名セレクタの結果：{facility_name}")
            st.info(f"電話番号：{phone_number}")
            st.info(f"WebサイトURLセレクタの結果：{website_url}")
            st.info(f"業務内容セレクタの結果：{short_description}")
        
        return {
            "facility_name": facility_name,
            "phone_number": phone_number,
            "website_url": website_url,
            "job_description": job_description,
            "short_description": short_description,
            "source_url": detail_url
        }, None
    except Exception as e:
        st.error(f"詳細情報の解析中にエラーが発生しました: {str(e)}")
        if debug_mode:
            import traceback
            st.code(traceback.format_exc(), language="python")
        return None, f"詳細情報の解析中にエラーが発生しました: {str(e)}"

# Function to display job details in a table
def display_job_table(job_list):
    # Prepare data for the table
    table_data = []
    for job in job_list:
        table_data.append({
            "施設名": job['facility_name'],
            "電話番号": job['phone_number'],
            "業務内容": job['short_description'],
            "詳細": f"[詳細を表示]({job['source_url']})",
            "ウェブサイト": f"[サイトへ]({job['website_url']})" if job['website_url'] != "情報なし" else "情報なし"
        })
    
    # Convert to DataFrame and display
    df = pd.DataFrame(table_data)
    st.dataframe(df, use_container_width=True)

# Function to display full job details
def display_full_job_details(job):
    with st.expander(f"【詳細】{job['facility_name']}"):
        st.markdown(f"**施設名**: {job['facility_name']}")
        st.markdown(f"**電話番号**: {job['phone_number']}")
        
        if job['website_url'] != "情報なし":
            st.markdown(f"**ウェブサイト**: [{job['website_url']}]({job['website_url']})")
        else:
            st.markdown("**ウェブサイト**: 情報なし")
        
        st.markdown("**業務内容**:")
        st.markdown(job['job_description'])
        
        st.markdown(f"[元の求人情報を見る]({job['source_url']})")

# Test direct URL access
direct_url = st.sidebar.text_input("直接URLを入力（デバッグ用）") if debug_mode else None

# Search logic
if direct_url and debug_mode:
    st.info(f"直接入力されたURLを使用: {direct_url}")
    with st.spinner('URLから情報を取得中...'):
        job_details, error = get_job_details(direct_url)
        
        if error:
            st.error(error)
        elif job_details:
            # Display job details
            display_full_job_details(job_details)
elif search_keyword:
    with st.spinner('検索中...'):
        job_links, error, search_url = get_job_listings(search_keyword)
        
        # Display search URL for debugging
        if debug_mode:
            st.markdown(f"検索URL: [{search_url}]({search_url})")
        
        if error:
            st.error(error)
            if debug_mode:
                st.error("セレクタが変更された可能性があります。手動で確認してみてください。")
                st.markdown(f"[検索結果を直接確認する]({search_url})")
        elif job_links:
            job_list = []
            total_jobs = len(job_links)
            
            # Create a progress bar
            progress_bar = st.progress(0)
            status_text = st.empty()
            
            for idx, link in enumerate(job_links):
                status_text.text(f"求人情報を取得中... ({idx+1}/{total_jobs})")
                progress_bar.progress((idx+1)/total_jobs)
                
                if debug_mode:
                    st.info(f"求人詳細ページにアクセスしています: {link}")
                
                job_details, error = get_job_details(link)
                
                if error:
                    if debug_mode:
                        st.error(f"詳細ページの取得に失敗: {error}")
                        st.markdown(f"[詳細ページを直接確認する]({link})")
                elif job_details:
                    job_list.append(job_details)
            
            # Clear progress indicators
            progress_bar.empty()
            status_text.empty()
            
            # Display results
            if job_list:
                st.success(f"{len(job_list)}件の求人情報を取得しました！")
                
                # Display jobs in a table
                display_job_table(job_list)
                
                # Show full details in expandable sections
                st.subheader("📋 詳細情報")
                for job in job_list:
                    display_full_job_details(job)
            else:
                st.warning("求人情報を取得できませんでした。")
else:
    st.info("上の検索ボックスに職種名や施設名を入力してください。")
    if debug_mode:
        st.info("または、サイドバーから直接URLを入力してデバッグすることもできます。") 