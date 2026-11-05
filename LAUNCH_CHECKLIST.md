# Videoluk yayın planı

Bu plan maliyeti mümkün olduğunca geç başlatır. Kurgu DNA çalışması, referans videolar teslim edilene kadar kapsam dışındadır.

## 1. Şimdi: ücretsiz yerel beta

- `python3 scripts/acceptance_test.py` ile biyografi, tanıtım ve eğitim metinleri sınanır.
- Yatay, dikey ve kare proje yönleri doğrulanır.
- Gerçek MP4 render, seslendirme, SRT altyazı, indirme, kredi ve proje kaydı uçtan uca çalıştırılır.
- Yönetim ekranındaki **Yayına hazırlık merkezi** eksik bağlantıları gizli anahtar göstermeden listeler.
- Metin için yerel motor, görsel için Wikimedia/kullanıcı yüklemesi kullanılabildiğinden ücretli API zorunlu değildir.

## 2. Kapalı kullanıcı betası

Sunucu kiralamadan önce yerel ağda veya geliştirici bilgisayarında 3–5 kontrollü kullanıcıyla şu senaryolar denenir:

1. Biyografi videosu oluşturma ve metni elle düzeltme.
2. Pexels/Wikimedia arama ve kullanıcı medyası yükleme.
3. Seslendirme, altyazı stili ve timeline sahne sıralaması.
4. Yatay, dikey ve kare MP4 + SRT indirme.
5. Hatalı renderın yönetim ekranında görünmesi.

Her testte konu, süre, sonuç, hata ve kullanıcı yorumu kaydedilir. Kritik hata varken ticari yayına geçilmez.

## 3. Ücret başlatan yayın adımı

Yalnız beta kabul edildiğinde:

- Alan adı alınır ve HTTPS kullanan sunucuya yönlendirilir.
- `.env.example` kopyalanır; gerçek değerler yalnız sunucudaki `.env` dosyasına yazılır.
- `VIDEOLUK_AUTH_REQUIRED=1` ve `VIDEOLUK_SECURE_COOKIES=1` açılır.
- SMTP hesabı bağlanır; davet ve parola yenileme e-postaları denenir.
- Pexels anahtarı eklenir. Yapay zekâ metin/görsel sağlayıcıları kalite ve birim maliyet testi sonrasında açılır.
- `python3 scripts/validate_env.py .env` hatasız bitmeden servis dışarı açılmaz.

## 4. Canlı ödeme

- Önce iyzico sandbox anahtarlarıyla başarılı/başarısız/tekrar callback testleri yapılır.
- Şirket hesabı onaylandıktan sonra canlı API ve secret anahtarları girilir.
- `VIDEOLUK_IYZICO_BASE_URL` sandbox olmayan canlı adrese alınır.
- Gizlilik ve kullanım koşullarındaki `EKLENECEK` alanları gerçek ticari unvan, adres ve e-postayla doldurulur.
- Yönetim ekranı “Ticari yayına hazır” demeden gerçek satış açılmaz.

## 5. Kurgu DNA

Yaklaşık 100 referans video geldiğinde ayrı aşamada analiz edilir. Otomatik çıkarılan plan süreleri, ritim ve geçiş tercihleri önce yönetici onayından geçer; doğrudan kullanıcı üretimine uygulanmaz.
