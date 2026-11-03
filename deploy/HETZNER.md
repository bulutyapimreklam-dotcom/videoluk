# Videoluk için Hetzner kurulumu

## Başlangıç sunucusu

- Konum: Nuremberg (`nbg1`)
- Sistem: Ubuntu 24.04
- Plan: CX33, 4 paylaşımlı vCPU, 8 GB RAM, 80 GB NVMe
- Ağ: IPv4 ve IPv6
- Yedek: Hetzner günlük backup açık
- Güvenlik duvarı: TCP 22 yalnızca yönetici IP'si; TCP 80 ve 443 herkese açık

İlk beta için ayrı GPU sunucusu açılmaz. FFmpeg renderları CX33 üzerinde yürür; yapay zekâ görsel üretimi API üzerinden sağlanır. Kullanım büyüyünce video render worker ayrı bir dedicated CPU sunucuya, görsel üretimi ise sıfıra ölçeklenen GPU servisine taşınır.

## Oluşturma sırası

1. Hetzner Cloud içinde `videoluk-production` projesi oluşturun.
2. Kendi bilgisayarınızdaki SSH public key'i hesaba ekleyin.
3. Yukarıdaki özelliklerle `videoluk-app-1` sunucusunu oluşturun.
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

## Kapasite yükseltme eşiği

- Render kuyruğu sürekli 3 işin üzerinde kalırsa önce CX43'e yükseltin.
- Disk %70'e ulaştığında eski renderlar için saklama politikası uygulayın veya Volume ekleyin.
- Yapay zekâ görsel işleri ayda yaklaşık 40 GPU saatini aşarsa serverless ile sürekli GPU pod maliyetini yeniden karşılaştırın.
- Günlük yedeği aynı sunucuda bırakmayın; Storage Box veya S3 uyumlu object storage'a kopyalayın.
