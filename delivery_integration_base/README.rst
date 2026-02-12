# Delivery Integration Base

Bu modül ne işe yarar?

- Delivery Integration Base modülü, kargo entegrasyonunun çalışması için gerekli bazı
  temel alanlar ve fonksiyonları barındırır.
- Teslimat yöntemine barkod oluşturma yeteneği ekler. Teslimat barkodunu PDF şeklinde
  indirmeye olanak sağlar. Yazıcı ayarlandığı takdirde direkt olarak ZPL çıktısı da
  alınabilir.
- Alıcı ödemeli ve gönderici ödemeli olarak iki tür ödeme şekli destekler.
- Teslim Yöntemine para birimi ekler.
- Kargo firmalarının fiyatlama için kullandığı bölgeler için `delivery_region` modeli
  ekler.
- Türkiye içinde yaygın kullanılan fiyat kuralı unsurlarını `delivey_price_rule`
  modeline ekler.
- Teslimat içerisinden direkt barkod bastırma özelliği.
- Satış siparişinde, kargo firmalarından toplu şekilde fiyat alma sihirbazı.
- Teslimat transfer sürecinde müşteriye SMS ile bilgi verir.

### Gerekli Modüller:

- l10n_tr_address
  ([odoo-turkey/l10n-turkey](https://github.com/odoo-turkey/l10n-turkey))
- delivery_state ([oca/delivery-carrier](https://github.com/OCA/delivery-carrier))
- product_dimension ([oca/product-attribute](https://github.com/OCA/product-attribute))
- queue_job ([oca/queue](https://github.com/oca/queue))
- sms_verimor_http
  ([odoo-turkey/integration](https://github.com/odoo-turkey/integration))
- short_url_yourls
  ([aaltinisik/customaddons](https://github.com/aaltinisik/customaddons))

### Notlar:

Bu modül henüz geliştirilme aşamasındadır. Odoo 12.0 temel alınarak tasarlanmıştır.

### Geliştirici:

- [Yiğit Budak](https://github.com/yibudak)

### Odoo Türkiye yerelleştirme projemize katkılarınızı bekliyoruz.

- Proje LGPL lisansı ile lisanslanmıştır. Katkılarınız da bu lisans koşullarını kabul
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
