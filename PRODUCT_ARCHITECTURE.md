# Videoluk ürün ve altyapı mimarisi

## Ürün vaadi

Videoluk'un çıktısı tek tıkla rastgele hazırlanmış bir video değil, editoryal olarak
onaylanabilir ve timeline üzerinde düzeltilebilir bir ilk kurgu olmalıdır.

Referans yaklaşım:

- Pictory: senaryo ve sahne tabanlı üretim
- Descript: transkript merkezli ses ve görüntü senkronizasyonu
- CapCut: otomatik taslaktan tam timeline düzenlemeye geçiş
- InVideo: doğal dille yönetilen üretim ajanı ve işlem öncesi maliyet
- Fliki: kolay seslendirme, dil ve yerelleştirme

## Hedef üretim hattı

1. Fikir ve üretim şartnamesi
2. Düzenlenebilir senaryo
3. Sahne değil, tek görsel fikir içeren anlamsal plan listesi
4. Her plan için zaman kodlu seslendirme
5. Her plan için çok adaylı stok/AI medya araması
6. Anlamsal uygunluk, teknik kalite ve lisans puanlaması
7. Eşik altı adayların reddedilmesi
8. Kullanıcı storyboard onayı
9. Ses merkezli timeline
10. Sunucu render ve kalite kontrol
11. MP4, SRT ve medya lisans dökümü

## Servis sınırları

Mevcut tek dosyalı sunucu, ticari beta öncesinde aşağıdaki modüllere ayrılmalıdır:

- `story/`: senaryo, beat ve plan oluşturma
- `media/`: sağlayıcı adaptörleri, arama, önbellek ve puanlama
- `audio/`: TTS, kelime zaman kodları, müzik ve miks
- `timeline/`: proje şeması, sürümleme ve düzenleme işlemleri
- `render/`: FFmpeg kompozisyonu, kuyruk ve işçiler
- `billing/`: abonelik, kredi, maliyet ve kullanım kaydı
- `accounts/`: kullanıcı, ekip, rol ve çalışma alanları
- `quality/`: otomatik kontrol ve yayın kapısı

## Kalite kapıları

Bir plan ancak aşağıdaki şartları sağlarsa otomatik olarak timeline'a girebilir:

- Metin-medya anlam puanı minimum eşikten yüksek
- Doğru yön ve yeterli çözünürlük
- Lisans ve kaynak bilgisi mevcut
- Aynı projede gereksiz tekrar yok
- Medya süresi planı karşılıyor
- Filigran veya bozuk dosya yok
- Komşu planlarla dönem ve görsel dil çelişkisi kabul edilebilir

Eşik karşılanmazsa sistem yanlış medya yerleştirmez; kullanıcıya alternatif seçme,
medya yükleme veya AI üretme seçenekleri sunar.

## Maliyet modeli

Standart stok, timeline ve CPU render abonelik kotasına dahil edilebilir. Değişken ve
pahalı işler krediyle çalışmalıdır:

- üretken video
- üretken görsel
- premium ses veya ses klonlama
- premium stok
- yüksek çözünürlük veya hızlı render

Her iş başlamadan önce tahmini kredi, gerçek sağlayıcı maliyeti ve yeniden üretim
maliyeti kullanıcıya gösterilmelidir.

## Uygulama sırası

1. Pexels video sağlayıcısı ve medya lisans kaydı
2. Çok adaylı arama, tekrar engelleme ve kalite puanı
3. Sahne bazlı ses hattı ve ardından kelime seviyesinde forced alignment
4. Storyboard onayı ve medya alternatifleri
5. Gerçek çok kanallı timeline
6. Kalite kontrol raporu ve render öncesi engeller
7. Marka kiti, şablonlar ve Kurgu DNA
8. Abonelik, kredi ve canlı ödeme
9. Ayrı render işçileri, nesne depolama ve gözlemlenebilirlik
10. Ajans çalışma alanı ve müşteri onayı

