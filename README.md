# TrafficScraper

Scrape local traffic information and display relevant route data on screen.

Check for Northbound incidents between 6AM and 8AM and Sounthbound between 3PM and 7PM.

Use 3 LED's to show the status.

* GREEN (flashing) - working and in the time zone where information is needed.
* RED - an incident that may interfere with the journey has been detected.
* YELLOW - No internet or the http request failed for some reason.

Throw the connected switch to override the timezones and perform an immediate request.
Or when VNC'd in, press the "o" button to have the same effect.

Using a Raspberry Pi Zero W running the Stretch OS

Pre-requisite:

* sudo apt-get install python-lxml
* sudo pip install pushbullet.py
* sudo apt-get install xdotool

Hardware:

* Resistors on the vero are 1/8W 220 OHMS
* White wire on the far left is the 3.3V power supply.
* The flats on the LED's face to the right.

As I run without a mouse/keyboard attached it is necessary to keep the HDMI port alive

sudo nano /etc/lightdm/lightdm.conf

in section [SeatDefaults] add or modifiy existing line

xserver-command=X -s 0 -dpms

To autostart the code on power up alter the following file:

sudo nano ~/.config/lxsession/LXDE-pi/autostart

To run in a terminal window (sudo is optional), add the following line :

@lxterminal -e /usr/bin/sudo /usr/bin/python /home/pi/MarksStuff/scraper9.py

ALSO, make sure it goes BEFORE the line @xscreensaver

