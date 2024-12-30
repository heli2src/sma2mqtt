#!/usr/bin/env python3
"""
Released under the MIT License (MIT). See LICENSE.

Read values from sma-inverter with TCP modbus and publish the registervalues to the mqtt-broker.

   set PNOM to 100%
"""
import logging
from pymodbus.client.sync import ModbusTcpClient as ModbusClient
import paho.mqtt.client as mqttc                        # https://pypi.org/project/paho-mqtt/
import datetime
from time import time


ID = 3
BROKER = '127.0.0.1'
INVERTER = '192.xxx.xxx.xx'  # IP from the SMA solar inverter
PORT = 1883
TIME_SENDMQTT = 2           # send every 2 seconds new values
TIME_SENDPNOM = 20
debug = False

register = {'TIME':  {'adr': 30193, 'dat': 0},         # DtTm.Tm Systemzeit U32 DT (in s seit dem 1.1.1970) translate to datetime
            'STIME': {'adr': 30193, 'dat': 0},         # DtTm.Tm Systemzeit U32 DT (in s seit dem 1.1.1970)
            'P_DC':  {'adr': 30961, 'dat': 0},         # DcMs.Watt = DC Leistung Eingang S32 FIX0 (Vorzeichenbehaftet)
            'P_AC':  {'adr': 30775, 'dat': 0},         # GridMs.TotW = Pac, AC Leistung Eingang S32 FIX0 (Vorzeichenbehaftet)
            }
#           'TotWhOut': {'adr': 30513, 'dat': 0},      # Metering.TotWhOut  Gesamtertrag  64bit!!
PNOM = 40016                                           # PNormierte Wirkleistungsbegrenzung durch Anlagensteuerung in %

logger = logging.getLogger(__name__)
print('start sma__mqtt.py')
sma = ModbusClient(host=INVERTER, port=502)
client = mqttc.Client(clean_session=True)
client.online = False
client.will_set("sma/online", "offline", 1)

ltime = time()
wtime = ltime
solartarget = 52        # =2.6kW


def on_message(client, userdata, message):
    global solartarget
    solartarget = int(message.payload.decode("utf-8"))


def on_connect(client, userdata, flags, rc):
    logger.info('{} on_connect to {}, rc={}'.format(__name__, BROKER, rc))
    if rc == 0 and debug:
        print('MQTT Broker {} connected'.format(BROKER))
    elif rc == 5 and debug:
        print('MQTT Broker {}, authentication error'.format(BROKER))
    elif debug:
        print('MQTT Broker {}, connection failed ({})'.format(BROKER, mqttc.connack_string(rc)))


def on_disconnect(client, userdata,  rc):
    msg = ("MQTT Broker {} disconnected".format(BROKER))
    client.loop_stop()
    if rc > 0:
        msg += ', {}'.format(mqttc.connack_string(rc))
    if debug:
        print(msg)
    client.online = False


client.on_connect = on_connect
client.on_disconnect = on_disconnect
client.on_message = on_message
client.connect(BROKER, PORT, 60)    # blocking command
client.loop_start()
client.subscribe('Solar/targetpower')
print('sma mqtt client startet with connection to Broker={}'.format(BROKER))
logger.info('sma mqtt client startet with connection to Broker={}'.format(BROKER))
client.online = True

while (True):
    if not client.online:
        client.reconnect()
        client.online = True
        logger.info('sma mqtt client restartet with connection to {}'.format(BROKER))
    try:
        if time()-ltime > TIME_SENDMQTT:
            ltime = time()
            for reg in register:                # read all register and save the value to dat
                read = sma.read_holding_registers(register[reg]['adr'], 2, unit=ID).registers
                if (reg == 'STIME') or (reg == 'TIME'):
                    read = read[0]*2**16 + read[1]
                    if reg == 'STIME':
                        read = str(datetime.datetime.fromtimestamp(read))
                else:
                    if read[0] == 32768:
                        read = 0
                    else:
                        read = read[1]
                register[reg].update({'dat': read})
            client.publish("sma/online", "online", retain=True)
            for reg in register:
                client.publish("sma/{}".format(reg), register[reg]['dat'], retain=True)
                if debug:
                    print("sma/{}".format(reg), register[reg]['dat'])
        # set pnom
        hour = datetime.datetime.today().hour
        if (time()-wtime > TIME_SENDPNOM):
            sma.write_register(PNOM, solartarget, unit=3)
            wtime = time()
    except Exception as e:
        msg = "sma: error while updating values - {}".format(e)
        logger.error(msg)
        if debug:
            print(msg)

# should be never be reached...
client.loop_stop()
client.disconnect()
sma.close()
