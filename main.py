import asyncio
from machine import Pin,reset,Timer,I2C
import time
import network
import socket
import io
import gc,json
import binascii
import deflate, io
import onewire,ds18x20


# настройка выхода светодиода
led_blink = Pin(2, Pin.OUT)
# Настройка выходом кнопок
but_red   = Pin(14, Pin.IN)
but_green   = Pin(13, Pin.IN)
but_blue   = Pin(12, Pin.IN)
# настройка выхода термодатчика DS18B20
ow = onewire.OneWire(Pin(16)) # create a OneWire bus on GPIO16

# Словарь (JSON) структура передачи данных между Сервером и клиентом
reg={"bulbState":"off",     # режим работы лампочки
     "temp":25,             # температура
     "tempState":"online"}; # наличие датчика ds18b20

# Задача по управлению светодиодом
async def Task1_led():
    while True:
        if reg["bulbState"]=="blink":
            print('Task1 - led on')
            if led_blink.value()==1:
                led_blink.value(0)
                print('Task1 - blink - led off')
            else:
                led_blink.value(1)
                print('Task1 - led on')
            await asyncio.sleep_ms(1000)
        elif reg["bulbState"]=="on":
            led_blink.value(1)
            print('Task1 - led on')
            await asyncio.sleep_ms(500)
        else:
            led_blink.value(0)
            print('Task1 - led off')
            await asyncio.sleep_ms(500)
            
# Задача по опросу кнопок         
async def Task2_butCheck():
    while True:
        #print(f"Task2 {but_red.value()} ")
        if but_red.value()==1:
            reg["bulbState"]="on"
        elif but_green.value()==1:
            reg["bulbState"]="blink"
        elif but_blue.value()==1:
            reg["bulbState"]="off"
        await asyncio.sleep_ms(100)

# Задача по опросу термодатчика  
async def Task4_temp():
    #ow = onewire.OneWire(Pin(16)) # create a OneWire bus on GPIO16 
    while True:
        ds = ds18x20.DS18X20(ow)
        roms = ds.scan()
        try:
            ds.convert_temp()
        except:
            await asyncio.sleep_ms(1000)
            reg["tempState"]="offline"
            print(f"Task4 Temp={reg['tempState']}")
            continue
        await asyncio.sleep_ms(1000)
        for rom in roms:
            try:
                reg["temp"]=ds.read_temp(rom)
                reg["tempState"]="online"
            except:
                reg["tempState"]="offline"
        print(f"Task4 Temp={reg['temp']}")
        
        

# Задача по обработчику потоков для асинхронного веб-сервера
# Asynchronous functio to handle client's requests
async def handle_client(reader, writer):
    global state
    # Принимаем все данные
    print("Client connected")
    sum=0
    request_line=b''
    while True:
        st=await  reader.read(2048)
        request_line+=st
        n=len(st)
        sum+=n
        del st
        #print(request_line)
        if n<2048:
            break  
    # печатаем исходное сообщение
    print(request_line)    
    print(f"header size = {sum} byte")
    request = request_line.decode('UTF-8').split()
    #print('Request:', request[1])
    # Send the HTTP response and close the connection
    writer.write('HTTP/1.0 200 OK\r\nContent-type: text/html\r\n\r\n')
    #-------------------------------------------------------
    FileSend={  "send":False, # Заполняем что необходимо отправить данные на сервер
                "typefile":"r", # если тип данных текстовый html,js, css то "r", иначе бинарный "rb"
                "namefile":"",   #  имя файла для отправки
                "sizeblock": 8192 # размер блока для отправки
               }
    # проверяем что данные для парсинга 
    try:
        if (request[0]=="GET" or request[0]=="POST"):
            pass
    except:
        # при возникновении исключения закачиваем обработку
        del request
        del request_line
        mem=gc.mem_free()
        print(f"Осталось памяти в конце {mem}")        
        await writer.drain()
        await writer.wait_closed()
        print("Ошибка запроса")
        return
    #---------------------------------------
    # Парсим данные для отправки файлов
    if (request[0]=="GET"):
        
        if (request[1]=="/"):
            FileSend["send"]=True
            FileSend["typefile"]="r"
            FileSend["namefile"]="/index.html"
        elif (request[1].find(".html")>0 ) or \
            (request[1].find(".js")>0 ) or \
            (request[1].find(".css")>0 ):
            # отрправляем данные в текстовом режиме 
            FileSend["send"]=True
            FileSend["typefile"]="r"
            FileSend["namefile"]=request[1]
            
        elif (request[1].find(".png")>0 ) or \
             (request[1].find(".jpg")>0 ) or \
             (request[1].find(".ico")>0 ):
            # отрправляем данные в данные бинарном режиме 
            FileSend["send"]=True
            FileSend["typefile"]="rb"
            FileSend["namefile"]=request[1] # отбрасываем косую черту
    # обработка данных из        
    elif (request[0]=="POST"):
        # заменяем символы unicode на соответсующие символы
        request[1]=request[1].replace("%7B","{")
        request[1]=request[1].replace("%7D","}")
        request[1]=request[1].replace("%22",'"')
        request[1]=request[1].replace("%20"," ")
        print(f"Запрос RAW: {request[1]}")
        dataReceived=request[1].split()
        dataType=dataReceived[0]
        print(f"Тип запроса: {dataType}")
        
        if dataType=="/sendData":
            dataJSON=json.loads(dataReceived[1])
            print("JSON данные",dataJSON)
            reg["bulbState"]=dataJSON["bulbState"]
        elif dataType=="/readData":
            dataJSON=json.loads(dataReceived[1])
            print("JSON данные",dataJSON)
            #reg["bulbState"]=dataJSON["bulbState"]
        #request[1]=request[1][1:]     # Удаляем первый символ косая черта
        #requestJSON=request[1].split() # Делим строку на вид запроса и данные JSON
        #print(requestJSON)
        # обрабатываем данные
        del request
        writer.write( json.dumps(reg) )
        await writer.drain()
        await writer.wait_closed()
        print('Client Disconnected')
        return
    #-----------------------------------------------
    #----Отправка файла-----
    if (FileSend["send"]):
        try:
            with io.open(FileSend["namefile"],FileSend["typefile"]) as file:
                i=-1
                while(True):
                    st=file.read(FileSend["sizeblock"])
                    # Отправляем данные браузеру
                    sizeblockfile=len(st)
                    i=i+1
                    try:
                        writer.write(st)
                        await writer.drain()
                    except:
                        print("Ошибка страницы")
                        del sizeblockfile
                        del i
                        del st
                        break
                    del st
                    mem=gc.mem_free()
                    print(f"Блок {i} файла {FileSend["namefile"]}")
                    print(f"Отравлено {sizeblockfile} байт. Осталось ОЗУ {mem} байт")     
                    if (sizeblockfile<FileSend["sizeblock"]):
                        del sizeblockfile
                        del i
                        break
                    del sizeblockfile        
        except:
            print("File not found")  
        del FileSend
        del request
        await writer.drain()
        await writer.wait_closed()
        print('Client Disconnected')
        return
    # конец отправки файла
    #-------------------------------------------
    
    await writer.drain()
    await writer.wait_closed()
    print('Client Disconnected')
    # конец обработчика потоков Веб-сервера

if __name__ == '__main__':
    print("Run main")
    #Настройка точки доступа
    ap_if = network.WLAN(network.AP_IF)
    ap_if.active(True)
    ap_if.config(essid="MyPoint", password="12345678")
    #Настройка проверки пароля точки доступа
    #ap_if.config(authmode=network.AUTH_WPA_WPA2_PSK)
    # ожидаем включение точки доступа
    while ap_if.active() == False:
      pass
    print('Connection successful')
    print(ap_if.ifconfig())
    #------------------------------
    # Настройка веб-сервера
    # Настраиваем задачу Асинхронного веб-сервера
    # Передаем имя функции обработчика потоков,
    # настраиваем на работу с любым IP
    # на порту 80
    server = asyncio.start_server(handle_client, "0.0.0.0", 80)
    #-----------------------------------------------------
    # Добавляем задачи в планировщик
    # 1. Передаем задачу обработки веб-сервера
    asyncio.create_task( server )
    # 2. Передаем задачу управления светодиодом
    asyncio.create_task( Task1_led() )
    # 3. Передаем задачу опроса кнопок
    asyncio.create_task( Task2_butCheck() )
    # 4. Передаем задачу опроса термодатчика
    asyncio.create_task( Task4_temp() )
    #---------------------------------
    # Запускаем бесконечный цикл планировщика
    asyncio.Loop.run_forever()