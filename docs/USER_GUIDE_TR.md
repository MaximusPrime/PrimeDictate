# PrimeDictate Kullanıcı Kılavuzu

Bu kılavuz PrimeDictate `1.0.0` sürümünün günlük kullanımını, yerel ve bulut seçeneklerinin farklarını, veri akışını ve temel sorun giderme adımlarını açıklar.

## İçindekiler

- [Temel çalışma modeli](#temel-çalışma-modeli)
- [İlk kurulum](#ilk-kurulum)
- [Ana sayfa](#ana-sayfa)
- [Ses → Metin ayarları](#ses--metin-ayarları)
- [Dikte dili](#dikte-dili)
- [Metin İşleme ve API](#metin-işleme-ve-api)
- [Ses ve kısayollar](#ses-ve-kısayollar)
- [Yüzen kayıt göstergesi](#yüzen-kayıt-göstergesi)
- [Dosya transkripsiyonu](#dosya-transkripsiyonu)
- [Geçmiş ve tanılama](#geçmiş-ve-tanılama)
- [Gizlilik](#gizlilik)
- [Önerilen yapılandırmalar](#önerilen-yapılandırmalar)
- [Sorun giderme](#sorun-giderme)

## Temel Çalışma Modeli

PrimeDictate iki bağımsız aşamadan oluşur:

```text
1. SES → METİN
   Mikrofon kaydı, seçilen STT motoruyla transkripte dönüştürülür.

2. METİN İŞLEME
   İstenirse transkript kural tabanlı yöntemle veya bir LLM ile düzenlenir.
```

Birinci aşama zorunludur. İkinci aşama kapatılabilir.

Önemli ayrım:

| Seçim | Görevi |
|---|---|
| STT motoru | Sesi yazıya dönüştürür |
| STT modeli | Ses tanıma doğruluğunu ve performansını belirler |
| Metin işleme yöntemi | Oluşan yazıyı temizler veya yeniden biçimlendirir |
| Metin işleme modeli | Yalnızca LLM tabanlı düzenlemede kullanılır |

Bulut STT seçmek, metin düzenlemeyi otomatik olarak buluta taşımaz. Yerel STT kullanırken bulut LLM seçmek de sesi buluta göndermez; yalnızca oluşan transkript metni ilgili servise gider.

## İlk Kurulum

1. PrimeDictate'i başlatın.
2. **Ses → Metin** sayfasını açın.
3. STT çalışma konumunu seçin.
4. Yerel motor seçtiyseniz bir Whisper modeli seçip indirin.
5. Bulut STT seçtiyseniz sağlayıcıyı, modeli ve gerekli API anahtarını ayarlayın.
6. Konuşacağınız dili seçin veya **Otomatik algıla** seçeneğini kullanın.
7. **Metin İşleme & API** sayfasında düzenleme davranışını belirleyin.
8. **Ses & Kısayollar** sayfasından mikrofonu ve global kısayolu kontrol edin.
9. **Ayarları Kaydet** düğmesine basın.

Varsayılan kısayol `Ctrl+Alt+D`, çalışma biçimi ise bas-aç modudur.

## Ana Sayfa

Ana sayfa etkin yapılandırmanın kısa özetini gösterir:

- Aktif STT motoru
- Aktif model
- Seçilen veya algılanan konuşma dili
- Global kısayol
- Yerel/bulut gizlilik durumu

Otomatik dil kullanılırken CPU veya CUDA motoru güven bilgisi sağlayabiliyorsa algılanan dil ve güven yüzdesi burada gösterilir. Bu bilgiyi sağlamayan motorlarda PrimeDictate tahmini bir yüzde üretmez.

## Ses → Metin Ayarları

### Yerel CPU

Whisper modeli bilgisayarın işlemcisinde çalışır.

Uygun olduğu durumlar:

- En geniş donanım uyumluluğu isteniyorsa
- Sesin cihazdan çıkmaması gerekiyorsa
- Uyumlu GPU bulunmuyorsa

Büyük modeller CPU üzerinde daha yavaş çalışabilir.

### Yerel GPU - CUDA

Whisper modeli NVIDIA ekran kartında çalışır.

Gereksinimler:

- Uyumlu NVIDIA ekran kartı
- Güncel NVIDIA sürücüsü
- Seçilen model için yeterli ekran kartı belleği

CUDA `float16` yüklemesi başarısız olursa uygulama desteklendiği ölçüde `int8` yüklemeyi dener. Motor hatası ve açık kullanıcı izni varsa yapılandırılmış bulut fallback devreye girebilir.

### Yerel GPU - Vulkan

PrimeDictate, Vulkan desteğiyle derlenmiş whisper.cpp çalışma zamanını kullanır. AMD ve Intel GPU'lar için temel yerel hızlandırma seçeneğidir; uyumlu NVIDIA cihazlarda da kullanılabilir.

Uygulama açıldıktan sonra seçilen model arka planda hazırlanır. Dahili `whisper-server` modeli bellekte tutarak ardışık diktelerde tekrar model yükleme maliyetini kaldırır. İlk hazırlık birkaç saniye sürebilir; sonraki dikteler aynı kalıcı motoru kullanır. Sunucu yalnızca yerel bilgisayardaki `127.0.0.1` adresine, rastgele porta ve o çalıştırmaya özel gizli istek yoluna bağlanır. Başlatılamazsa uygulama doğrulanmış tek-seferlik CLI yöntemine otomatik döner.

Uygulama:

- Dahili runtime dosyalarının SHA-256 bütünlüğünü kontrol eder.
- CLI'ın gerçek Vulkan backend içerdiğini doğrular.
- Kalıcı server'ı yalnızca doğrulanmış CLI ile aynı runtime klasöründen çalıştırır.
- Algılanan Vulkan cihazını gösterir.
- İleri seviye kullanım için özel `whisper-cli.exe` seçimine izin verir.

Runtime'ın doğrulanması, sürücü ve donanımın çalışmayı kesin olarak başaracağı anlamına gelmez.

### Bulut STT

Bulut STT seçildiğinde ses kaydı seçilen sağlayıcıya gönderilir. Yerel Whisper modeli indirilmez veya kullanılmaz.

Desteklenen entegrasyonlar:

| Sağlayıcı | Kullanım biçimi |
|---|---|
| Groq | Uzak Whisper transkripsiyonu |
| OpenAI | Seçilen OpenAI transkripsiyon modeli |
| Google Gemini | Güvenli transkripsiyon talimatıyla multimodal ses işleme |

Gemini dil yönlendirmesi yapılandırılmış Whisper dil alanı yerine model talimatıyla uygulanır. Sonuç davranışı seçilen Gemini modeline ve servis erişimine bağlıdır.

### Bulut Fallback

**Yerel motor başarısızsa buluta geçmeme izin ver** seçeneği varsayılan olarak kapalı tutulmalıdır. Açıldığında ses, yalnızca yerel STT işlemi hata verirse yapılandırılmış bulut sağlayıcıya gönderilebilir.

Bu seçenek açıkken kullanılacak bulut sağlayıcı ve model, yerel motor ayarlarının altında ayrıca gösterilir.

## Yerel Model Boyutu

| Model | Hız | Bellek ihtiyacı | Genel öneri |
|---|---|---|---|
| `tiny` | En yüksek | En düşük | Kısa kayıtlar ve zayıf donanım |
| `base` | Çok yüksek | Düşük | Hafif günlük kullanım |
| `small` | Dengeli | Orta | Genel dikte için iyi denge |
| `medium` | Daha düşük | Yüksek | Doğruluk odaklı kullanım |
| `large-v3-turbo` | Donanıma bağlı | En yüksek | Güçlü donanım ve çok dilli doğruluk |

Bu seçim sadece yerel motorlarda görünür. Bulut sağlayıcıların uzak modelleri kendi alanından seçilir.

## Dikte Dili

PrimeDictate, Whisper'ın çok dilli kataloğundaki 100 dili sunar. Liste aranabilir yapıdadır.

Belirli bir dil seçmenin avantajları:

- Dil algılama aşamasını atlayabilir.
- Kısa kayıtlarda yanlış dil algılama riskini azaltabilir.
- Destekleyen bulut sağlayıcılara doğru dil ipucunu iletebilir.

**Otomatik algıla** şu durumlarda uygundur:

- Farklı diller arasında sık geçiş yapılıyorsa
- Dosyanın dili önceden bilinmiyorsa
- Tek yapılandırmayla çok dilli kayıtlar işlenecekse

Dosya transkripsiyonunda güven oranı en az `%60` olan ilk otomatik dil sonucu sonraki parçalarda korunur. Daha düşük güvenli sonuçlar dili kilitlemez. Böylece uzun bir dosyanın her parçasının farklı dil olarak yorumlanması önlenirken zayıf ilk tahmine bağımlı kalınmaz.

## Metin İşleme ve API

### İşlemeyi Kapatmak

**STT çıktısını otomatik düzenle** kapalıysa transkript doğrudan kullanılır. LLM çağrısı veya kural tabanlı düzenleme yapılmaz.

### Kural Tabanlı Yöntem

Tamamen yerel çalışır ve model gerektirmez.

Uygulanan temel işlemler:

- Türkçe ve İngilizce temel düşünme seslerini temizleme
- Gereksiz boşlukları düzeltme
- İlk harfi büyütme
- Eksik temel noktalama işaretini ekleme

Hazır LLM profilleri ve özel kullanıcı talimatları bu yöntemde uygulanmaz.

### Yerel LLM

Ollama veya LM Studio gibi OpenAI uyumlu yerel bir endpoint kullanılabilir.

Varsayılan örnek adres:

```text
http://localhost:11434/v1
```

Endpoint'in çalışır durumda olması ve yazılan model adının yerel sunucuda bulunması gerekir.

### Bulut LLM

Desteklenen metin sağlayıcıları Gemini, Grok, Groq ve OpenAI'dır. Bu aşamada sağlayıcıya ses değil, STT sonucunda oluşmuş metin gönderilir.

API anahtarları düz metin `config.json` dosyasına yazılmaz. Windows Kimlik Bilgisi Yöneticisi'nde saklanır.

### Düzenleme Profilleri

| Profil | Davranış |
|---|---|
| Standart | Dolgu sesleri, yazım, noktalama ve tekrarları düzenler |
| Resmi iş dili | Metni profesyonel iş yazışmasına dönüştürür |
| Kodlama ve teknik terimler | Değişken, kütüphane ve teknik adları korur |
| İngilizceye çevir | Transkripti doğal İngilizceye çevirir |
| Maddeler halinde özetle | Metni kısa maddeler ve özet biçiminde düzenler |

Standart, resmi ve teknik profiller kullanıcı ayrıca istemedikçe transkriptin dilini korur.

## Ses ve Kısayollar

### Arayüz Dili

Uygulama arayüzü Türkçe ve İngilizce kullanılabilir. Bu ayar konuşma dilinden bağımsızdır.

### Mikrofon

**Varsayılan Sistem Mikrofonu**, Windows'un etkin giriş cihazını kullanır. Belirli bir cihaz seçilirse PrimeDictate doğrudan o aygıtı açmayı dener.

Canlı seviye göstergesi kayıt sırasında giriş seviyesini görmeye yardımcı olur. Ses algılanmıyorsa önce Windows gizlilik izinleri ve giriş aygıtı kontrol edilmelidir.

### Kısayol Modları

| Mod | Davranış |
|---|---|
| Bas-Aç | İlk basış kaydı başlatır, ikinci basış bitirir |
| Bas-Tut | Tuş basılı olduğu sürece kayıt yapar |

Kısayol başka bir uygulama tarafından kullanılıyorsa farklı bir kombinasyon seçin.

## Yüzen Kayıt Göstergesi

Gösterge kayıt başladığında aktif monitörün kullanılabilir alanında alt-orta konuma yerleşir.

Konum davranışı:

- İlk kullanımda imlecin bulunduğu aktif monitör esas alınır.
- Gösterge görev çubuğunun arkasına veya ekran dışına taşınmaz.
- Sol fare düğmesiyle sürüklenebilir.
- Bırakılan konum ayarlara kaydedilir.
- Monitör veya çözünürlük değiştiğinde kayıtlı konum en yakın geçerli ekran alanına çekilir.

Gösterge pencere odağını almadan kayıt, transkripsiyon, başarı ve hata durumlarını bildirir. Kayıt sırasında ses dalgası ile Durdur düğmesi görünür. Sonuç beklenirken sarı **Metne çevriliyor** durumu gösterilir ve Play bilinçli olarak devre dışıdır. Sonuç gelir gelmez Play yeniden etkinleşir; yeni dikte için ek başarı bekleme süresi yoktur. Yeşil sonuç veya **Hazır** durumu, ana pencere kapalıyken de motorun yeniden kullanılabildiğini gösterir.

## Dosya Transkripsiyonu

Desteklenen biçimler:

```text
.mp3  .wav  .mp4  .m4a  .mkv  .flac  .ogg
```

Dosyalar belleğe bütünüyle yüklenmek yerine sınırlı parçalar halinde çözülür. İptal işlemi işbirliklidir: CPU/CUDA segment sınırında durur; kalıcı Vulkan veya bulut HTTP isteğinin tamamlanması gerekebilir; tek-seferlik Vulkan fallback kullanılıyorsa çalışan CLI süreci sonlandırılabilir.

Canlı dikteyle aynı STT motoru, dil ve metin işleme ayarları kullanılır. Özet veya çeviri profili seçiliyse bu profil dosya parçalarının sonuçlarına da uygulanır.

## Geçmiş ve Tanılama

### Geçmiş

Geçmiş etkinse son transkriptler `%APPDATA%\PrimeDictate\history.json` dosyasında saklanır. Arama, kopyalama ve tüm geçmişi temizleme işlemleri arayüzden yapılabilir.

Geçmiş kaydı **Davranış ve Otomasyon** bölümünden kapatılabilir.

### Tanılama

Tanılama sayfası şu durumlar için kullanılmalıdır:

- Yerel model yüklenmiyor
- Vulkan runtime doğrulanmıyor
- Bulut isteği reddediliyor
- Mikrofon aygıtı bulunamıyor
- Model indirme işlemi başarısız oluyor

Bulut hata kayıtları API anahtarını, ham sesi veya servis hata gövdesindeki hassas içeriği yazmadan HTTP durumu, hata sınıfı ve varsa güvenli istek kimliğini gösterir.

## Gizlilik

| Yapılandırma | Ses | Transkript |
|---|---|---|
| Yerel STT + kural tabanlı | Cihazda kalır | Cihazda kalır |
| Yerel STT + yerel LLM | Cihazda kalır | Yerel endpoint'e gider |
| Yerel STT + bulut LLM | Cihazda kalır | Bulut LLM'e gider |
| Bulut STT | Bulut STT'ye gider | Seçilen işleme yöntemine göre hareket eder |

Kullanıcı verileri:

```text
%APPDATA%\PrimeDictate\config.json
%APPDATA%\PrimeDictate\history.json
%APPDATA%\PrimeDictate\models\faster-whisper\
%APPDATA%\PrimeDictate\models\whisper.cpp\
```

Portable sürüm de aynı kullanıcı klasörünü kullanır. EXE'nin yanına API anahtarı, geçmiş veya model yazmaz.

## Önerilen Yapılandırmalar

### En yüksek gizlilik

```text
STT: Yerel CPU / CUDA / Vulkan
Bulut fallback: Kapalı
Metin işleme: Kural tabanlı veya yerel LLM
Geçmiş: Kullanıcı tercihine göre
```

### Hızlı bulut transkripsiyonu

```text
STT: Groq veya OpenAI
Dil: Biliniyorsa açıkça seçili
Metin işleme: Kapalı, kural tabanlı veya ihtiyaca göre LLM
```

### Teknik dikte

```text
STT: Donanıma uygun yerel motor
Model: small veya daha büyük
Metin işleme: Yerel/bulut LLM
Profil: Kodlama ve teknik terimler
```

## Sorun Giderme

### Yönetici olarak çalışan uygulamalara yapıştırma

PrimeDictate normalde standart kullanıcı yetkileriyle açılır. Yönetici olarak başlatılmış bir hedef uygulamaya Windows güvenlik sınırı nedeniyle tuş gönderilemezse **Ayarlar > PrimeDictate'i yönetici olarak çalıştır** seçeneğini etkinleştirin ve uygulamayı yeniden başlatın. Sonraki açılışta Windows UAC onayı ister. Ayar hem kurulu hem portable sürümde aynıdır; setup yalnız Program Files kurulumu için yönetici yetkisi ister ve uygulamayı kalıcı olarak yükseltilmiş çalışmaya zorlamaz. Yönetici modu ile Windows başlangıcı birlikte açıksa her oturum açılışında UAC onayı gerekir.

### Mikrofon başlamıyor

1. Windows mikrofon gizlilik iznini kontrol edin.
2. Başka bir uygulamanın aygıtı özel modda tutmadığından emin olun.
3. **Ses & Kısayollar** bölümünden farklı cihaz seçin.
4. **Mikrofon Tanı Bilgisi** çıktısını inceleyin.

### Yerel model hazır değil

1. Doğru backend ve model boyutunun seçili olduğunu kontrol edin.
2. **Seçilen Modeli İndir** düğmesini kullanın.
3. İnternet bağlantısını ve `%APPDATA%\PrimeDictate\models` yazma iznini kontrol edin.
4. Tanılama günlüğünü inceleyin.

### Vulkan kullanılamıyor

1. Güncel GPU sürücüsünü kurun.
2. Dahili runtime durumunu kontrol edin.
3. Bütünlük hatası varsa uygulama paketini güvenilir kaynaktan yeniden edinin.
4. Donanım Vulkan desteklemiyorsa CPU veya CUDA motoruna geçin.

Kalıcı server başlatılamazsa PrimeDictate otomatik CLI fallback kullanır ve tanılama günlüğüne uyarı yazar. Performansı kontrol etmek için günlükte `Persistent Vulkan transcription server is ready` ve `Dictation stop-to-result latency=...` satırlarını arayın.

### Bulut isteği başarısız

1. Seçilen sağlayıcının API anahtarını kontrol edin.
2. Hesabın seçilen modele erişimi olduğunu doğrulayın.
3. Kota ve bölge kısıtlamalarını kontrol edin.
4. Tanılama ekranındaki HTTP durumunu inceleyin.
5. Özel model adı girildiyse sağlayıcının güncel model kimliğiyle eşleştiğini doğrulayın.

### Metin aktif pencereye yapıştırılmıyor

PrimeDictate güvenlik nedeniyle başlangıçta yakalanan pencere odağını geri getiremezse `Ctrl+V` göndermez. Sonuç panoda tutulur ve elle yapıştırılabilir.

**Önceki pano metnini geri yükle** seçeneği yalnızca düz metni korur. Kopyalanmış resimler, dosyalar, HTML ve diğer özel pano biçimleri geri yüklenmez.

### Overlay görünmüyor

1. **Yüzen ses dalgası göstergesini kullan** seçeneğini kontrol edin.
2. Kaydı yeniden başlatın.
3. Monitör bağlantısı değiştiyse uygulamayı yeniden açın.
4. Sorun sürerse `%APPDATA%\PrimeDictate\config.json` içindeki `overlay_position` değerini yalnızca uygulama kapalıyken kaldırın.

## Destek

- Web: [maximusprimesoftware.pages.dev](https://maximusprimesoftware.pages.dev/)
- Repository: [github.com/MaximusPrime/PrimeDictate](https://github.com/MaximusPrime/PrimeDictate)
- E-posta: [maximusprimesoftware@gmail.com](mailto:maximusprimesoftware@gmail.com)

Güvenlik sorunları için herkese açık issue açmadan önce [SECURITY.md](../SECURITY.md) belgesini okuyun.
