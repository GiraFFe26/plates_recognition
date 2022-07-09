from bs4 import BeautifulSoup
from datetime import datetime
import requests
import lxml
import time
from fake_useragent import UserAgent
import os
import easyocr
import cv2
import numpy as np
import imutils
import httplib2
import apiclient.discovery
from oauth2client.service_account import ServiceAccountCredentials
from memory_profiler import profile

ua = UserAgent()

try:
    os.mkdir('car3_data')
except FileExistsError:
    pass


# Получение ссылок всех машин сайта.
def get_cars(url):
    car_urls = []
    #    proxies = {
    #        'http': '149.28.120.8:59394',
    #        'https': '149.28.120.8:59394'
    #    }
    response = requests.get(url, headers={'user-agent': f'{ua.random}'})
    time.sleep(10)
    src = response.text
    soup = BeautifulSoup(src, 'lxml')
    cars = soup.find_all('div', class_='products-i vipped')
    for car_a in cars:
        car_url = 'https://ru.turbo.az' + car_a.find('a', class_='products-i__link').get('href')
        car_urls.append(car_url)
    car_urls2 = []
    car_urls2.append(car_urls[0])
    print(car_urls2)
    get_photos(car_urls2)


# Скачивание фото - сразу поиск номера, если нашёл, то заполняет таблицу в final()
@profile
def get_photos(car_urls):
    photos_urls = []
    # Файл, полученный в Google Developer Console
    CREDENTIALS_FILE = 'creds.json'
    # ID Google Sheets документа (можно взять из его URL)
    spreadsheet_id = 'id'
    # Авторизуемся и получаем service — экземпляр доступа к API
    credentials = ServiceAccountCredentials.from_json_keyfile_name(
        CREDENTIALS_FILE,
        ['https://www.googleapis.com/auth/spreadsheets',
         'https://www.googleapis.com/auth/drive'])
    httpAuth = credentials.authorize(httplib2.Http())
    service = apiclient.discovery.build('sheets', 'v4', http=httpAuth)
    # ЧТЕНИЕ ФАЙЛА
    val = []
    num = 2
    l = 5000
    while True:
        values = service.spreadsheets().values().get(
            spreadsheetId=spreadsheet_id,
            range=f'Лист2!M{num}:M{l}',
            majorDimension='COLUMNS'
        ).execute()
        num = l
        l = l + 5000
        try:
            val = values['values'][0] + val
        except KeyError:
            break
    car_total = len(val) + 1
    try:
        with open('failed_links2.txt', 'r', encoding='UTF-8') as file:
            val = val + file.read().split()
    except FileNotFoundError:
        pass
    for v in val:
        for car_url in car_urls:
            if car_url == v:
                car_urls.remove(car_url)
    for car_url in car_urls:
        fail = 1
        try:
            response = requests.get(car_url, headers={'user-agent': f'{ua.random}'})
            time.sleep(10)
        except Exception:
            continue
        src = response.text
        soup = BeautifulSoup(src, 'lxml')
        try:
            main_photo_url = soup.find('a', class_='product-photos-large').get('href')
            photos_urls.append(main_photo_url)
        except AttributeError:
            pass
        try:
            other_photos = soup.find('div', class_='product-photos-thumbnails_m').find_all('a')
        except AttributeError:
            try:
                other_photos = soup.find('div', class_='product-photos-thumbnails_l').find_all('a')
            except AttributeError:
                try:
                    other_photos = soup.find('div', class_='product-photos-thumbnails_s').find_all('a')
                except AttributeError:
                    try:
                        other_photos = soup.find('div', class_='product-photos-thumbnails_xl').find_all('a')
                    except AttributeError:
                        print(car_url)
        for other_photo in other_photos:
            photos = other_photo.get('href')
            photos_urls.append(photos)
        # СКАЧИВАНИЕ ФОТО И ПОИСК НОМЕРА
        for photo_url in photos_urls:
            req = requests.get(photo_url, headers={'user-agent': f'{ua.random}'})
            time.sleep(6)
            with open(f'car_photo_other{photos_urls.index(photo_url)}.jpg', 'wb',encoding='UTF-8') as file:
                file.write(req.content)
            file_path = f'car_photo_other{photos_urls.index(photo_url)}.jpg'
            img = cv2.imread(file_path, 1)
            try:
                gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
            except cv2.error:
                continue
            bfilter = cv2.bilateralFilter(gray, 11, 17, 17)  # Noise reduction
            edged = cv2.Canny(bfilter, 30, 200)  # Edge detection
            keypoints = cv2.findContours(edged.copy(), cv2.RETR_TREE, cv2.CHAIN_APPROX_SIMPLE)
            contours = imutils.grab_contours(keypoints)
            contours = sorted(contours, key=cv2.contourArea, reverse=True)
            location = None
            for contour in contours:
                approx = cv2.approxPolyDP(contour, 10, True)
                if len(approx) == 4:
                    location = approx
                    break
            mask = np.zeros(gray.shape, np.uint8)
            try:
                new_image = cv2.drawContours(mask, [location], 0, 255, -1)
            except cv2.error:
                continue
            new_image = cv2.bitwise_and(img, img, mask=mask)
            (x, y) = np.where(mask == 255)
            (x1, y1) = (np.min(x), np.min(y))
            (x2, y2) = (np.max(x), np.max(y))
            cropped_image = gray[x1:x2 + 1, y1:y2 + 1]
            reader = easyocr.Reader(['en'])
            result = reader.readtext(cropped_image, detail=0,
                                     contrast_ths=0.7, adjust_contrast=1, rotation_info=[30, 45, 60],
                                     width_ths=0.9,
                                     allowlist='ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789')
            #            print(result)
            ## ОТБОР НОМЕРА ПО СИМВОЛАМ
            if len(result) != 0:
                p = str(result[0])
                if 7 <= len(p) <= 9:
                    cnt = len(([s for s in p if s.isdigit()]))
                    word = len(([s for s in p if s.isalpha()]))
                    if 4 <= int(cnt) < 8:
                        if 1 <= int(word) < 3:
                            if p[0].isalpha() == False and int(word) != 1:
                                plate = p
                                image_url1 = photos_urls[photos_urls.index(photo_url)]
                                try:
                                    image_url2 = photos_urls[photos_urls.index(photo_url) + 1]
                                except IndexError:
                                    image_url2 = photos_urls[photos_urls.index(photo_url) - 1]
                                car_total = car_total + 1
                                fail = 0
                                final(car_url, plate, car_total, image_url1, image_url2)
                                os.remove(file_path)
                                break
                            else:
                                os.remove(file_path)
                                continue
                        else:
                            os.remove(file_path)
                            continue
                    else:
                        os.remove(file_path)
                        continue
                else:
                    os.remove(file_path)
                    continue
            else:
                os.remove(file_path)
                continue
        if fail == 1:
            with open('failed_links2.txt', 'a', encoding='UTF-8') as file:
                file.write(car_url + '\n')
        else:
            pass
        photos_urls.clear()


# Если скрипт смог найти номер у машины, то парсит всю оставшуюся нужную информацию. И заполнение гугл таблицы.
def final(url, plate, car_total, image_url1, image_url2):
    try:
        if plate_old != plate:
            rep = True
            while rep == True:
                try:
                    response = requests.get(url, headers={'user-agent': f'{ua.random}'})
                    time.sleep(10)
                    src = response.text
                    soup = BeautifulSoup(src, 'lxml')
                    name = soup.find('h1', class_='product-name product-name-row').text
                    rep = False
                except AttributeError:
                    pass
            properties = soup.find_all('li', class_='product-properties-i')
            mark = properties[1].find('div', class_='product-properties-value').text
            model = properties[2].find('div', class_='product-properties-value').text
            town = properties[0].find('div', class_='product-properties-value').text
            if len(properties) == 14:
                mileage = properties[-5].find('div', class_='product-properties-value').text[:-3]
            elif len(properties) == 15:
                mileage = properties[-6].find('div', class_='product-properties-value').text[:-3]
            else:
                mileage = properties[-7].find('div', class_='product-properties-value').text[:-3]
            try:
                lots = soup.find('div', class_='product-statistics').find_all('p')
                lot = lots[1].text
            except AttributeError:
                lot = 'Не указано'
            price = soup.find('div', class_='product-price').text
            try:
                seller = soup.find('div', class_='seller-name').text
            except AttributeError:
                seller = 'Не указано'
            try:
                phone = soup.find('div', class_='seller-phone').find('a', class_='phone').text
            except AttributeError:
                phone = 'Не указано'
            try:
                comms = soup.find('div', class_='product-description').find_all('p', class_=None)[0].text
            except AttributeError:
                comms = 'Не указано'
            now = str(datetime.now()).split('.')[0]

            # Файл, полученный в Google Developer Console
            CREDENTIALS_FILE = 'creds.json'
            # ID Google Sheets документа (можно взять из его URL)
            spreadsheet_id = 'id'

            # Авторизуемся и получаем service — экземпляр доступа к API
            credentials = ServiceAccountCredentials.from_json_keyfile_name(
                CREDENTIALS_FILE,
                ['https://www.googleapis.com/auth/spreadsheets',
                 'https://www.googleapis.com/auth/drive'])
            httpAuth = credentials.authorize(httplib2.Http())
            service = apiclient.discovery.build('sheets', 'v4', http=httpAuth)
            dirpath = 'car3_data/' + str(car_total)
            os.mkdir(dirpath)
            req = requests.get(image_url1, headers={'user-agent': f'{ua.random}'})
            time.sleep(6)
            with open(dirpath + '/Фото1.jpg', 'wb',encoding='UTF-8') as file:
                file.write(req.content)
            req = requests.get(image_url2, headers={'user-agent': f'{ua.random}'})
            time.sleep(6)
            with open(dirpath + '/Фото2.jpg', 'wb',encoding='UTF-8') as file:
                file.write(req.content)
            rep = True
            while rep == True:
                try:
                    values = service.spreadsheets().values().batchUpdate(
                        spreadsheetId=spreadsheet_id,
                        body={
                            "valueInputOption": "USER_ENTERED",
                            "data": [
                                {"range": "Лист2!A1:O1",
                                 "majorDimension": "ROWS",
                                 "values": [
                                     ['Название автомобиля', 'Марка автомобиля', 'Модель автомобиля',
                                      'Номер автомобиля', 'Пробег, км', 'Город', 'Дата лота',
                                      'Время добавления', 'Цена лота',
                                      'Продавец', 'Номер продавца', 'Комментарии продавца', 'Ссылка на авто', 'Фото1',
                                      'Фото2']]},
                                {"range": f"Лист2!A{car_total}:O{car_total}",
                                 "majorDimension": "ROWS",
                                 "values": [
                                     [str(name), str(mark), str(model), str(plate), str(mileage), str(town), str(lot),
                                      str(now), str(price), str(seller),
                                      str(phone),
                                      str(comms), str(url), f'=IMAGE("{image_url1}")', f'=IMAGE("{image_url2}")']]}
                            ]
                        }
                    ).execute()
                    rep = False
                except TimeoutError:
                    pass

    except UnboundLocalError:
        rep = True
        while rep == True:
            try:
                response = requests.get(url, headers={'user-agent': f'{ua.random}'})
                time.sleep(10)
                src = response.text
                soup = BeautifulSoup(src, 'lxml')
                name = soup.find('h1', class_='product-name product-name-row').text
                rep = False
            except AttributeError:
                pass
        properties = soup.find_all('li', class_='product-properties-i')
        mark = properties[1].find('div', class_='product-properties-value').text
        model = properties[2].find('div', class_='product-properties-value').text
        town = properties[0].find('div', class_='product-properties-value').text
        if len(properties) == 14:
            mileage = properties[-5].find('div', class_='product-properties-value').text[:-3]
        elif len(properties) == 15:
            mileage = properties[-6].find('div', class_='product-properties-value').text[:-3]
        else:
            mileage = properties[-7].find('div', class_='product-properties-value').text[:-3]
        try:
            lots = soup.find('div', class_='product-statistics').find_all('p')
            lot = lots[1].text
        except AttributeError:
            lot = 'Не указано'
        price = soup.find('div', class_='product-price').text
        try:
            seller = soup.find('div', class_='seller-name').text
        except AttributeError:
            seller = 'Не указано'
        try:
            phone = soup.find('div', class_='seller-phone').find('a', class_='phone').text
        except AttributeError:
            phone = 'Не указано'
        try:
            comms = soup.find('div', class_='product-description').find_all('p', class_=None)[0].text
        except AttributeError:
            comms = 'Не указано'
        now = str(datetime.now()).split('.')[0]

        # Файл, полученный в Google Developer Console
        CREDENTIALS_FILE = 'creds.json'
        # ID Google Sheets документа (можно взять из его URL)
        spreadsheet_id = 'id'

        # Авторизуемся и получаем service — экземпляр доступа к API
        credentials = ServiceAccountCredentials.from_json_keyfile_name(
            CREDENTIALS_FILE,
            ['https://www.googleapis.com/auth/spreadsheets',
             'https://www.googleapis.com/auth/drive'])
        httpAuth = credentials.authorize(httplib2.Http())
        service = apiclient.discovery.build('sheets', 'v4', http=httpAuth)
        dirpath = 'car3_data/' + str(car_total)
        os.mkdir(dirpath)
        req = requests.get(image_url1, headers={'user-agent': f'{ua.random}'})
        time.sleep(6)
        with open(dirpath + '/Фото1.jpg', 'wb',encoding='UTF-8') as file:
            file.write(req.content)
        req = requests.get(image_url2, headers={'user-agent': f'{ua.random}'})
        time.sleep(6)
        with open(dirpath + '/Фото2.jpg', 'wb',encoding='UTF-8') as file:
            file.write(req.content)
        rep = True
        while rep == True:
            try:
                values = service.spreadsheets().values().batchUpdate(
                    spreadsheetId=spreadsheet_id,
                    body={
                        "valueInputOption": "USER_ENTERED",
                        "data": [
                            {"range": "Лист2!A1:O1",
                             "majorDimension": "ROWS",
                             "values": [
                                 ['Название автомобиля', 'Марка автомобиля', 'Модель автомобиля', 'Номер автомобиля',
                                  'Пробег, км', 'Город', 'Дата лота',
                                  'Время добавления', 'Цена лота',
                                  'Продавец', 'Номер продавца', 'Комментарии продавца', 'Ссылка на авто', 'Фото1',
                                  'Фото2']]},
                            {"range": f"Лист2!A{car_total}:O{car_total}",
                             "majorDimension": "ROWS",
                             "values": [
                                 [str(name), str(mark), str(model), str(plate), str(mileage), str(town), str(lot),
                                  str(now), str(price), str(seller),
                                  str(phone),
                                  str(comms), str(url), f'=IMAGE("{image_url1}")', f'=IMAGE("{image_url2}")']]}
                        ]
                    }
                ).execute()
                rep = False
            except TimeoutError:
                pass
    plate_old = plate


def main():
    get_cars('https://ru.turbo.az/autos')
    print('WORK HAS ENDED')


if __name__ == '__main__':
    main()


