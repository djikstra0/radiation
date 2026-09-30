# Sistem za obaveštavanje o radijaciji

Distribuirani IoT sistem za praćenje ambijentalne radijacije na više lokacija.

Sistem prikuplja podatke pomoću senzora, prenosi ih putem MQTT protokola, čuva u PostgreSQL/TimescaleDB bazi i prikazuje ih na web dashboard-u. Korisnici mogu da se pretplate na lokacije i dobijaju obaveštenja putem Telegram bota.

Projekat sadrži i simulatore za testiranje sistema bez fizičkih senzora.
