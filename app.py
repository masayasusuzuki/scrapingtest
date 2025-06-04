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

# メモリ使用量の最適化設定
optimize_memory = st.sidebar.checkbox("メモリ使用量を最適化", value=True)
enable_gc = st.sidebar.checkbox("定期的なメモリ解放", value=True) if optimize_memory else False

# User input
search_keyword = st.text_input("職種名や施設名を入力してください（例：看護師 渋谷メディカルクリニック）")

# 「開始」ボタンの追加
start_button = st.button("開始", type="primary")

# 取得件数の設定
max_jobs = st.sidebar.slider("取得する求人数", min_value=1, max_value=300, value=10)

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
    
    # デバッグ用に入力テキストを記録
    debug_text = text[:100] + "..." if len(text) > 100 else text
    
    # 電話番号のパターン（市外局番-市内局番-番号）
    patterns = [
        # フリーダイヤル（0120）パターン
        r'0120[\-\s]?\d{3}[\-\s]?\d{3}',  # 0120-123-456
        r'0120[\-\s]?\d{2}[\-\s]?\d{4}',  # 0120-12-3456
        r'0120\d{6}',  # 0120123456（ハイフンなし）
        
        # 標準的な電話番号パターン
        r'0\d{1,4}[-(]?\d{1,4}[)-]?\d{3,4}',  # 03-1234-5678 or 03(1234)5678
        
        # 特定キーワード後の電話番号
        r'電話番号[^\d]*([\d\-\(\)]{7,15})',  # 「電話番号：03-1234-5678」のようなパターン
        r'TEL[^\d]*([\d\-\(\)]{7,15})',  # 「TEL：03-1234-5678」のようなパターン
        r'Tel[^\d]*([\d\-\(\)]{7,15})',  # 「Tel：03-1234-5678」のようなパターン
        r'電話[^\d]*([\d\-\(\)]{7,15})',  # 「電話：03-1234-5678」のようなパターン
        
        # キーワード後のフリーダイヤル
        r'電話番号[^\d]*(0120[\-\s]?\d{3}[\-\s]?\d{3})',
        r'TEL[^\d]*(0120[\-\s]?\d{3}[\-\s]?\d{3})',
        r'Tel[^\d]*(0120[\-\s]?\d{3}[\-\s]?\d{3})',
        r'電話[^\d]*(0120[\-\s]?\d{3}[\-\s]?\d{3})',
        
        # 数字のみの塊を検出
        r'\D(0\d{9,10})\D',  # 0で始まる10-11桁の数字
        r'\D(\d{9,11})\D',   # 9-11桁の数字
        r'\D(\d{7})\D',      # 7桁の数字（0120の後半部分の可能性）
        
        # 5-6桁の番号パターン（最後の手段）
        r'\D(\d{5,6})\D',  # 単独の5-6桁の番号
    ]
    
    # まずフリーダイヤルを優先的に検索
    free_dial_patterns = patterns[0:3] + patterns[8:12]
    for pattern in free_dial_patterns:
        matches = re.search(pattern, text, re.IGNORECASE)
        if matches:
            # グループがキャプチャされている場合はそのグループを、されていない場合は全体を返す
            phone = matches.group(1) if len(matches.groups()) > 0 else matches.group(0)
            # 0120の後に7桁の数字がある場合、適切にフォーマット
            if re.match(r'0120\d{6}', phone):
                # 0120-XXX-XXX の形式に整形
                return f"{phone[:4]}-{phone[4:7]}-{phone[7:]}"
            return phone
    
    # 次に特定キーワード付きのパターンを検索
    keyword_patterns = patterns[4:8]
    for pattern in keyword_patterns:
        matches = re.search(pattern, text, re.IGNORECASE)
        if matches:
            # グループがキャプチャされている場合はそのグループを、されていない場合は全体を返す
            phone = matches.group(1) if len(matches.groups()) > 0 else matches.group(0)
            # 数字のみに変換してから整形
            digits = re.sub(r'[^\d]', '', phone)
            if len(digits) >= 10:
                if digits.startswith('0120') and len(digits) >= 10:
                    return f"{digits[:4]}-{digits[4:7]}-{digits[7:10]}"
                elif len(digits) == 10:
                    return f"{digits[:2]}-{digits[2:6]}-{digits[6:10]}"
                elif len(digits) == 11:
                    return f"{digits[:3]}-{digits[3:7]}-{digits[7:11]}"
            return phone
    
    # 数字のみのパターンを検索
    digit_patterns = patterns[12:15]
    for pattern in digit_patterns:
        # テキストの周りにスペースを追加して、パターン開始と終了のマッチを容易にする
        padded_text = f" {text} "
        matches = re.search(pattern, padded_text, re.IGNORECASE)
        if matches:
            digits = matches.group(1)
            if digits:
                # 10-11桁の数字
                if len(digits) >= 10:
                    if digits.startswith('0120'):
                        return f"{digits[:4]}-{digits[4:7]}-{digits[7:10]}"
                    elif len(digits) == 10:
                        return f"{digits[:2]}-{digits[2:6]}-{digits[6:10]}"
                    elif len(digits) == 11:
                        return f"{digits[:3]}-{digits[3:7]}-{digits[7:11]}"
                    else:
                        return digits
                # 7桁の数字（0120の後半部分の可能性）
                elif len(digits) == 7 and (digits.startswith('197') or digits.startswith('473')):
                    return f"0120-{digits[:3]}-{digits[3:7]}"
                # その他の数字
                else:
                    return digits
    
    # キーワードなしの通常パターンを検索
    for pattern in [patterns[3]] + patterns[15:]:
        matches = re.search(pattern, text, re.IGNORECASE)
        if matches:
            phone = matches.group(0)
            # 数字だけの場合、長さをチェック
            if re.match(r'^\d+$', phone):
                # 7桁の場合は0120の可能性を考慮
                if len(phone) == 7 and (phone.startswith('197') or phone.startswith('473')):
                    return f"0120-{phone[:3]}-{phone[3:]}"
                # その他の短い番号
                elif len(phone) <= 6:
                    return phone
            return phone
    
    # 最後の手段：すべての数字を抽出して可能性を検討
    digits_list = re.findall(r'\d+', text)
    for digits in digits_list:
        if len(digits) >= 10:  # 標準的な電話番号の長さ
            if digits.startswith('0120'):
                return f"{digits[:4]}-{digits[4:7]}-{digits[7:10] if len(digits) >= 10 else digits[7:]}"
            elif len(digits) == 10:
                return f"{digits[:2]}-{digits[2:6]}-{digits[6:10]}"
            elif len(digits) == 11:
                return f"{digits[:3]}-{digits[3:7]}-{digits[7:11]}"
        elif len(digits) == 7 and (digits.startswith('197') or digits.startswith('473')):
            return f"0120-{digits[:3]}-{digits[3:7]}"
    
    return None

# Function to clean text for extraction
def clean_text_for_extraction(text):
    if not text:
        return ""
    
    # HTMLタグを削除
    text = re.sub(r'<[^>]+>', ' ', text)
    
    # 不要な文字を削除
    text = re.sub(r'[\[\]【】［］()（）「」『』≪≫<>＜＞""\'\']+', ' ', text)
    
    # 連続する空白を1つにまとめる
    text = re.sub(r'\s+', ' ', text)
    
    return text.strip()

# Function to extract representative name from text
def extract_representative(text):
    if not text:
        return ""
    
    # テキストを前処理
    text = clean_text_for_extraction(text)
    
    # 代表者のパターン
    patterns = [
        # ラベル「代表者」の後に続く名前
        r'代表者\s*[\n\r:：]*\s*([^\n\r（(【［[{]+)',
        r'代表取締役\s*[\n\r:：]*\s*([^\n\r（(【［[{]+)',
        r'院長\s*[\n\r:：]*\s*([^\n\r:：（(【［[{]+)',
        r'理事長\s*[\n\r:：]*\s*([^\n\r:：（(【［[{]+)',
        # 「代表」「院長」単語の後に続く名前
        r'代表\s*[\n\r:：]*\s*([^\n\r:：（(【［[{]+)',
        r'院長\s*[\n\r:：]*\s*([^\n\r:：（(【［[{]+)',
        r'理事長\s*[\n\r:：]*\s*([^\n\r:：（(【［[{]+)'
    ]
    
    for pattern in patterns:
        matches = re.search(pattern, text, re.DOTALL)
        if matches and matches.group(1):
            # 取得した名前の前後の空白を削除
            name = matches.group(1).strip()
            # 不適切な値や短すぎる値は無視
            if name and name != "者" and len(name) > 1:
                # 不適切な値を除外
                if re.search(r'[】］）】\])]$', name) or name == "名" or "名】" in name or "株式会社" in name:
                    continue
                
                # 名前っぽくない文字列を除外
                if re.search(r'^\d+$', name) or re.search(r'^[A-Za-z0-9_\-\.]+$', name):
                    continue
                
                # 名前に含まれそうな余分な情報（住所など）を削除
                name = re.sub(r'所在住所.*$', '', name)
                name = re.sub(r'住所.*$', '', name)
                name = re.sub(r'[0-9０-９]{5,}.*$', '', name)  # 郵便番号などの数字が続くパターン
                name = re.sub(r'東京都.*$', '', name)  # 住所が含まれる場合
                name = re.sub(r'大阪府.*$', '', name)
                name = re.sub(r'神奈川県.*$', '', name)
                name = re.sub(r'埼玉県.*$', '', name)
                name = re.sub(r'千葉県.*$', '', name)
                name = re.sub(r'代表電話.*$', '', name)
                name = re.sub(r'事業内容.*$', '', name)
                
                # 最終的なクリーニング
                name = name.strip()
                if len(name) > 1:
                    return name
    
    return ""

# Function to extract address from text
def extract_address(text):
    if not text:
        return ""
    
    # テキストを前処理
    text = clean_text_for_extraction(text)
    
    # 住所のパターン
    patterns = [
        # 「勤務地」の後に続くテキスト
        r'勤務地\s*[\n\r:：]*\s*([^\n\r]{5,100})',
        # 「所在住所」または「所在地」の後に続くテキスト
        r'所在住所\s*[\n\r:：]*\s*([^\n\r]{5,100})',
        r'所在地\s*[\n\r:：]*\s*([^\n\r]{5,100})',
        # 郵便番号から始まる住所
        r'〒\d{3}-\d{4}\s*([^\n\r]{5,100})',
        r'\d{3}-\d{4}\s*([^\n\r]{5,100})',
        r'\d{7}\s*([^\n\r]{5,100})'
    ]
    
    for pattern in patterns:
        matches = re.search(pattern, text, re.DOTALL)
        if matches and matches.group(1):
            # 抽出した住所を整形（改行や余分なスペースを削除）
            address = matches.group(1).strip()
            address = re.sub(r'\s+', ' ', address)
            return address
    
    return ""

# Function to make requests with retry logic
def make_request(url, max_retries=5, timeout=30):
    # Validate URL before sending request
    if not is_valid_job_url(url):
        return None, f"無効なURL: {url}"
    
    for attempt in range(max_retries):
        try:
            # Add a random delay between requests
            if attempt > 0:
                # 再試行の場合は待機時間を長くする
                sleep_time = random.uniform(3, 7)
                if debug_mode:
                    st.warning(f"再試行のため {sleep_time:.1f} 秒待機しています...")
                time.sleep(sleep_time)
            else:
                # 初回リクエストの場合は短い待機時間
                time.sleep(random.uniform(0.5, 1.5))
            
            if debug_mode:
                st.info(f"リクエスト送信中: {url}")
            response = requests.get(url, headers=get_headers(), timeout=timeout)
            if debug_mode:
                st.success(f"ステータスコード: {response.status_code}")
            response.raise_for_status()
            return response, None
        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 503 and attempt < max_retries - 1:
                st.warning(f"サーバーが一時的に利用できません。再試行中... ({attempt+1}/{max_retries})")
                continue
            # その他のHTTPエラー
            return None, f"HTTPエラー: {e.response.status_code} - {e}"
        except requests.exceptions.Timeout:
            if attempt < max_retries - 1:
                st.warning(f"リクエストがタイムアウトしました。再試行中... ({attempt+1}/{max_retries})")
                continue
            return None, "リクエストがタイムアウトしました。サーバーが混雑している可能性があります。"
        except requests.exceptions.RequestException as e:
            if attempt < max_retries - 1:
                st.warning(f"リクエストエラーが発生しました。再試行中... ({attempt+1}/{max_retries})")
                continue
            return None, f"リクエストエラー: {str(e)}"
    
    return None, "最大再試行回数に達しました。後でもう一度お試しください。"

# Function to display HTML response
def display_html_response(response, title):
    if show_html and response:
        with st.expander(f"{title} - HTML表示"):
            # メモリ最適化のため、大きなHTMLの場合は一部のみを表示
            html_text = response.text
            if optimize_memory and len(html_text) > 20000:
                html_text = html_text[:10000] + "\n...(省略)..." + html_text[-10000:]
            
            st.code(html.escape(html_text), language="html")
            
            # 明示的にメモリ解放
            if enable_gc:
                html_text = None
                import gc
                gc.collect()

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
    base_search_url = f"https://toranet.jp/prefectures/tokyo/job_search/kw/{encoded_keyword}"
    
    # If direct_listing is checked, use the search URL directly
    if direct_listing:
        st.info("一覧ページを直接詳細ページとして使用します")
        return [base_search_url], None, base_search_url
    
    # ページネーション対応のために変数を準備
    all_job_links = []
    current_page = 1
    max_pages = 10  # 最大ページ数（安全のため）
    
    while len(all_job_links) < max_jobs and current_page <= max_pages:
        # ページURLを構築（1ページ目は通常のURL、2ページ目以降はページ番号を追加）
        if current_page == 1:
            search_url = base_search_url
        else:
            search_url = f"{base_search_url}/page/{current_page}"
        
        if debug_mode:
            st.info(f"ページ {current_page} の求人を取得中: {search_url}")
        
        response, error = make_request(search_url)
        if error:
            if current_page > 1:
                # 2ページ目以降でエラーが出た場合は、ページネーションの終了とみなす
                if debug_mode:
                    st.warning(f"ページ {current_page} の取得に失敗しました。これ以上のページはないと判断します。")
                break
            else:
                # 1ページ目からエラーの場合は本当のエラーとして処理
                return None, error, search_url
        
        # Display HTML for debugging
        display_html_response(response, f"検索結果ページ {current_page}")
        
        try:
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # Advanced link finding approach - get multiple links
            page_job_links = find_all_job_links(soup, search_url)
            
            if not page_job_links:
                if current_page == 1:
                    # 1ページ目でリンクがない場合は、検索ページ自体が求人詳細かチェック
                    if any(tag.name in ['h1', 'h2'] and ('求人情報' in tag.text or '仕事内容' in tag.text) for tag in soup.find_all(['h1', 'h2'])):
                        if debug_mode:
                            st.success("検索ページ自体が求人詳細ページのようです。直接使用します。")
                        return [search_url], None, search_url
                    
                    return None, "求人リンクが見つかりませんでした。サイト構造が変更された可能性があります。", search_url
                else:
                    # 2ページ目以降でリンクがない場合は、ページネーションの終了とみなす
                    if debug_mode:
                        st.info(f"ページ {current_page} には求人リンクがありません。これ以上のページはないと判断します。")
                    break
            
            # 新しく見つけたリンクを追加（重複を避けるためにセットを使用）
            existing_links = set(all_job_links)
            for link in page_job_links:
                if link not in existing_links and len(all_job_links) < max_jobs:
                    all_job_links.append(link)
                    existing_links.add(link)
            
            if debug_mode:
                st.success(f"ページ {current_page} から {len(page_job_links)} 件のリンクを取得しました。現在の合計: {len(all_job_links)} 件")
            
            # 次のページに進む
            current_page += 1
            
            # 既に十分な数のリンクが得られた場合は終了
            if len(all_job_links) >= max_jobs:
                if debug_mode:
                    st.info(f"設定された上限 {max_jobs} 件に達したため、ページネーションを終了します。")
                break
                
            # ページ間の待機時間を設定して、サーバー負荷を軽減
            if current_page <= max_pages:
                time.sleep(random.uniform(1.0, 3.0))
                
        except Exception as e:
            st.error(f"解析エラー: {str(e)}")
            import traceback
            if debug_mode:
                st.code(traceback.format_exc(), language="python")
            if current_page == 1:
                return None, f"パース中にエラーが発生しました: {str(e)}", search_url
            else:
                # 2ページ目以降のエラーは、ここまでのリンクを使って続行
                break
    
    if debug_mode:
        st.success(f"合計 {len(all_job_links)} 件の求人リンクを取得しました（{current_page-1} ページ探索）")
    
    # 1ページ目から最大ページ数まで探索して見つかったリンクを返す
    return all_job_links, None, base_search_url

# Function to clean facility name
def clean_facility_name(name):
    if not name:
        return "情報なし"
    
    # 「の求人詳細」などの不要なテキストを削除
    name = re.sub(r'の求人詳細$', '', name)
    name = re.sub(r'の求人情報$', '', name)
    name = re.sub(r'の求人$', '', name)
    name = re.sub(r'の募集詳細$', '', name)
    name = re.sub(r'の募集$', '', name)
    name = re.sub(r'の採用情報$', '', name)
    name = re.sub(r'詳細情報$', '', name)
    name = re.sub(r'詳細$', '', name)
    
    # さらに一般的なパターンを削除
    name = re.sub(r'の仕事$', '', name)
    name = re.sub(r'の仕事内容$', '', name)
    name = re.sub(r'の会社概要$', '', name)
    name = re.sub(r'の企業情報$', '', name)
    name = re.sub(r'【.*?】', '', name)  # 【】で囲まれた部分を削除
    name = re.sub(r'「.*?」', '', name)  # 「」で囲まれた部分を削除
    name = re.sub(r'\(.*?\)', '', name)  # ()で囲まれた部分を削除
    name = re.sub(r'（.*?）', '', name)  # （）で囲まれた部分を削除
    
    # とらばーゆ関連の文言を削除
    name = re.sub(r'とらばーゆ', '', name)
    name = re.sub(r'転職情報', '', name)
    
    # 職種名を削除（一般的な職種名のパターン）
    job_patterns = [
        '看護師', '介護士', '医師', '薬剤師', '理学療法士', '作業療法士', 
        '言語聴覚士', '保育士', '栄養士', '調理師', '事務', 'スタッフ',
        '正社員', 'パート', 'アルバイト', '契約社員', '派遣'
    ]
    for pattern in job_patterns:
        name = re.sub(f'{pattern}(募集)?$', '', name)
        name = re.sub(f'^{pattern}', '', name)
    
    # 連続する空白を1つにまとめる
    name = re.sub(r'\s+', ' ', name)
    
    # 前後の空白と不要な記号を削除
    name = name.strip()
    name = re.sub(r'^[、,.:：・]+', '', name)
    name = re.sub(r'[、,.:：・]+$', '', name)
    
    # 再度前後の空白を削除
    return name.strip()

# Function to scrape job details
def get_job_details(detail_url):
    # Validate URL before processing
    if not is_valid_job_url(detail_url):
        return None, f"無効な詳細ページURL: {detail_url}"
    
    # Add a slight delay before making the next request
    time.sleep(random.uniform(0.3, 1.0))
    
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
                # 施設名から不要なテキストを削除
                facility_name = clean_facility_name(facility_name)
                if debug_mode and show_html:
                    st.success(f"施設名が見つかりました（セレクタ: {selector}）")
                break
        
        # Fallback: Try to find text that looks like a company name (often near the top of the page)
        if facility_name == "情報なし":
            # Look for text that might be a company name (often near the top of the page)
            top_elements = soup.find_all(['div', 'span', 'p'], limit=20)
            for elem in top_elements:
                text = elem.text.strip()
                # Company names typically aren't very long and don't contain certain patterns
                if 5 < len(text) < 50 and ('株式会社' in text or '有限会社' in text or '病院' in text or 'クリニック' in text):
                    facility_name = text
                    # 施設名から不要なテキストを削除
                    facility_name = clean_facility_name(facility_name)
                    if debug_mode and show_html:
                        st.success(f"テキストパターンから施設名を検出: {text}")
                    break
            
            # さらにタイトルから施設名を抽出（最終手段）
            if facility_name == "情報なし":
                title_tag = soup.find('title')
                if title_tag:
                    title_text = title_tag.text.strip()
                    # よくあるタイトルパターン "求人 - 会社名" や "会社名の求人詳細"
                    for separator in ['|', '-', '：', ':', '／', '/']: 
                        if separator in title_text:
                            parts = title_text.split(separator)
                            for part in parts:
                                part = part.strip()
                                if 5 < len(part) < 50 and not re.search(r'求人|募集|採用|とらばーゆ|転職', part):
                                    facility_name = part
                                    # 施設名から不要なテキストを削除
                                    facility_name = clean_facility_name(facility_name)
                                    if debug_mode and show_html:
                                        st.success(f"タイトルから施設名を検出: {part}")
                                    break
                            if facility_name != "情報なし":
                                break
                    
                    # セパレータがない場合はタイトル全体から余計な部分を削除
                    if facility_name == "情報なし":
                        # 「求人」「募集」などの単語を削除
                        cleaned_title = re.sub(r'(求人|募集|採用|詳細)(情報)?', '', title_text)
                        cleaned_title = clean_facility_name(cleaned_title)
                        if 5 < len(cleaned_title) < 50:
                            facility_name = cleaned_title
                            if debug_mode and show_html:
                                st.success(f"クリーニングしたタイトルから施設名を検出: {cleaned_title}")
        
        # Extract representative name using label-based approach
        representative = ""
        
        # 0. HTMLクラスベースでの代表者検出（提供されたソースコードに基づく）
        representative_elements = soup.select('p.styles_content__HWIR6')
        for element in representative_elements:
            # 前の要素が「代表者」を含むh3であるかチェック
            prev_el = element.find_previous()
            if prev_el and prev_el.name == 'h3' and '代表者' in prev_el.text:
                # p要素の中身が空でないことを確認（空の場合は代表者なし）
                content = element.text.strip()
                if content and content != "者" and len(content) > 1:
                    if not re.search(r'[】］）】\])]$', content) and content != "名" and "名】" not in content:
                        # 余分な情報を削除
                        content = re.sub(r'所在住所.*$', '', content)
                        content = re.sub(r'住所.*$', '', content)
                        content = re.sub(r'[0-9０-９]{5,}.*$', '', content)
                        content = re.sub(r'東京都.*$', '', content)
                        content = re.sub(r'大阪府.*$', '', content)
                        content = re.sub(r'神奈川県.*$', '', content)
                        content = re.sub(r'埼玉県.*$', '', content)
                        content = re.sub(r'千葉県.*$', '', content)
                        content = re.sub(r'代表電話.*$', '', content)
                        content = re.sub(r'事業内容.*$', '', content)
                        
                        # 最終的なクリーニング
                        content = content.strip()
                        if len(content) > 1:
                            representative = content
                            
                        if debug_mode and show_html:
                            st.success(f"HTMLクラスから代表者を検出: {representative}")
                # 明示的に空のp要素を検出した場合は、代表者なしと判断してループを抜ける
                break
        
        # 1. 企業情報セクションを優先的に探す
        if not representative:
            company_info_sections = soup.find_all(['div', 'section'], string=lambda s: s and '企業情報' in s)
            company_info_sections += soup.find_all(['div', 'section'], class_=lambda c: c and ('company' in c or 'corp' in c))
            
            for section in company_info_sections:
                # セクション内で代表者情報を探す
                rep_labels = section.find_all(string=re.compile('代表者|代表取締役|院長|理事長'))
                for label in rep_labels:
                    parent = label.parent
                    # 隣接要素を探す
                    siblings = list(parent.next_siblings)
                    for sibling in siblings[:3]:  # 最初の3つの兄弟要素のみチェック
                        if hasattr(sibling, 'text') and sibling.text.strip():
                            name = sibling.text.strip()
                            if name and name != "者" and len(name) > 1:
                                if not re.search(r'[】］）】\])]$', name) and name != "名" and "名】" not in name:
                                    representative = name
                                    if debug_mode and show_html:
                                        st.success(f"企業情報セクションから代表者を検出: {representative}")
                                    break
                
                    if representative:
                        break
        
        # 2. If still not found, try generic extraction from the page
        if not representative:
            # Try table-based extraction
            tables = soup.find_all('table')
            for table in tables:
                rows = table.find_all('tr')
                for row in rows:
                    cells = row.find_all(['th', 'td'])
                    if len(cells) >= 2:
                        header = cells[0].text.strip()
                        if '代表者' in header:
                            name = cells[1].text.strip()
                            # 不適切な値をチェック
                            if name and name != "者" and len(name) > 1:
                                if not re.search(r'[】］）】\])]$', name) and name != "名" and "名】" not in name:
                                    representative = name
                                    if debug_mode and show_html:
                                        st.success(f"テーブルから代表者を検出: {representative}")
                                    break
        
        # 3. Last resort: use regex on entire page text
        if not representative:
            page_text = soup.get_text()
            extracted = extract_representative(page_text)
            if extracted:
                representative = extracted
                if debug_mode and show_html:
                    st.success(f"ページ全体から代表者を検出: {representative}")
        
        # Extract address using label-based approach - now looking for "勤務地" instead of "所在住所"
        location = ""
        
        # 0. HTMLクラスベースでの勤務地検出
        location_elements = soup.select('p.styles_content__HWIR6')
        for element in location_elements:
            # 前の要素が「勤務地」を含むh3であるかチェック
            prev_el = element.find_previous()
            if prev_el and prev_el.name == 'h3' and '勤務地' in prev_el.text:
                # p要素の中身が空でないことを確認
                content = element.text.strip()
                if content and len(content) > 5:  # 勤務地として十分な長さがあるか
                    location = content
                    if debug_mode and show_html:
                        st.success(f"HTMLクラスから勤務地を検出: {location}")
                    break
        
        # 1. 企業情報セクションを優先的に探す
        if not location and len(company_info_sections) > 0:
            for section in company_info_sections:
                # セクション内で勤務地情報を探す
                addr_labels = section.find_all(string=re.compile('勤務地|所在地|所在住所|住所'))
                for label in addr_labels:
                    parent = label.parent
                    # 隣接要素を探す
                    siblings = list(parent.next_siblings)
                    for sibling in siblings[:3]:  # 最初の3つの兄弟要素のみチェック
                        if hasattr(sibling, 'text') and sibling.text.strip():
                            addr_text = sibling.text.strip()
                            if addr_text and len(addr_text) > 5:  # 住所として十分な長さがあるか
                                location = addr_text
                                if debug_mode and show_html:
                                    st.success(f"企業情報セクションから勤務地を検出: {location}")
                                break
                    
                    if location:
                        break
                
                if location:
                    break
        
        # 2. Look for elements containing "勤務地" or "所在地" labels
        if not location:
            addr_elements = soup.find_all(string=re.compile("勤務地|所在地|所在住所"))
            for element in addr_elements:
                parent = element.parent
                
                # Check if the text is exactly the label (or close to it)
                if re.match(r'^(勤務地|所在地|所在住所)[:：]?$', element.strip()):
                    # 1-a. Try to find next sibling that contains the address
                    next_sibling = parent.next_sibling
                    if next_sibling and hasattr(next_sibling, 'text') and next_sibling.text.strip():
                        location = next_sibling.text.strip()
                        if debug_mode and show_html:
                            st.success(f"勤務地ラベルの次の要素から勤務地を検出: {location}")
                        break
                    
                    # 1-b. Try to find next element in parent
                    next_element = parent.find_next()
                    if next_element and next_element.text.strip():
                        location = next_element.text.strip()
                        if debug_mode and show_html:
                            st.success(f"勤務地ラベルの親要素の次の要素から勤務地を検出: {location}")
                        break
                
                # 2. Parent might contain both label and value
                parent_text = parent.text.strip()
                extracted = extract_address(parent_text)
                if extracted:
                    location = extracted
                    if debug_mode and show_html:
                        st.success(f"勤務地ラベルを含む要素から勤務地を抽出: {location}")
                    break
        
        # 3. If still not found, try table-based extraction
        if not location:
            tables = soup.find_all('table')
            for table in tables:
                rows = table.find_all('tr')
                for row in rows:
                    cells = row.find_all(['th', 'td'])
                    if len(cells) >= 2:
                        header = cells[0].text.strip()
                        if '勤務地' in header or '所在地' in header or '所在住所' in header or '住所' in header:
                            location = cells[1].text.strip()
                            if debug_mode and show_html:
                                st.success(f"テーブルから勤務地を検出: {location}")
                            break
        
        # 4. Last resort: use regex on entire page text
        if not location:
            page_text = soup.get_text()
            extracted = extract_address(page_text)
            if extracted:
                location = extracted
                if debug_mode and show_html:
                    st.success(f"ページ全体から勤務地を検出: {location}")
        
        # 会社名が勤務地に含まれているかチェック
        if location and facility_name and facility_name != "情報なし" and facility_name in location:
            # 会社名を最初に分離
            parts = location.split(facility_name)
            if len(parts) > 1:
                # 会社名の後のテキストを勤務地として使用
                location = parts[1].strip()
                # 先頭の余分な文字（コロンなど）を削除
                location = re.sub(r'^[、,:：\s]+', '', location)

        # 勤務地: などのプレフィックスを削除
        location = re.sub(r'^勤務地[：:]\s*', '', location)
        location = re.sub(r'^所在地[：:]\s*', '', location)
        location = re.sub(r'^住所[：:]\s*', '', location)

        # 余分な情報が続く場合は切り捨て
        location = re.sub(r'代表電話.*$', '', location)
        location = re.sub(r'事業内容.*$', '', location)
        location = re.sub(r'応募情報.*$', '', location)
        location = re.sub(r'選考プロセス.*$', '', location)

        # 最終的なクリーニング
        location = location.strip()
        
        # Extract phone number
        phone_number = "情報なし"
        
        # 0. HTMLクラスベースでの電話番号検出
        phone_elements = soup.select('p.styles_content__HWIR6')
        for element in phone_elements:
            # 前の要素が「代表電話番号」を含むh3であるかチェック
            prev_el = element.find_previous()
            if prev_el and prev_el.name == 'h3' and ('代表電話番号' in prev_el.text or '電話番号' in prev_el.text or 'TEL' in prev_el.text.upper()):
                # p要素の中身が空でないことを確認
                content = element.text.strip()
                if debug_mode and show_html:
                    st.info(f"電話番号候補（HTMLクラス）: {content}")
                if content:
                    # 数字のみを抽出
                    digits = re.sub(r'[^\d]', '', content)
                    if digits:
                        # 桁数に基づいて適切なフォーマットを適用
                        if len(digits) >= 10:  # 標準的な電話番号の桁数
                            if digits.startswith('0120') and len(digits) >= 10:
                                # フリーダイヤル: 0120-XXX-XXX
                                phone_number = f"{digits[:4]}-{digits[4:7]}-{digits[7:10]}"
                            elif len(digits) == 10:
                                # 固定電話: 03-XXXX-XXXX
                                phone_number = f"{digits[:2]}-{digits[2:6]}-{digits[6:10]}"
                            elif len(digits) == 11:
                                # 携帯電話: 090-XXXX-XXXX
                                phone_number = f"{digits[:3]}-{digits[3:7]}-{digits[7:11]}"
                            else:
                                # その他のケース
                                phone_number = digits
                        else:
                            # 桁数が少ない場合、0120の可能性を考慮
                            if len(digits) == 7 and (digits.startswith('197') or digits.startswith('473')):
                                phone_number = f"0120-{digits[:3]}-{digits[3:7]}"
                            else:
                                phone_number = digits
                        
                        if debug_mode and show_html:
                            st.success(f"HTMLクラスから代表電話番号を検出: {phone_number}")
                        break

        # もう一つのアプローチ: h3タグ「代表電話番号」の次にあるpタグを直接検索
        if phone_number == "情報なし":
            tel_headers = soup.find_all('h3', string=lambda s: s and ('代表電話番号' in s or '電話番号' in s or 'TEL' in s.upper()))
            for header in tel_headers:
                # 次の兄弟要素を取得
                next_elem = header.find_next()
                if next_elem and next_elem.name == 'p':
                    content = next_elem.text.strip()
                    if content:
                        # 数字のみを抽出
                        digits = re.sub(r'[^\d]', '', content)
                        if digits:
                            if len(digits) >= 10:
                                if digits.startswith('0120') and len(digits) >= 10:
                                    phone_number = f"{digits[:4]}-{digits[4:7]}-{digits[7:10]}"
                                elif len(digits) == 10:
                                    phone_number = f"{digits[:2]}-{digits[2:6]}-{digits[6:10]}"
                                elif len(digits) == 11:
                                    phone_number = f"{digits[:3]}-{digits[3:7]}-{digits[7:11]}"
                                else:
                                    phone_number = digits
                            else:
                                if len(digits) == 7 and (digits.startswith('197') or digits.startswith('473')):
                                    phone_number = f"0120-{digits[:3]}-{digits[3:7]}"
                                else:
                                    phone_number = digits
                            
                            if debug_mode and show_html:
                                st.success(f"h3タグの次のpタグから代表電話番号を検出: {phone_number}")
                            break

        # テーブル構造から電話番号を検索 - 「代表電話番号」というラベルを持つthの隣接tdを検索
        if phone_number == "情報なし":
            tel_th_elements = soup.find_all('th', string=lambda s: s and ('代表電話番号' in s or '電話番号' in s or 'TEL' in s.upper()))
            for th in tel_th_elements:
                # 隣接するtd要素を取得
                td = th.find_next_sibling('td')
                if td:
                    content = td.text.strip()
                    if content:
                        # 数字のみを抽出
                        digits = re.sub(r'[^\d]', '', content)
                        if digits:
                            if len(digits) >= 10:
                                if digits.startswith('0120') and len(digits) >= 10:
                                    phone_number = f"{digits[:4]}-{digits[4:7]}-{digits[7:10]}"
                                elif len(digits) == 10:
                                    phone_number = f"{digits[:2]}-{digits[2:6]}-{digits[6:10]}"
                                elif len(digits) == 11:
                                    phone_number = f"{digits[:3]}-{digits[3:7]}-{digits[7:11]}"
                                else:
                                    phone_number = digits
                            else:
                                if len(digits) == 7 and (digits.startswith('197') or digits.startswith('473')):
                                    phone_number = f"0120-{digits[:3]}-{digits[3:7]}"
                                else:
                                    phone_number = digits
                            
                            if debug_mode and show_html:
                                st.success(f"テーブル構造から代表電話番号を検出: {phone_number}")
                            break

        # 一般的なセレクタによる検索
        if phone_number == "情報なし":
            phone_selectors = [
                'div.tel', 
                'div.phone',
                'span.tel',
                'span.phone',
                'p.tel',
                'a[href^="tel:"]',
                'div.contact',
                'div.telNo',
                'p:contains("TEL")',
                'div:contains("TEL")',
                'p:contains("電話")',
                'div:contains("電話")'
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
        
        # Extract job description - try multiple selectors
        job_description = "情報なし"
        
        # 1. 「職種/仕事内容」セクションから情報を抽出
        job_sections = soup.find_all('h3', string=lambda s: s and ('職種/仕事内容' in s or '仕事内容' in s))
        for section in job_sections:
            # 親要素を取得
            parent_th = section.find_parent('th')
            if parent_th:
                # 隣接するtd要素を取得
                td = parent_th.find_next_sibling('td')
                if td:
                    content = td.text.strip()
                    if content:
                        job_description = content
                        if debug_mode and show_html:
                            st.success(f"「職種/仕事内容」セクションから業務内容を検出: {content[:100]}...")
                        break
        
        # 2. styles_content__cGhMI クラスを持つ要素から抽出（特定のクラス名を使用）
        if job_description == "情報なし":
            job_content_elements = soup.select('td.styles_content__cGhMI.styles_commonContent__NDgRD.styles_recruitCol__rbAHs')
            for element in job_content_elements:
                # 前の要素（th）に「職種/仕事内容」が含まれているか確認
                prev_th = element.find_previous('th')
                if prev_th and prev_th.find('p') and ('職種/仕事内容' in prev_th.text or '仕事内容' in prev_th.text):
                    content = element.text.strip()
                    if content:
                        job_description = content
                        if debug_mode and show_html:
                            st.success(f"styles_content__cGhMI クラスから業務内容を検出: {content[:100]}...")
                        break
        
        # 3. もともとあった様々なセレクタを使った検索方法（フォールバック）
        if job_description == "情報なし":
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
        
        # 4. Enhanced fallback mechanism for job description
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
            st.info(f"代表者：{representative if representative else '(情報なし)'}")
            st.info(f"勤務地：{location if location else '(情報なし)'}")
            st.info(f"電話番号：{phone_number}")
            st.info(f"業務内容セレクタの結果：{short_description}")
        
        # 各抽出ステップで代表者が取得できたら、そのたびに追加のクリーニングを行う
        if representative:
            # 余分な情報を削除
            representative = re.sub(r'所在住所.*$', '', representative)
            representative = re.sub(r'住所.*$', '', representative)
            representative = re.sub(r'[0-9０-９]{5,}.*$', '', representative)
            representative = re.sub(r'東京都.*$', '', representative)
            representative = re.sub(r'大阪府.*$', '', representative)
            representative = re.sub(r'神奈川県.*$', '', representative)
            representative = re.sub(r'埼玉県.*$', '', representative)
            representative = re.sub(r'千葉県.*$', '', representative)
            representative = re.sub(r'代表電話.*$', '', representative)
            representative = re.sub(r'事業内容.*$', '', representative)
            representative = re.sub(r'応募情報.*$', '', representative)
            representative = re.sub(r'選考プロセス.*$', '', representative)
            
            # 最終的なクリーニング
            representative = representative.strip()
        
        return {
            "facility_name": facility_name,
            "representative": representative,
            "location": location,  # 「所在住所」から「勤務地」に変更
            "phone_number": phone_number,
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
        # データを表示前に再度クリーニング
        facility_name = job['facility_name']
        
        representative = job['representative'] if job['representative'] else ""
        # 代表者データのクリーニング
        representative = re.sub(r'所在住所.*$', '', representative)
        representative = re.sub(r'住所.*$', '', representative)
        representative = re.sub(r'[0-9０-９]{5,}.*$', '', representative)
        representative = re.sub(r'東京都.*$', '', representative)
        representative = re.sub(r'大阪府.*$', '', representative)
        representative = re.sub(r'神奈川県.*$', '', representative)
        representative = re.sub(r'埼玉県.*$', '', representative)
        representative = re.sub(r'千葉県.*$', '', representative)
        representative = re.sub(r'代表電話.*$', '', representative)
        representative = re.sub(r'事業内容.*$', '', representative)
        representative = representative.strip()
        
        location = job['location'] if job['location'] else ""
        # 勤務地データのクリーニング
        location = re.sub(r'^勤務地[：:]\s*', '', location)
        location = re.sub(r'代表電話.*$', '', location)
        location = re.sub(r'事業内容.*$', '', location)
        location = re.sub(r'応募情報.*$', '', location)
        location = re.sub(r'選考プロセス.*$', '', location)
        location = location.strip()
        
        # 電話番号のクリーニングと整形
        phone_number = job['phone_number'] if job['phone_number'] != "情報なし" else ""
        
        # 電話番号の特殊処理
        if phone_number:
            # 数字だけの7桁の場合、0120の可能性を考慮
            if re.match(r'^\d{7}$', phone_number) and (phone_number.startswith('197') or phone_number.startswith('473')):
                phone_number = f"0120-{phone_number[:3]}-{phone_number[3:]}"
            # 数字だけで0で始まらない場合、0を前置
            elif re.match(r'^\d+$', phone_number) and not phone_number.startswith('0') and len(phone_number) > 5:
                if len(phone_number) == 9:  # 市外局番が抜けている可能性
                    phone_number = f"03-{phone_number[:4]}-{phone_number[4:]}"
                else:
                    phone_number = f"0{phone_number}"
            
            # 桁区切りがない場合は追加
            if re.match(r'^0\d{9,10}$', phone_number):
                if len(phone_number) == 10:  # 固定電話
                    phone_number = f"{phone_number[:2]}-{phone_number[2:6]}-{phone_number[6:]}"
                elif len(phone_number) == 11:  # 携帯電話
                    phone_number = f"{phone_number[:3]}-{phone_number[3:7]}-{phone_number[7:]}"
            
            # 数字とハイフン以外は削除
            phone_number = re.sub(r'[^\d\-]', '', phone_number)
        
        table_data.append({
            "施設名": facility_name,
            "代表者": representative,
            "所在地": location,
            "URL": job['source_url'],
            "電話番号": phone_number,
            "メールアドレス": "",  # プレースホルダー（将来的に実装）
            "主な事業内容": job['short_description']
        })
    
    # Convert to DataFrame and display
    df = pd.DataFrame(table_data)
    
    # カラム幅を設定して表示
    st.dataframe(
        df,
        use_container_width=True,
        hide_index=True,  # インデックス（行番号）を非表示
        column_config={
            "施設名": st.column_config.TextColumn("施設名", width="medium"),
            "代表者": st.column_config.TextColumn("代表者", width="small"),
            "所在地": st.column_config.TextColumn("所在地", width="large"),
            "URL": st.column_config.TextColumn("URL", width="medium"),
            "電話番号": st.column_config.TextColumn("電話番号", width="small"),
            "メールアドレス": st.column_config.TextColumn("メールアドレス", width="medium"),
            "主な事業内容": st.column_config.TextColumn("主な事業内容", width="large")
        }
    )

# Function to display full job details
def display_full_job_details(job):
    with st.expander(f"【詳細】{job['facility_name']}"):
        st.markdown(f"**施設名**: {job['facility_name']}")
        
        # 代表者情報（空の場合は表示しない）
        if job['representative']:
            # クリーニング
            representative = job['representative']
            representative = re.sub(r'所在住所.*$', '', representative)
            representative = re.sub(r'住所.*$', '', representative)
            representative = re.sub(r'[0-9０-９]{5,}.*$', '', representative)
            representative = re.sub(r'東京都.*$', '', representative)
            representative = re.sub(r'大阪府.*$', '', representative)
            representative = re.sub(r'神奈川県.*$', '', representative)
            representative = re.sub(r'埼玉県.*$', '', representative)
            representative = re.sub(r'千葉県.*$', '', representative)
            representative = re.sub(r'代表電話.*$', '', representative)
            representative = re.sub(r'事業内容.*$', '', representative)
            representative = representative.strip()
            
            st.markdown(f"**代表者**: {representative}")
        
        # 所在地情報（空の場合は表示しない）
        if job['location']:
            # クリーニング
            location = job['location']
            location = re.sub(r'^勤務地[：:]\s*', '', location)
            location = re.sub(r'代表電話.*$', '', location)
            location = re.sub(r'事業内容.*$', '', location)
            location = re.sub(r'応募情報.*$', '', location)
            location = re.sub(r'選考プロセス.*$', '', location)
            location = location.strip()
            
            st.markdown(f"**所在地**: {location}")
            
        st.markdown(f"**URL**: {job['source_url']}")
        
        # 電話番号情報（情報なしの場合は表示しない）
        if job['phone_number'] and job['phone_number'] != "情報なし":
            # 電話番号のクリーニング
            phone_number = job['phone_number']
            phone_number = re.sub(r'[^\d\-\(\)]', '', phone_number).strip()
            
            st.markdown(f"**電話番号**: {phone_number}")
        
        st.markdown("**主な事業内容**:")
        st.markdown(job['job_description'])

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
elif search_keyword and start_button:  # キーワードが入力されていて、かつ開始ボタンが押された場合
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
            
            # 進捗状況表示の改善
            st.info(f"合計 {total_jobs} 件の求人リンクが見つかりました。情報を取得しています...")
            
            # Create a progress bar
            progress_bar = st.progress(0)
            status_text = st.empty()
            
            # Create columns for real-time results
            result_placeholder = st.empty()
            
            # バッチサイズを設定（一度に表示を更新する件数）
            batch_size = min(10, total_jobs)
            next_update = batch_size
            
            # エラーカウンター
            error_count = 0
            error_limit = min(total_jobs // 2, 50)  # 最大エラー数（全体の半分か50のいずれか小さい方）
            
            for idx, link in enumerate(job_links):
                current_job_num = idx + 1
                status_text.text(f"求人情報を取得中... ({current_job_num}/{total_jobs})")
                progress_bar.progress(current_job_num/total_jobs)
                
                if debug_mode:
                    st.info(f"求人詳細ページにアクセスしています: {link}")
                
                job_details, error = get_job_details(link)
                
                if error:
                    error_count += 1
                    if debug_mode:
                        st.error(f"詳細ページの取得に失敗: {error}")
                        st.markdown(f"[詳細ページを直接確認する]({link})")
                    
                    # エラーが多すぎる場合は処理を中断
                    if error_count >= error_limit:
                        st.warning(f"エラーが多すぎるため、処理を中断します。取得済み: {len(job_list)}/{total_jobs}")
                        break
                elif job_details:
                    job_list.append(job_details)
                
                # バッチサイズごと、または最後の求人の場合に結果を更新
                if current_job_num >= next_update or current_job_num == total_jobs:
                    # 中間結果を表示
                    if job_list:
                        with result_placeholder.container():
                            st.success(f"現在 {len(job_list)}/{total_jobs} 件の求人情報を取得しました")
                            display_job_table(job_list)
                    next_update = min(next_update + batch_size, total_jobs)
                
                # メモリ使用量の最適化
                if enable_gc and current_job_num % 20 == 0:
                    import gc
                    gc.collect()
            
            # Clear progress indicators
            progress_bar.empty()
            status_text.empty()
            
            # Display final results
            if job_list:
                st.success(f"{len(job_list)}件の求人情報を取得しました！")
                
                # 最終結果を表示（result_placeholderを置き換え）
                result_placeholder.empty()
                
                # Display jobs in a table
                display_job_table(job_list)
                
                # メモリ使用量を考慮して詳細情報の表示を制御
                if len(job_list) > 50 and optimize_memory:
                    show_details = st.checkbox("詳細情報を表示する（大量のデータがあるため、表示には時間がかかる場合があります）")
                    if show_details:
                        st.subheader("📋 詳細情報")
                        for job in job_list:
                            display_full_job_details(job)
                else:
                    # Show full details in expandable sections
                    st.subheader("📋 詳細情報")
                    for job in job_list:
                        display_full_job_details(job)
            else:
                st.warning("求人情報を取得できませんでした。")
else:
    st.info("上の検索ボックスに職種名や施設名を入力し、「開始」ボタンをクリックしてください。")
    if debug_mode:
        st.info("または、サイドバーから直接URLを入力してデバッグすることもできます。") 