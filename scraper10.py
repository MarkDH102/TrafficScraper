# Mark Hollingworth
# 21-9-17
# Version 9

from lxml import html
from lxml import etree
from time import localtime
import time
import smtplib
from email.mime.text import MIMEText
import requests
import RPi.GPIO as GPIO
import curses
import sys
import signal
import os

from pushbullet import Pushbullet

_strData = ""
_strDataWithoutTimes = ""
_strOldData = ""
_strIncidents = []
_strIncidentsWithoutTimes = []
_intReqCount = 1
_blnOverrideTime = False
_blnWeekendStarted = False
_blnNotificationsOn = False
_overrideTimeout = 0

# This is a count of pushes sent to my mobile phone
_ecount = 0
_pb = None

def establishPushBulletConnection() :
    global _pb

    try :
        # This is my magic key
        _pb = Pushbullet("o.AT19RsFdKW0eXhXzI2FxNE5sJlnuapCB")
    except :
        _pb = None        


#============================================================================
# Send a pushbullet notification 
# NOTE that I can send up to 100 notifications per month for free.
#============================================================================
def sendPushMessage(message):

    global _ecount

    try :
        _ecount += 1
        if _pb == None :
            establishPushBulletConnection()
        if _pb != None :
            push = _pb.push_note("Traffic Alert", message)    
    except :
        pass


# ============================================================================
# Define some constants and a means to access them
# ============================================================================
def constant(f):
    def fset(self, value):
        raise TypeError
    def fget(self):
        return f()
    return property(fget, fset)


class _Const(object):
    @constant
    def INTERNET_ACCESS_LED():
        return 27
    @constant
    def INCIDENT_LED():
        return 17
    @constant
    def ACTIVITY_LED():
        return 4
    @constant
    def OVERRIDE_SWITCH():
        return 26

CONST = _Const()

# ============================================================================
# Send an email with the latest data files attached
# ============================================================================
def sendEmail():
    
    try :
        server=smtplib.SMTP('smtp-mail.outlook.com', 587)
        server.ehlo()
        server.starttls()
        server.ehlo()
        server.login("myemail@outlook.com", "GuessMyPassword")
        msg = MIMEText(_strData)
        msg['Subject'] = "Traffic Data from Pi"
        msg['From'] = "myemail@outlook.com"
        msg['To'] = "mywife@hotmail.com"
        msg.preamble = "Traffic Data from Pi"

        server.sendmail("myemail@outlook.com", "mywife@hotmail.com", msg.as_string())
        server.quit()
    except :
        pass

class TimeoutException(Exception) :
    pass

def _timeout(signum, frame) :
    raise TimeoutException()


# We have an incident that is relevant to us, so drill down to the full traffic description
# There is only one "trafficDesc" element on this page
def getMoreInfo(href, itime1, timeFlag):
    global _strIncidents
    global _strIncidentsWithoutTimes

    good = False
    err = 0

    if (itime1.lower().find("hour") > 0 ) or (itime1.lower().find("minute") > 0 ) :

        mhref = "http://www.worcesternews.co.uk" + href

        signal.signal(signal.SIGALRM, _timeout)
        signal.alarm(12)

        try :
            xpage = requests.get(mhref, timeout = 15.0)
            if xpage.status_code == 200 :
                xtree = html.fromstring(xpage.content)
                moreinfo = xtree.xpath('//p[@class="trafficDesc"]//text()')
                strX = moreinfo[0]

                x = strX.find("M5 ")
                y = strX.find("A41 ")
                # If the A41 is mentioned before the M5 then flag that we need to check it out
                if (y >= 0) and (y < x) :
                    x = -1

                if x >= 0 :
                    if (timeFlag == 0) and (strX.lower().find("north") >= 0) :
                        good = True
                    if (timeFlag == 1) and (strX.lower().find("south") >= 0) :
                        good = True
                else :
                    good = True

                #good = True

                if strX.lower().find("no problems") >= 0 :
                    good = False

                if strX.lower().find("a41 clear") >= 0 :
                    good = False

                if good == True :
                    # Add a live incident to the list
                    strX = strX.replace('\r', "")
                    strX = strX.replace('\n', " ")
                    _strIncidentsWithoutTimes.append(strX)
                    itime1 = itime1.lstrip("Last updated ")
                    strX = strX + " [" + itime1 + "]"
                    _strIncidents.append(strX)

        except (TimeoutException, requests.ConnectionError, requests.Timeout, requests.RequestException):
            _strIncidents.append("Internet connection timed out")
            _strIncidentsWithoutTimes.append("Internet connection timed out")
            err = 1

        except :
            e = sys.exc_info()[0]
            _strIncidents.append("Something went wrong {}".format(e))
            _strIncidentsWithoutTimes.append("Something went wrong {}".format(e))

            pass
        finally :
            signal.alarm(0)

    return good, err

# GET THE TRAFFIC INCIDENTS from the worcester news site
def getIncidents(morningOrEvening):
    w_incidents = []
    w_moreinfo = []
    w_test = []
    w_test1 = []
    cc = 0
    filteredIncidents = []

    signal.signal(signal.SIGALRM, _timeout)
    signal.alarm(12)

    try :
        page = requests.get('http://www.worcesternews.co.uk/li/traffic_and_travel.in.Worcester', timeout = 15.0)
        if page.status_code == 200 :
            #x = page.text.find("trafficShare") 
            #print("Looking")
            #if x > 0 :
                #print("Found")
                #y = page.text.find("<H4>", x)
                #if y > 0 :
                    #print("Found 1")
            #time.sleep(10);

            # YELLOW LED off
            GPIO.output(CONST.INTERNET_ACCESS_LED, 1)
            tree = html.fromstring(page.content)
            
            # XPath is a way of locating information in structured documents such as HTML or XML documents. 
            # A good introduction to XPath is on http://www.w3schools.com/xsl/xpath_intro.asp

            # This will create a list of text fields for all incidents (24 fields per incident)
            w_incidents = tree.xpath('//ul[@class="trafficList"]//text()')
            # This will create a list of the more detailed traffic web pages for each incident
            w_moreinfo = tree.xpath('//p[@class="trafficViewMore"]//@href')

            w_test = tree.xpath('//p[@class="trafficDesc"]//text()')
            w_test1 = tree.xpath('//p[@class="trafficLastUpdate"]//text()')

            #fp = open("/home/pi/MarksStuff/incidents.txt", "a")
            strData = ""
            #fp.write("New ---- ")
            for i in w_incidents :                
                cc = cc + 1
                if (cc == 3) or (cc == 4) or (cc == 6) or (cc == 8) or (cc == 12) or (cc == 14) :
                    strData += i
                    strData += " "
                    #fp.write(i)
                    #fp.write(" ##### ")
                if cc == 21 :
                    filteredIncidents.append(strData)
                    #fp.write(strData)
                    #fp.write("\r\nNew ---- ")
                    strData = ""
                    cc = 0
            #fp.close()
            #fp = open("/home/pi/MarksStuff/more.txt", "a")
            #for i in w_moreinfo :
                #fp.write(i)
                #fp.write("\r\n")
            #fp.close()
            #fp = open("/home/pi/MarksStuff/test.txt", "a")
            #for i in w_test :
                #fp.write(i)
                #fp.write("\r\n")
            #fp.close()
            #fp = open("/home/pi/MarksStuff/test1.txt", "a")
            #for i in w_test1 :
                #fp.write(i)
                #fp.write("\r\n")
            #fp.close()
 
            key.addstr(5, 0, "Incidents: {}   Pushes: {}".format(len(filteredIncidents), _ecount ) )

            # Index into the more info array
            cmi = 0
            ci = 0
            for incident in filteredIncidents :
                # Just in case the text fields incident count does not match up with the moreinfo count
                if cmi < len(w_moreinfo) :

                    try :
                        areWeInterested = True

                        if incident.find("A435") >= 0 :
                            areWeInterested = False
                        if incident.find("A4400") >= 0 :
                            areWeInterested = False
                        if incident.find("A441") >= 0 :
                            areWeInterested = False
                        if incident.find("A45") >= 0 :
                            areWeInterested = False
                        if incident.find("A465") >= 0 :
                            areWeInterested = False
                        if incident.find("A429") >= 0 :
                            areWeInterested = False
                        if incident.find("A417") >= 0 :
                            areWeInterested = False
                        if incident.find("A436") >= 0 :
                            areWeInterested = False
                        if incident.find("A48") >= 0 :
                            areWeInterested = False
                        if incident.find("A4103") >= 0 :
                            areWeInterested = False
                        if incident.lower().find("gloucester") >= 0 :
                            areWeInterested = False
                        if incident.lower().find("warwick") >= 0 :
                            areWeInterested = False
                        if incident.lower().find("coventry") >= 0 :
                            areWeInterested = False

                        if (incident.lower().find("hour") > 0) or (incident.lower().find("minute") > 0) :
                            areWeInterested = areWeInterested
                        else :
                            areWeInterested = False

                        if areWeInterested == True :
                            ci += 1
                            if ci < 26 :
                                key.addstr(15+ci, 0, "WI: {}".format(incident))
                    except :
                        key.addstr(31, 0, "ERR: {}".format(incident))
                        pass

                    dealtWith = False
                    err = 0

                    if incident.find("A38") >= 0:
                        # Drill down for location ?
                        if incident.find("Droitwich") > 0 :
                            dealtWith, err = getMoreInfo(w_moreinfo[cmi], w_test1[cmi], morningOrEvening)
                    if (dealtWith == False) and (incident.find("Roman") > 0) :
                        if incident.find("A4103") < 0 :
                            dealtWith, err = getMoreInfo(w_moreinfo[cmi], w_test1[cmi], morningOrEvening)
                    if (dealtWith == False) and (incident.find("A443") >= 0) :
                        dealtWith, err = getMoreInfo(w_moreinfo[cmi], w_test1[cmi], morningOrEvening)
                    if (dealtWith == False) and (incident.find("A4133") >= 0) :
                        dealtWith, err = getMoreInfo(w_moreinfo[cmi], w_test1[cmi], morningOrEvening)
                    if (dealtWith == False) and (incident.find("M5") >= 0) :
                        if (incident.find("Gloucestershire") < 0) and (incident.find("M50") < 0) and (incident.find("A40 ") < 0) :
                            dealtWith, err = getMoreInfo(w_moreinfo[cmi], w_test1[cmi], morningOrEvening)
                    if (dealtWith == False) and (incident.find("West Bromwich") >= 0) and (incident.find("M5") < 0) :
                        dealtWith, err = getMoreInfo(w_moreinfo[cmi], w_test1[cmi], morningOrEvening)
                    if (dealtWith == False) and (incident.find("A41 ") >= 0) :
                        #key.addstr(14, 0, "EX: {}".format(incident))
                        if incident.find("West Bromwich") >= 0 :
                            dealtWith, err = getMoreInfo(w_moreinfo[cmi], w_test1[cmi], morningOrEvening)
                    if (dealtWith == False) and (incident.find("A4041") >= 0) :
                        if incident.find("Newton") >= 0 :
                            dealtWith, err = getMoreInfo(w_moreinfo[cmi], w_test1[cmi], morningOrEvening)
                    if (dealtWith == False) and (incident.find("A4031") >= 0) :
                        dealtWith, err = getMoreInfo(w_moreinfo[cmi], w_test1[cmi], morningOrEvening)

                # Did getMoreInfo time out on the internet request?
                if err == 1 :
                    # YELLOW LED on
                    GPIO.output(CONST.INTERNET_ACCESS_LED, 0)
                    # Presumably , no internet connection...
                    key.addstr(15, 0, "Error (Timeout)")

                cmi += 1

    except (TimeoutException, requests.ConnectionError, requests.Timeout, requests.RequestException):
        # YELLOW LED on
        GPIO.output(CONST.INTERNET_ACCESS_LED, 0)
        # Presumably , no internet connection...
        key.addstr(15, 0, "Error (Timeout)")
    except :
        e = sys.exc_info()[0]
        key.addstr(15, 0, "Error (Unknown) {}".format(e))
    finally:
        signal.alarm(0)
                            
    return len(w_incidents)


# Get rid of any duplicate incidents
def sortThroughIncidents():

    global _strData
    global _strDataWithoutTimes

    cpy = []
    cnt = 0
    if len(_strIncidentsWithoutTimes) > 0 :
        for i in _strIncidentsWithoutTimes :
            if not i in cpy:
                cpy.append(_strIncidentsWithoutTimes[cnt])
                _strData += _strIncidents[cnt]
                _strData += "\n"
                _strDataWithoutTimes += i        
                cnt += 1

# Start of the main code - setup the LED's

errorFlag = 0

try :

    # Check the command line parameters
    _blnOverrideTime = False
    for arg in sys.argv :
        if arg == "-t" :
            _blnOverrideTime = True

    GPIO.setwarnings(False)

    GPIO.setmode(GPIO.BCM)
    # 4 is GREEN
    GPIO.setup(CONST.ACTIVITY_LED, GPIO.OUT)
    # 17 is RED
    GPIO.setup(CONST.INCIDENT_LED, GPIO.OUT)
    # 27 is YELLOW
    GPIO.setup(CONST.INTERNET_ACCESS_LED, GPIO.OUT)
    # 26 is the override input switch
    GPIO.setup(CONST.OVERRIDE_SWITCH, GPIO.IN, GPIO.PUD_UP)

    # Make sure they are OFF
    GPIO.output(CONST.ACTIVITY_LED, 1)
    GPIO.output(CONST.INCIDENT_LED, 1)
    GPIO.output(CONST.INTERNET_ACCESS_LED, 1)

    key = curses.initscr()
    curses.noecho()
    key.keypad(1)
    key.nodelay(1)
    key.clear()

    os.system("xdotool getactivewindow windowmove 40 35 windowsize --usehints 165 43")
    # I think that the xdotool needs time to get going...???
    time.sleep(10)

    enterPressed = 0
    # This is the main loop - do forever
    while (enterPressed == 0) :
        # Only check Mon to Fri
        if ( (localtime().tm_wday >= 0) and (localtime().tm_wday < 5) ) or ( _blnOverrideTime == True) :
            _blnWeekendStarted = False
            doReq = False
            doMorn = 0
            _strData = ""
            _strDataWithoutTimes = ""
            _strIncidents = []
            _strIncidentsWithoutTimes = []
            if (localtime().tm_hour >= 6) and (localtime().tm_hour < 8) :
                doReq = True
                key.addstr(0, 0, "")
                key.clrtoeol()
                key.addstr(0, 0, "Performing Morning request")
                key.refresh()
                _intReqCount += 1
                # Do the morning check
                getIncidents(0)

            if ( localtime().tm_hour >= 15) and (localtime().tm_hour <= 18) :
                doReq = True
                doMorn = 1
                key.addstr(0, 0, "")
                key.clrtoeol()
                key.addstr(0, 0, "Performing Evening request")
                key.refresh()
                _intReqCount += 1
                # Do the evening check
                getIncidents(1)

            if (_blnOverrideTime == True) and (doReq == False) :
                doReq = True
                key.addstr(0, 0, "")
                key.clrtoeol()
                doMorn = 0
                if localtime().tm_hour < 12 :
                    key.addstr(0, 0, "Performing Morning request")
                if localtime().tm_hour >= 12 :
                    doMorn = 1
                    key.addstr(0, 0, "Performing Evening request")
                key.refresh()
                _intReqCount += 1
                getIncidents(doMorn)

            if doReq == False :
                key.clear()
                key.addstr(2, 0, "Not in checking time zone")
                # Make sure they are OFF
                GPIO.output(CONST.ACTIVITY_LED, 1)
                GPIO.output(CONST.INCIDENT_LED, 1)
                GPIO.output(CONST.INTERNET_ACCESS_LED, 1)
                _intReqCount = 0
            else :
                s = ""
                if _blnOverrideTime == True :
                    s = "(Overriding time check press s to stop)"
                if _blnNotificationsOn == False :
                    s += "   (Notifications OFF press n to restart)"
                key.addstr(2, 0, "")
                key.clrtoeol()
                key.addstr(2, 0, "Request count {} ".format(_intReqCount) + s)
                key.refresh()
                sortThroughIncidents()

            if len(_strData) > 0 :
                if len(_strData) > 1000 :
                    _strData = _strData[:1000]
                GPIO.output(CONST.INCIDENT_LED, 0)
                # Show on screen even if nothing has changed            
                key.addstr(7, 0, _strData)
                if _strOldData != _strDataWithoutTimes :
                    # Only alert in the evening check and if we are NOT overriding
                    if (doMorn == 1) and (_blnOverrideTime == False):
                        if _blnNotificationsOn == True :
                            if _strDataWithoutTimes != "" :
                                sendPushMessage(_strDataWithoutTimes)
                            else :
                                # Send a push notification to say no incidents
                                sendPushMessage("No incidents")

                    _strOldData = _strDataWithoutTimes
            else :
                GPIO.output(CONST.INCIDENT_LED, 1)

            # Now go to sleep for approx 5 minutes - but keep checking for q/o/s keys
            key.addstr(0, 0, "")
            key.clrtoeol()
            key.addstr(0, 0, "Press <q to Quit> <o/s to Override/Stop Override> <k/n to Stop/Start Notification> ")
            key.refresh()

            c = 0
            state = 0
            while (c != 300) :
                if time.time() > _overrideTimeout :
                    _overrideTimeout = 0

                c += 1
                time.sleep(1)
                if doReq == True :
                    # Flash the green LED to show we are scanning
                    GPIO.output(CONST.ACTIVITY_LED, state)
                    if state == 0 :
                        state = 1
                    else :
                        state = 0

                if GPIO.input(CONST.OVERRIDE_SWITCH) == 0 :
                    if _blnOverrideTime == False :
                        _blnOverrideTime = True
                        break
                else :
                    if _overrideTimeout == 0 :
                        if _blnOverrideTime == True :
                            _blnOverrideTime = False
                            break;

                k = key.getch()
                if k > -1 :
                    if k == ord('q') :
                        enterPressed = 1
                        break
                    if k == ord('o') :
                        _blnOverrideTime = True
                        _overrideTimeout = int(time.time()) + 300
                        break
                    if k == ord('s') :
                        _blnOverrideTime = False
                        _overrideTimeout = 0
                        break
                    if k == ord('k') :
                        _blnNotificationsOn = False
                        break
                    if k == ord('n') :
                        _blnNotificationsOn = True
                        break
                        
            # Leave GREEN LED in the off state
            GPIO.output(CONST.ACTIVITY_LED, 1)
            key.clear()
        else :
            if _blnWeekendStarted == False :
                _blnOverrideTime = False
                key.clear()
                key.addstr(0, 0, "It's a weekend - Hooray <Press q to Quit> ")
                key.refresh()
                _blnWeekendStarted = True
                # Make sure they are OFF
                GPIO.output(CONST.ACTIVITY_LED, 1)
                GPIO.output(CONST.INCIDENT_LED, 1)
                GPIO.output(CONST.INTERNET_ACCESS_LED, 1)
                
            # It's a weekend, so just check for a user quit
            time.sleep(5)
            k = key.getch()
            if k > -1 :
                if k == ord('q') :
                    enterPressed = 1
                    break

    GPIO.cleanup()
    key.keypad(0)
    curses.echo()
    curses.endwin()

except :

    errorFlag = 1
    e = sys.exc_info()[0]
    print("Error (press CTRL-C to exit)! {}".format(e))

if errorFlag == 1 :
    while (1 == 1) :
        time.sleep(1)
