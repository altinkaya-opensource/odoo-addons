# Delivery Aras Kargo

Odoo için Aras Kargo entegrasyonu.

### Fonksiyonlar:

- Gönderi Oluşturma (createShipment)
- Gönderi İptal Etme (cancelShipment)
- Gönderi Takibi (queryShipment)

Aras Kargo'nun API teknik dokümanı `docs/` klasörünün içinde bulabilirsiniz.

### Kurulum:

- `Depo/Yapılandırma/Teslimat Yöntemleri` menüsünden bir taşıyıcı kaydı oluşturun.
- Yetkiliniz tarafından size sağlanan API bilgilerinizi kaydediniz. (UserLanguage alanı
  `TR` olarak ayarlanabilir)
- Entegrasyonun tam olarak çalışması için Teslimat Bölgeleri'ni doldurmanız ve
  fiyatlandırma kuralı eklemeniz gerekmektedir.

### Gerekli Modüller:

-     delivery_integration_base ([odoo-turkey/integration](https://github.com/odoo-turkey/integration))

### Python bağımlılıkları:

- zeep
- phonenumbers

### Notlar:

Bu modül henüz geliştirilme aşamasındadır. Odoo 12.0 temel alınarak tasarlanmıştır.

### Geliştirici:

- [Ahmet Yiğit Budak](https://github.com/yibudak)

### Odoo Türkiye yerelleştirme projemize katkılarınızı bekliyoruz.

- Proje LGPL lisansı ile lisanslanmıştır. Katkılarınızda bu lisans koşullarını kabul
  etmiş sayılırsınız.
- Projemizdeki modüllerin ve içeriğin **OCA kalite standartları**nı sağlamasını
  amaçlıyoruz.
- [Contribute to OCA](https://odoo-community.org/page/Contribute) sayfasında genel
  bilgiler mevcut.
- Eklenecek modüller için genel kurallara
  https://github.com/OCA/maintainer-tools/blob/master/CONTRIBUTING.md adresinden
  erişebilirsiniz.
- Modülleri geliştirirken
  [OCA tarafından hazırlanan kalite kontrol programları](https://github.com/OCA/maintainer-quality-tools)
  ile kalite kontrol işinizi kolaylaştırabilirsiniz.
