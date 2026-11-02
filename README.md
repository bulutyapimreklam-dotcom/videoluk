# Videoluk

Videoluk, metin ve sahnelerden kendi sunucusunda video oluşturan bağımsız video stüdyosudur. Bu depo ilk çalışan CPU tabanlı MVP çekirdeğini içerir.

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
- `GET /api/media/search`
- `POST /api/voices/generate`
- `GET /api/voices/:id`
- `POST /api/projects`
- `POST /api/renders`
- `GET /api/renders/:id`
- `GET /api/renders/:id/download`
- `GET /api/renders/:id/subtitles`

Render işleri arka planda FFmpeg ile yürütülür. Dikey, yatay ve kare 1080p çıktı desteklenir.
