# cities.csv — источник, лицензия, перегенерация

Файл cities.csv в этой папке — список городов РФ с IANA-поясом для анкеты
(решения Р-16 и Р-17, задача cities-1). Город в БД не хранится: по выбору города
берётся только пояс tz.

## Источник
- Репозиторий: https://github.com/hflabs/city
- Commit: ae661bffe572880472249097c9b29c42b09650ea («Данные от 11.10.2021»)
- Файл: city.csv — https://raw.githubusercontent.com/hflabs/city/ae661bffe572880472249097c9b29c42b09650ea/city.csv
- sha256 исходника: aefd11fd133881c348e0138b273a300ec6b3909c8f61d8d1d5ffc5e85021ec0d

## Лицензия и атрибуция
Данные: HFLabs / DaData.ru, лицензия Creative Commons Attribution-ShareAlike 4.0
International (CC BY-SA 4.0), https://creativecommons.org/licenses/by-sa/4.0/
Файл cities.csv — производные данные и распространяется под той же лицензией CC BY-SA 4.0.

## Что изменено относительно источника
- Оставлены только три колонки: city, region, tz. Координаты, коды, индексы,
  население и прочие поля не переносятся.
- city — первое непустое по порядку: поле settlement; поле city; поле area, если
  area_type «г» (городские округа, например Воскресенск Московской области);
  название region у городов федерального значения (region_type «г»).
- region приведён к виду для показа: «обл» → «… область», «край» → «… край»,
  «Респ» → «Республика …», «АО» → «… автономный округ», «Аобл» → «… автономная
  область», «г» и «Чувашия» — название как есть; если слово типа уже есть в
  названии, оно не добавляется повторно.
- Пояс «UTC+N» заменён IANA-поясом, один на смещение: UTC+2 Europe/Kaliningrad,
  UTC+3 Europe/Moscow, UTC+4 Europe/Samara, UTC+5 Asia/Yekaterinburg, UTC+6 Asia/Omsk,
  UTC+7 Asia/Novosibirsk, UTC+8 Asia/Irkutsk, UTC+9 Asia/Yakutsk, UTC+10 Asia/Vladivostok,
  UTC+11 Asia/Magadan, UTC+12 Asia/Kamchatka.
- Строки отсортированы по (city, region); кодировка UTF-8, окончания строк LF.

## Перегенерация
Руками файл не правится. Из корня репо:

    python3 tools/build_cities.py

Без сети — с локальной копией city.csv:

    python3 tools/build_cities.py --input путь/к/city.csv

Скрипт печатает строку «sha256: …» — её значение вписать выше. Проверка данных:

    bash tools/check.sh api
