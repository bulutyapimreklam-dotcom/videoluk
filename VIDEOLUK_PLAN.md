# Videoluk ürün ve teknik planı

## Ürün tanımı

Videoluk; kullanıcıdan video türü, süre, yön, görsel kaynağı ve metin alarak sahneleri hazırlayan, seslendirme ve altyazı üreten, tarayıcıda düzenleme imkânı veren ve videoyu kendi render altyapısında MP4 olarak teslim eden bağımsız bir video üretim platformudur.

Ana vaat: Türkiye odaklı, kolay kullanılan ve üretim maliyeti şeffaf bir yapay zekâ video stüdyosu.

## Kurgu Beyni yaklaşımı

Videoluk'un yaratıcı avantajı, kurgu kararlarını genel model zevkine bırakmamasıdır. Deneyimli medya profesyonelinin bilgisi üç katmanda korunur:

1. **Kurgu DNA:** Ritim, plan süresi, kanca, dramatik yapı, zorunlu ve yasak tercihler gibi açık kurallar.
2. **Onaylı örnek hafızası:** Kullanıcının timeline üzerinde yaptığı önce/sonra değişiklikleri ve değişikliğin gerekçesi.
3. **Model katmanı:** Kurallar ve ilgili örnekler üretim bağlamına eklenir. Yeterli kaliteli veri biriktiğinde versiyonlanmış eğitim/evaluation veri seti hazırlanır; model hiçbir zaman tek başına yaratıcı otorite olmaz.

Her otomatik sahne kararı `editingReason` alanıyla açıklanır. Böylece kullanıcı yalnızca sonucu değil, sistemin hangi kurgu prensibini uyguladığını da denetler.

## Marka sistemi

- Ürün adı: Videoluk
- Web uygulaması: app.videoluk.com
- Tanıtım sitesi: videoluk.com
- API: api.videoluk.com
- Dosya alanı: media.videoluk.com
- Sistem bileşenleri: videoluk-web, videoluk-api, videoluk-render, videoluk-ai-worker
- Varsayılan dil: Türkçe; altyapı çoklu dil desteğine hazır
- Ton: sade, güvenilir, üretken ve erişilebilir

## Kullanıcı akışı

1. Kullanıcı proje açar; video türünü, 9:16 / 16:9 / 1:1 yönünü ve süreyi seçer.
2. Görsel kaynağı olarak stok video, yapay zekâ görseli veya karma mod seçilir.
3. Metin ya da konu girilir; sistem senaryoyu sahnelere böler.
4. Her sahne için arama sorgusu veya görsel üretim istemi hazırlanır.
5. Kullanıcı stok sonuçlarını seçer ya da yapay zekâ görsellerini üretir.
6. Ses, müzik, altyazı ve sahne süreleri otomatik hazırlanır.
7. Timeline editörü açılır; sahneler, metin, medya ve ses düzenlenir.
8. Render işi kuyruğa alınır, ilerleme yüzdesi gösterilir.
9. Tamamlanan MP4, altyazı dosyası ve kapak görseli indirilebilir.

## Bağımsız sistem mimarisi

```text
Videoluk Web
    |
Videoluk API + kullanıcı/proje yönetimi
    |
PostgreSQL + Redis iş kuyruğu + S3 uyumlu medya deposu
    |                         |
AI Worker (isteğe bağlı GPU) Render Worker (CPU/FFmpeg)
    |                         |
Görsel / TTS / transkripsiyon MP4 / WebM / SRT / kapak
```

Tüm servisler Docker ile paketlenir. Sağlayıcıya özel kod yazılmaz; S3 uyumlu depolama, standart PostgreSQL ve Redis kullanılır. Böylece sistem Hetzner, RunPod, Vast.ai veya başka bir sunucuya taşınabilir.

## Maliyet stratejisi

- API, veritabanı ve normal video birleştirme sürekli açık, uygun fiyatlı CPU sunucusunda çalışır.
- FFmpeg render işleri mümkün olduğunca CPU üzerinde yapılır.
- GPU yalnızca yapay zekâ görseli, ağır transkripsiyon veya yerel model gerektiğinde açılır.
- GPU worker boşta tutulmaz; kuyruk geldiğinde çalışır ve iş bitince kapanır.
- Aynı görsel, ses ve ara render tekrar kullanılmak üzere önbelleğe alınır.
- Önizleme düşük çözünürlükte, son render seçilen çözünürlükte üretilir.
- Her proje başlamadan önce tahmini kredi/maliyet kullanıcıya gösterilir.

## MVP bileşenleri

### 1. Çekirdek platform

- E-posta ile kayıt ve oturum
- Proje kaydetme, çoğaltma ve silme
- Sahne JSON modeli ve otomatik kayıt
- Yükleme, dosya saklama ve imzalı indirme bağlantıları
- Kullanım kotası ve kredi kaydı

### 2. İçerik üretimi

- Metinden sahne planı
- Sahne başına anlatım, görsel istemi ve süre
- Pexels/Pixabay benzeri stok sağlayıcı adaptörü
- Yapay zekâ görsel sağlayıcı adaptörü
- Türkçe seslendirme sağlayıcı adaptörü
- Otomatik SRT/VTT altyazı

### 3. Editör

- Gerçek sahne listesi ve timeline
- Sürükle-bırak sıralama
- Sahne süresi değiştirme, bölme, çoğaltma ve silme
- Medya değiştirme ve yeniden üretme
- Seslendirme, müzik seviyesi ve altyazı stili
- Dikey, yatay ve kare canlı önizleme

### 4. Render motoru

- Kuyruk tabanlı asenkron işleme
- FFmpeg filter graph oluşturucu
- Pan/zoom, geçiş, metin, altyazı ve ses miksleme
- 720p önizleme; 1080p son çıktı
- İlerleme, hata tekrarı ve iptal
- MP4, kapak PNG, SRT ve VTT çıktıları

## Veri modeli

- users
- workspaces
- projects
- scenes
- media_assets
- voice_tracks
- caption_tracks
- render_jobs
- usage_events
- credit_transactions

Her proje sürümlenir. Render işi, o andaki proje sürümünün değişmez bir kopyasını kullanır; kullanıcı editöre devam etse bile çalışan render bozulmaz.

## Güvenlik ve operasyon

- API anahtarları sadece sunucu ortam değişkenlerinde tutulur.
- Kullanıcı yüklemeleri tür ve boyut kontrolünden geçirilir.
- İndirme/yükleme bağlantıları kısa ömürlü ve imzalıdır.
- Render worker dışarıya açık olmaz; sadece kuyruktan iş alır.
- İşler kullanıcı ve proje kimliğiyle izole edilir.
- Günlük veritabanı yedeği, hata takibi ve maliyet alarmı kurulur.

## Uygulama sırası

### Faz 1 — Gerçek çalışan temel

API, proje/sahne modeli, medya deposu, Redis kuyruğu ve Docker tabanlı FFmpeg worker. Kullanıcının yüklediği medya, metin, ses ve altyazıdan gerçek MP4 üretimi.

### Faz 2 — Otomatik üretim

Stok arama, sahne planlama, TTS ve altyazı üretimi. Sağlayıcılar adaptör üzerinden değiştirebilir olacak.

### Faz 3 — GPU ve yapay zekâ görseli

Scale-to-zero GPU worker, görsel üretme kuyruğu, önbellek ve maliyet ölçümü.

### Faz 4 — Ticari sürüm

Kredi paketleri, abonelik, ekip çalışma alanı, marka kiti, şablonlar, kullanım analitiği ve yönetim ekranı.

## İlk teslim hedefi

İlk gerçek MVP'nin kabul ölçütü: Kullanıcı bir metin girer, sistem en az üç sahne oluşturur, sahnelere stok veya yüklenmiş medya bağlar, Türkçe seslendirme ve altyazı üretir, timeline üzerinde düzenleme sunar ve bağımsız FFmpeg worker üzerinden indirilebilir 1080p MP4 hazırlar.

## Mevcut teslim durumu

İlk çalışan ürün hedefi tamamlandı:

- Fikirden düzenlenebilir Türkçe senaryo ve sahne planı
- Dikey, yatay ve kare proje oluşturma
- Pexels veya ücretsiz Wikimedia üzerinden otomatik stok medya yerleştirme
- OpenAI uyumlu, değiştirilebilir yapay zekâ görsel sağlayıcısı ve stok geri dönüşü
- Sunucu TTS seslendirmesi; geliştirme ortamında tarayıcı önizlemesi
- Sahne metni/görsel istemi düzenleme, medya değiştirme, bölme, çoğaltma, silme, hız ve sürükle-bırak sıralama
- Geri al/ileri al, tarayıcı taslağı ve SQLite sunucu otomatik kaydı
- Güvenli kullanıcı girişi, HttpOnly oturum ve kullanıcıya özel proje kütüphanesi
- Proje açma, sunucuda güncelleme, çoğaltma ve render dosyalarıyla birlikte silme
- Kullanıcıya özel görsel/video/logo/müzik kütüphanesi, güvenli dosya doğrulaması ve sahneye atama
- Timeline müzik kanalı, ses seviyesi ve seslendirmeyle FFmpeg miksleme
- Kullanıcı başına proje, depolama ve aylık render kotası; hesap ekranında kullanım göstergeleri
- Kredi bakiyesi, değişmez kredi hareketleri, render öncesi maliyet tahmini ve başarısız işte otomatik iade
- iyzico Checkout Form paket satışı, sunucu tarafı callback doğrulaması ve tek-seferlik kredi yükleme
- Tek komutlu üretim doğrulama/kurulum/sağlık/günlük yönetimi ve çevrimiçi SQLite + medya yedeği
- Owner rolüne özel kullanıcı, proje, depolama, render ve ödeme özetli yönetim ekranı
- Disk, kuyruk ve 24 saatlik hata ölçümleri; sınırlı sistem olay günlüğü ve yönetici uyarıları
- Sağlayıcıdan bağımsız HTTPS webhook hata alarmı, Bearer yetkilendirmesi ve tekrar bildirim koruması
- Owner tarafından kullanıcı oluşturma, kredi düzenleme, kullanıcıya özel kota ve hesap pasifleştirme
- Altyazı açma/kapama, stil ve konumun gerçek rendera aktarılması
- Kuyruklu FFmpeg render, yeniden başlatma kurtarması, MP4 ve SRT indirme
- Docker/Caddy üretim paketi, özel beta erişim koruması ve GitHub doğrulama hattı

Kurgu DNA eğitim katmanının sonraki geliştirmeleri ürün sahibinin isteğiyle ertelenmiştir. Mevcut profil ve geri bildirim altyapısı korunur; ana video üretim akışını engellemez.
