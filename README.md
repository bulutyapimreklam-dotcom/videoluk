# Videoluk

Videoluk, metin ve sahnelerden kendi sunucusunda video oluşturan bağımsız video stüdyosudur. Bu depo ilk çalışan CPU tabanlı MVP çekirdeğini içerir.

## Kurgu Beyni ve Kurgu DNA'sı

Videoluk yalnızca genel bir yapay zekâ promptuyla kurgu üretmez. Kurgu Beyni katmanı, deneyimli kurgu yönetmeninin prensiplerini her üretimde zorunlu şartname olarak uygular:

- Kanca süresi, ortalama plan uzunluğu, ritim dili ve anlatı yapısı
- Zorunlu kurgu kararları ve asla yapılmayacak tercihler
- Geçiş politikası ve sahne başına karar gerekçesi
- Timeline üzerinde düzeltilen işlerin “önce / sonra / neden” kaydı
- Seçili profile ait son düzeltmelerin yeni üretimlerde bağlam olarak kullanılması

Arayüzde **Kurgu DNA'sı → Düzenle** bölümünden ana profil tanımlanır. Timeline düzenlendikten sonra düzeltmenin nedeni **Bu düzeltmeyi öğret** ile kaydedilir. Bu yaklaşım, kontrolsüz fine-tuning yerine önce açıklanabilir kural + örnek geri çağırma katmanı kurar; yeterli onaylı örnek biriktiğinde aynı kayıtlar daha sonra model eğitimi için veri setine dönüştürülebilir.

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

Bu koruma ilk özel beta içindir; uygulama internete parolasız açılmaz. İleride çok kullanıcılı hesap sistemi eklendiğinde Caddy katmanındaki geçici beta parolası kaldırılabilir.

Render motoru varsayılan olarak bir işi aynı anda çalıştırır ve en fazla sekiz işi kuyruğa alır. Uygun CPU kapasitesi varsa `.env` içinde `VIDEOLUK_RENDER_WORKERS` artırılabilir. Sunucu yeniden başladığında `queued` veya `rendering` durumunda kalan işler otomatik olarak güvenli biçimde yeniden kuyruğa alınır.

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

Seslendirme sunucuda üretilir. macOS geliştirme ortamında sistemdeki `say`, Docker imajında ise açık kaynak `espeak-ng` kullanılır. Üretilen WAV dosyası proje renderına otomatik eklenir.

## API

- `GET /api/health`
- `POST /api/scripts/generate`
- `GET /api/editing-profiles`
- `POST /api/editing-profiles`
- `POST /api/editing-feedback`
- `GET /api/media/search`
- `POST /api/voices/generate`
- `GET /api/voices/:id`
- `POST /api/projects`
- `POST /api/renders`
- `GET /api/renders/:id`
- `GET /api/renders/:id/download`
- `GET /api/renders/:id/subtitles`

Render işleri arka planda FFmpeg ile yürütülür. Dikey, yatay ve kare 1080p çıktı desteklenir.

## Beta güvenlik sınırları

- API yalnızca aynı origin üzerinden erişime açıktır; ayrı bir web alanı kullanılacaksa `VIDEOLUK_ALLOWED_ORIGIN` açıkça tanımlanır.
- İstek gövdeleri 1 MB ile, stok medya indirmeleri 200 MB ile sınırlandırılır.
- Üretim trafiği Caddy HTTPS ve Basic Auth katmanından geçer.
- Render paralelliği ve kuyruk uzunluğu ortam değişkenleriyle sınırlıdır.
- API yanıtları önbelleğe alınmaz; iframe, kamera, mikrofon ve konum erişimi güvenlik başlıklarıyla kapatılır.
