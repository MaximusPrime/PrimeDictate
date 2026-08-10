# PrimeDictate 1.0.0 — İlk Resmî Sürüm

PrimeDictate'in ilk resmî sürümüne hoş geldiniz.

PrimeDictate, Windows üzerinde herhangi bir uygulamada kullanılabilen; yerel çalışmayı, kullanıcı kontrolünü ve gizliliği merkeze alan bir sesli yazma uygulamasıdır. Global kısayol ile konuşmanızı kaydeder, seçtiğiniz motorla metne dönüştürür ve sonucu güvenli biçimde aktif çalışma alanınıza aktarır.

## Öne çıkan özellikler

- Windows genelinde **Bas-Aç** ve **Bas-Tut** dikte modları
- CPU, NVIDIA CUDA ve AMD / Intel / NVIDIA Vulkan üzerinde yerel Whisper desteği
- Groq, OpenAI ve Google Gemini ile isteğe bağlı bulut transkripsiyonu
- Yerel kural tabanlı metin düzenleme veya seçilen yapay zekâ sağlayıcısıyla gelişmiş metin işleme
- Türkçe ve İngilizce arayüz; çok dilli konuşma tanıma ve otomatik dil algılama
- MP3, WAV, MP4, M4A, MKV, FLAC ve OGG dosyaları için uzun kayıt transkripsiyonu
- TXT, SRT, VTT ve JSON çıktı seçenekleri
- Kayıt durumunu gösteren taşınabilir yüzen dikte paneli
- Sistem tepsisi üzerinden model yükleme, RAM / VRAM boşaltma ve oyun modu kontrolleri
- Kayıt boyunca diğer Windows uygulamalarının sesini isteğe bağlı olarak sessize alma
- Dikte geçmişi, arama, kopyalama ve yerel geçmiş yönetimi
- Standart ve yönetici yetkili uygulamalara güvenli metin aktarımı
- Windows ile başlangıç ve yönetici modu desteği

## Gizlilik yaklaşımı

Yerel CPU, CUDA veya Vulkan motoru seçildiğinde ses cihazdan ayrılmaz. Bulut STT yalnızca kullanıcı tarafından açıkça seçildiğinde veya kullanıcı izinli bulut yedeği etkinleştirildiğinde kullanılır. Konuşmayı metne çevirme ve metni yapay zekâyla düzenleme birbirinden bağımsız aşamalardır.

API anahtarları düz metin yapılandırma dosyasında tutulmaz; Windows Credential Manager veya kullanıcıya bağlı Windows DPAPI koruması kullanılır. Tanılama günlükleri API anahtarlarını, ham ses içeriğini ve sağlayıcıların hassas hata gövdelerini kaydetmez.

## İndirme seçenekleri

- **PrimeDictate-Setup.exe** — Windows kurulum paketi
- **PrimeDictate-Portable.exe** — kurulum gerektirmeyen taşınabilir sürüm
- **SHA256SUMS.txt** — indirilen dosyaların bütünlüğünü doğrulamak için SHA-256 değerleri

Yerel modeller ilk kullanımda seçilen motor için ayrıca indirilir. Bulut modelleri için ilgili sağlayıcıda etkin bir API hesabı, model erişimi ve kullanılabilir kota gerekir.

## Sistem gereksinimleri

- Windows 10 veya Windows 11, 64 bit
- Canlı dikte için mikrofon
- Yerel GPU hızlandırması kullanılacaksa güncel ekran kartı sürücüsü
- Seçilen yerel model için yeterli disk alanı ve RAM / VRAM

Windows, imzasız uygulamalarda SmartScreen uyarısı gösterebilir. Dosyayı çalıştırmadan önce bu release ile yayımlanan `SHA256SUMS.txt` değerini kontrol edebilirsiniz.

---

## English

Welcome to the first official release of PrimeDictate.

PrimeDictate is a privacy-focused, system-wide dictation application for Windows. It records speech from a global hotkey, transcribes it with the engine you select, and safely delivers the result to your active workspace.

### Highlights

- System-wide Toggle and Push-to-Talk dictation modes
- Local Whisper on CPU, NVIDIA CUDA, and AMD / Intel / NVIDIA Vulkan
- Optional cloud transcription with Groq, OpenAI, and Google Gemini
- Local rule-based cleanup or advanced text processing with a selected AI provider
- Turkish and English interface with multilingual speech recognition
- Long-form MP3, WAV, MP4, M4A, MKV, FLAC, and OGG transcription
- TXT, SRT, VTT, and JSON exports
- Movable floating dictation control and system tray model controls
- Optional muting of other Windows applications during recording
- Local dictation history and safe clipboard-based text delivery
- Windows startup and elevated-application support

Local CPU, CUDA, and Vulkan transcription keeps audio on the device. Cloud speech-to-text is used only when explicitly selected or permitted as a fallback. API credentials are protected with Windows Credential Manager or user-bound DPAPI storage.

Choose `PrimeDictate-Setup.exe` for the installed edition or `PrimeDictate-Portable.exe` for the standalone edition. Use `SHA256SUMS.txt` to verify your download.
