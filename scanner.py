import requests
import threading
import queue
import ipaddress
import os
import re
import random
import time

# --- KONFIGURASI HUNTER (ELITE FILTER & CROSS-COMBINATION) ---
THREADS_SCAN = 100       # Dioptimalkan untuk runner gratisan agar stabil
TIMEOUT_SCAN = 3         # Standar ketat untuk High Quality (HQ)
TEST_URL_DETAIL = "http://httpbin.org/get?show_env=1"
TEST_URL_QUALITY = "https://www.google.com"

# Port paling potensial yang sering bocor (Open Proxy/Mikrotik/Squid)
PORTS = [80, 8080, 3128, 1080, 8888, 7890, 9050, 5678]

hunted_results = []
q_scan = queue.Queue()
print_lock = threading.Lock()

# User-Agent Rotator untuk menghindari deteksi firewall agresif
UA_LIST = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0",
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_2 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.2 Mobile/15E148 Safari/604.1"
]

def get_anon(res_json, my_ip):
    origin = res_json.get('origin', '')
    if my_ip and my_ip in origin: return "Transparent"
    return "Elite" if not res_json.get('headers', {}).get('Via') else "Anonymous"

def hunter_worker(my_ip):
    # Menggunakan session per thread untuk efisiensi koneksi
    session = requests.Session()
    while not q_scan.empty():
        proxy = q_scan.get()
        # Mencoba dua protokol paling umum yang sering ditemukan saat scanning
        for proto in ['http', 'socks5']:
            try:
                px = {"http": f"{proto}://{proxy}", "https": f"{proto}://{proxy}"}
                headers = {"User-Agent": random.choice(UA_LIST)}
                
                # Tahap 1: Validasi Anonimitas & Header (Httpbin)
                r = session.get(TEST_URL_DETAIL, proxies=px, timeout=TIMEOUT_SCAN, headers=headers)
                if r.status_code == 200:
                    data_json = r.json()
                    
                    # Tahap 2: Validasi Kualitas Nyata (Wajib Tembus Google)
                    g = session.get(TEST_URL_QUALITY, proxies=px, timeout=5, headers=headers)
                    if g.status_code == 200:
                        ip_only = proxy.split(':')[0]
                        
                        # Tahap 3: Deteksi Negara & ISP (IP-API)
                        try:
                            # Mengambil detail negara dan nama ISP (Provider)
                            geo_url = f"http://ip-api.com/json/{ip_only}?fields=status,countryCode,isp"
                            c_req = session.get(geo_url, timeout=5)
                            c_data = c_req.json()
                            
                            if c_data.get('status') == 'success':
                                cc = c_data.get('countryCode', 'UN')
                                isp = c_data.get('isp', 'Unknown ISP')
                                # Potong nama ISP jika terlalu panjang agar rapi
                                isp_name = (isp[:25] + '..') if len(isp) > 25 else isp
                            else:
                                cc, isp_name = "UN", "Private/Unknown"
                        except:
                            cc, isp_name = "UN", "Lookup Error"
                        
                        anon = get_anon(data_json, my_ip)
                        # FORMAT FINAL: IP:PORT | PROTO | CC | ANON | ISP
                        result_entry = f"{proxy} | {proto.upper()} | {cc} | {anon} | {isp_name}"
                        
                        with print_lock:
                            print(f"[HUNTED SUCCESS] {result_entry}")
                        hunted_results.append(result_entry)
                        
                        # Jeda singkat untuk mematuhi rate limit API Geolocation gratisan
                        time.sleep(1.2)
                        break
            except:
                continue
        q_scan.task_done()

def main():
    # Buat folder output terpisah
    output_dir = 'results/hunted'
    if not os.path.exists(output_dir): os.makedirs(output_dir, exist_ok=True)
    
    # Ambil IP publik runner untuk pengecekan anonimitas
    try: 
        my_ip = requests.get("https://api.ipify.org", timeout=10).text
    except: 
        my_ip = None

    if not os.path.exists('results/all.txt'):
        print("Data all.txt tidak ditemukan. Jalankan main.py dulu!")
        return

    print("--- Memulai Hyper-Combination Hunter (Elite Filter) ---")
    
    # 1. Analisis Komponen IP Sukses (Gaya Kombinasi Silang)
    block_a_b = set() # Network Parent (Contoh: 120.29)
    block_c = set()   # Subnet Sukses (Contoh: .144)
    
    with open('results/all.txt', 'r') as f:
        for line in f:
            match = re.search(r'(\d+\.\d+\.\d+\.\d+)', line)
            if match:
                parts = match.group(1).split('.')
                block_a_b.add(f"{parts[0]}.{parts[1]}")
                block_c.add(parts[2])

    print(f"Menganalisis {len(block_a_b)} Network Parent...")

    # 2. GENERATE TARGET DENGAN LOGIKA KOMBINASI SILANG
    # Kita ambil 40 Parent secara acak untuk sesi perburuan ini
    parents_list = list(block_a_b)
    sampled_parents = random.sample(parents_list, min(len(parents_list), 40))
    
    for parent in sampled_parents:
        # Untuk setiap parent network, kita tebak 50 kombinasi IP potensial
        for _ in range(50):
            # Padukan blok A.B dengan blok C yang pernah sukses di tempat lain
            random_c = random.choice(list(block_c))
            # Blok D (Host) dipilih secara acak 1-254
            random_d = random.randint(1, 254)
            target_ip = f"{parent}.{random_c}.{random_d}"
            # Pasangkan dengan port random dari list port populer kita
            target_port = random.choice(PORTS)
            q_scan.put(f"{target_ip}:{target_port}")

    print(f"Total target perburuan: {q_scan.qsize()} kombinasi unik.")

    # 3. Jalankan Hunter Threads
    for _ in range(THREADS_SCAN):
        threading.Thread(target=hunter_worker, args=(my_ip,), daemon=True).start()
    
    q_scan.join()

    # 4. Simpan hasil buruan eksklusif (Append jika ingin menumpuk, 'w' jika ingin fresh)
    if hunted_results:
        file_path = f"{output_dir}/hunted_elite.txt"
        with open(file_path, "w") as f:
            f.write("\n".join(hunted_results))
        print(f"--- SELESAI: Berhasil mengamankan {len(hunted_results)} proxy buruan! ---")
    else:
        print("--- SELESAI: Belum ada proxy langka yang tertangkap jaring. ---")

if __name__ == "__main__":
    main()
