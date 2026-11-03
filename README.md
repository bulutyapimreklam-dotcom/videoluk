# Videoluk

Videoluk, metin ve sahnelerden kendi sunucusunda video oluşturan bağımsız video stüdyosudur. Bu depo ilk çalışan CPU tabanlı MVP çekirdeğini içerir.

## Kurgu Beyni ve Kurgu DNA'sı

Videoluk yalnızca genel bir yapay zekâ promptuyla kurgu üretmez. Kurgu Beyni katmanı, deneyimli kurgu yönetmeninin prensiplerini her üretimde zorunlu şartname olarak uygular:

- Kanca süresi, ortalama plan uzunluğu, ritim dili ve anlatı yapısı
- Zorunlu kurgu kararları ve asla yapılmayacak tercihler
- Geçiş politikası ve sahne başına karar gerekçesi
- Timeline üzerinde düzeltilen işlerin “önce / sonra / neden” kaydı
- Seçili profile ait son düzeltmelerin yeni üretimlerde bağlam olarak kullanılması
- Toplu referans video yükleme, FFmpeg ile kesme/plan ritmi analizi ve editör onaylı profil güncellemesi

Arayüzde **Kurgu DNA'sı → Düzenle** bölümünden ana profil tanımlanır. Aynı ekrandan MP4, MOV, M4V, WEBM veya MKV referanslar topluca yüklenebilir. Analiz motoru videoları sırayla işler; süre, yön, ses varlığı, kesme noktaları ve ortalama plan süresini çıkarır. Ölçümler editör onayı olmadan profile yazılmaz; **Analizi Kurgu DNA'ya uygula** ile onaylandığında ritim kuralına dönüşür. Timeline düzenlendikten sonra düzeltmenin nedeni **Bu düzeltmeyi öğret** ile ayrıca kaydedilebilir.

## Yerelde çalıştırma

Gereksinimler: Python 3.11+ ve FFmpeg.

```bash
python3 server.py
```

Ardından `http://127.0.0.1:8787` adresini açın.

## Docker ile çalıştırma

```bash
docker compose up --build
```

Oluşturulan proje kayıtları, MP4 dosyaları ve SRT altyazıları `videoluk-data` volume alanında saklanır.

## Üretim sunucusuna kurulum

Ubuntu/Debian tabanlı bir sunucuda Docker ve Docker Compose kurulduktan sonra:

```bash
cp .env.example .env
# .env içindeki alan adı ve gerekli sağlayıcı anahtarlarını düzenleyin
cd deploy
docker compose -f compose.production.yaml up -d --build
```

`VIDEOLUK_DOMAIN` gerçek alan adına ayarlandığında Caddy TLS sertifikasını otomatik yönetir. DNS kaydının sunucu IP adresine yönlenmiş, 80 ve 443 portlarının açık olması gerekir. Uygulama container'ı dışarıya doğrudan açılmaz; yalnızca Caddy üzerinden erişilir.

Üretim kurulumu HTTP Basic Auth ile korunur. Parola hash'ini sunucuda üretin ve çıktıyı `.env` dosyasındaki `VIDEOLUK_BASIC_AUTH_HASH` alanına tek tırnak içinde yazın:

```bash
docker run --rm caddy:2-alpine caddy hash-password --plaintext 'uzun-ve-guclu-parolaniz'
```

Üretim yönetimi tek komutlu yardımcıyla yapılır:

```bash
./deploy/manage.sh validate  # Güvenlik ve ortam ayarlarını kontrol eder
./deploy/manage.sh deploy    # Doğrular, imajı kurar ve servisleri başlatır
./deploy/manage.sh status    # Container ve API sağlık durumunu gösterir
./deploy/manage.sh logs      # Uygulama ve Caddy günlüklerini izler
./deploy/manage.sh backup    # Çalışan veritabanının tutarlı anlık görüntüsünü ve medyayı arşivler
```

Yedekler varsayılan olarak depo kökündeki `backups/` klasörüne UTC zaman damgasıyla yazılır. Başka bir disk kullanmak için `VIDEOLUK_BACKUP_DIR=/mnt/videoluk-backups` tanımlanabilir. Yedek arşivi SQLite çevrimiçi backup API'siyle alınan tutarlı veritabanını, kullanıcı medyasını, renderları ve ses dosyalarını içerir; API anahtarlarını içeren `.env` dosyasını içermez.

Bu dış koruma ilk özel beta içindir; uygulama internete parolasız açılmaz. Kullanıcı hesapları yeterince olgunlaştığında Caddy katmanındaki ortak beta parolası kaldırılabilir.

Videoluk ayrıca uygulama içinde kullanıcıya özel oturum ve proje izolasyonu uygular. `.env` içinde aşağıdaki alanlar doldurulur:

```env
VIDEOLUK_AUTH_REQUIRED=1
VIDEOLUK_ADMIN_EMAIL=yonetici@videoluk.com
VIDEOLUK_ADMIN_PASSWORD=uzun-ve-benzersiz-bir-parola
VIDEOLUK_SECURE_COOKIES=1
```

İlk yönetici hesabı sunucu ilk kez başlatıldığında oluşturulur. Parola PBKDF2-SHA256 ile rastgele tuz ve 310.000 iterasyon kullanılarak saklanır; düz parola veritabanına yazılmaz. Oturum çerezi `HttpOnly`, `SameSite=Strict` ve üretimde `Secure` olarak gönderilir. Her kullanıcı yalnızca kendi projelerini listeleyebilir, açabilir, güncelleyebilir, çoğaltabilir, render edebilir ve silebilir. Yerel geliştirmede `VIDEOLUK_AUTH_REQUIRED=0` kullanılır.

Render motoru varsayılan olarak bir işi aynı anda çalıştırır ve en fazla sekiz işi kuyruğa alır. Uygun CPU kapasitesi varsa `.env` içinde `VIDEOLUK_RENDER_WORKERS` artırılabilir. Sunucu yeniden başladığında `queued` veya `rendering` durumunda kalan işler otomatik olarak güvenli biçimde yeniden kuyruğa alınır.

Maliyet kontrolü için kullanıcı başına proje, depolama ve aylık render kotaları uygulanır. Varsayılan değerler 50 proje, 5 GB medya ve ayda 60 renderdır. Proje kütüphanesi bu kullanımı görsel olarak gösterir. Limitler `VIDEOLUK_MAX_PROJECTS_PER_USER`, `VIDEOLUK_MAX_STORAGE_BYTES_PER_USER` ve `VIDEOLUK_MAX_MONTHLY_RENDERS_PER_USER` değişkenleriyle paket veya sunucu kapasitesine göre ayarlanabilir.

Her hesap başlangıçta varsayılan 120 kredi alır. Render öncesinde video süresi, seslendirme ve yapay zekâ sahne sayısına göre tahmini kredi maliyeti gösterilir; kullanıcı onayladığında kredi hareketi değişmez bir işlem kaydı olarak saklanır. Başarısız renderın kredisi otomatik iade edilir. Başlangıç bakiyesi `VIDEOLUK_STARTER_CREDITS` ile ayarlanabilir. Ödeme sağlayıcısı daha sonra yalnızca pozitif kredi hareketi oluşturan katman olarak bağlanacaktır.

Kredi satın alma iyzico Checkout Form ile hazırlanmıştır. Kart verisi Videoluk'a uğramaz; kullanıcı iyzico ödeme sayfasına yönlendirilir. Callback tokenı sunucudan iyzico'ya tekrar sorgulanır, ödeme tutarı/sepet/para birimi ve fraud onayı eşleşmeden kredi eklenmez. Aynı sipariş ikinci kez kredi yükleyemez. Sandbox için `VIDEOLUK_IYZICO_API_KEY`, `VIDEOLUK_IYZICO_SECRET_KEY`, `VIDEOLUK_IYZICO_BASE_URL` ve HTTPS kullanan `VIDEOLUK_PUBLIC_BASE_URL` ayarlanmalıdır.

Sağlık kontrolü:

```bash
curl https://alan-adiniz.example/api/health
```

## Yapay zekâ metin motoru

Videoluk herhangi bir OpenAI-uyumlu metin servisine bağlanabilir. `.env.example` dosyasını `.env` olarak kopyalayıp aşağıdaki değerleri doldurun:

```env
VIDEOLUK_LLM_URL=https://saglayici-adresi.example
VIDEOLUK_LLM_MODEL=model-adi
VIDEOLUK_LLM_API_KEY=gizli-anahtar
```

Anahtar yalnızca sunucunun ortam değişkeninde tutulur ve tarayıcıya gönderilmez. Uzak model ayarlanmamışsa veya erişilemiyorsa Videoluk yerel, ücretsiz taslak motoruna otomatik döner. Aynı sözleşme Ollama ve diğer OpenAI-uyumlu yerel model sunucularıyla da kullanılabilir.

Biyografi ve “kimdir?” türündeki bilgi isteyen içeriklerde, harici dil modeli bağlı değilse Türkçe Wikipedia özeti kaynak olarak kullanılır. Böylece aynı genel cümlenin tekrarlandığı şablon yerine doğrulanabilir bilgi sahnelere ayrılır.

## Stok video ve seslendirme

Pexels üzerinden ücretsiz stok video aramak için `.env` dosyasına `VIDEOLUK_PEXELS_API_KEY` ekleyin. Anahtar yoksa sistem Wikimedia Commons üzerinde anahtarsız görsel aramasına geçer. Arayüz kaynak, üretici ve lisans bilgisini sonuçlarla birlikte gösterir. Seçilen medya render sırasında indirilir, güvenli alan adı kontrolünden geçirilir, 200 MB sınırıyla önbelleğe alınır ve sahnenin yönüne/süresine göre FFmpeg ile kadrajlanır.

Sahne oluşturma artık seçilen kaynağa göre medyayı otomatik hazırlar. **Stok görüntü** seçilirse her sahne için Pexels/Wikimedia aranır. **Yapay zekâ** seçilirse `VIDEOLUK_IMAGE_URL`, `VIDEOLUK_IMAGE_MODEL` ve `VIDEOLUK_IMAGE_API_KEY` ile tanımlanan OpenAI uyumlu görsel servisi kullanılır. Görsel motoru bağlı değilse üretim durmaz; sistem bunu arayüzde bildirip otomatik olarak ücretsiz stok medyaya geçer. Üretilen görseller sunucudaki kalıcı veri alanında saklanır ve render motoruna yerel dosya olarak aktarılır.

Seslendirme sunucuda üretilir. macOS geliştirme ortamında sistemdeki `say`, Docker imajında ise açık kaynak `espeak-ng` kullanılır. Üretilen WAV dosyası proje renderına otomatik eklenir.

Kullanıcılar editörün medya kütüphanesine JPG, PNG, WEBP, MP4, MOV, WEBM ve MKV dosyaları yükleyebilir; yüklemeler yalnızca kendi hesaplarına görünür ve sahnelere atanabilir. MP3, WAV, M4A, AAC, OGG ve FLAC müzikler timeline'daki müzik kanalına eklenir, ses seviyesi seçilir ve seslendirmeyle FFmpeg üzerinde mikslenir. Dosyalar uzantının yanı sıra FFprobe ile içerik türü açısından da doğrulanır. Dosya başına varsayılan sınır 500 MB'dir; `VIDEOLUK_MAX_UPLOAD_BYTES` ile değiştirilebilir.

## API

- `GET /api/health`
- `GET /api/auth/status`
- `POST /api/auth/login`
- `POST /api/auth/logout`
- `POST /api/scripts/generate`
- `GET /api/editing-profiles`
- `POST /api/editing-profiles`
- `POST /api/editing-feedback`
- `GET /api/training-videos?profileId=:id`
- `POST /api/training-videos?profileId=:id`
- `POST /api/training/apply`
- `GET /api/media/search`
- `POST /api/uploads`
- `GET /api/uploads?kind=:kind`
- `GET /api/uploads/:id`
- `GET /api/uploads/:id/thumbnail`
- `DELETE /api/uploads/:id`
- `POST /api/voices/generate`
- `GET /api/voices/:id`
- `POST /api/images/generate`
- `GET /api/images/:id`
- `POST /api/projects`
- `GET /api/projects`
- `GET /api/projects/:id`
- `GET /api/usage`
- `POST /api/cost-estimate`
- `GET /api/credit-packages`
- `POST /api/payments/iyzico/checkout`
- `POST /api/payments/iyzico/callback`
- `POST /api/projects/:id/duplicate`
- `DELETE /api/projects/:id`
- `POST /api/renders`
- `GET /api/renders/:id`
- `GET /api/renders/:id/download`
- `GET /api/renders/:id/subtitles`

Render işleri arka planda FFmpeg ile yürütülür. Dikey, yatay ve kare 1080p çıktı desteklenir.

Editör; sahne başlığı ve seslendirme metni düzenleme, görsel istemini değiştirme, seçili medyayı yeniden üretme, stoktan veya kullanıcı kütüphanesinden değiştirme, sahne bölme/çoğaltma/silme/sürükleyerek sıralama, hız değiştirme, müzik seçme ve geri al/ileri al özelliklerini içerir. Taslak tarayıcıda otomatik saklanır. Altyazının açık/kapalı durumu, stili, konumu, müzik ve ses seviyesi sunucu renderına aktarılır.

## Beta güvenlik sınırları

- API yalnızca aynı origin üzerinden erişime açıktır; ayrı bir web alanı kullanılacaksa `VIDEOLUK_ALLOWED_ORIGIN` açıkça tanımlanır.
- JSON istek gövdeleri 1 MB, stok medya indirmeleri 200 MB, kullanıcı medyası 500 MB ve eğitim videosu başına yükleme varsayılan olarak 2 GB ile sınırlandırılır.
- Üretim trafiği Caddy HTTPS ve Basic Auth katmanından geçer.
- Render paralelliği ve kuyruk uzunluğu ortam değişkenleriyle sınırlıdır.
- API yanıtları önbelleğe alınmaz; iframe, kamera, mikrofon ve konum erişimi güvenlik başlıklarıyla kapatılır.
