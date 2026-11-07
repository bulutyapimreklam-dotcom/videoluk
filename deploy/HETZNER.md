# Videoluk için Hetzner kurulumu

## Başlangıç sunucusu

- Konum: Nuremberg (`nbg1`)
- Sistem: Ubuntu 24.04
- Plan: CX23, 2 paylaşımlı vCPU, 4 GB RAM, 40 GB NVMe
- Ağ: IPv4 ve IPv6
- Render: aynı anda 1 iş; yoğunluk oluşursa CX33'e çevrimiçi büyütme
- Yedek: ilk denemede ücretli backup kapalı; veri alınmaya başladığında açılır
- Güvenlik duvarı: TCP 22 yalnızca yönetici IP'si; TCP 80 ve 443 herkese açık

Kasım 2026 resmi liste fiyatıyla CX23 Almanya'da IPv4 ve vergi hariç aylık €5,49'dur. Sunucu saatlik ücretlenir ve aylık üst sınıra ulaşır; deneme başarısız olursa silindiği ana kadar kullanılan saat kadar ücret oluşur. Birincil IPv4, vergi ve isteğe bağlı backup ayrıca fiyatlanır.

İlk beta için ayrı GPU sunucusu açılmaz. FFmpeg renderları CX23 üzerinde yürür; yapay zekâ görsel üretimi API üzerinden sağlanır. Bu seçim düşük maliyetlidir fakat 1080p render CX33'e göre daha yavaş tamamlanır. Render kuyruğu oluşunca sunucu CX33'e büyütülür; daha sonra video render worker ayrı bir dedicated CPU sunucuya, görsel üretimi ise sıfıra ölçeklenen GPU servisine taşınır.

## Oluşturma sırası

1. Hetzner Cloud içinde `videoluk-production` projesi oluşturun.
2. Kendi bilgisayarınızdaki SSH public key'i hesaba ekleyin.
3. Yukarıdaki özelliklerle `videoluk-app-1` sunucusunu oluşturun. İlk kurulumda ücretli backup seçmeyin.
4. Cloud Firewall ekleyin. SSH anahtarınızın kaybolması durumunda Hetzner Rescue Console kurtarma yoludur.
5. Sunucu IP'sini alan adının `A` kaydına yazın; `AAAA` kullanacaksanız IPv6 kaydını da ekleyin.
6. SSH ile bağlanıp bu depoyu klonlayın ve kurulumu çalıştırın:

```bash
ssh root@SUNUCU_IP
git clone https://github.com/bulutyapimreklam-dotcom/videoluk.git /tmp/videoluk-install
bash /tmp/videoluk-install/deploy/bootstrap-ubuntu.sh
cp /opt/videoluk/.env.example /opt/videoluk/.env
```

7. `/opt/videoluk/.env` içindeki alan adı, yönetici parolası, Basic Auth hash'i ve sağlayıcı anahtarlarını doldurun.
8. Uygulamayı doğrulayıp başlatın:

```bash
sudo -u videoluk /opt/videoluk/deploy/manage.sh validate
sudo -u videoluk /opt/videoluk/deploy/manage.sh deploy
sudo -u videoluk /opt/videoluk/deploy/manage.sh status
```

9. Gerçek kullanıcı verisi alınmadan önce en az bir yedeği başka bir cihaza indirin. Kapalı beta başladığında Hetzner backup'ı açın veya `manage.sh backup` çıktısını ayrı depolamaya zamanlayın.

## Kapasite yükseltme eşiği

- Tek bir 30 saniyelik 1080p render düzenli olarak 3 dakikayı aşıyorsa veya kuyruk sürekli 2 işin üzerinde kalırsa CX33'e yükseltin.
- CX33 üzerinde kuyruk sürekli 3 işin üzerinde kalırsa CX43'e yükseltin.
- Disk %70'e ulaştığında eski renderlar için saklama politikası uygulayın veya Volume ekleyin.
- Yapay zekâ görsel işleri ayda yaklaşık 40 GPU saatini aşarsa serverless ile sürekli GPU pod maliyetini yeniden karşılaştırın.
- Günlük yedeği aynı sunucuda bırakmayın; Storage Box veya S3 uyumlu object storage'a kopyalayın.
